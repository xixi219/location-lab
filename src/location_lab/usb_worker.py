"""Private SDK subprocess. Never imported SDK until explicit start request.

Interface pinned to pymobiledevice3 11.52.1. No bundled SDK, pairing, native
fallback, automatic clear or device selection. Public stdout is protocol only.
"""
import asyncio
from contextlib import AsyncExitStack
import importlib.metadata
import json
import os
import sys

from .core import Coordinate

EXPECTED_SDK_VERSION = '11.52.1'
MAX_FRAME = 4096


class SDKSession:
    """Original adapter for a persistent, explicitly selected USB DVT session.

    Factory injection is only a Python test seam; the subprocess CLI cannot load
    arbitrary test modules. Unsupported SDK interface/version fails closed.
    """
    def __init__(self, identity, sdk=None):
        self.identity = identity
        self.sdk = sdk
        self.stack = AsyncExitStack()
        self.location = None
        self.rsd = None

    @staticmethod
    def load_sdk():
        if importlib.metadata.version('pymobiledevice3') != EXPECTED_SDK_VERSION:
            raise RuntimeError('sdk_version_mismatch')
        from pymobiledevice3.usbmux import list_devices
        import pymobiledevice3.remote.userspace_tunnel as userspace
        from pymobiledevice3.lockdown import create_using_usbmux
        # Pin the SDK's internal factory to USB in this isolated worker only.
        # UserspaceRsdTunnel otherwise omits connection_type in its factory call.
        async def usb_only_factory(*, serial=None, autopair=False, **kwargs):
            if not serial or autopair is not False or kwargs:
                raise RuntimeError('usb_factory_scope_invalid')
            lockdown = await create_using_usbmux(serial=serial, autopair=False,
                connection_type='USB', usbmux_address='/var/run/usbmuxd')
            if lockdown.udid != serial:
                await lockdown.close()
                raise RuntimeError('lockdown_identity_mismatch')
            return lockdown
        userspace.create_using_usbmux = usb_only_factory
        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        return dict(list_devices=list_devices, tunnel=userspace.UserspaceRsdTunnel,
                    provider=DvtProvider, location=LocationSimulation)

    async def check_identity(self):
        devices = await self.sdk['list_devices'](usbmux_address='/var/run/usbmuxd')
        # Reject simultaneous network aliases too; never let SDK choose a fallback.
        matches = [d for d in devices if d.serial == self.identity]
        if len(matches) != 1 or matches[0].connection_type != 'USB':
            raise RuntimeError('usb_identity_ambiguous_or_missing')
        if self.rsd is not None and self.rsd.udid != self.identity:
            raise RuntimeError('rsd_identity_mismatch')

    async def start(self):
        self.sdk = self.sdk or self.load_sdk()
        await self.check_identity()
        # Unlike PreferredRsdTunnel, no native or Bonjour fallback is allowed.
        self.rsd = await self.stack.enter_async_context(self.sdk['tunnel'](
            serial=self.identity, autopair=False, remotepairing_fallback=False))
        await self.check_identity()
        provider = await self.stack.enter_async_context(self.sdk['provider'](self.rsd))
        self.location = await self.stack.enter_async_context(self.sdk['location'](provider))
        # Opening DVT is the service/trust preflight. It never enables developer mode.

    async def command(self, action, request):
        await self.check_identity()
        if action == 'set':
            point = Coordinate(request.get('latitude'), request.get('longitude'))
            await self.location.set(point.latitude, point.longitude)
        elif action == 'clear':
            await self.location.clear()
            # SDK clear only returns after dispatch; there is no device/GPS ACK.
        elif action != 'status':
            raise ValueError('invalid_action')


async def serve(reader, send, sdk_factory=SDKSession):
    session = None
    generation = None
    while True:
        line = await reader.readline()
        if not line:
            return 0  # No automatic clear or replay on parent EOF.
        if len(line) > MAX_FRAME:
            return 2
        try:
            req = json.loads(line)
            if not isinstance(req, dict) or not isinstance(req.get('request_id'), str) or not isinstance(req.get('generation'), str):
                return 2
            rid, gen = req['request_id'], req['generation']
            if len(rid) > 128 or len(gen) > 128:
                return 2
            action = req.get('action')
            if session is None:
                if action != 'start' or req.get('allow_device_write') is not True or not isinstance(req.get('identity'), str) or not req['identity']:
                    return 2
                generation = gen
                session = sdk_factory(req['identity'])
                await session.start()
            else:
                if gen != generation or action not in {'status', 'set', 'clear'}:
                    return 2
                await session.command(action, req)
            send(dict(request_id=rid, generation=gen, ok=True,
                      hardware_verified=False, physical_restored=False))
        except Exception:
            # No upstream exception text, identity or coordinate leaves this process.
            if 'rid' in locals():
                send(dict(request_id=rid, generation=gen, ok=False, code='sdk_operation_failed'))
            return 2


def main():
    if sys.argv[1:] != ['--private-worker'] or sys.platform != 'darwin':
        return 2
    # Suppress SDK stdout/stderr even if it writes directly to their fds.
    output = os.fdopen(os.dup(1), 'w', buffering=1)
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    # Force local usbmux for SDK internal calls, ignoring remote endpoint env.
    os.environ['USBMUXD_SOCKET_ADDRESS'] = '/var/run/usbmuxd'
    os.environ.pop('PYMOBILEDEVICE3_UDID', None)
    async def run():
        reader = asyncio.StreamReader(limit=MAX_FRAME + 1)
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)
        def send(value):
            output.write(json.dumps(value, separators=(',', ':')) + '\n')
            output.flush()
        return await serve(reader, send)
    try:
        return asyncio.run(run())
    except BaseException:
        return 2


if __name__ == '__main__':
    # Hard process exit: no SDK teardown hook may perform an implicit clear.
    os._exit(main())
