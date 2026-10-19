"""Targeted QQ Music SMTC control; never falls back to global media keys."""
import asyncio
import copy
import subprocess
import threading
import time
import math
import io
from pathlib import Path
from .transport import BridgeError

def timeline_position(position,duration,playing,rate,updated_at,now):
    """SMTC Position is measured at LastUpdatedTime, not at this request."""
    rate=rate if isinstance(rate,(int,float)) and math.isfinite(rate) and 0<rate<=4 else 1.0
    age=now-updated_at
    compensation=age*rate if playing and 0<=age<=10 else 0
    return min(duration,max(0,position+compensation)) if duration>0 else max(0,position+compensation)

def artwork_jpeg(raw):
    if not raw or len(raw)>2*1024*1024:return b''
    from PIL import Image,ImageOps
    with Image.open(io.BytesIO(raw)) as image:
        if image.width*image.height>16_000_000:return b''
        image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((512,512))
        output=io.BytesIO();image.save(output,'JPEG',quality=85);return output.getvalue()

def choose_qq_session(sessions,current=None):
    candidates=[s for s in sessions if s.source_app_user_model_id.lower()=='qqmusic.exe']
    return next((s for s in candidates if current and s.source_app_user_model_id==current.source_app_user_model_id),
                candidates[0] if candidates else None)

class MusicController:
    def __init__(self,path):
        self.path=Path(path); self.lock=threading.Lock(); self.closed=threading.Event(); self.ready=threading.Event()
        from .music_window import MusicWindow
        self.window=MusicWindow(path)
        self.loop=self.manager=None
        self.art_key='';self.art=b'';self.art_attempt=0;self.art_task=None;self.sample_clock=time.monotonic()
        self.value={'available':False,'target':'QQ音乐','title':'等待 QQ 音乐媒体会话','artist':'',
                    'playback_status':'unavailable','source_app_id':'','error':''}
        self.thread=threading.Thread(target=self._thread,name='pb-qq-music',daemon=True); self.thread.start()

    def _thread(self):
        initialized=False
        try:
            import winrt.runtime
            winrt.runtime.init_apartment(winrt.runtime.ApartmentType.MULTI_THREADED)
            initialized=True
            asyncio.run(self._run())
        except Exception as exc:
            with self.lock: self.value.update(available=False,error=str(exc))
        finally:
            if initialized: winrt.runtime.uninit_apartment()
            self.ready.set()

    async def _run(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        self.loop=asyncio.get_running_loop(); self.action_lock=asyncio.Lock()
        self.manager=await asyncio.wait_for(Manager.request_async(),5)
        self.ready.set()
        while not self.closed.is_set():
            try: await self._refresh()
            except Exception as exc:
                with self.lock: self.value.update(available=False,error=str(exc))
            await asyncio.sleep(.2)

    def _session(self):
        if self.manager is None: return None
        return choose_qq_session(list(self.manager.get_sessions()),self.manager.get_current_session())

    async def _refresh(self):
        session=self._session()
        if session is None:
            value={'available':False,'target':'QQ音乐','title':'打开 QQ 音乐后显示当前歌曲','artist':'',
                   'playback_status':'unavailable','source_app_id':'',
                   'error':'未发现 QQ 音乐媒体会话；不会控制其他播放器'}
        else:
            properties=await asyncio.wait_for(session.try_get_media_properties_async(),3)
            info=session.get_playback_info(); timeline=session.get_timeline_properties()
            controls=info.controls
            playing=info.playback_status.name.lower()=='playing'
            duration=max(0,(timeline.end_time-timeline.start_time).total_seconds())
            rate=info.playback_rate or 1.0
            position=timeline_position(timeline.position.total_seconds(),duration,playing,rate,
                                       timeline.last_updated_time.timestamp(),time.time())
            value={'available':True,'target':'QQ音乐','source_app_id':session.source_app_user_model_id,
                   'title':properties.title[:200],'artist':properties.artist[:160],
                   'playback_status':info.playback_status.name.lower(),
                   'position_seconds':position,'playback_rate':rate,
                   'duration_seconds':duration,
                   'can_toggle':controls.is_play_pause_toggle_enabled,
                   'can_previous':controls.is_previous_enabled,'can_next':controls.is_next_enabled,'error':''}
            from .lyrics import track_key
            key=track_key(value)
            if key!=self.art_key:
                with self.lock:self.art_key=key;self.art=b'';self.art_attempt=0
            if not self.art and (self.art_task is None or self.art_task.done()) and time.monotonic()-self.art_attempt>10:
                self.art_attempt=time.monotonic()
                self.art_task=asyncio.create_task(self._load_art(properties.thumbnail,key))
            value['artwork_key']=key if self.art else ''
        with self.lock:self.value=value;self.sample_clock=time.monotonic()

    async def _load_art(self,thumbnail,key):
        try:
            if thumbnail:
                from winrt.windows.storage.streams import DataReader
                stream=await asyncio.wait_for(thumbnail.open_read_async(),2)
                try:
                    if 0<stream.size<=2*1024*1024:
                        reader=DataReader(stream.get_input_stream_at(0))
                        try:
                            size=await asyncio.wait_for(reader.load_async(stream.size),2)
                            raw=bytearray(size);reader.read_bytes(raw)
                            art=artwork_jpeg(raw)
                            with self.lock:
                                if key==self.art_key and not self.closed.is_set():self.art=art
                        finally:reader.close()
                finally:stream.close()
        except Exception:pass # Optional art never delays the media clock/control.

    async def _action(self,action,source_app_id):
        async with self.action_lock:
            session=self._session()
            if session is None: raise BridgeError('没有 QQ 音乐媒体会话；请先打开 QQ 音乐')
            if source_app_id and session.source_app_user_model_id!=source_app_id:
                raise BridgeError('媒体会话已改变，请刷新面板再操作')
            names={'play':'try_play_async','pause':'try_pause_async','toggle':'try_toggle_play_pause_async',
                   'previous':'try_skip_previous_async','next':'try_skip_next_async'}
            if action not in names: raise BridgeError('不支持的音乐操作')
            accepted=await asyncio.wait_for(getattr(session,names[action])(),5)
            if not accepted: raise BridgeError('QQ 音乐未接受这个操作')
            await self._refresh()
            return {'ok':True,'music':self.status()}

    def action(self,action,source_app_id=None):
        if action in ('open','window_toggle','minimize'):return self.window.action(action)
        if action not in ('play','pause','toggle','previous','next'): raise BridgeError('不支持的音乐操作')
        if not self.ready.wait(5) or not self.loop or self.loop.is_closed() or self.manager is None:
            raise BridgeError('音乐控制尚未就绪：'+self.status().get('error',''))
        future=asyncio.run_coroutine_threadsafe(self._action(action,source_app_id),self.loop)
        try: return future.result(8)
        except TimeoutError:
            future.cancel(); raise BridgeError('音乐操作未及时确认，请查看播放状态；不要连续重试切换动作')

    def status(self):
        with self.lock:
            value=copy.deepcopy(self.value)
            if value.get('playback_status')=='playing':
                value['position_seconds']=min(value.get('duration_seconds',0),value.get('position_seconds',0)+min(2,max(0,time.monotonic()-self.sample_clock))*value.get('playback_rate',1))
        value['window']=self.window.status()
        return value

    def artwork(self,key):
        with self.lock:return self.art if key==self.art_key else b''

    def close(self):
        self.closed.set(); self.thread.join(4)
