import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from phonebridge.remote_input import emit_enter,emit_text

class EnterKeyTests(unittest.TestCase):
    def test_exactly_one_checked_return_key_pair(self):
        user=SimpleNamespace(GetAsyncKeyState=Mock(return_value=0))
        with patch('phonebridge.remote_input.c.windll',SimpleNamespace(user32=user),create=True),patch('phonebridge.remote_input._send_keyboard') as send:
            emit_enter();send.assert_called_once_with(((0x0d,0,0),(0x0d,0,2)))
    def test_held_modifier_prevents_accidental_shortcut(self):
        user=SimpleNamespace(GetAsyncKeyState=Mock(return_value=0x8000))
        with patch('phonebridge.remote_input.c.windll',SimpleNamespace(user32=user),create=True),patch('phonebridge.remote_input._send_keyboard') as send:
            with self.assertRaises(RuntimeError):emit_enter()
            send.assert_not_called()
    def test_unicode_text_still_uses_code_units_not_virtual_return(self):
        with patch('phonebridge.remote_input._send_keyboard') as send:
            emit_text('中🙂')
            events=send.call_args.args[0]
            self.assertEqual(len(events),6)
            self.assertTrue(all(vk==0 and flags in (4,6) for vk,scan,flags in events))
    def test_partial_input_releases_return_without_retrying_key_down(self):
        user=SimpleNamespace(GetAsyncKeyState=Mock(return_value=0),keybd_event=Mock())
        with patch('phonebridge.remote_input.c.windll',SimpleNamespace(user32=user),create=True),patch('phonebridge.remote_input._send_keyboard',side_effect=RuntimeError('partial')) as send:
            with self.assertRaises(RuntimeError):emit_enter()
            send.assert_called_once();user.keybd_event.assert_called_once_with(0x0d,0,2,0)
