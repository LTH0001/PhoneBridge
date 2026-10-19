"""Serialize Core Audio queries/actions on one COM thread. Never controls capture."""
import copy
import math
import queue
import threading
from concurrent.futures import Future

class PlaybackController:
    def __init__(self):
        self.lock=threading.Lock();self.closed=threading.Event();self.commands=queue.Queue(maxsize=32)
        self.value={'available':False,'devices':[],'default_id':'','volume_percent':None,'muted':False,'error':''}
        self.thread=threading.Thread(target=self._run,name='pb-playback-devices',daemon=True);self.thread.start()

    def _snapshot(self):
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import EDataFlow,DEVICE_STATE
        devices=AudioUtilities.GetAllDevices(EDataFlow.eRender.value,DEVICE_STATE.ACTIVE.value)
        current=AudioUtilities.GetSpeakers()
        return {'available':True,'devices':[{'id':d.id,'name':d.FriendlyName,'default':d.id==current.id} for d in devices],
                'default_id':current.id,'default_name':current.FriendlyName,
                'volume_percent':round(current.volume_percent,1),'muted':bool(current.EndpointVolume.GetMute()),'error':''}

    def _action(self,action,device_id=None,value=None):
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import ERole
        state=self._snapshot()
        if action=='device':
            if device_id not in {d['id'] for d in state['devices']}:raise ValueError('播放设备已断开或不是有效的输出设备')
            enum=AudioUtilities.GetDeviceEnumerator()
            previous={role:enum.GetDefaultAudioEndpoint(0,role.value).GetId() for role in (ERole.eConsole,ERole.eMultimedia)}
            try: AudioUtilities.SetDefaultDevice(device_id,roles=[ERole.eConsole,ERole.eMultimedia])
            except Exception:
                for role,old in previous.items():
                    try:AudioUtilities.SetDefaultDevice(old,roles=[role])
                    except Exception:pass
                raise
        elif action in ('volume','delta','mute'):
            if device_id and device_id!=state['default_id']:raise ValueError('当前播放设备已改变，请刷新后重试')
            current=AudioUtilities.GetSpeakers()
            if action=='mute':
                if type(value) is not bool:raise ValueError('静音参数必须为布尔值')
                current.EndpointVolume.SetMute(int(value),None)
            else:
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('无效音量')
                if action=='delta':
                    if not -15<=value<=15:raise ValueError('单次音量调整不能超过 15%')
                    volume=max(0,min(100,current.volume_percent+value))
                else:
                    if not 0<=value<=100:raise ValueError('音量范围是 0–100%')
                    volume=value
                current.volume_percent=volume
        else:raise ValueError('未知播放设备操作')
        result=self._snapshot()
        with self.lock:self.value=result
        return {'ok':True,'playback':copy.deepcopy(result)}

    def _run(self):
        import comtypes
        comtypes.CoInitialize()
        try:
            while not self.closed.is_set():
                try:
                    state=self._snapshot()
                    with self.lock:self.value=state
                except Exception as error:
                    with self.lock:self.value.update(available=False,error=str(error))
                try:command,future=self.commands.get(timeout=1)
                except queue.Empty:continue
                if not future.set_running_or_notify_cancel():continue
                try:future.set_result(self._action(**command))
                except Exception as error:future.set_exception(error)
        finally:comtypes.CoUninitialize()

    def action(self,action,device_id=None,value=None):
        if action not in ('device','volume','delta','mute'):raise ValueError('未知播放设备操作')
        if self.closed.is_set():raise ValueError('播放设备控制已关闭')
        future=Future()
        try:self.commands.put_nowait(({'action':action,'device_id':device_id,'value':value},future))
        except queue.Full:raise ValueError('播放操作过多，请稍后再试')
        try:return future.result(timeout=8)
        except TimeoutError:future.cancel();raise ValueError('播放设备操作未确认，请刷新状态；不会自动重试')

    def status(self):
        with self.lock:return copy.deepcopy(self.value)

    def close(self):self.closed.set();self.thread.join(3)
