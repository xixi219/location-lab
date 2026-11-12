"""Private atomic progress storage. POSIX only; no coordinates/device identifiers.

Exclusive lifetime flock prevents two owners of the same journal. The fake selected-device boundary additionally owns an identity-keyed process
lease across different journals; real Mac transport integration remains future work.
"""
import json
import os
from pathlib import Path
import stat
import tempfile


class JournalError(RuntimeError):
    pass


class ProgressJournal:
    def __init__(self, path):
        import fcntl
        self.path = Path(path).absolute()
        self._fd = None
        repo = Path(__file__).resolve().parents[2]
        if self.path.resolve().is_relative_to(repo) or self.path.is_symlink():
            raise JournalError("journal must be a private regular file outside repository")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = self.path.parent.stat()
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            raise JournalError("journal directory must be owned by current user with mode 0700")
        lock = self.path.with_name(self.path.name + '.lock')
        try:
            self._fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.close()
            raise JournalError("journal is unavailable or already owned") from exc

    def read(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise JournalError("journal unavailable") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 8_000_000:
                raise JournalError("journal file is not private or has invalid size")
            with os.fdopen(fd, 'r', encoding='utf-8') as stream:
                fd = None
                document = json.load(stream)
                if not isinstance(document, dict):
                    raise JournalError("existing journal must contain an object; preserve original")
                return document
        except (ValueError, OSError) as exc:
            raise JournalError("journal unreadable or corrupt; preserve it for review") from exc
        finally:
            if fd is not None:
                os.close(fd)

    def write(self, document):
        name = None
        try:
            if self.path.is_symlink():
                raise JournalError("journal target changed")
            fd, name = tempfile.mkstemp(prefix='.progress-', dir=self.path.parent)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(document, stream, sort_keys=True, separators=(',', ':'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            name = None
            parent = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        except (OSError, ValueError) as exc:
            raise JournalError("journal write outcome uncertain; stop operations") from exc
        finally:
            if name is not None:
                try:
                    os.unlink(name)
                except FileNotFoundError:
                    pass

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
