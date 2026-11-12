import concurrent.futures
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import unittest
from uuid import uuid4

from location_lab.core import Coordinate
from location_lab.device_boundary import DeviceBoundaryError, DeviceDescriptor, FakeDeviceTransport, SelectedDeviceBackend


class DeviceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.identity = 'synthetic-' + str(uuid4())
        self.transport = FakeDeviceTransport(self.identity)
        self.backend = SelectedDeviceBackend(self.transport, self.identity)
        self.addCleanup(self.backend.close)
        self.a, self.b = Coordinate(1, 2), Coordinate(3, 4)

    def ready(self):
        self.backend.preflight()
        self.backend.clear_location()

    def assert_code(self, code, operation):
        with self.assertRaises(DeviceBoundaryError) as raised:
            operation()
        self.assertEqual(raised.exception.code, code)
        self.assertNotIn(self.identity, str(raised.exception))

    def test_explicit_preflight_then_clear(self):
        self.assert_code('preflight_required', self.backend.clear_location)
        self.backend.preflight()
        self.assertTrue(self.backend.unknown)
        self.assert_code('recovery_required', lambda: self.backend.set_location(self.a))
        self.backend.clear_location()
        self.backend.set_location(self.a)
        self.backend.set_location(self.b)
        self.assertEqual(self.transport.point, self.b)
        self.assertEqual(self.transport.clear_calls, 1)
        self.assertTrue(self.backend.simulated)

    def test_exact_identity_and_ambiguity(self):
        self.transport.devices = (DeviceDescriptor('synthetic-other'),)
        self.assert_code('selected_device_missing', self.backend.preflight)
        self.transport.devices = (DeviceDescriptor(self.identity), DeviceDescriptor(self.identity))
        self.assert_code('ambiguous_device', self.backend.preflight)
        self.transport.devices = (DeviceDescriptor(self.identity), DeviceDescriptor('synthetic-other'))
        self.backend.preflight()  # Explicit selection disambiguates different devices.

    def test_compatibility_trust_and_service_checks(self):
        for kwargs, code in [({'compatible': False}, 'unsupported_device'), ({'simulated': False}, 'unsupported_device'), ({'trusted': False}, 'untrusted_device'), ({'developer_service': False}, 'developer_service_unavailable')]:
            self.transport.devices = (DeviceDescriptor(self.identity, **kwargs),)
            self.assert_code(code, self.backend.preflight)
            self.assertFalse(self.backend.ready)
            self.assertTrue(self.backend.unknown)

    def test_identity_rechecked_for_operations(self):
        self.ready()
        self.transport.devices = (DeviceDescriptor('synthetic-other'),)
        self.assert_code('selected_device_missing', lambda: self.backend.set_location(self.a))
        self.assertEqual(self.transport.set_calls, 0)
        self.assertTrue(self.backend.unknown)

    def test_one_owner_until_close_including_disconnect(self):
        self.assert_code('device_busy', lambda: SelectedDeviceBackend(self.transport, self.identity))
        self.backend.disconnect()
        self.assert_code('device_busy', lambda: SelectedDeviceBackend(self.transport, self.identity))
        self.backend.close()
        replacement = SelectedDeviceBackend(self.transport, self.identity)
        self.addCleanup(replacement.close)
        self.assert_code('owner_closed', self.backend.preflight)

    def test_owner_disconnect_can_repreflight_without_fake_cable_change(self):
        self.ready()
        self.backend.disconnect()
        self.assertTrue(self.transport.connected)
        self.assertFalse(self.backend.ready)
        self.backend.preflight()
        self.assertTrue(self.backend.unknown)
        self.backend.clear_location()
        self.backend.set_location(self.a)

    def test_partial_set_requires_preflight_and_clear(self):
        self.ready()
        self.transport.inject_fault('set', 'partial')
        self.assert_code('outcome_unknown', lambda: self.backend.set_location(self.a))
        self.assertEqual(self.transport.point, self.a)
        self.assert_code('preflight_required', lambda: self.backend.set_location(self.b))
        self.backend.preflight()
        self.assert_code('recovery_required', lambda: self.backend.set_location(self.b))
        self.backend.clear_location()
        self.backend.set_location(self.b)

    def test_timeout_before_and_after_have_no_late_work(self):
        for fault, expected in [('timeout_before', None), ('timeout_after', self.a)]:
            self.ready()
            self.transport.inject_fault('set', fault)
            self.assert_code('timeout', lambda: self.backend.set_location(self.a))
            self.assertEqual(self.transport.point, expected)
            self.assertTrue(self.backend.unknown)
            self.assertFalse(self.backend.ready)
            self.assertEqual(self.transport.point, expected)  # No future or queued action.

    def test_modeled_latency_times_out_without_sleep(self):
        self.ready()
        self.transport.latency_seconds = self.backend.timeout + 1
        self.assert_code('timeout', lambda: self.backend.set_location(self.a))
        self.assertIsNone(self.transport.point)

    def test_disconnect_after_set_and_explicit_recovery(self):
        self.ready()
        self.transport.inject_fault('set', 'disconnect_after')
        self.assert_code('outcome_unknown', lambda: self.backend.set_location(self.a))
        self.assert_code('disconnected', self.backend.preflight)
        self.transport.connected = True
        self.backend.preflight()
        self.assertTrue(self.backend.unknown)
        self.backend.clear_location()
        self.assertFalse(self.backend.unknown)

    def test_clear_failure_does_not_claim_recovery(self):
        self.ready()
        self.backend.set_location(self.a)
        self.transport.inject_fault('clear', 'failure_before')
        self.assert_code('transport_failed', self.backend.clear_location)
        self.assertTrue(self.backend.unknown)
        self.assertEqual(self.transport.point, self.a)

    def test_close_does_not_clear_or_claim_restore(self):
        self.ready()
        self.backend.set_location(self.a)
        self.backend.close()
        self.assertEqual(self.transport.point, self.a)
        self.assertTrue(self.backend.unknown)
        self.assert_code('owner_closed', self.backend.clear_location)

    def test_serial_commands(self):
        self.ready()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(self.backend.set_location, [self.a, self.b] * 20))
        self.assertEqual(self.transport.set_calls, 40)
        self.assertEqual(self.transport.clear_calls, 1)

    def subprocess_claim(self, identity, environment=None):
        code = """
import sys
from location_lab.device_boundary import DeviceBoundaryError, FakeDeviceTransport, SelectedDeviceBackend
try:
    backend = SelectedDeviceBackend(FakeDeviceTransport(sys.argv[1]), sys.argv[1])
except DeviceBoundaryError as error:
    print(error.code)
else:
    backend.close()
    print('acquired')
"""
        result = subprocess.run([sys.executable, '-c', code, identity],
                                capture_output=True, text=True, timeout=5,
                                env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_process_lease_same_identity_independent_of_tmpdir(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, TMPDIR=directory)
            self.assertEqual(self.subprocess_claim(self.identity, env), 'device_busy')
            self.assertEqual(self.subprocess_claim('synthetic-' + str(uuid4()), env), 'acquired')
            self.backend.close()
            self.assertEqual(self.subprocess_claim(self.identity, env), 'acquired')

    def test_lease_is_private_empty_hashed_and_persists_after_close(self):
        root = Path('/tmp') / ('location-lab-device-owners-' + str(os.getuid()))
        lock = root / (hashlib.sha256(self.identity.encode()).hexdigest() + '.lock')
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(root.stat().st_uid, os.getuid())
        self.assertFalse(root.is_symlink())
        self.assertEqual(lock.stat().st_mode & 0o777, 0o600)
        self.assertEqual(lock.read_bytes(), b'')
        inode = lock.stat().st_ino
        self.backend.close()
        self.assertEqual(lock.stat().st_ino, inode)

    def test_constructor_lease_failure_does_not_reserve_identity(self):
        identity = 'synthetic-' + str(uuid4())
        with patch('location_lab.device_boundary._acquire_device_lease', side_effect=DeviceBoundaryError('owner_lock_unavailable')):
            self.assert_code('owner_lock_unavailable', lambda: SelectedDeviceBackend(FakeDeviceTransport(identity), identity))
        backend = SelectedDeviceBackend(FakeDeviceTransport(identity), identity)
        backend.close()

    def test_lock_symlink_rejected(self):
        identity = 'synthetic-' + str(uuid4())
        root = Path('/tmp') / ('location-lab-device-owners-' + str(os.getuid()))
        lock = root / (hashlib.sha256(identity.encode()).hexdigest() + '.lock')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            target.touch(mode=0o600)
            lock.symlink_to(target)
            try:
                self.assert_code('owner_lock_unavailable', lambda: SelectedDeviceBackend(FakeDeviceTransport(identity), identity))
            finally:
                lock.unlink()
        backend = SelectedDeviceBackend(FakeDeviceTransport(identity), identity)
        backend.close()

    def test_flock_failure_closes_created_descriptors(self):
        identity = 'synthetic-' + str(uuid4())
        opened, closed = [], []
        real_open, real_close = os.open, os.close
        def tracked_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        def tracked_close(fd):
            closed.append(fd)
            return real_close(fd)
        with patch('location_lab.device_boundary.os.open', side_effect=tracked_open), patch('location_lab.device_boundary.os.close', side_effect=tracked_close), patch('location_lab.device_boundary.fcntl.flock', side_effect=OSError('synthetic failure')):
            self.assert_code('owner_lock_unavailable', lambda: SelectedDeviceBackend(FakeDeviceTransport(identity), identity))
        self.assertEqual(sorted(opened), sorted(closed))
        self.assertEqual(len(opened), 2)
        backend = SelectedDeviceBackend(FakeDeviceTransport(identity), identity)
        backend.close()

    def test_invalid_or_nonfake_backend_rejected(self):
        for timeout in [0, -1, True, float('inf'), float('nan')]:
            with self.assertRaises(ValueError):
                SelectedDeviceBackend(self.transport, 'synthetic-unused', timeout)
        with self.assertRaises(ValueError):
            SelectedDeviceBackend(object(), 'synthetic-unused')
        with self.assertRaises(ValueError):
            SelectedDeviceBackend(self.transport, '')
