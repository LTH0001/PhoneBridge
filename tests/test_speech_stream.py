import base64
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from phonebridge.speech import LocalSpeech

PCM=base64.b64encode(bytes(8000)).decode()

class SpeechStreamTests(unittest.TestCase):
    def setUp(self):
        self.input=SimpleNamespace(lock=threading.RLock(),_check=Mock(),text=Mock(),submit=Mock())
        self.service=LocalSpeech(self.input);self.service.model=object()
        self.recognizer=Mock();self.recognizer.AcceptWaveform.return_value=False
        fake=SimpleNamespace(Model=Mock(),SetLogLevel=Mock(),KaldiRecognizer=Mock(return_value=self.recognizer))
        patcher=patch.dict('sys.modules',{'vosk':fake});patcher.start();self.addCleanup(patcher.stop)
        focus=patch('phonebridge.speech.foreground',return_value=10);self.focus=focus.start();self.addCleanup(focus.stop)
        self.service.start('session')
    def partial(self,seq,text):
        import json
        self.recognizer.PartialResult.return_value=json.dumps({'partial':text})
        return self.service.chunk('session',seq,PCM)
    def test_stable_partials_type_before_release_without_duplicate_characters(self):
        for seq,value in enumerate(('你','你好','你好世','你好世界')):self.partial(seq,value)
        self.assertEqual([c.args[1] for c in self.input.text.call_args_list],['你','好'])
        self.recognizer.FinalResult.return_value='{"text":"你好世界"}'
        result=self.service.finish('session',4)
        self.assertEqual(result['characters'],4)
        self.assertEqual(''.join(c.args[1] for c in self.input.text.call_args_list),'你好世界')
    def test_repeated_sequence_aborts_without_retyping(self):
        self.partial(0,'你好')
        with self.assertRaises(ValueError):self.partial(0,'你好')
        self.assertIsNone(self.service.stream);self.input.text.assert_not_called()
    def test_focus_change_stops_typing_into_another_window(self):
        self.focus.return_value=20
        with self.assertRaises(ValueError):self.partial(0,'你好世界')
        self.input.text.assert_not_called();self.assertIsNone(self.service.stream)
    def test_cancel_keeps_prior_input_and_never_commits_tail(self):
        for seq,text in enumerate(('你好','你好世界')):self.partial(seq,text)
        before=self.input.text.call_count
        result=self.service.finish('session',2,cancelled=True)
        self.assertTrue(result['cancelled']);self.assertEqual(self.input.text.call_count,before)
        self.recognizer.FinalResult.assert_not_called()
    def test_changed_final_never_backspaces_or_duplicates(self):
        self.partial(0,'你好');self.partial(1,'你好世界')
        self.recognizer.FinalResult.return_value='{"text":"他好世界"}'
        with self.assertRaises(ValueError):self.service.finish('session',2)
        self.assertEqual(self.input.text.call_count,1);self.assertIsNone(self.service.stream)
    def test_endpoint_final_resets_segment_for_next_phrase(self):
        self.recognizer.AcceptWaveform.return_value=True
        self.recognizer.Result.return_value='{"text":"你好"}'
        self.service.chunk('session',0,PCM)
        self.recognizer.Result.return_value='{"text":"世界"}'
        self.service.chunk('session',1,PCM)
        self.recognizer.FinalResult.return_value='{"text":""}'
        self.service.finish('session',2)
        self.assertEqual(''.join(c.args[1] for c in self.input.text.call_args_list),'你好世界')
    def test_stream_audio_bound_and_invalid_chunks(self):
        for pcm in ('*bad*','A'*24001,base64.b64encode(bytes(3)).decode()):
            with self.assertRaises(ValueError):self.service.chunk('session',0,pcm)
        self.input.text.assert_not_called()
        self.service.stream['bytes']=1920000
        with self.assertRaises(ValueError):self.partial(0,'你好')
        self.assertIsNone(self.service.stream)
    def test_explicit_enter_happens_once_after_final_text(self):
        calls=Mock();calls.attach_mock(self.input.text,'text');calls.attach_mock(self.input.submit,'submit')
        self.recognizer.FinalResult.return_value='{"text":"你好"}'
        result=self.service.finish('session',0,enter=True)
        self.assertTrue(result['submitted'])
        self.assertEqual([c[0] for c in calls.mock_calls],['text','submit'])
        self.input.submit.assert_called_once_with('session',confirmed=True)
        with self.assertRaises(ValueError):self.service.finish('session',0,enter=True)
        self.assertEqual(self.input.submit.call_count,1)
    def test_no_enter_on_empty_audio_default_finish_or_cancel(self):
        self.recognizer.FinalResult.return_value='{"text":""}'
        self.assertFalse(self.service.finish('session',0,enter=True)['submitted'])
        self.service.start('session');self.recognizer.FinalResult.return_value='{"text":"你好"}'
        self.assertFalse(self.service.finish('session',0)['submitted'])
        self.service.start('session');self.service.finish('session',0,cancelled=True)
        self.input.submit.assert_not_called()
    def test_invalid_enter_flags_rejected(self):
        for enter in (1,None,'true'):
            with self.assertRaises(ValueError):self.service.finish('session',0,enter=enter)
        with self.assertRaises(ValueError):self.service.finish('session',0,cancelled=True,enter=True)
        self.input.submit.assert_not_called()
    def test_failed_tail_input_never_submits(self):
        self.recognizer.FinalResult.return_value='{"text":"你好"}';self.input.text.side_effect=RuntimeError('blocked')
        with self.assertRaises(RuntimeError):self.service.finish('session',0,enter=True)
        self.input.submit.assert_not_called();self.assertIsNone(self.service.stream)
    def test_focus_change_after_final_text_never_submits(self):
        self.recognizer.FinalResult.return_value='{"text":"你好"}'
        self.input.text.side_effect=lambda *args,**kw:setattr(self.focus,'return_value',20)
        with self.assertRaises(ValueError):self.service.finish('session',0,enter=True)
        self.input.submit.assert_not_called()
