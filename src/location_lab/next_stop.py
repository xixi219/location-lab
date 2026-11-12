"""Private queue + serialized OFFLINE controller with optional durable progress.

No real device transport, network client, or restart replay.
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .core import Coordinate, MemoryBackend, Session, State
from .progress_journal import JournalError, ProgressJournal


@dataclass(frozen=True)
class Stop:
    name: str
    address: str
    point: Coordinate


def load_queue(path):
    """Read an explicit private file; never reorder, write, or disclose coordinates."""
    path = Path(path).resolve()
    repo = Path(__file__).resolve().parents[2]
    if path.is_relative_to(repo):
        raise ValueError("queue must be outside the repository")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("executed") is not False or data.get("hardware_verified") is not False:
        raise ValueError("expected an unexecuted, hardware-unverified queue")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("queue must contain steps")
    result = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("invalid queue step")
        name, address = step.get("name"), step.get("address")
        if not isinstance(name, str) or not name.strip() or not isinstance(address, str):
            raise ValueError("invalid stop name/address")
        result.append(Stop(name, address, Coordinate(step.get("latitude"), step.get("longitude"))))
    return tuple(result)


class NextStopController:
    """Serialized offline owner with optional durable intent and receipts.

    Never supply a real backend to this prototype.

    Each request is bound to epoch + version + action. Accepted attempts consume a
    version even on failure. Unknown/disconnect blocks next. Clear does not rewind
    the queue. Duplicate IDs return their original receipt, not a new operation.
    """
    def __init__(self, stops, backend=None, journal_path=None, device_identity=None):
        self.stops = tuple(stops)
        if not self.stops or not all(isinstance(s, Stop) for s in self.stops):
            raise ValueError("at least one Stop is required")
        self.session = Session(backend if backend is not None else MemoryBackend())
        self.session.state = State.UNKNOWN
        self.connected = False
        self.cursor = 0
        self.epoch = str(uuid4())
        self.version = 0
        self._receipts = {}
        self._lock = RLock()
        self.storage_fault = False
        self.closed = False
        self.journal = None
        self._pending = None
        self._queue_hash = hashlib.sha256(json.dumps([(s.name, s.address, s.point.latitude, s.point.longitude) for s in self.stops], ensure_ascii=False).encode()).hexdigest()
        selected_identity = getattr(self.session.backend, "identity", "memory-mock")
        if device_identity is not None and device_identity != selected_identity:
            raise ValueError("journal identity must match selected backend")
        self._device_hash = hashlib.sha256(selected_identity.encode()).hexdigest()
        if journal_path is not None:
            try:
                self.journal = ProgressJournal(journal_path)
                self._restore(self.journal.read())
                self._persist()
            except Exception:
                if self.journal:
                    self.journal.close()
                raise

    def _restore(self, data):
        if data is None:
            return
        try:
            if set(data) != {"schema", "queue_hash", "device_hash", "cursor", "version", "receipts", "pending"} or data["schema"] != 1 or data["queue_hash"] != self._queue_hash or data["device_hash"] != self._device_hash:
                raise ValueError()
            if type(data["cursor"]) is not int or not 0 <= data["cursor"] <= len(self.stops) or type(data["version"]) is not int or data["version"] < 0:
                raise ValueError()
            receipts = data["receipts"]
            if not isinstance(receipts, dict) or len(receipts) > 10000:
                raise ValueError()
            for key, entry in receipts.items():
                if not isinstance(key, str) or len(key) != 64 or not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str) or len(entry[0]) != 64 or not isinstance(entry[1], dict):
                    raise ValueError()
                receipt = entry[1]
                if set(receipt) != {"ok", "code", "epoch", "version", "completed"} or type(receipt["ok"]) is not bool or not isinstance(receipt["code"], str) or not isinstance(receipt["epoch"], str) or type(receipt["version"]) is not int or type(receipt["completed"]) is not int or not 0 <= receipt["completed"] <= len(self.stops):
                    raise ValueError()
                if receipt["code"] not in {"ok", "outcome_unknown", "disconnected", "recovery_required", "end_of_queue", "backend_failed"} or receipt["ok"] != (receipt["code"] == "ok") or receipt["version"] < 0 or receipt["version"] > data["version"] or receipt["completed"] > data["cursor"]:
                    raise ValueError()
                from uuid import UUID
                UUID(receipt["epoch"])
            pending = data["pending"]
            if pending is not None and (not isinstance(pending, str) or pending not in receipts or receipts[pending][1]["code"] != "outcome_unknown"):
                raise ValueError()
            self.cursor = data["cursor"]
            self.version = data["version"] + 1
            self._receipts = receipts
            # Pending request retains outcome_unknown permanently. No replay.
        except (KeyError, TypeError, ValueError):
            raise JournalError("journal corrupt or queue/device binding mismatch; preserve original") from None

    def _persist(self):
        if self.journal:
            self.journal.write(dict(schema=1, queue_hash=self._queue_hash,
                                    device_hash=self._device_hash, cursor=self.cursor,
                                    version=self.version, receipts=self._receipts,
                                    pending=self._pending))

    def close(self):
        with self._lock:
            self.closed = True
            self.connected = False
            self.session.state = State.UNKNOWN
            self.session.point = None
            if hasattr(self.session.backend, "close"):
                self.session.backend.close()
            if self.journal:
                self.journal.close()


    def snapshot(self):
        with self._lock:
            def display(stop):
                return {"name": stop.name, "address": stop.address}
            return {"mode": "offline-mock", "device_connected": False,
                    "hardware_verified": False, "physical_restored": False,
                    "mock_connected": self.connected, "state": self.session.state.value,
                    "epoch": self.epoch, "version": self.version,
                    "completed": self.cursor, "total": len(self.stops),
                    "current": display(self.stops[self.cursor - 1]) if self.cursor and self.session.state == State.ACTIVE else None,
                    "next": display(self.stops[self.cursor]) if self.cursor < len(self.stops) else None,
                    "durable_progress": self.journal is not None, "storage_fault": self.storage_fault,
                    "can_next": not self.closed and not self.storage_fault and self.connected and self.session.state != State.UNKNOWN and self.cursor < len(self.stops)}

    def execute(self, request):
        with self._lock:
            required = {"request_id", "epoch", "version", "action"}
            if not isinstance(request, dict) or set(request) != required:
                return {"ok": False, "code": "invalid_request"}
            rid = request["request_id"]
            if not isinstance(rid, str) or not 1 <= len(rid) <= 128 or type(request["version"]) is not int or not isinstance(request["epoch"], str) or not isinstance(request["action"], str):
                return {"ok": False, "code": "invalid_request"}
            key = hashlib.sha256(rid.encode()).hexdigest()
            fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
            if key in self._receipts:
                prior, receipt = self._receipts[key]
                return dict(receipt) if prior == fingerprint else {"ok": False, "code": "request_id_conflict"}
            if self.closed or self.storage_fault:
                return {"ok": False, "code": "storage_unavailable" if self.storage_fault else "closed"}
            if request["epoch"] != self.epoch:
                return {"ok": False, "code": "wrong_session"}
            if request["version"] != self.version:
                return {"ok": False, "code": "stale_command"}
            if request["action"] not in {"connect_mock", "disconnect_mock", "next", "clear"}:
                return {"ok": False, "code": "invalid_action"}
            if len(self._receipts) >= 10000:
                return {"ok": False, "code": "session_limit"}
            self.version += 1
            previous_cursor = self.cursor
            def receipt(code):
                return {"ok": code == "ok", "code": code, "epoch": self.epoch,
                        "version": self.version, "completed": self.cursor}
            # Intent and an indeterminate receipt must be durable BEFORE side effects.
            self._receipts[key] = (fingerprint, receipt("outcome_unknown"))
            self._pending = key
            try:
                self._persist()
            except JournalError:
                self.storage_fault = True
                self.connected = False
                self.session.state = State.UNKNOWN
                self.session.point = None
                return receipt("storage_unavailable")
            action = request["action"]
            code = "ok"
            try:
                if action == "connect_mock":
                    if hasattr(self.session.backend, "preflight"):
                        self.session.backend.preflight()
                    self.connected = True
                elif action == "disconnect_mock":
                    if hasattr(self.session.backend, "disconnect"):
                        self.session.backend.disconnect()
                    self.connected = False
                    self.session.state = State.UNKNOWN
                    self.session.point = None
                elif not self.connected:
                    code = "disconnected"
                elif action == "next" and self.session.state == State.UNKNOWN:
                    code = "recovery_required"
                elif action == "next" and self.cursor == len(self.stops):
                    code = "end_of_queue"
                elif action == "clear":
                    self.session.clear_location()
                else:
                    self.session.set_location(self.stops[self.cursor].point)
                    self.cursor += 1
            except Exception:
                code = "backend_failed"
                self.connected = False
                self.session.state = State.UNKNOWN
                self.session.point = None
            except BaseException:
                self.connected = False
                self.session.state = State.UNKNOWN
                self.session.point = None
                self.storage_fault = True
                raise
            result = receipt(code)
            self._receipts[key] = (fingerprint, result)
            self._pending = None
            try:
                self._persist()
            except JournalError:
                # ACK may have happened, or rename may have succeeded. Do not claim
                # advancement; block this owner until restart/review of durable state.
                self.cursor = previous_cursor
                self.storage_fault = True
                self.connected = False
                self.session.state = State.UNKNOWN
                self.session.point = None
                result = receipt("outcome_unknown")
                self._receipts[key] = (fingerprint, result)
            return dict(result)
