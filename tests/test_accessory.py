import json
import unittest
from unittest.mock import Mock
from phonebridge import proto
from phonebridge.accessory import AccessoryTransport,FrameBuffer,probe,switch
from phonebridge.transport import BridgeError

class AccessoryTests(unittest.TestCase):
    def test_control_timeout_has_actionable_error_and_closes(self):
        transport=AccessoryTransport(Mock(),Mock(),Mock(),Mock())
        transport._send=Mock();transport.close=Mock()
        with self.assertRaisesRegex(BridgeError,'USB 控制响应超时'):
            transport.request(proto.T_GET_STATUS,expect=proto.T_STATUS,timeout=.001)
        transport.close.assert_called_once()
        self.assertIn('授权',transport.status()['error'])
    def test_fragmented_and_coalesced_bulk_packets(self):
        a=proto.frame_json(proto.T_STATUS,1,7,{'ok':True});b=proto.frame_json(0xc0,5,8,{'path':'/api/dashboard/status'})
        parser=FrameBuffer();self.assertEqual(parser.feed(a[:13]),[])
        values=parser.feed(a[13:]+b);self.assertEqual([f[1] for f in values],[1,5]);self.assertEqual(values[1][2],8)
    def test_payload_does_not_resync_on_magic_inside_video(self):
        parser=FrameBuffer();packet=proto.frame(0x1001,2,1,0,0,b'PB01'*50)
        self.assertEqual(parser.feed(packet[:50]),[]);self.assertEqual(parser.feed(packet[50:])[0][5],b'PB01'*50)
    def test_invalid_headers_rejected(self):
        for magic,version,sid,size in ((b'BAD!',1,1,0),(b'PB01',2,1,0),(b'PB01',1,6,0),(b'PB01',1,1,16*1024*1024+1)):
            with self.subTest(magic=magic,version=version,sid=sid,size=size):
                with self.assertRaises(BridgeError):FrameBuffer().feed(proto.HEADER.pack(magic,version,1,sid,0,0,0,size))
    def test_probe_readonly(self):
        device=Mock();device.ctrl_transfer.return_value=bytes([2,0]);self.assertEqual(probe(device),2)
        device.ctrl_transfer.assert_called_once_with(0xc0,51,0,0,2,timeout=1500)
    def test_bad_probe_never_switches(self):
        for value in (b'',b'\x00\x00',b'\x03\x00'):
            device=Mock();device.ctrl_transfer.return_value=value
            with self.assertRaises(BridgeError):switch(device)
            self.assertEqual(device.ctrl_transfer.call_count,1)
    def test_switch_identifies_our_accessory_before_start(self):
        device=Mock();device.ctrl_transfer.return_value=bytes([2,0]);switch(device)
        calls=device.ctrl_transfer.call_args_list;self.assertEqual(len(calls),8)
        self.assertEqual(calls[1].args,(0x40,52,0,0,b'PhoneBridge\0'));self.assertEqual(calls[2].args,(0x40,52,0,1,b'PhoneBridge USB\0'))
        self.assertEqual(calls[-1].args,(0x40,53,0,0,b''))

if __name__=='__main__':unittest.main()
