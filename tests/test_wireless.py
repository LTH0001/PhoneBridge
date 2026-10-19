import json
import socket
import ssl
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from phonebridge.wireless import WirelessServer,receive,send

class WirelessTests(unittest.TestCase):
    def setUp(self):
        self.api=SimpleNamespace(bridge=SimpleNamespace(connected=False),port=1,token='private')
        self.server=WirelessServer(self.api,'127.0.0.1')
        self.context=ssl.create_default_context(cadata=x509.load_der_x509_certificate(self.server.certificate).public_bytes(serialization.Encoding.PEM).decode())
        self.context.check_hostname=False
    def tearDown(self):self.server.close()
    def connect(self,sid,token):
        raw=socket.create_connection(('127.0.0.1',self.server.port),timeout=2)
        sock=self.context.wrap_socket(raw,server_hostname='PhoneBridge local pairing');sock.settimeout(2)
        send(sock,{'sid':sid,'token':token});return sock
    def pair(self):
        with self.connect(0,self.server.invite) as sock:return receive(sock)['session']
    def test_invite_single_use_and_session_is_distinct(self):
        invite=self.server.invite;session=self.pair();self.assertNotEqual(invite,session)
        with self.connect(0,invite) as sock:
            with self.assertRaises(Exception):receive(sock)
    def test_expired_invite_denied(self):
        self.server.expires=time.monotonic()-1
        with self.connect(0,self.server.invite) as sock:
            with self.assertRaises(Exception):receive(sock)
    def test_wrong_credentials_denied(self):
        with self.connect(0,'wrong') as sock:
            with self.assertRaises(Exception):receive(sock)
    def test_existing_usb_not_taken_over(self):
        self.api.bridge.connected=True
        with self.connect(0,self.server.invite) as sock:
            with self.assertRaises(Exception):receive(sock)
    def test_unauthenticated_rpc_denied(self):
        with self.connect(5,'wrong') as sock:
            with self.assertRaises(Exception):receive(sock)
    def test_privileged_api_never_forwarded(self):
        for path in ('/api/shutdown','/api/files/download','/api/camera/register-system','/api/connect','/api/wireless/pair','http://example.com','/api/music/art?key=../../'):
            with patch('phonebridge.wireless.urlopen') as request:
                self.assertIn('error',self.server.rpc({'path':path,'body':{}}));request.assert_not_called()
    def test_authenticated_rpc_uses_session_not_local_api_token(self):
        session=self.pair()
        with patch.object(self.server,'rpc',return_value={'ok':'limited'}) as call:
            with self.connect(5,session) as sock:
                self.assertTrue(receive(sock)['ok']);send(sock,{'path':'/api/dashboard/status'});self.assertEqual(receive(sock),{'ok':'limited'})
            call.assert_called_once()
    def test_duplicate_channel_rejected(self):
        session=self.pair()
        with self.connect(2,session) as first:
            self.assertTrue(receive(first)['ok'])
            with self.connect(2,session) as second:
                with self.assertRaises(Exception):receive(second)
    def test_close_revokes_all_credentials(self):
        self.pair();self.server.close();self.assertEqual(self.server.session,'');self.assertEqual(self.server.invite,'')
    def test_plaintext_not_accepted(self):
        with socket.create_connection(('127.0.0.1',self.server.port),timeout=2) as sock:
            sock.settimeout(2);send(sock,{'sid':0,'token':self.server.invite})
            with self.assertRaises(Exception):receive(sock)
    def test_nonlocal_bind_rejected(self):
        with self.assertRaises(ValueError):WirelessServer(self.api,'8.8.8.8')
    def test_framing_limit(self):
        reader,writer=socket.socketpair()
        try:
            writer.sendall(b'x'*10)
            with self.assertRaises(Exception):receive(reader,3)
        finally:reader.close();writer.close()

if __name__=='__main__':unittest.main()
