"""Product window control: only the configured QQMusic.exe, never WM_CLOSE."""
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import subprocess
import threading
import time
import psutil

class Placement(c.Structure):
    _fields_=[('length',w.UINT),('flags',w.UINT),('showCmd',w.UINT),('min',w.POINT),('max',w.POINT),('normal',w.RECT)]

class MusicWindow:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.Lock();self.cached={};self.updated=0
        self.user=c.WinDLL('user32',use_last_error=True)
        self.callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
        signatures={'EnumWindows':([self.callback,w.LPARAM],w.BOOL),
            'GetWindowThreadProcessId':([w.HWND,c.POINTER(w.DWORD)],w.DWORD),
            'GetWindow':([w.HWND,w.UINT],w.HWND),'GetWindowPlacement':([w.HWND,c.POINTER(Placement)],w.BOOL),
            'IsWindowVisible':([w.HWND],w.BOOL),'IsIconic':([w.HWND],w.BOOL),
            'ShowWindowAsync':([w.HWND,c.c_int],w.BOOL),'SetForegroundWindow':([w.HWND],w.BOOL),
            'GetWindowTextW':([w.HWND,w.LPWSTR,c.c_int],c.c_int)}
        signatures['GetClassNameW']=([w.HWND,w.LPWSTR,c.c_int],c.c_int)
        for name,(args,result) in signatures.items():
            fn=getattr(self.user,name);fn.argtypes=args;fn.restype=result
    def _windows(self):
        pids=set()
        for process in psutil.process_iter(['name']):
            if (process.info.get('name') or '').casefold()!='qqmusic.exe':continue
            try:
                if Path(process.exe()).resolve()==self.path.resolve():pids.add(process.pid)
            except (OSError,ValueError,psutil.Error):continue
        result=[]
        def visit(hwnd,_):
            pid=w.DWORD();self.user.GetWindowThreadProcessId(hwnd,c.byref(pid))
            if pid.value not in pids or self.user.GetWindow(hwnd,4):return True
            placement=Placement();placement.length=c.sizeof(placement)
            if not self.user.GetWindowPlacement(hwnd,c.byref(placement)):return True
            r=placement.normal;width=r.right-r.left;height=r.bottom-r.top
            title=c.create_unicode_buffer(512);self.user.GetWindowTextW(hwnd,title,512)
            cls=c.create_unicode_buffer(256);self.user.GetClassNameW(hwnd,cls,256)
            if width>=320 and height>=180 and title.value and title.value!='TipWindow':
                result.append({'handle':int(hwnd),'pid':pid.value,'area':width*height,
                               'class':cls.value,'title':title.value,
                               'visible':bool(self.user.IsWindowVisible(hwnd)),'minimized':bool(self.user.IsIconic(hwnd))})
            return True
        self.user.EnumWindows(self.callback(visit),0)
        return sorted(result,key=lambda item:item['area'],reverse=True)
    def _state(self):
        items=self._windows();window=items[0] if items else None
        return {'available':bool(window),'visible':bool(window and window['visible'] and not window['minimized']),
                'minimized':bool(window and window['minimized'])}
    def status(self):
        with self.lock:
            if time.monotonic()-self.updated>1:
                try:self.cached=self._state()
                except Exception:self.cached={'available':False,'visible':False,'error':'窗口状态暂不可用'}
                self.updated=time.monotonic()
            return dict(self.cached)
    def action(self,action):
        if action not in ('open','window_toggle','minimize'):raise ValueError('未知窗口操作')
        with self.lock:
            items=self._windows();window=items[0] if items else None
            minimize=action=='minimize' or (action=='window_toggle' and window and window['visible'] and not window['minimized'])
            if minimize:
                if window:self.user.ShowWindowAsync(window['handle'],6)
                outcome='minimized'
            elif window:
                self.user.ShowWindowAsync(window['handle'],9 if window['minimized'] else 5)
                self.user.SetForegroundWindow(window['handle']) # Windows may deny foreground stealing.
                outcome='shown'
            else:
                if not self.path.is_file() or self.path.name.casefold()!='qqmusic.exe':raise ValueError('QQ 音乐程序路径未配置或不存在')
                subprocess.Popen([str(self.path)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));outcome='launched'
            self.updated=0
            return {'ok':True,'window_action':outcome}
