"""Explicit, short-lived phone input sessions; no clipboard, shell or elevation."""
import ctypes as c
import math
import secrets
import threading
import time

def checked_number(value,limit):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>limit:
        raise ValueError('输入超出允许范围')
    return round(value)

def validate_event(event):
    if not isinstance(event,dict):raise ValueError('无效触控事件')
    kind=event.get('kind')
    if kind=='move':return (kind,checked_number(event.get('dx',0),1000),checked_number(event.get('dy',0),1000))
    if kind=='scroll':return (kind,checked_number(event.get('dy',0),1200))
    if kind=='click' and event.get('button','left') in ('left','right'):return (kind,event.get('button','left'))
    if kind=='button' and event.get('down') in (True,False) and isinstance(event.get('down'),bool):return (kind,event['down'])
    if kind=='navigation' and event.get('action') in ('back','desktop'):return (kind,event['action'])
    if kind=='key' and isinstance(event.get('key'),str) and event['key'] in ('0','1','2','3','4','5','6','7','8','9','.','+','-','*','/','backspace','enter'):return (kind,event['key'])
    raise ValueError('不支持的触控事件')

def emit_mouse(flags,dx=0,dy=0,data=0):
    c.windll.user32.mouse_event(flags,dx,dy,data&0xffffffff,0)

def emit_shortcut(codes):
    try:
        for code in codes:c.windll.user32.keybd_event(code,0,0,0)
    finally:
        for code in reversed(codes):c.windll.user32.keybd_event(code,0,2,0)

def emit_text(text):
    raw=text.encode('utf-16-le');events=[]
    for index in range(0,len(raw),2):
        unit=int.from_bytes(raw[index:index+2],'little')
        events.extend(((0,unit,4),(0,unit,6)))
    _send_keyboard(events)

def emit_enter():
    emit_control(0x0d)

def emit_control(vk):
    # Explicit control-key down/up, never a newline embedded in dictated text.
    user=c.windll.user32
    if any(user.GetAsyncKeyState(key)&0x8000 for key in (0x10,0x11,0x12,0x5b,0x5c)):
        raise RuntimeError('电脑正按住修饰键，未发送按键；请检查当前窗口')
    try:_send_keyboard(((vk,0,0),(vk,0,2)))
    except Exception:
        # A partial SendInput must not leave the key held down. Never retry key-down.
        user.keybd_event(vk,0,2,0)
        raise

def _send_keyboard(keys):
    from ctypes import wintypes as w
    class Mouse(c.Structure):_fields_=[('x',w.LONG),('y',w.LONG),('data',w.DWORD),('flags',w.DWORD),('time',w.DWORD),('extra',c.c_size_t)]
    class Keyboard(c.Structure):_fields_=[('vk',w.WORD),('scan',w.WORD),('flags',w.DWORD),('time',w.DWORD),('extra',c.c_size_t)]
    class Union(c.Union):_fields_=[('mouse',Mouse),('keyboard',Keyboard)]
    class Input(c.Structure):_fields_=[('type',w.DWORD),('value',Union)]
    events=[]
    for vk,scan,flags in keys:
        event=Input();event.type=1;event.value.keyboard=Keyboard(vk,scan,flags,0,0);events.append(event)
    values=(Input*len(events))(*events)
    send=c.WinDLL('user32',use_last_error=True).SendInput
    send.argtypes=[w.UINT,c.POINTER(Input),c.c_int];send.restype=w.UINT
    if send(len(values),values,c.sizeof(Input))!=len(values):
        raise RuntimeError('Windows 未接受全部输入，目标可能是管理员窗口；请检查文字，不要盲目重复发送。不会自动提权。')

