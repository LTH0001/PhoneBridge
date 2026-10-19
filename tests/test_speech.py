import base64
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from phonebridge.speech import LocalSpeech

class SpeechTests(unittest.TestCase):
    def service(self):return LocalSpeech(SimpleNamespace(lock=threading.RLock(),_check=Mock()))
    def test_invalid_audio_rejected_before_model_load(self):
        service=self.service()
        for value in (None,'*bad*','A'*640001,base64.b64encode(bytes(100)).decode(),base64.b64encode(bytes(3201)).decode()):
            with self.assertRaises(ValueError):service.recognize('session',value)
        self.assertIsNone(service.model)
    def test_recognition_only_returns_review_text(self):
        service=self.service();recognizer=Mock();recognizer.AcceptWaveform.return_value=False
        recognizer.FinalResult.return_value='{"text":"你 好 世 界"}'
        fake=SimpleNamespace(Model=Mock(),KaldiRecognizer=Mock(return_value=recognizer),SetLogLevel=Mock())
        with patch.dict('sys.modules',{'vosk':fake}):result=service.recognize('session',base64.b64encode(bytes(32000)).decode())
        self.assertEqual(result['text'],'你好世界');self.assertTrue(result['offline'])
        service.input._check.assert_called_once_with('session')
    def test_busy_model_does_not_queue_stale_audio(self):
        service=self.service();service.lock.acquire()
        try:
            with self.assertRaises(ValueError):service.recognize('session',base64.b64encode(bytes(32000)).decode())
        finally:service.lock.release()
