"""Opt-in, unverified real USB backend with a kill-and-reap process barrier.

Only the child imports the separately installed SDK. No hardware is accessed at
construction. A timed-out worker must be reaped before any new preflight. Device
state stays unknown even after worker death: kernel/device-side work is not an
independent location observation. The next explicit preflight + clear is required.
"""
import json
from math import isfinite
import os
import selectors
import signal
import subprocess
import sys
from threading import RLock
import time
from uuid import uuid4

from .core import Coordinate
from .device_boundary import DeviceBoundaryError, _acquire_device_lease
from .usb_worker import MAX_FRAME


class WorkerProcess:
    """Bounded byte IPC, no background command threads or inherited secret argv."""
    def __init__(self, python_executable, lease_fd):
        self.process = subprocess.Popen(
            [python_executable, '-m', 'location_lab.usb_worker', '--private-worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, close_fds=True, pass_fds=(lease_fd,), start_new_session=True)
        try:
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
        except BaseException:
            # Do not leak a spawned process if pipe setup fails.
            if not self.stop():
                raise DeviceBoundaryError('worker_not_quiescent') from None
            raise
        self.buffer = b''

    def exchange(self, request, timeout):
        payload = json.dumps(request, separators=(',', ':')).encode() + b'\n'
        if len(payload) > MAX_FRAME:
            raise DeviceBoundaryError('worker_frame_invalid')
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE)
            while payload:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise DeviceBoundaryError('worker_timeout')
                written = os.write(self.process.stdin.fileno(), payload)
                payload = payload[written:]
            selector.unregister(self.process.stdin)
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b'\n' not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise DeviceBoundaryError('worker_timeout')
                chunk = os.read(self.process.stdout.fileno(), MAX_FRAME + 1)
                if not chunk:
                    raise DeviceBoundaryError('worker_disconnected')
                self.buffer += chunk
                if len(self.buffer) > MAX_FRAME:
                    raise DeviceBoundaryError('worker_frame_invalid')
        line, self.buffer = self.buffer.split(b'\n', 1)
        # Unsolicited trailing replies are never consumed as a future ACK.
        if self.buffer:
            raise DeviceBoundaryError('worker_protocol_invalid')
        return json.loads(line)

    def stop(self, timeout=3.0):
        """Return True only if worker exit is confirmed. Never unlock here."""
        try:
            if self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # It may have exited between poll and kill; still reap.
            self.process.wait(timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            return False
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()
        return True


class RealDeviceBackend:
    simulated = False
    hardware_verified = False

    def __init__(self, identity, *, allow_device_write=False,
                 python_executable=sys.executable, timeout=15.0, runner_factory=None):
        if allow_device_write is not True:
            raise DeviceBoundaryError('explicit_device_write_opt_in_required')
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 256:
            raise ValueError('explicit device identity required')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not isfinite(timeout) or timeout <= 0:
            raise ValueError('positive finite timeout required')
        if runner_factory is None and sys.platform != 'darwin':
            raise DeviceBoundaryError('mac_required')
        self._identity = identity
        self._python = python_executable
        self.timeout = timeout
        self._factory = runner_factory or WorkerProcess
        self._lock = RLock()
        self._lease_fd = _acquire_device_lease(identity)
        self._owner_pid = os.getpid()
        self._worker = None
        self._generation = None
        self.ready = False
        self.unknown = True
        self.fenced = False
        self._closed = False

    @property
    def identity(self):
        return self._identity

    @property
    def transport_connected(self):
        # A prior preflight cannot prove cable/channel liveness at snapshot time.
        return False

    @property
    def last_preflight_succeeded(self):
        return self.ready and not self.fenced and not self._closed

    def _check(self):
        if self._closed or os.getpid() != self._owner_pid:
            raise DeviceBoundaryError('owner_closed')
        if self.fenced:
            raise DeviceBoundaryError('worker_not_quiescent')

    def _stop(self):
        self.ready = False
        self.unknown = True
        if self._worker is not None:
            try:
                stopped = self._worker.stop()
            except Exception:
                stopped = False
            if not stopped:
                self.fenced = True
                return False
            self._worker = None
        return True

    def _exchange(self, action, **fields):
        request_id = str(uuid4())
        req = dict(request_id=request_id, generation=self._generation, action=action, **fields)
        try:
            reply = self._worker.exchange(req, self.timeout)
            if not isinstance(reply, dict) or reply.get('request_id') != request_id or reply.get('generation') != self._generation or reply.get('ok') is not True:
                raise DeviceBoundaryError('worker_reply_invalid')
            if reply.get('hardware_verified') is not False or reply.get('physical_restored') is not False:
                raise DeviceBoundaryError('worker_reply_invalid')
        except BaseException as error:
            self._stop()
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise DeviceBoundaryError('worker_operation_unknown') from None

    def preflight(self):
        with self._lock:
            self._check()
            if self._worker is not None:
                self._exchange('status')
                self.ready = True
                return
            self._generation = str(uuid4())
            try:
                self._worker = self._factory(self._python, self._lease_fd)
            except Exception as error:
                self.ready = False
                self.unknown = True
                if isinstance(error, DeviceBoundaryError) and error.code == 'worker_not_quiescent':
                    self.fenced = True
                raise DeviceBoundaryError('worker_unavailable') from None
            self._exchange('start', identity=self.identity, allow_device_write=True)
            self.ready = True  # Never clears UNKNOWN.

    def set_location(self, point):
        if not isinstance(point, Coordinate):
            raise ValueError('point must be a Coordinate')
        with self._lock:
            self._check()
            if not self.ready or self.unknown:
                raise DeviceBoundaryError('preflight_and_recovery_required')
            self._exchange('set', latitude=point.latitude, longitude=point.longitude)

    def clear_location(self):
        with self._lock:
            self._check()
            if not self.ready:
                raise DeviceBoundaryError('preflight_required')
            self._exchange('clear')
            self.unknown = False

    def disconnect(self):
        with self._lock:
            self._check()
            if not self._stop():
                raise DeviceBoundaryError('worker_not_quiescent')

    def close(self):
        with self._lock:
            if os.getpid() != self._owner_pid:
                # A fork child cannot kill the parent worker or release its lease.
                if self._lease_fd is not None:
                    os.close(self._lease_fd)
                    self._lease_fd = None
                self._closed = True
                return
            if self.fenced and self._worker is None:
                return  # Failed construction left a worker whose exit is unconfirmed.
            if not self._stop():
                return  # Keep lease owned; caller must not assume close succeeded.
            if self._lease_fd is not None:
                # Do not LOCK_UN: inherited worker fd owns same open description.
                os.close(self._lease_fd)
                self._lease_fd = None
            self._closed = True
