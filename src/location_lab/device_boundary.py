"""Fake-only selected-device boundary for offline Mac companion contract tests.

No USB discovery, subprocess, network, third-party import, or hardware claims.
A future real transport must guarantee that timed-out calls are quiescent before
returning; a caller-side thread timeout alone is NOT a safe implementation.
"""
from dataclasses import dataclass, field
from math import isfinite
import errno
import hashlib
import os
import stat

try:
    import fcntl
except ImportError:  # The fake companion contract currently targets POSIX only.
    fcntl = None
from threading import RLock
from typing import Protocol

from .core import Coordinate


class DeviceBoundaryError(RuntimeError):
    """Stable public code, never raw device identity or transport exception."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _acquire_device_lease(identity):
    """Fixed per-user POSIX namespace, independent of journal and TMPDIR.

    Never unlink a lock file: deleting it could let another owner lock a new inode.
    Files contain no identity, coordinate, PID, token or other private content.
    """
    if fcntl is None or not hasattr(os, 'getuid'):
        raise DeviceBoundaryError('owner_lock_unsupported')
    directory_fd = lease_fd = None
    try:
        uid = os.getuid()
        root = '/tmp/location-lab-device-owners-' + str(uid)
        try:
            os.mkdir(root, 0o700)
        except FileExistsError:
            pass
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        metadata = os.fstat(directory_fd)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != uid or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise DeviceBoundaryError('owner_lock_unsafe')
        filename = hashlib.sha256(identity.encode('utf-8')).hexdigest() + '.lock'
        lease_fd = os.open(filename, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                           0o600, dir_fd=directory_fd)
        metadata = os.fstat(lease_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != uid or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1:
            raise DeviceBoundaryError('owner_lock_unsafe')
        try:
            fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise DeviceBoundaryError('device_busy') from None
            raise
        result, lease_fd = lease_fd, None
        return result
    except DeviceBoundaryError:
        raise
    except OSError:
        raise DeviceBoundaryError('owner_lock_unavailable') from None
    finally:
        if lease_fd is not None:
            os.close(lease_fd)
        if directory_fd is not None:
            os.close(directory_fd)


@dataclass(frozen=True)
class DeviceDescriptor:
    identity: str = field(repr=False)
    compatible: bool = True
    trusted: bool = True
    developer_service: bool = True
    simulated: bool = True


class DeviceTransport(Protocol):
    """Design contract only; this release deliberately accepts only fake transport.

    Implementations must bind each operation to the selected identity, respect a
    deadline, and return/raise only when no late mutation can occur. ACK is not an
    independent observation. Cancellation-barrier failure must stay unknown.
    """
    def discover(self) -> tuple[DeviceDescriptor, ...]: ...
    def preflight(self, identity: str) -> DeviceDescriptor: ...
    def set_location(self, point: Coordinate, *, identity: str, timeout: float) -> None: ...
    def clear_location(self, *, identity: str, timeout: float) -> None: ...


class FakeDeviceTransport:
    """Deterministic synchronous fake; delays are modeled, never slept or queued.

    Faults: failure_before, timeout_before, timeout_after, disconnect_before,
    disconnect_after, partial. 'after' / partial mutate then raise, hence unknown.
    """
    simulated = True
    FAULTS = frozenset({'failure_before', 'timeout_before', 'timeout_after',
                        'disconnect_before', 'disconnect_after', 'partial'})

    def __init__(self, identity='synthetic-device'):
        if not isinstance(identity, str) or not identity:
            raise ValueError('explicit identity required')
        self.devices = (DeviceDescriptor(identity),)
        self.connected = True
        self.point = None
        self.set_calls = 0
        self.clear_calls = 0
        self.latency_seconds = 0.0
        self._faults = {}
        self._lock = RLock()

    def inject_fault(self, action, fault):
        if action not in {'set', 'clear'} or fault not in self.FAULTS:
            raise ValueError('invalid fake fault')
        with self._lock:
            self._faults[action] = fault

    def discover(self):
        with self._lock:
            if not self.connected:
                raise DeviceBoundaryError('disconnected')
            return tuple(self.devices)

    def preflight(self, identity):
        with self._lock:
            matches = [d for d in self.discover() if d.identity == identity]
            if not matches:
                raise DeviceBoundaryError('selected_device_missing')
            if len(matches) != 1:
                raise DeviceBoundaryError('ambiguous_device')
            device = matches[0]
            if not device.simulated or not device.compatible:
                raise DeviceBoundaryError('unsupported_device')
            if not device.trusted:
                raise DeviceBoundaryError('untrusted_device')
            if not device.developer_service:
                raise DeviceBoundaryError('developer_service_unavailable')
            return device

    def _operate(self, action, point, identity, timeout):
        with self._lock:
            self.preflight(identity)  # Revalidate identity at the operation boundary.
            fault = self._faults.pop(action, None)
            if action == 'set':
                self.set_calls += 1
            else:
                self.clear_calls += 1
            if fault == 'disconnect_before':
                self.connected = False
                raise DeviceBoundaryError('disconnected')
            if fault == 'failure_before':
                raise DeviceBoundaryError('transport_failed')
            if fault == 'timeout_before' or self.latency_seconds > timeout:
                raise DeviceBoundaryError('timeout')
            self.point = point  # No pending asynchronous operation can survive return.
            if fault == 'disconnect_after':
                self.connected = False
                raise DeviceBoundaryError('outcome_unknown')
            if fault == 'timeout_after':
                raise DeviceBoundaryError('timeout')
            if fault == 'partial':
                raise DeviceBoundaryError('outcome_unknown')

    def set_location(self, point, *, identity=None, timeout=5.0):
        if not isinstance(point, Coordinate):
            raise ValueError('point must be a Coordinate')
        self._operate('set', point, identity, timeout)

    def clear_location(self, *, identity=None, timeout=5.0):
        self._operate('clear', None, identity, timeout)


class SelectedDeviceBackend:
    """Exclusive in-process and POSIX process owner of a selected FAKE device.

    Identity-keyed process lease is independent of journal path. Disconnect keeps
    ownership; close releases it without claiming a device clear or restoration.
    """
    simulated = True
    _owners = {}
    _owners_lock = RLock()

    def __init__(self, transport, identity, timeout=5.0):
        if not isinstance(transport, FakeDeviceTransport) or transport.simulated is not True:
            raise ValueError('only fake transport is implemented')
        if not isinstance(identity, str) or not identity:
            raise ValueError('explicit identity required')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not isfinite(timeout) or timeout <= 0:
            raise ValueError('positive finite timeout required')
        self.transport = transport
        self._identity = identity
        self.timeout = timeout
        self.ready = False
        self.unknown = True
        self._closed = False
        self._lock = RLock()
        self._owner_token = object()
        self._owner_pid = os.getpid()
        self._lease_fd = None
        with self._owners_lock:
            if identity in self._owners:
                raise DeviceBoundaryError('device_busy')
            self._lease_fd = _acquire_device_lease(identity)
            self._owners[identity] = self._owner_token

    @property
    def identity(self):
        return self._identity

    def _check_owner(self):
        with self._owners_lock:
            if self._closed or os.getpid() != self._owner_pid or self._owners.get(self.identity) is not self._owner_token:
                raise DeviceBoundaryError('owner_closed')

    def preflight(self):
        with self._lock:
            self._check_owner()
            try:
                result = self.transport.preflight(self.identity)
            except Exception as error:
                self.ready = False
                self.unknown = True
                code = error.code if isinstance(error, DeviceBoundaryError) else 'preflight_failed'
                raise DeviceBoundaryError(code) from None
            self.ready = True
            # Preflight is not recovery and must not clear unknown.
            return result

    def _operate(self, action, point=None):
        with self._lock:
            self._check_owner()
            if not self.ready:
                raise DeviceBoundaryError('preflight_required')
            if action == 'set' and self.unknown:
                raise DeviceBoundaryError('recovery_required')
            try:
                if action == 'set':
                    self.transport.set_location(point, identity=self.identity, timeout=self.timeout)
                else:
                    self.transport.clear_location(identity=self.identity, timeout=self.timeout)
            except Exception as error:
                self.ready = False
                self.unknown = True
                code = error.code if isinstance(error, DeviceBoundaryError) else 'transport_failed'
                raise DeviceBoundaryError(code) from None
            self.unknown = False

    def set_location(self, point):
        if not isinstance(point, Coordinate):
            raise ValueError('point must be a Coordinate')
        self._operate('set', point)

    def clear_location(self):
        self._operate('clear')

    def disconnect(self):
        with self._lock:
            self._check_owner()
            self.ready = False
            self.unknown = True
            # Detach the owner only; simulated physical connectivity is separate.

    def close(self):
        with self._lock:
            self.ready = False
            self.unknown = True
            with self._owners_lock:
                if self._owners.get(self.identity) is self._owner_token:
                    del self._owners[self.identity]
                if self._lease_fd is not None:
                    try:
                        # A fork child must not unlock the parent's shared lease.
                        if os.getpid() == self._owner_pid:
                            fcntl.flock(self._lease_fd, fcntl.LOCK_UN)
                    finally:
                        os.close(self._lease_fd)
                        self._lease_fd = None
            self._closed = True
