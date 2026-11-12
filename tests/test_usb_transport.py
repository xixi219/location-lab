import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from uuid import uuid4

from location_lab.core import Coordinate
from location_lab.device_boundary import DeviceBoundaryError, _acquire_device_lease
from location_lab.usb_transport import RealDeviceBackend, WorkerProcess
from location_lab.usb_worker import SDKSession, serve


class RunnerDouble:
    def __init__(self, python, fd):
        self.commands = []
        self.stops = 0
        self.fault = None
        self.reaped = True
        os.fstat(fd)  # Real production lease fd supplied.

    def exchange(self, request, timeout):
        self.commands.append(request)
        if self.fault == 'timeout':
            raise TimeoutError('private error must be hidden')
        result = dict(request_id=request['request_id'], generation=request['generation'],
                      ok=True, hardware_verified=False, physical_restored=False)
        if self.fault == 'stale': result['generation'] = 'old'
        if self.fault == 'wrong_request': result['request_id'] = 'old'
        if self.fault == 'false_verified': result['hardware_verified'] = True
        return result

    def stop(self):
        self.stops += 1
        return self.reaped


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.identity = 'synthetic-' + str(uuid4())
        self.created = []
        def factory(python, fd):
            result = RunnerDouble(python, fd); self.created.append(result); return result
        self.b = RealDeviceBackend(self.identity, allow_device_write=True, runner_factory=factory)
        self.addCleanup(self.b.close)

    def ready(self):
        self.b.preflight(); self.b.clear_location()

    def test_opt_in_and_lazy_initialization(self):
        self.assertEqual(self.created, [])
        with self.assertRaises(DeviceBoundaryError): RealDeviceBackend('synthetic-no-opt-in')
        with patch('location_lab.usb_transport.sys.platform', 'linux'):
            with self.assertRaises(DeviceBoundaryError): RealDeviceBackend('synthetic-no-mac', allow_device_write=True)
        self.assertFalse(self.b.simulated)
        self.assertFalse(self.b.hardware_verified)

    def test_persistent_direct_a_b_and_explicit_clear(self):
        self.b.preflight()
        with self.assertRaises(DeviceBoundaryError): self.b.set_location(Coordinate(1, 2))
        self.b.clear_location()
        self.b.set_location(Coordinate(1, 2)); self.b.set_location(Coordinate(3, 4))
        self.assertEqual(len(self.created), 1)
        self.assertEqual([c['action'] for c in self.created[0].commands], ['start', 'clear', 'set', 'set'])
        self.assertFalse(self.b.unknown)

    def test_timeout_reaped_then_explicit_reconnect_and_clear(self):
        self.ready(); first = self.created[0]; first.fault = 'timeout'
        with self.assertRaisesRegex(DeviceBoundaryError, 'worker_operation_unknown'):
            self.b.set_location(Coordinate(1, 2))
        self.assertEqual(first.stops, 1)
        self.assertFalse(self.b.ready); self.assertTrue(self.b.unknown)
        self.b.preflight()
        self.assertNotEqual(first.commands[0]['generation'], self.created[-1].commands[0]['generation'])
        with self.assertRaises(DeviceBoundaryError): self.b.set_location(Coordinate(3, 4))
        self.b.clear_location(); self.b.set_location(Coordinate(3, 4))

    def test_unreaped_worker_fences_and_retains_lease(self):
        self.ready(); worker = self.created[0]; worker.reaped = False; worker.fault = 'timeout'
        with self.assertRaises(DeviceBoundaryError): self.b.set_location(Coordinate(1, 2))
        self.assertTrue(self.b.fenced)
        for action in [self.b.preflight, self.b.clear_location, self.b.disconnect]:
            with self.assertRaises(DeviceBoundaryError): action()
        self.b.close()
        with self.assertRaises(DeviceBoundaryError): _acquire_device_lease(self.identity)
        worker.reaped = True; self.b.close()
        fd = _acquire_device_lease(self.identity); os.close(fd)

    def test_stale_late_ack_wrong_request_and_false_claim_rejected(self):
        for fault in ['stale', 'wrong_request', 'false_verified']:
            self.ready(); worker = self.created[-1]; worker.fault = fault
            with self.assertRaises(DeviceBoundaryError): self.b.set_location(Coordinate(1, 2))
            self.assertEqual(worker.stops, 1)
            self.assertFalse(self.b.ready)

    def test_disconnect_close_never_auto_clear(self):
        self.ready(); worker = self.created[0]
        self.b.set_location(Coordinate(1, 2)); self.b.disconnect(); self.b.close()
        self.assertEqual([r['action'] for r in worker.commands], ['start', 'clear', 'set'])
        self.assertTrue(self.b.unknown)

    def test_clear_failure_returns_unknown_and_blocks_set(self):
        self.ready(); worker=self.created[-1]; worker.fault='timeout'
        with self.assertRaises(DeviceBoundaryError): self.b.clear_location()
        self.assertTrue(self.b.unknown); self.assertFalse(self.b.ready)
        with self.assertRaises(DeviceBoundaryError): self.b.set_location(Coordinate(1,2))

    def test_factory_failure_no_request_and_no_raw_error(self):
        self.b._factory = lambda *a: (_ for _ in ()).throw(RuntimeError(self.identity))
        with self.assertRaisesRegex(DeviceBoundaryError, '^worker_unavailable$'): self.b.preflight()


