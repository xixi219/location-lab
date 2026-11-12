import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from location_lab.local_control import LocalControlServer, request_local, main, dispatch
from unittest.mock import patch
from location_lab.next_stop import NextStopController
from test_next_stop import STOPS, CountingBackend


class LocalControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'controller.sock'
        self.backend = CountingBackend()
        self.c = NextStopController(STOPS, self.backend)
        try:
            self.server = LocalControlServer(self.c, self.path)
        except PermissionError:
            self.c.close(); self.tmp.cleanup()
            self.skipTest('AF_UNIX unavailable in this execution environment; run on Mac')

    def tearDown(self):
        self.server.close(); self.c.close(); self.tmp.cleanup()

    def command(self, action):
        state = request_local(self.path, {'action': 'status'})['state']
        return {'action': action, 'request_id': str(uuid4()), 'epoch': state['epoch'], 'version': state['version']}

    def test_explicit_cli_status_next_clear_and_retry(self):
        for action in ['preflight', 'clear']:
            self.assertTrue(request_local(self.path, self.command(action))['ok'])
        command = self.command('next')
        first = request_local(self.path, command)
        self.assertEqual(first, request_local(self.path, command))
        self.assertEqual(self.backend.sets, 1)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = main(['status', '--socket', str(self.path)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())['state']['completed'], 1)
        self.assertTrue(request_local(self.path, self.command('clear'))['ok'])
        self.assertEqual(self.c.cursor, 1)

    def test_invalid_stale_and_missing_fields_do_not_advance(self):
        request_local(self.path, self.command('preflight'));request_local(self.path, self.command('clear'))
        stale = self.command('next')
        request_local(self.path, self.command('next'))
        self.assertEqual(request_local(self.path, stale)['code'], 'stale_command')
        self.assertFalse(request_local(self.path, {'action': 'next'})['ok'])
        self.assertFalse(request_local(self.path, {'action': 'set', 'latitude': 1, 'longitude': 2})['ok'])
        self.assertEqual(self.backend.sets, 1)

    def test_status_no_side_effects_and_private_endpoint(self):
        for _ in range(5): request_local(self.path, {'action': 'status'})
        self.assertEqual(self.backend.sets + self.backend.clears, 0)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError): LocalControlServer(self.c, self.path)
        self.assertTrue(request_local(self.path, {'action': 'status'})['ok'])

    def test_cli_requires_all_intent_fields(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['next', '--socket', str(self.path)])
        self.assertEqual(self.backend.sets, 0)

    def test_nonprivate_directory_and_symlink_rejected(self):
        directory = Path(self.tmp.name) / 'public'; directory.mkdir(mode=0o755)
        with self.assertRaises(ValueError): LocalControlServer(self.c, directory / 'control.sock')
        link = Path(self.tmp.name) / 'link';link.symlink_to(self.path)
        with self.assertRaises(ValueError): request_local(link, {'action':'status'})


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.backend = CountingBackend()
        self.c = NextStopController(STOPS, self.backend)
        self.addCleanup(self.c.close)

    def request(self, action):
        return dict(action=action, request_id=str(uuid4()), epoch=self.c.epoch, version=self.c.version)

    def test_status_and_receipt_are_readonly(self):
        for action in ['preflight', 'clear']:
            self.assertTrue(dispatch(self.c, self.request(action))['ok'])
        req = self.request('next'); receipt = dispatch(self.c, req)
        version = self.c.version
        for _ in range(5):
            self.assertEqual(dispatch(self.c, {'action':'receipt','request_id':req['request_id']})['receipt'],receipt)
            self.assertTrue(dispatch(self.c, {'action':'status'})['ok'])
        self.assertFalse(dispatch(self.c, {'action':'receipt','request_id':'never-seen'})['found'])
        self.assertEqual(self.c.version,version)
        self.assertEqual(self.backend.sets,1)

    def test_cli_exact_mutation_and_receipt_doubles(self):
        req = self.request('next')
        with patch('location_lab.local_control.request_local', return_value={'ok':True}) as local, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['next','--socket','unused','--request-id',req['request_id'],'--epoch',req['epoch'],'--version',str(req['version'])]),0)
            local.assert_called_once_with('unused',req)
        with patch('location_lab.local_control.request_local', return_value={'ok':True,'found':False}) as local, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['receipt','--socket','unused','--request-id','synthetic-request']),0)
            local.assert_called_once_with('unused',{'action':'receipt','request_id':'synthetic-request'})

    def test_invalid_or_stale_never_mutates(self):
        for req in [{},None,{'action':'set'}, {'action':'next'}, {'action':'status','unexpected':True}]:
            self.assertFalse(dispatch(self.c,req)['ok'])
        req=self.request('next');req['version']=-1
        self.assertEqual(dispatch(self.c,req)['code'],'stale_command')
        self.assertEqual(self.backend.sets+self.backend.clears,0)

    def test_network_unknown_no_retry(self):
        with patch('location_lab.local_control.request_local', side_effect=TimeoutError) as local, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['next','--socket','unused','--request-id','synthetic','--epoch','synthetic','--version','0']),2)
            self.assertEqual(local.call_count,1)
            self.assertEqual(json.loads(output.getvalue())['code'],'local_result_unknown')