class RemoteInput:
    def __init__(self,bridge):
        self.bridge=bridge;self.lock=threading.RLock();self.session='';self.owner=None
        self.last=0;self.dragged=False;self.closed=threading.Event()
        threading.Thread(target=self._watch,daemon=True,name='pb-input-watch').start()

    def begin(self,confirmed=False):
        if confirmed is not True:raise ValueError('请在手机确认启用电脑键鼠输入')
        with self.lock:
            if not self.bridge.connected:raise ValueError('请先连接自己的电脑')
            self._release();self.session=secrets.token_urlsafe(24);self.owner=self.bridge.transport;self.last=time.monotonic()
            return {'session':self.session,'idle_timeout':90}

    def _check(self,session):
        if not isinstance(session,str) or not self.session or not secrets.compare_digest(session,self.session):raise ValueError('触控板尚未启用或已失效')
        if not self.bridge.connected or self.owner is not self.bridge.transport or time.monotonic()-self.last>90:
            self._release();self.session='';raise ValueError('连接已变化，请重新启用触控板')
        self.last=time.monotonic()

    def _release(self):
        if self.dragged:
            try:emit_mouse(4)
            finally:self.dragged=False

    def end(self,session):
        with self.lock:
            if self.session and session==self.session:self._release();self.session=''
        return {'ok':True}

    def events(self,session,events):
        if not isinstance(events,list) or len(events)>32:raise ValueError('触控事件过多')
        validated=[validate_event(event) for event in events]
        with self.lock:
            self._check(session)
            for event in validated:
                kind=event[0]
                if kind=='move':emit_mouse(1,event[1],event[2])
                elif kind=='scroll':emit_mouse(0x800,data=event[1])
                elif kind=='click':
                    down,up=(2,4) if event[1]=='left' else (8,16)
                    try:emit_mouse(down)
                    finally:emit_mouse(up)
                elif kind=='button':
                    if event[1]!=self.dragged:emit_mouse(2 if event[1] else 4);self.dragged=event[1]
                elif kind=='key':
                    self._release()
                    if event[1]=='enter':emit_enter()
                    elif event[1]=='backspace':emit_control(0x08)
                    else:emit_text(event[1])
                else:
                    self._release();emit_shortcut((0x12,0x25) if event[1]=='back' else (0x5b,0x44))
        return {'ok':True}

    def text(self,session,text,confirmed=False):
        if confirmed is not True or not isinstance(text,str) or not 0<len(text)<=2000:raise ValueError('请检查并确认最多 2000 字的输入内容')
        if any(ord(ch)<32 or 0xd800<=ord(ch)<=0xdfff or ord(ch)==127 for ch in text):
            raise ValueError('请使用单段文字，不包含回车、制表符或控制字符')
        with self.lock:
            self._check(session);self._release();emit_text(text)
        return {'ok':True,'characters':len(text)}

    def submit(self,session,confirmed=False):
        if confirmed is not True:raise ValueError('仅明确右滑确认时允许回车')
        with self.lock:
            self._check(session);self._release();emit_enter()
        return {'ok':True}

    def desktop(self,confirmed=False):
        if confirmed is not True:raise ValueError('请明确点击显示电脑桌面')
        with self.lock:
            if self.closed.is_set() or not self.bridge.connected:raise ValueError('手机与电脑未连接，请重新连接')
            self._release();emit_shortcut((0x5b,0x44))
        return {'ok':True}

    def previous(self,confirmed=False):
        if confirmed is not True:raise ValueError('请明确点击切换电脑上一窗口')
        with self.lock:
            if self.closed.is_set() or not self.bridge.connected:raise ValueError('手机与电脑未连接，请重新连接')
            self._release();emit_shortcut((0x12,0x09))
        return {'ok':True}

    def _watch(self):
        while not self.closed.wait(.25):
            with self.lock:
                age=time.monotonic()-self.last
                if self.session and (not self.bridge.connected or self.owner is not self.bridge.transport or age>90):
                    self._release();self.session=''
                elif self.dragged and age>2:self._release()

    def close(self):
        self.closed.set()
        with self.lock:self._release();self.session=''