class SDKTests(unittest.IsolatedAsyncioTestCase):
    def sdk(self):
        calls = []
        identity = 'synthetic-sdk'
        devices = [SimpleNamespace(serial=identity, connection_type='USB')]
        async def list_devices(**kwargs):
            self.assertEqual(kwargs, {'usbmux_address': '/var/run/usbmuxd'})
            return devices
        @asynccontextmanager
        async def tunnel(**kwargs):
            calls.append(('tunnel', kwargs))
            yield SimpleNamespace(udid=identity)
        @asynccontextmanager
        async def provider(rsd):
            yield object()
        class Location:
            async def set(self, lat, lon): calls.append(('set', lat, lon))
            async def clear(self): calls.append(('clear',))
        @asynccontextmanager
        async def location(p): yield Location()
        return dict(list_devices=list_devices,tunnel=tunnel,provider=provider,location=location), calls, devices

    async def test_actual_sdk_adapter_persistent_and_no_autopair(self):
        sdk,calls,devices = self.sdk(); session=SDKSession('synthetic-sdk',sdk)
        await session.start()
        await session.command('clear', {})
        await session.command('set', {'latitude':1,'longitude':2})
        await session.command('set', {'latitude':3,'longitude':4})
        self.assertEqual(calls[0], ('tunnel',dict(serial='synthetic-sdk',autopair=False,remotepairing_fallback=False)))
        self.assertEqual([c[0] for c in calls], ['tunnel','clear','set','set'])
        devices[0].connection_type='Network'
        with self.assertRaises(RuntimeError): await session.command('set',{'latitude':5,'longitude':6})
        self.assertEqual(len(calls),4)

    async def test_identity_mismatch_duplicate_and_rsd_mismatch_fail_closed(self):
        for mode in ['missing','duplicate','rsd']:
            sdk,calls,devices=self.sdk(); session=SDKSession('synthetic-sdk',sdk)
            if mode=='missing': devices.clear()
            if mode=='duplicate': devices.append(devices[0])
            if mode=='rsd':
                @asynccontextmanager
                async def wrong(**kw): yield SimpleNamespace(udid='other')
                sdk['tunnel']=wrong
            with self.assertRaises(RuntimeError): await session.start()
            self.assertFalse(any(c[0] in ('set','clear') for c in calls))

    async def test_worker_protocol_and_eof_no_clear(self):
        sdk,calls,_ = self.sdk()
        reader=asyncio.StreamReader()
        requests=[dict(action='start',identity='synthetic-sdk',allow_device_write=True),dict(action='set',latitude=1,longitude=2),dict(action='set',latitude=3,longitude=4)]
        for i,r in enumerate(requests):
            reader.feed_data((json.dumps(dict(r,request_id=str(i),generation='synthetic-session'))+'\n').encode())
        reader.feed_eof(); out=[]
        self.assertEqual(await serve(reader,out.append,lambda identity:SDKSession(identity,sdk)),0)
        self.assertEqual(len(out),3)
        self.assertEqual([c[0] for c in calls],['tunnel','set','set'])
        self.assertTrue(all(r['hardware_verified'] is False for r in out))

    async def test_worker_stale_generation_stops_before_second_operation(self):
        sdk,calls,_=self.sdk(); reader=asyncio.StreamReader(); out=[]
        requests=[dict(action='start',identity='synthetic-sdk',allow_device_write=True,request_id='r',generation='g'),dict(action='set',latitude=1,longitude=2,request_id='r2',generation='old')]
        for r in requests: reader.feed_data((json.dumps(r)+'\n').encode())
        reader.feed_eof()
        self.assertEqual(await serve(reader,out.append,lambda identity:SDKSession(identity,sdk)),2)
        self.assertEqual(len(out),1)
        self.assertEqual([c[0] for c in calls],['tunnel'])

    async def test_worker_requires_start_optin_and_bounded_valid_frame(self):
        for raw in [b'{}\n',b'[]\n',b'x'*5000+b'\n',json.dumps(dict(action='start',identity='synthetic-sdk',request_id='r',generation='g')).encode()+b'\n']:
            reader=asyncio.StreamReader();reader.feed_data(raw);reader.feed_eof();out=[]
            def forbidden(_): raise AssertionError('must not create SDK session')
            self.assertEqual(await serve(reader,out.append,forbidden),2)
            self.assertEqual(out,[])

    async def test_worker_rejects_stale_generation_and_redacts_sdk_exception(self):
        class Failed:
            async def start(self): raise RuntimeError('private synthetic coordinate detail')
        reader=asyncio.StreamReader(); reader.feed_data((json.dumps(dict(action='start',identity='synthetic',allow_device_write=True,request_id='r',generation='g'))+'\n').encode());reader.feed_eof();out=[]
        self.assertEqual(await serve(reader,out.append,lambda _:Failed()),2)
        self.assertNotIn('private',json.dumps(out));self.assertFalse(out[0]['ok'])

    async def test_lazy_sdk_factory_forces_usb_local_and_never_autopairs(self):
        calls=[]
        async def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(udid=kwargs['serial'])
        userspace=SimpleNamespace(UserspaceRsdTunnel=object,create_using_usbmux=None)
        modules={
            'pymobiledevice3': SimpleNamespace(remote=SimpleNamespace(userspace_tunnel=userspace)),
            'pymobiledevice3.remote': SimpleNamespace(userspace_tunnel=userspace),
            'pymobiledevice3.remote.userspace_tunnel': userspace,
            'pymobiledevice3.usbmux': SimpleNamespace(list_devices=object),
            'pymobiledevice3.lockdown': SimpleNamespace(create_using_usbmux=create),
            'pymobiledevice3.services': SimpleNamespace(),
            'pymobiledevice3.services.dvt': SimpleNamespace(),
            'pymobiledevice3.services.dvt.instruments': SimpleNamespace(),
            'pymobiledevice3.services.dvt.instruments.dvt_provider': SimpleNamespace(DvtProvider=object),
            'pymobiledevice3.services.dvt.instruments.location_simulation': SimpleNamespace(LocationSimulation=object),
        }
        with patch.dict(sys.modules,modules), patch('location_lab.usb_worker.importlib.metadata.version',return_value='11.52.1'):
            SDKSession.load_sdk()
            await userspace.create_using_usbmux(serial='synthetic-sdk',autopair=False)
            with self.assertRaises(RuntimeError): await userspace.create_using_usbmux(serial='synthetic-sdk',autopair=True)
        self.assertEqual(calls,[dict(serial='synthetic-sdk',autopair=False,connection_type='USB',usbmux_address='/var/run/usbmuxd')])

    def test_version_pin_rejects_before_import_or_device_access(self):
        with patch('location_lab.usb_worker.importlib.metadata.version',return_value='0.0.0'):
            with self.assertRaisesRegex(RuntimeError,'sdk_version_mismatch'): SDKSession.load_sdk()


