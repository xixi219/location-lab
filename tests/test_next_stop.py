import concurrent.futures
import http.client
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from uuid import uuid4

from location_lab.core import Coordinate, MemoryBackend
from location_lab.next_stop import NextStopController, Stop, load_queue
from location_lab.next_stop_web import make_server

STOPS = (Stop('測試站甲', '虛構地址甲', Coordinate(10, 20)), Stop('測試站乙', '虛構地址乙', Coordinate(11, 21)))


class CountingBackend(MemoryBackend):
    def __init__(self):
        super().__init__()
        self.sets = self.clears = 0
        self.fail_set = self.fail_clear = False

    def set_location(self, point):
        self.sets += 1
        super().set_location(point)
        if self.fail_set:
            raise RuntimeError('private coordinates should never escape')

    def clear_location(self):
        self.clears += 1
        if self.fail_clear:
            raise RuntimeError('private detail')
        super().clear_location()


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.backend = CountingBackend()
        self.c = NextStopController(STOPS, self.backend)

    def request(self, action):
        s = self.c.snapshot()
        return dict(request_id=str(uuid4()), epoch=s['epoch'], version=s['version'], action=action)

    def act(self, action):
        return self.c.execute(self.request(action))

    def ready(self):
        self.act('connect_mock')
        self.act('clear')

    def test_start_disconnected_unknown(self):
        self.assertEqual(self.act('next')['code'], 'disconnected')
        self.act('connect_mock')
        self.assertEqual(self.act('next')['code'], 'recovery_required')
        self.assertEqual(self.backend.sets, 0)

    def test_direct_next_and_end(self):
        self.ready()
        self.assertTrue(self.act('next')['ok'])
        self.assertEqual(self.c.snapshot()['next']['name'], STOPS[1].name)
        self.assertTrue(self.act('next')['ok'])
        self.assertEqual(self.backend.clears, 1)  # No automatic clear A -> B.
        self.assertEqual(self.act('next')['code'], 'end_of_queue')
        self.assertEqual(self.backend.sets, 2)

    def test_duplicate_returns_original_receipt(self):
        self.ready()
        request = self.request('next')
        first = self.c.execute(request)
        self.assertEqual(first, self.c.execute(request))
        self.assertEqual(self.backend.sets, 1)
        request['action'] = 'clear'
        self.assertEqual(self.c.execute(request)['code'], 'request_id_conflict')

    def test_stale_multiple_tabs(self):
        self.ready()
        old = self.request('next')
        self.act('next')
        self.assertEqual(self.c.execute(old)['code'], 'stale_command')
        self.assertEqual(self.c.cursor, 1)

    def test_concurrent_commands_one_station(self):
        self.ready()
        requests = [self.request('next') for _ in range(20)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(self.c.execute, requests))
        self.assertEqual(sum(r['ok'] for r in results), 1)
        self.assertEqual(self.backend.sets, 1)

    def test_failure_does_not_advance_and_retry_dedup(self):
        self.ready()
        self.backend.fail_set = True
        request = self.request('next')
        receipt = self.c.execute(request)
        self.assertEqual(receipt['code'], 'backend_failed')
        self.assertEqual(self.c.cursor, 0)
        self.assertEqual(receipt, self.c.execute(request))
        self.assertEqual(self.backend.sets, 1)
        self.assertEqual(self.act('next')['code'], 'disconnected')
        self.backend.fail_set = False
        self.act('connect_mock')
        self.act('clear')
        self.assertTrue(self.act('next')['ok'])
        self.assertEqual(self.c.cursor, 1)

    def test_clear_failure_remains_unknown(self):
        self.ready()
        self.act('next')
        self.backend.fail_clear = True
        self.assertEqual(self.act('clear')['code'], 'backend_failed')
        self.assertEqual(self.c.snapshot()['state'], 'unknown')
        self.assertFalse(self.c.snapshot()['physical_restored'])
        self.backend.fail_clear = False
        self.act('connect_mock')
        self.assertTrue(self.act('clear')['ok'])
        self.assertEqual(self.c.cursor, 1)
        self.assertIsNone(self.c.snapshot()['current'])

    def test_disconnect_and_reconnect_requires_clear(self):
        self.ready()
        self.act('next')
        self.act('disconnect_mock')
        self.assertEqual(self.act('next')['code'], 'disconnected')
        self.act('connect_mock')
        self.assertEqual(self.act('next')['code'], 'recovery_required')
        self.act('clear')
        self.act('next')
        self.assertEqual(self.c.cursor, 2)

    def test_restart_never_replays(self):
        self.ready()
        old = self.request('next')
        self.act('next')
        self.c = NextStopController(STOPS, self.backend)
        self.assertEqual(self.c.execute(old)['code'], 'wrong_session')
        self.assertFalse(self.c.snapshot()['can_next'])
        self.assertEqual(self.c.cursor, 0)
        self.assertEqual(self.backend.sets, 1)

    def test_snapshot_private_and_read_only(self):
        self.ready()
        s = self.c.snapshot()
        for _ in range(5):
            self.assertEqual(s, self.c.snapshot())
        text = json.dumps(s)
        self.assertNotIn('latitude', text)
        self.assertNotIn('longitude', text)
        self.assertFalse(s['device_connected'])
        self.assertFalse(s['hardware_verified'])
        self.assertEqual(self.backend.sets, 0)

    def test_invalid_requests_no_writes(self):
        for request in [None, [], {}, {'action': 'next'}, dict(self.request('next'), version=True), dict(self.request('next'), action=[])]:
            self.assertFalse(self.c.execute(request)['ok'])
        self.assertEqual(self.backend.sets + self.backend.clears, 0)

    def test_queue_validation_and_original_order(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'queue.json'
            d = dict(executed=False, hardware_verified=False, steps=[dict(name=s.name, address=s.address, latitude=s.point.latitude, longitude=s.point.longitude) for s in STOPS])
            p.write_text(json.dumps(d))
            before = p.read_bytes()
            self.assertEqual(load_queue(p), STOPS)
            self.assertEqual(p.read_bytes(), before)
            for bad in [float('nan'), float('inf'), True, 91]:
                d['steps'][0]['latitude'] = bad
                p.write_text(json.dumps(d))
                with self.assertRaises(ValueError):
                    load_queue(p)

    def test_queue_inside_repo_rejected(self):
        with self.assertRaises(ValueError):
            load_queue(Path(__file__).parent / 'private.json')


class WebTests(unittest.TestCase):
    def setUp(self):
        self.backend = CountingBackend()
        self.c = NextStopController(STOPS, self.backend)
        self.server = make_server(self.c)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        status, body = self.call('GET', '/')
        self.assertEqual(status, 200)
        self.token = re.search("const token='([^']+)'", body).group(1)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self, method, path, body=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            client.request(method, path, body=body, headers=headers or {})
            response = client.getresponse()
            return response.status, response.read().decode()
        finally:
            client.close()

    def test_read_never_operates_and_no_coordinate_leak(self):
        for path in ['/', '/api/state', '/api/command', '/?action=next']:
            self.call('GET', path, headers={'X-Preview-Token': self.token})
        status, body = self.call('GET', '/api/state', headers={'X-Preview-Token': self.token})
        self.assertEqual(status, 200)
        self.assertNotIn('latitude', body)
        self.assertEqual(self.backend.sets + self.backend.clears, 0)
        self.assertEqual(self.c.version, 0)

    def test_cross_origin_host_token_rejected(self):
        headers = {'X-Preview-Token': self.token, 'Content-Type': 'application/json'}
        for extra in [{'Origin': 'https://evil.example'}, {'Host': 'evil.example'}, {'X-Preview-Token': 'wrong'}]:
            status, _ = self.call('POST', '/api/command', '{}', headers | extra)
            self.assertEqual(status, 403)
        self.assertEqual(self.c.version, 0)

    def test_api_command_and_repeat(self):
        headers = {'X-Preview-Token': self.token, 'Content-Type': 'application/json'}
        for action in ['connect_mock', 'clear', 'next']:
            req = json.dumps(dict(request_id=str(uuid4()), epoch=self.c.epoch, version=self.c.version, action=action))
            status, body = self.call('POST', '/api/command', req, headers)
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)['ok'])
        _, repeated = self.call('POST', '/api/command', req, headers)
        self.assertEqual(body, repeated)
        self.assertEqual(self.c.cursor, 1)
        self.assertEqual(self.backend.sets, 1)

    def test_malformed_api_no_write(self):
        for body, kind in [('x', 'application/json'), ('{}', 'text/plain'), ('x' * 4097, 'application/json')]:
            status, _ = self.call('POST', '/api/command', body, {'X-Preview-Token': self.token, 'Content-Type': kind})
            self.assertEqual(status, 400)
        self.assertEqual(self.c.version, 0)

    def test_ui_no_autoplay_and_safe_text(self):
        _, body = self.call('GET', '/')
        self.assertIn('if(busy||!state)return', body)
        self.assertIn('.textContent=', body)
        self.assertNotIn('innerHTML', body)
        self.assertNotIn('setInterval', body)
        self.assertNotIn('setTimeout', body)
        self.assertNotIn('latitude', body)
