import json
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock,patch
from phonebridge.apk_install import ApkInstaller
from phonebridge.core import Bridge
from phonebridge.api import LocalAPI

class ApkInstallTests(unittest.TestCase):
    def bridge(self):
        bridge=Mock();bridge.detect.return_value=[{'serial':'phone1','state':'device'},
            {'serial':'phone2','state':'unauthorized'},{'serial':'192.168.1.1:5555','state':'device'}]
        return bridge

    def test_requires_consent_and_authorized_physical_device(self):
        bridge=self.bridge();install=ApkInstaller(bridge)
        for serial,confirmed in [('phone1',False),('phone2',True),('missing',True),('192.168.1.1:5555',True),('phone1','yes')]:
            with self.assertRaises(Exception):install.start(serial,confirmed)
        bridge.install.assert_not_called()
        self.assertEqual(len(install.devices()),2)

    def test_only_one_job_and_explicit_target(self):
        bridge=self.bridge();gate=threading.Event()
        bridge.install.side_effect=lambda **kw:gate.wait(3)
        install=ApkInstaller(bridge)
        try:
            self.assertEqual(install.start('phone1',True)['state'],'installing')
            with self.assertRaises(Exception):install.start('phone1',True)
            bridge.install.assert_called_once_with(serial='phone1')
        finally:gate.set()
        for _ in range(100):
            if install.status()['state']!='installing':break
            time.sleep(.01)
        self.assertEqual(install.status()['state'],'success')

    def test_rejection_is_actionable_and_not_retried(self):
        bridge=self.bridge();bridge.install.side_effect=RuntimeError('INSTALL_FAILED_ABORTED: User rejected permissions')
        install=ApkInstaller(bridge);install.start('phone1',True)
        for _ in range(100):
            if install.status()['state']!='installing':break
            time.sleep(.01)
        self.assertEqual(install.status()['state'],'error')
        self.assertIn('不会自动重试',install.status()['message'])
        bridge.install.assert_called_once()

    def test_install_does_not_retarget_connected_phone(self):
        bridge=Bridge.__new__(Bridge);bridge.lock=threading.RLock();bridge.serial='existing'
        bridge.auto_reconnect=True;bridge.config={'adb':'adb.exe'};bridge.log=Mock()
        bridge.detect=Mock(return_value=[{'serial':'phone1','state':'device'}])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);apk=root/'android/app/build/phonebridge.apk';apk.parent.mkdir(parents=True);apk.write_bytes(b'test')
            with patch('phonebridge.core.ROOT',root),patch('phonebridge.core.adb_run',return_value='Success') as adb:
                bridge.install(serial='phone1')
                self.assertEqual(adb.call_args.args[1],'phone1')
                self.assertIn(str(apk),adb.call_args.args)
        self.assertEqual(bridge.serial,'existing');self.assertTrue(bridge.auto_reconnect)

class ApkApiTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        (root/'phonebridge').mkdir();(root/'phonebridge/setup.html').write_text('<title>Setup</title>')
        apk=root/'android/app/build/phonebridge.apk';apk.parent.mkdir(parents=True);apk.write_bytes(b'test APK')
        for name in ('HostTelemetry','MusicController','SystemInfo','PlaybackController'):
            self.stack.enter_context(patch('phonebridge.api.'+name))
        self.stack.enter_context(patch('phonebridge.api.ROOT',root))
        self.bridge=Mock(config={});self.bridge.detect.return_value=[]
        self.api=LocalAPI(self.bridge,0);self.addCleanup(self.api.close)
        self.url='http://127.0.0.1:'+str(self.api.port)

    def request(self,path,body=None,headers=None):
        req=urllib.request.Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers or {})
        return urllib.request.urlopen(req)

    def test_static_shell_has_no_token_and_api_requires_auth(self):
        with self.request('/setup') as response:
            self.assertNotIn(self.api.token,response.read().decode())
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        for path in ('/api/apk/status','/api/apk/devices','/api/apk/download'):
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(path)
            self.assertEqual(error.exception.code,401)

    def test_download_is_fixed_attachment(self):
        with self.request('/api/apk/download',headers={'Authorization':'Bearer '+self.api.token}) as response:
            self.assertEqual(response.read(),b'test APK')
            self.assertIn('attachment;',response.headers['Content-Disposition'])

    def test_cross_origin_and_query_only_install_rejected(self):
        body={'serial':'phone1','confirmed':True}
        for path,headers in [('/api/apk/install?token='+self.api.token,{}),
                ('/api/apk/install',{'Authorization':'Bearer '+self.api.token,'Origin':'http://evil.example'})]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(path,body,headers)
            self.assertEqual(error.exception.code,403)
        self.bridge.install.assert_not_called()
