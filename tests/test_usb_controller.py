import http.client
import tempfile
from pathlib import Path
import unittest
from uuid import uuid4
import threading
from location_lab.next_stop import NextStopController
from location_lab.usb_transport import RealDeviceBackend
from location_lab.progress_journal import JournalError
from location_lab.next_stop_web import make_server
from test_usb_transport import RunnerDouble
from test_next_stop import STOPS, CountingBackend


class USBControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'progress.json'
        self.identity = 'synthetic-' + str(uuid4())
        self.workers = []
        def factory(python, fd):
            worker=RunnerDouble(python,fd);self.workers.append(worker);return worker
        self.factory=factory
        self.backend=RealDeviceBackend(self.identity,allow_device_write=True,runner_factory=factory)
        self.c=NextStopController(STOPS,self.backend,self.path)

    def tearDown(self):
        self.c.close();self.tmp.cleanup()

    def act(self,action):
        return self.c.execute(dict(action=action,request_id=str(uuid4()),epoch=self.c.epoch,version=self.c.version))

    def test_real_path_double_journal_restart_and_timeout(self):
        self.assertTrue(self.act('preflight')['ok']);self.assertTrue(self.act('clear')['ok'])
        self.assertTrue(self.act('next')['ok'])
        state=self.c.snapshot()
        self.assertEqual(state['mode'],'usb-unverified')
        self.assertFalse(state['hardware_verified']);self.assertFalse(state['physical_restored']);self.assertFalse(state['device_connected'])
        self.assertEqual(state['connection_status'],'not_live_verified')
        self.workers[-1].fault='timeout'
        self.assertEqual(self.act('next')['code'],'backend_failed')
        self.assertEqual(self.c.cursor,1)
        self.assertFalse(self.c.snapshot()['can_next'])
        self.c.close()
        backend=RealDeviceBackend(self.identity,allow_device_write=True,runner_factory=self.factory)
        self.c=NextStopController(STOPS,backend,self.path)
        self.assertEqual(self.c.cursor,1)
        self.assertFalse(self.c.snapshot()['can_next'])
        self.act('preflight');self.act('clear');self.assertTrue(self.act('next')['ok'])
        self.assertEqual(self.c.cursor,2)

    def test_mock_journal_cannot_be_reused_as_usb(self):
        self.c.close();self.path.unlink()
        mock=CountingBackend();mock.identity=self.identity
        controller=NextStopController(STOPS,mock,self.path);controller.close()
        before=self.path.read_bytes()
        backend=RealDeviceBackend(self.identity,allow_device_write=True,runner_factory=self.factory)
        try:
            with self.assertRaises(JournalError):NextStopController(STOPS,backend,self.path)
            self.assertEqual(before,self.path.read_bytes())
        finally:backend.close()

    def test_real_page_is_not_labeled_offline_and_get_does_not_start_worker(self):
        server=make_server(self.c)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            conn.request('GET','/');reply=conn.getresponse();body=reply.read().decode();conn.close()
            self.assertEqual(reply.status,200)
            self.assertIn('USB 控制原型',body)
            self.assertNotIn('所有操作僅影響記憶體',body)
            self.assertIn('非即時',body)
            self.assertIn('呼叫返回不等於地圖已接受',body)
            self.assertNotIn('ACK 不等於',body)
            self.assertIn('清除指令已返回（未驗證）',body)
            self.assertNotIn('已清除（硬體結果未驗證）',body)
            self.assertEqual(self.workers,[])
        finally:server.shutdown();server.server_close();thread.join()
