import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from phonebridge.remote_input import RemoteInput,validate_event

class RemoteInputTests(unittest.TestCase):
    def setUp(self):
        self.bridge=SimpleNamespace(connected=True,transport=object())
        self.controller=RemoteInput(self.bridge);self.addCleanup(self.controller.close)
        self.mouse=patch('phonebridge.remote_input.emit_mouse').start();self.addCleanup(patch.stopall)
        self.typing=patch('phonebridge.remote_input.emit_text').start()
        self.keys=patch('phonebridge.remote_input.emit_shortcut').start()
        self.enter=patch('phonebridge.remote_input.emit_enter').start()
        self.control=patch('phonebridge.remote_input.emit_control').start()
    def begin(self):return self.controller.begin(True)['session']
    def test_opt_in_required(self):
        for value in (False,None,1,'true'):
            with self.assertRaises(ValueError):self.controller.begin(value)
        self.bridge.connected=False
        with self.assertRaises(ValueError):self.begin()
    def test_events_require_current_session(self):
        token=self.begin()
        with self.assertRaises(ValueError):self.controller.events('bad',[])
        self.controller.events(token,[{'kind':'move','dx':12,'dy':-8},{'kind':'scroll','dy':120},{'kind':'click','button':'right'}])
        self.assertEqual(self.mouse.call_count,4)
        self.controller.end(token)
        with self.assertRaises(ValueError):self.controller.events(token,[])
    def test_validation_is_atomic_before_any_injection(self):
        token=self.begin()
        with self.assertRaises(ValueError):self.controller.events(token,[{'kind':'click'},{'kind':'shell','command':'bad'}])
        self.mouse.assert_not_called()
        for event in ({'kind':'move','dx':float('nan')},{'kind':'move','dx':True},{'kind':'move','dy':1001},{'kind':'navigation','action':'enter'},{'kind':'button','down':1}):
            with self.assertRaises(ValueError):validate_event(event)
        with self.assertRaises(ValueError):self.controller.events(token,[{}]*33)
    def test_drag_released_on_stop_and_session_replacement(self):
        token=self.begin();self.controller.events(token,[{'kind':'button','down':True}])
        self.assertTrue(self.controller.dragged);self.begin();self.assertFalse(self.controller.dragged)
        self.mouse.assert_called_with(4)
    def test_transport_change_and_expiry_revoke_session(self):
        token=self.begin();self.bridge.transport=object()
        with self.assertRaises(ValueError):self.controller.events(token,[])
        token=self.begin();self.controller.last-=91
        with self.assertRaises(ValueError):self.controller.events(token,[])
    def test_text_is_reviewed_single_paragraph_not_clipboard_or_enter(self):
        token=self.begin()
        for text,confirmed in [('hello',False),('a\nb',True),('a\tb',True),('\x00',True),('',True),('a'*2001,True)]:
            with self.assertRaises(ValueError):self.controller.text(token,text,confirmed)
        self.typing.assert_not_called()
        result=self.controller.text(token,'中文输入🙂',True)
        self.typing.assert_called_once_with('中文输入🙂');self.assertEqual(result['characters'],5)
        self.keys.assert_not_called()
    def test_shortcuts_are_an_allowlist(self):
        token=self.begin();self.controller.events(token,[{'kind':'navigation','action':'back'}])
        self.keys.assert_called_once_with((0x12,0x25))
    def test_submit_requires_explicit_confirmation_and_live_session(self):
        token=self.begin()
        with self.assertRaises(ValueError):self.controller.submit(token)
        with self.assertRaises(ValueError):self.controller.submit('bad',True)
        self.enter.assert_not_called()
        self.controller.submit(token,True);self.enter.assert_called_once_with()
        self.controller.end(token)
        with self.assertRaises(ValueError):self.controller.submit(token,True)
    def test_numberpad_allowlist_and_explicit_single_key_events(self):
        token=self.begin()
        keys=('0','1','2','3','4','5','6','7','8','9','.','+','-','*','/','backspace','enter')
        self.controller.events(token,[{'kind':'key','key':key} for key in keys])
        self.assertEqual(self.typing.call_count,15)
        self.control.assert_called_once_with(0x08);self.enter.assert_called_once_with()
        for key in ('cmd','delete','tab','ctrl+a','00','\n',None,1,{},[]):
            with self.assertRaises(ValueError):validate_event({'kind':'key','key':key})
    def test_bad_numberpad_batch_is_rejected_before_any_input(self):
        token=self.begin()
        with self.assertRaises(ValueError):self.controller.events(token,[{'kind':'key','key':'1'},{'kind':'key','key':'cmd'}])
        self.typing.assert_not_called();self.enter.assert_not_called();self.control.assert_not_called()
    def test_desktop_is_explicit_and_independent_of_touchpad_session(self):
        with self.assertRaises(ValueError):self.controller.desktop()
        self.controller.desktop(True);self.keys.assert_called_once_with((0x5b,0x44))
        self.assertEqual(self.controller.session,'')
        token=self.begin();self.controller.desktop(True);self.assertEqual(self.controller.session,token)
        self.bridge.connected=False
        with self.assertRaises(ValueError):self.controller.desktop(True)
        self.assertEqual(self.keys.call_count,2)
    def test_previous_window_is_alt_tab_not_browser_back_or_phone_navigation(self):
        for confirmed in (False,None,1,'true'):
            with self.assertRaises(ValueError):self.controller.previous(confirmed)
        self.keys.assert_not_called()
        self.controller.previous(True);self.keys.assert_called_once_with((0x12,0x09))
        self.assertEqual(self.controller.session,'')
        token=self.begin();self.controller.previous(True);self.assertEqual(self.controller.session,token)
        self.bridge.connected=False
        with self.assertRaises(ValueError):self.controller.previous(True)
        self.assertEqual(self.keys.call_count,2)
    def test_phone_surface_and_voice_are_explicit(self):
        from pathlib import Path
        root=Path(__file__).resolve().parent.parent
        source=(root/'android/app/src/InputActivity.java').read_text('utf-8')
        self.assertIn('new HoldToTalk',source)
        speech=(root/'android/app/src/HoldToTalk.java').read_text('utf-8')
        self.assertIn('/api/speech/chunk',speech);self.assertIn('右滑回车',speech)
        self.assertIn('protected void onPause()',source)
        pad=(root/'android/app/src/TouchpadView.java').read_text('utf-8')
        self.assertNotIn('PanelNavigation',pad);self.assertNotIn('VolumeLayout',pad)
