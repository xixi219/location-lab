"""Private Unix socket control + one-shot CLI; not a cloud or mobile relay.

Status never changes device state. Mutations require explicit epoch/version/id.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import threading

MAX_BYTES = 4096


def validate_socket_path(path):
    path = Path(path).absolute()
    repo = Path(__file__).resolve().parents[2]
    if path.resolve().is_relative_to(repo) or path.is_symlink():
        raise ValueError('private endpoint must be outside repo and not symlinked')
    parent = path.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError('endpoint parent must be owned by current user with mode 0700')
    return path


def dispatch(controller, request):
    if request == {'action': 'status'}:
        return {'ok': True, 'state': controller.snapshot()}
    if isinstance(request, dict) and set(request) == {'action', 'request_id'} and request['action'] == 'receipt':
        return controller.lookup_receipt(request['request_id'])
    if isinstance(request, dict) and request.get('action') in {'next', 'clear', 'preflight', 'disconnect'}:
        return controller.execute(request)
    return {'ok': False, 'code': 'invalid_request'}


class LocalControlServer:
    def __init__(self, controller, path):
        self.path = validate_socket_path(path)
        # Never remove an existing endpoint; it might still have a live owner.
        if self.path.exists():
            raise ValueError('endpoint exists; do not replace a possibly live controller')
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(3)
                try:
                    line = self.rfile.readline(MAX_BYTES + 1)
                    if len(line) > MAX_BYTES or not line.endswith(b'\n'):
                        raise ValueError()
                    request = json.loads(line)
                    result = dispatch(controller, request)
                except (ValueError, OSError):
                    result = {'ok': False, 'code': 'invalid_request'}
                try:
                    self.wfile.write(json.dumps(result, ensure_ascii=False).encode() + b'\n')
                except OSError:
                    pass  # Caller must query status; never automatically replay.
        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True
            def handle_error(self, request, client_address):
                pass  # Never disclose raw request or queue data in logs.
        self.server = Server(str(self.path), Handler)
        os.chmod(self.path, 0o600)
        self.inode = self.path.stat().st_ino
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        try:
            if self.path.lstat().st_ino == self.inode:
                self.path.unlink()
        except FileNotFoundError:
            pass


def request_local(path, request, timeout=35):
    path = validate_socket_path(path)
    metadata = path.lstat()
    if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError('unsafe local endpoint')
    payload = json.dumps(request).encode() + b'\n'
    if len(payload) > MAX_BYTES:
        raise ValueError('request too large')
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall(payload)
        with client.makefile('rb') as stream:
            response = stream.readline(65537)
        if len(response) > 65536 or not response.endswith(b'\n'):
            raise ValueError('invalid response')
        result = json.loads(response)
        if not isinstance(result, dict):
            raise ValueError('invalid response')
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='One explicit command to an existing local controller; no automatic retry')
    parser.add_argument('action', choices=('status', 'receipt', 'next', 'clear', 'preflight', 'disconnect'))
    parser.add_argument('--socket', required=True)
    parser.add_argument('--request-id')
    parser.add_argument('--epoch')
    parser.add_argument('--version', type=int)
    args = parser.parse_args(argv)
    request = {'action': args.action}
    if args.action == 'status':
        if args.request_id is not None or args.epoch is not None or args.version is not None:
            parser.error('status does not take command identity fields')
    elif args.action == 'receipt':
        if not args.request_id or args.epoch is not None or args.version is not None:
            parser.error('receipt requires only --request-id')
        request['request_id'] = args.request_id
    else:
        if not args.request_id or not args.epoch or args.version is None:
            parser.error('mutation requires --request-id, --epoch and --version from status')
        request.update(request_id=args.request_id, epoch=args.epoch, version=args.version)
    try:
        result = request_local(args.socket, request)
    except (OSError, ValueError):
        result = {'ok': False, 'code': 'local_result_unknown', 'hardware_verified': False}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('ok') is True else 2


if __name__ == '__main__':
    raise SystemExit(main())
