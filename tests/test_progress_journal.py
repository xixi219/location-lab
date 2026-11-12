import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from location_lab.next_stop import NextStopController, Stop
from location_lab.core import Coordinate
from location_lab.progress_journal import JournalError, ProgressJournal
from test_next_stop import CountingBackend, STOPS


class DurableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'progress.json'
        self.backend = CountingBackend()
        self.backend.identity = 'synthetic-device'
        self.c = NextStopController(STOPS, self.backend, self.path, 'synthetic-device')

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def request(self, action):
        return dict(request_id=str(uuid4()), epoch=self.c.epoch, version=self.c.version, action=action)

    def act(self, action):
        return self.c.execute(self.request(action))

    def ready(self):
        self.act('connect_mock'); self.act('clear')

    def restart(self, stops=STOPS, identity='synthetic-device'):
        self.c.close()
        self.c = NextStopController(stops, self.backend, self.path, identity)

    def test_restart_preserves_progress_blocks_replay(self):
        self.ready()
        req = self.request('next'); receipt = self.c.execute(req)
        old = self.request('next')
        self.restart()
        self.assertEqual(self.c.cursor, 1)
        self.assertFalse(self.c.snapshot()['can_next'])
        self.assertEqual(self.c.execute(req), receipt)
        self.assertEqual(self.c.lookup_receipt(req['request_id'])['receipt'], receipt)
        self.assertEqual(self.c.execute(old)['code'], 'wrong_session')
        self.assertEqual(self.backend.sets, 1)
        self.ready(); self.act('next')
        self.assertEqual(self.c.cursor, 2)

    def test_crash_between_intent_and_ack(self):
        self.ready()
        req = self.request('next')
        with patch.object(self.backend, 'set_location', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.c.execute(req)
        self.restart()
        self.assertEqual(self.c.cursor, 0)
        self.assertEqual(self.c.execute(req)['code'], 'outcome_unknown')
        self.assertFalse(self.c.snapshot()['can_next'])
        self.assertEqual(self.backend.sets, 0)

    def test_ack_then_write_failure_never_reports_success(self):
        self.ready()
        req = self.request('next')
        original = self.c.journal.write
        writes = 0
        def fail_second(doc):
            nonlocal writes
            writes += 1
            if writes == 2: raise JournalError('fault')
            original(doc)
        with patch.object(self.c.journal, 'write', side_effect=fail_second):
            self.assertEqual(self.c.execute(req)['code'], 'outcome_unknown')
        self.assertEqual(self.backend.sets, 1)
        self.assertEqual(self.c.cursor, 0)
        self.assertTrue(self.c.storage_fault)
        self.assertEqual(self.act('clear')['code'], 'storage_unavailable')
        self.restart()
        self.assertEqual(self.c.execute(req)['code'], 'outcome_unknown')
        self.assertEqual(self.c.cursor, 0)
        self.ready(); self.act('next')
        self.assertEqual(self.c.cursor, 1)

    def test_intent_write_failure_no_backend_operation(self):
        self.ready()
        with patch.object(self.c.journal, 'write', side_effect=JournalError('fault')):
            self.assertEqual(self.act('next')['code'], 'storage_unavailable')
        self.assertEqual(self.backend.sets, 0)
        self.assertTrue(self.c.storage_fault)

    def test_uncertain_rename_result_restart_reads_actual_committed_state(self):
        self.ready()
        original = self.c.journal.write; calls = 0
        def uncertain(doc):
            nonlocal calls
            calls += 1; original(doc)
            if calls == 2: raise JournalError('directory fsync uncertain')
        req = self.request('next')
        with patch.object(self.c.journal, 'write', side_effect=uncertain):
            self.assertEqual(self.c.execute(req)['code'], 'outcome_unknown')
        self.restart()
        self.assertEqual(self.c.cursor, 1)
        self.assertTrue(self.c.execute(req)['ok'])
        self.assertFalse(self.c.snapshot()['can_next'])
        self.assertEqual(self.backend.sets, 1)

    def test_queue_device_mismatch_preserves_file(self):
        before = self.path.read_bytes()
        self.c.close()
        for stops, device in [(STOPS[::-1], 'synthetic-device'), (STOPS, 'other-synthetic-device')]:
            with self.assertRaises((JournalError, ValueError)):
                NextStopController(stops, self.backend, self.path, device)
            self.assertEqual(self.path.read_bytes(), before)

    def test_corruption_does_not_reset_progress(self):
        self.c.close()
        for content in ['invalid', 'null', 'true', '0', '{}', '[]', '{"schema":1}']:
            self.path.write_text(content)
            with self.assertRaises(JournalError):
                NextStopController(STOPS, self.backend, self.path, 'synthetic-device')
            self.assertEqual(self.path.read_text(), content)

    def test_private_no_raw_queue_or_identity_or_request_ids(self):
        self.ready(); req = self.request('next'); self.c.execute(req)
        raw = self.path.read_text()
        for private in [STOPS[0].name, STOPS[0].address, 'latitude', 'longitude', 'synthetic-device', req['request_id']]:
            self.assertNotIn(private, raw)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_exclusive_lifetime_owner(self):
        with self.assertRaises(JournalError):
            ProgressJournal(self.path)
        self.c.close()
        j = ProgressJournal(self.path); j.close()

    def test_symlink_and_nonprivate_directory_rejected(self):
        link = self.path.parent / 'symlink.json'; link.symlink_to(self.path)
        with self.assertRaises(JournalError): ProgressJournal(link)
        directory = self.path.parent / 'public'; directory.mkdir(mode=0o755)
        with self.assertRaises(JournalError): ProgressJournal(directory / 'progress.json')

    def test_fifo_rejected_without_blocking(self):
        import subprocess
        import sys
        self.c.close()
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        script = "from location_lab.progress_journal import ProgressJournal,JournalError; import sys; j=ProgressJournal(sys.argv[1]);\ntry: j.read()\nexcept JournalError: sys.exit(0)\nelse: sys.exit(1)\nfinally: j.close()"
        result = subprocess.run([sys.executable, '-c', script, str(self.path)], timeout=3, capture_output=True)
        self.assertEqual(result.returncode, 0)

    def test_atomic_failure_keeps_previous_bytes(self):
        before = self.path.read_bytes()
        with patch('location_lab.progress_journal.os.replace', side_effect=OSError('synthetic failure')):
            with self.assertRaises(JournalError): self.c.journal.write({'test': True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('.progress-*')), [])


class IntegratedFakeTests(unittest.TestCase):
    def test_two_processes_with_different_journals_cannot_own_same_device(self):
        import subprocess
        import sys
        from location_lab.device_boundary import FakeDeviceTransport, SelectedDeviceBackend
        identity = 'synthetic-' + str(uuid4())
        with tempfile.TemporaryDirectory() as directory:
            backend = SelectedDeviceBackend(FakeDeviceTransport(identity), identity)
            c = NextStopController(STOPS, backend, Path(directory) / 'first.json')
            script = """
import sys
from location_lab.core import Coordinate
from location_lab.next_stop import NextStopController,Stop
from location_lab.device_boundary import FakeDeviceTransport,SelectedDeviceBackend,DeviceBoundaryError
try:
    backend=SelectedDeviceBackend(FakeDeviceTransport(sys.argv[1]),sys.argv[1])
except DeviceBoundaryError as error:
    print(error.code)
else:
    c=NextStopController([Stop('Synthetic','Synthetic',Coordinate(1,2))],backend,sys.argv[2])
    c.close()
    print('acquired')
"""
            def claim():
                return subprocess.run([sys.executable, '-c', script, identity, str(Path(directory) / 'second.json')], capture_output=True, text=True, timeout=5)
            try:
                denied = claim()
                self.assertEqual(denied.returncode, 0)
                self.assertEqual(denied.stdout.strip(), 'device_busy')
                self.assertFalse((Path(directory) / 'second.json').exists())
                c.close()
                allowed = claim()
                self.assertEqual(allowed.returncode, 0)
                self.assertEqual(allowed.stdout.strip(), 'acquired')
            finally:
                c.close()

    def test_fake_partial_timeout_disconnect_restart(self):
        from location_lab.device_boundary import FakeDeviceTransport, SelectedDeviceBackend
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'progress.json'
            identity = 'synthetic-' + str(uuid4())
            transport = FakeDeviceTransport(identity)
            backend = SelectedDeviceBackend(transport, identity)
            controller = NextStopController(STOPS, backend, path)
            def act(action):
                return controller.execute(dict(request_id=str(uuid4()), epoch=controller.epoch, version=controller.version, action=action))
            try:
                self.assertTrue(act('connect_mock')['ok']); self.assertTrue(act('clear')['ok'])
                for fault in ['partial', 'timeout_after', 'disconnect_after']:
                    transport.inject_fault('set', fault)
                    self.assertEqual(act('next')['code'], 'backend_failed')
                    self.assertEqual(controller.cursor, 0)
                    self.assertFalse(controller.snapshot()['can_next'])
                    transport.connected = True
                    self.assertTrue(act('connect_mock')['ok'])
                    self.assertEqual(act('next')['code'], 'recovery_required')
                    self.assertTrue(act('clear')['ok'])
                self.assertTrue(act('next')['ok'])
                controller.close()
                backend = SelectedDeviceBackend(transport, identity)
                controller = NextStopController(STOPS, backend, path)
                self.assertEqual(controller.cursor, 1)
                self.assertFalse(controller.snapshot()['device_connected'])
                self.assertFalse(controller.snapshot()['can_next'])
                self.assertTrue(act('connect_mock')['ok']); self.assertTrue(act('clear')['ok'])
                transport.inject_fault('clear', 'failure_before')
                self.assertEqual(act('clear')['code'], 'backend_failed')
                self.assertFalse(controller.snapshot()['physical_restored'])
                act('connect_mock'); act('clear')
                self.assertTrue(act('next')['ok'])
                self.assertEqual(controller.cursor, 2)
                self.assertEqual(act('next')['code'], 'end_of_queue')
            finally:
                controller.close()