class PipeTests(unittest.TestCase):
    def harmless(self, source):
        # Exercise actual production WorkerProcess byte IPC with a harmless child,
        # swapping only Popen's argv; never import the SDK or enumerate devices.
        import subprocess
        real = subprocess.Popen
        def launch(argv, **kwargs):
            self.assertNotIn('synthetic-id', ' '.join(argv))
            self.assertIn('--private-worker',argv)
            return real([sys.executable,'-c',source],**kwargs)
        fd = _acquire_device_lease('synthetic-pipe-'+str(uuid4()))
        with patch('location_lab.usb_transport.subprocess.Popen',side_effect=launch):
            worker = WorkerProcess(sys.executable,fd)
        os.close(fd)
        self.addCleanup(worker.stop)
        return worker

    def test_parent_sigkill_child_retains_lease_until_child_exits(self):
        import subprocess
        import signal
        import time
        identity='synthetic-parent-crash-'+str(uuid4())
        script = """
import os,sys,time,subprocess
from unittest.mock import patch
from location_lab.device_boundary import _acquire_device_lease
from location_lab.usb_transport import WorkerProcess
real=subprocess.Popen
fd=_acquire_device_lease(sys.argv[1])
def launch(argv,**kwargs):
    return real([sys.executable,'-c','import time;time.sleep(60)'],**kwargs)
with patch('location_lab.usb_transport.subprocess.Popen',side_effect=launch):
    worker=WorkerProcess(sys.executable,fd)
print(worker.process.pid,flush=True)
time.sleep(60)
"""
        parent=subprocess.Popen([sys.executable,'-c',script,identity],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        child_pid=None
        try:
            import selectors
            with selectors.DefaultSelector() as selector:
                selector.register(parent.stdout,selectors.EVENT_READ)
                self.assertTrue(selector.select(5),'helper must start promptly')
                child_pid=int(parent.stdout.readline())
            os.kill(parent.pid,signal.SIGKILL);parent.wait(timeout=5)
            with self.assertRaises(DeviceBoundaryError): _acquire_device_lease(identity)
            os.killpg(child_pid,signal.SIGKILL)
            deadline=time.monotonic()+5
            while True:
                try:
                    fd=_acquire_device_lease(identity);os.close(fd);break
                except DeviceBoundaryError:
                    if time.monotonic()>deadline: raise
                    time.sleep(0.01)
        finally:
            if parent.poll() is None: parent.kill();parent.wait(timeout=5)
            parent.stdout.close()
            if child_pid:
                try: os.killpg(child_pid,signal.SIGKILL)
                except ProcessLookupError: pass

    def test_child_inherits_lease_after_parent_descriptor_closes(self):
        import subprocess
        identity = 'synthetic-inherited-' + str(uuid4())
        fd = _acquire_device_lease(identity)
        real = subprocess.Popen
        def launch(argv, **kwargs):
            return real([sys.executable, '-c', 'import time;time.sleep(60)'], **kwargs)
        with patch('location_lab.usb_transport.subprocess.Popen', side_effect=launch):
            worker = WorkerProcess(sys.executable, fd)
        os.close(fd)
        try:
            with self.assertRaises(DeviceBoundaryError): _acquire_device_lease(identity)
            self.assertTrue(worker.stop())
            replacement = _acquire_device_lease(identity); os.close(replacement)
        finally:
            worker.stop()

    def test_pipe_initialization_failure_stops_child(self):
        import subprocess
        real=subprocess.Popen; children=[]
        def launch(argv,**kwargs):
            process=real([sys.executable,'-c','import time;time.sleep(60)'],**kwargs)
            children.append(process);return process
        fd=_acquire_device_lease('synthetic-init-'+str(uuid4()))
        try:
            with patch('location_lab.usb_transport.subprocess.Popen',side_effect=launch),patch('location_lab.usb_transport.os.set_blocking',side_effect=OSError('synthetic')):
                with self.assertRaises(OSError): WorkerProcess(sys.executable,fd)
            self.assertIsNotNone(children[0].returncode)
        finally:
            os.close(fd)
            for child in children:
                if child.poll() is None: child.kill();child.wait()

    def test_real_pipe_roundtrip_then_eof(self):
        worker=self.harmless("import sys,json\nfor l in sys.stdin:\n r=json.loads(l);print(json.dumps(r),flush=True)")
        req=dict(request_id='r',generation='g',action='status')
        self.assertEqual(worker.exchange(req,2),req)
        self.assertTrue(worker.stop())

    def test_real_pipe_timeout_kills_and_reaps(self):
        worker=self.harmless('import time;time.sleep(60)')
        with self.assertRaises(DeviceBoundaryError): worker.exchange(dict(request_id='r'),0.03)
        self.assertTrue(worker.stop())
        self.assertIsNotNone(worker.process.returncode)

    def test_real_pipe_oversized_and_wrong_json(self):
        for source in ["print('x'*5000,flush=True)","print('notjson',flush=True)"]:
            worker=self.harmless(source)
            with self.assertRaises((DeviceBoundaryError,ValueError)): worker.exchange(dict(request_id='r'),2)
            self.assertTrue(worker.stop())
