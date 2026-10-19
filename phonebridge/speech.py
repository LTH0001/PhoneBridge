"""Local batch and opt-in streaming dictation. No cloud or disk audio."""
import base64
import json
import re
import threading
import os
import shutil
import time
import ctypes
from pathlib import Path
from .config import ROOT

def model_path():
    """Vosk's Windows native loader cannot open Unicode model paths."""
    source=ROOT/'vendor/vosk-model-small-cn-0.22'
    if str(source).isascii():return source
    cache=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'PhoneBridge/SpeechModels/vosk-model-small-cn-0.22'
    if not str(cache).isascii():
        raise ValueError('离线语音引擎需要英文路径，请将 PhoneBridge 解压到英文路径后重试')
    # App-owned, versioned cache. Never overwrite or remove unrelated directories.
    for item in source.rglob('*'):
        if item.is_file():
            destination=cache/item.relative_to(source)
            destination.parent.mkdir(parents=True,exist_ok=True)
            if not destination.exists() or destination.stat().st_size!=item.stat().st_size:
                temporary=destination.with_name(destination.name+'.copying')
                shutil.copyfile(item,temporary)
                os.replace(temporary,destination)
    return cache

class LocalSpeech:
    def __init__(self,remote_input):
        self.input=remote_input;self.lock=threading.Lock();self.model=None;self.stream=None

    def _model(self):
        from vosk import Model,SetLogLevel
        SetLogLevel(-1)
        if self.model is None:self.model=Model(str(model_path()))
        return self.model

    @staticmethod
    def _clean(text):
        return re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])','',' '.join(text.split()))[:2000]

    def start(self,session):
        with self.input.lock:self.input._check(session)
        with self.lock:
            from vosk import KaldiRecognizer
            self.stream=None
            focus=foreground()
            recognizer=KaldiRecognizer(self._model(),16000)
            self.stream={'session':session,'recognizer':recognizer,'seq':0,'bytes':0,'previous':'',
                         'committed':'','characters':0,'last':time.monotonic(),'focus':focus}
        return {'ok':True,'streaming':True,'max_seconds':60}

    def _stream(self,session,seq):
        with self.input.lock:self.input._check(session)
        stream=self.stream
        if not stream or stream['session']!=session:raise ValueError('语音会话已失效，请重新按住说话')
        if isinstance(seq,bool) or not isinstance(seq,int) or seq!=stream['seq']:
            self.stream=None;raise ValueError('语音分片顺序变化，已停止；不会重复输入')
        if time.monotonic()-stream['last']>15 or foreground()!=stream['focus']:
            self.stream=None;raise ValueError('连接超时或电脑前台窗口已变化，语音已停止')
        stream['last']=time.monotonic()
        return stream

    def _commit(self,stream,text,final):
        text=self._clean(text)
        if final:stable=text
        else:
            common=os.path.commonprefix((stream['previous'],text))
            stable=common[:-1] if common else ''
        stream['previous']=text
        committed=stream['committed']
        if not stable.startswith(committed):
            # Never backspace or replace arbitrary application content.
            if final:raise ValueError('识别结果出现修正，已停止；已输入文字保留，请检查电脑')
            return ''
        delta=stable[len(committed):]
        if delta:
            if stream['characters']+len(delta)>2000:raise ValueError('本次输入已达 2000 字上限')
            if foreground()!=stream['focus']:raise ValueError('电脑前台窗口已变化，语音已停止')
            self.input.text(stream['session'],delta,confirmed=True)
            stream['committed']=stable;stream['characters']+=len(delta)
        if final:stream['previous']='';stream['committed']=''
        return delta

    def chunk(self,session,seq,pcm):
        if not isinstance(pcm,str) or len(pcm)>24000:raise ValueError('语音分片过大')
        try:audio=base64.b64decode(pcm,validate=True)
        except Exception:raise ValueError('无效语音分片') from None
        if not 2<=len(audio)<=16000 or len(audio)%2:raise ValueError('无效 PCM16 语音分片')
        with self.lock:
            stream=self._stream(session,seq)
            try:
                stream['bytes']+=len(audio)
                if stream['bytes']>1920000:raise ValueError('本次语音已达 60 秒上限')
                recognizer=stream['recognizer'];final=recognizer.AcceptWaveform(audio)
                result=json.loads(recognizer.Result() if final else recognizer.PartialResult())
                delta=self._commit(stream,result.get('text' if final else 'partial',''),final)
                stream['seq']+=1
                return {'ok':True,'seq':stream['seq'],'delta':delta,'characters':stream['characters']}
            except Exception:self.stream=None;raise

    def finish(self,session,seq,cancelled=False,enter=False):
        if not isinstance(cancelled,bool):raise ValueError('无效的取消标记')
        if not isinstance(enter,bool) or cancelled and enter:raise ValueError('无效的回车确认标记')
        with self.lock:
            if cancelled:
                if self.stream and self.stream['session']==session:self.stream=None
                return {'ok':True,'cancelled':True,'delta':''}
            stream=self._stream(session,seq)
            try:
                text=json.loads(stream['recognizer'].FinalResult()).get('text','')
                delta=self._commit(stream,text,True)
                submitted=False
                if enter and stream['characters']>0:
                    if foreground()!=stream['focus']:raise ValueError('电脑前台窗口已变化，未发送回车')
                    self.input.submit(session,confirmed=True);submitted=True
                return {'ok':True,'delta':delta,'characters':stream['characters'],'submitted':submitted}
            finally:self.stream=None

    def recognize(self,session,pcm):
        with self.input.lock:self.input._check(session)
        if not isinstance(pcm,str) or len(pcm)>640000:raise ValueError('录音最长 15 秒')
        try:audio=base64.b64decode(pcm,validate=True)
        except Exception:raise ValueError('无效的 PCM 录音') from None
        if not 3200<=len(audio)<=480000 or len(audio)%2:raise ValueError('需要 16 kHz 单声道 PCM16，录音长度 0.1 至 15 秒')
        if not self.lock.acquire(blocking=False):raise ValueError('上一段语音仍在识别，请稍候')
        try:
            from vosk import Model,KaldiRecognizer,SetLogLevel
            SetLogLevel(-1)
            if self.model is None:self.model=Model(str(model_path()))
            recognizer=KaldiRecognizer(self.model,16000);parts=[]
            for offset in range(0,len(audio),8000):
                if recognizer.AcceptWaveform(audio[offset:offset+8000]):parts.append(json.loads(recognizer.Result()).get('text',''))
            parts.append(json.loads(recognizer.FinalResult()).get('text',''))
            text=re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])','',' '.join(parts).strip())[:2000]
            return {'text':text,'offline':True,'message':'请检查识别结果，再输入到电脑' if text else '未识别到清晰语音，请靠近麦克风重试'}
        finally:self.lock.release()

def foreground():
    if os.name=='nt':
        fn=ctypes.windll.user32.GetForegroundWindow;fn.restype=ctypes.c_void_p
        return fn()
    return 0
