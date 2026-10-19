"""Windows output devices and touch injection; no kernel changes."""
import ctypes
import json
import subprocess
import sys
import winreg
from contextlib import contextmanager
from pathlib import Path

CATEGORY = r'CLSID\{860BB310-5D01-11D0-BD3B-00A0C911CE86}\Instance'

def camera_registered():
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, 'Software\\Classes\\' + CATEGORY) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    with winreg.OpenKey(key, winreg.EnumKey(key, i)) as entry:
                        try:
                            name = winreg.QueryValueEx(entry, 'FriendlyName')[0]
                            if name in ('PhoneBridge Camera', 'AWC Virtual Cam', 'DirectShow Softcam'):
                                return True
                        except OSError:
                            pass
        except OSError:
            pass
    return False

def register_camera(dll):
    if not Path(dll).is_file():
        raise RuntimeError('本包不含旧 DirectShow 摄像头 DLL，请使用“Windows 原生摄像头”注册入口')
    # Registry redirection is process-wide, so run in a disposable helper.
    command=([sys.executable,'--register-directshow'] if getattr(sys,'frozen',False)
             else [sys.executable,'-m','phonebridge.windows','--register'])
    p = subprocess.run(command+[str(Path(dll).resolve())],
                       capture_output=True, text=True, encoding='utf-8',
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=20)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return {'registered': camera_registered(), 'message': p.stdout.strip()}


def register_camera_system():
    from .config import ROOT
    p = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                         str(ROOT/'scripts/register-camera-system.ps1')], capture_output=True, timeout=30,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode: raise RuntimeError(p.stderr.decode('utf-8',errors='replace'))
    return {'result':p.stdout.decode('utf-8',errors='replace')}

def _register_current_user(dll):
    # Install only into the current user's COM classes, preserving system devices.
    library = ctypes.WinDLL(dll)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    advapi.RegOverridePredefKey.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi.RegOverridePredefKey.restype = ctypes.c_long
    # Keep FilterMapper's factory loaded before redirecting the HKCR root.
    ole = ctypes.OleDLL('ole32')
    class GUID(ctypes.Structure):
        _fields_ = [('data', ctypes.c_ubyte * 16)]
    def guid(value):
        import uuid
        return GUID((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))
    ole.CoInitialize(None)
    mapper = ctypes.c_void_p()
    clsid = guid('CDA42200-BD88-11D0-BD4E-00A0C911CE86')
    iid = guid('00000001-0000-0000-C000-000000000046')
    ole.CoGetClassObject(ctypes.byref(clsid), 1, None, ctypes.byref(iid), ctypes.byref(mapper))
    hkcr = ctypes.c_void_p(0xFFFFFFFF80000000 if ctypes.sizeof(ctypes.c_void_p) == 8 else 0x80000000)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r'Software\Classes', 0, winreg.KEY_ALL_ACCESS) as key:
        code = advapi.RegOverridePredefKey(hkcr, int(key))
        if code:
            raise OSError(code, 'Cannot redirect COM registration')
        try:
            library.DllRegisterServer.restype = ctypes.c_long
            hr = library.DllRegisterServer()
            if hr < 0:
                raise RuntimeError(f'Virtual camera registration failed: 0x{hr & 0xffffffff:08x}')
        finally:
            advapi.RegOverridePredefKey(hkcr, None)
    if mapper:
        table = ctypes.cast(mapper, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])(mapper)
    ole.CoUninitialize()
    # Use a recognizable name in camera pickers, without changing the class id.
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Classes\\' + CATEGORY) as key:
        for i in range(winreg.QueryInfoKey(key)[0]):
            with winreg.OpenKey(key, winreg.EnumKey(key, i), 0, winreg.KEY_ALL_ACCESS) as entry:
                name = winreg.QueryValueEx(entry, 'FriendlyName')[0]
                if name in ('AWC Virtual Cam', 'DirectShow Softcam'):
                    winreg.SetValueEx(entry, 'FriendlyName', 0, winreg.REG_SZ, 'PhoneBridge Camera')
    print('PhoneBridge Camera 已注册到当前 Windows 用户')

@contextmanager
def physical_pixels():
    """Avoid DPI-virtualized geometry when embedded in a DPI-unaware host."""
    setter=ctypes.windll.user32.SetThreadDpiAwarenessContext
    setter.argtypes=[ctypes.c_void_p]; setter.restype=ctypes.c_void_p
    previous=setter(ctypes.c_void_p(-4))
    try: yield
    finally:
        if previous: setter(ctypes.c_void_p(previous))


def monitors():
    with physical_pixels(): return _monitors()


def _monitors():
    from ctypes import wintypes
    result = []
    class MONITORINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD), ('szDevice', wintypes.WCHAR * 32)]
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.POINTER(wintypes.RECT), ctypes.c_ssize_t)
    def callback(handle, dc, rect, data):
        info = MONITORINFO(); info.cbSize = ctypes.sizeof(info)
        ctypes.windll.user32.GetMonitorInfoW(ctypes.c_void_p(handle), ctypes.byref(info))
        r = info.rcMonitor
        item={'id': len(result), 'left': r.left, 'top': r.top,
                       'width': r.right-r.left, 'height': r.bottom-r.top, 'primary': bool(info.dwFlags & 1),
                       'device':info.szDevice}
        try:
            scale=wintypes.UINT()
            if ctypes.windll.shcore.GetScaleFactorForMonitor(ctypes.c_void_p(handle),ctypes.byref(scale))==0:
                item.update(dpi=round(scale.value*96/100),scale_percent=scale.value)
        except OSError: pass
        result.append(item)
        return 1
    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback_type(callback), 0)
    return result

def extend_desktop():
    before = next((m['device'] for m in monitors() if m['primary']), None)
    code = ctypes.windll.user32.SetDisplayConfig(0,None,0,None,0x80|0x4)
    if code:
        raise OSError(code,'Windows 无法启用扩展桌面')
    after = next((m['device'] for m in monitors() if m['primary']), None)
    if before and after != before:
        raise RuntimeError('Windows 主显示器发生变化，请检查系统显示设置')
    return monitors()

def display_driver(action='status'):
    from .config import ROOT
    if action not in ('status','install','enable','disable','configure'):
        raise ValueError('无效的驱动操作')
    p = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                        str(ROOT/'scripts/display-driver.ps1'),'-Action',action],
                       capture_output=True,timeout=30,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode:
        raise RuntimeError(p.stderr.decode('utf-8',errors='replace'))
    return {'result':p.stdout.decode('utf-8',errors='replace')}

def virtual_display_device():
    from ctypes import wintypes
    class DISPLAY_DEVICE(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('DeviceName',wintypes.WCHAR*32),('DeviceString',wintypes.WCHAR*128),
                  ('StateFlags',wintypes.DWORD),('DeviceID',wintypes.WCHAR*128),('DeviceKey',wintypes.WCHAR*128)]
    result=[]
    for index in range(64):
        d=DISPLAY_DEVICE();d.cb=ctypes.sizeof(d)
        if not ctypes.windll.user32.EnumDisplayDevicesW(None,index,ctypes.byref(d),0): break
        if d.DeviceString == 'Virtual Display Driver':
            result.append(d.DeviceName)
    if len(result)!=1:
        raise RuntimeError('需要且仅能有一个 PhoneBridge/VirtualDrivers 显示后端，请先安装显示后端')
    return result[0]

def set_virtual_display(enabled, width=1920, height=1080, layout='below-left'):
    """Attach/detach only our virtual adapter. Never change the main monitor."""
    from ctypes import wintypes
    class POINTL(ctypes.Structure): _fields_=[('x',wintypes.LONG),('y',wintypes.LONG)]
    class DISPLAY_MODE(ctypes.Structure): _fields_=[('position',POINTL),('orientation',wintypes.DWORD),('fixed',wintypes.DWORD)]
    class MODE_UNION(ctypes.Union): _fields_=[('display',DISPLAY_MODE),('printer',ctypes.c_short*8)]
    class DEVMODE(ctypes.Structure):
        _fields_=[('dmDeviceName',wintypes.WCHAR*32),('dmSpecVersion',wintypes.WORD),('dmDriverVersion',wintypes.WORD),
            ('dmSize',wintypes.WORD),('dmDriverExtra',wintypes.WORD),('dmFields',wintypes.DWORD),('mode',MODE_UNION),
            ('dmColor',ctypes.c_short),('dmDuplex',ctypes.c_short),('dmYResolution',ctypes.c_short),('dmTTOption',ctypes.c_short),
            ('dmCollate',ctypes.c_short),('dmFormName',wintypes.WCHAR*32),('dmLogPixels',wintypes.WORD),
            ('dmBitsPerPel',wintypes.DWORD),('dmPelsWidth',wintypes.DWORD),('dmPelsHeight',wintypes.DWORD),
            ('dmDisplayFlags',wintypes.DWORD),('dmDisplayFrequency',wintypes.DWORD),('dmICMMethod',wintypes.DWORD),
            ('dmICMIntent',wintypes.DWORD),('dmMediaType',wintypes.DWORD),('dmDitherType',wintypes.DWORD),
            ('dmReserved1',wintypes.DWORD),('dmReserved2',wintypes.DWORD),('dmPanningWidth',wintypes.DWORD),('dmPanningHeight',wintypes.DWORD)]
    assert ctypes.sizeof(DEVMODE)==220
    device=virtual_display_device()
    active=monitors()
    current=next((m for m in active if m['device']==device),None)
    if current and current['primary']:
        raise RuntimeError('虚拟显示器当前为主屏，需要在 Windows 中先恢复物理主屏')
    if not enabled and not current: return active
    if enabled:
        from .layout import desktop_position
        main=next(m for m in active if m['primary'])
        position=desktop_position(main,int(width),int(height),layout)
        if current and (current['width'],current['height'],current['left'],current['top']) == (width,height,*position):
            return active
    mode=DEVMODE();mode.dmSize=ctypes.sizeof(mode)
    ctypes.windll.user32.EnumDisplaySettingsW(device,-2,ctypes.byref(mode))
    mode.dmFields=0x20|0x80000|0x100000
    if enabled:
        mode.dmPelsWidth=int(width);mode.dmPelsHeight=int(height)
        mode.mode.display.position.x,mode.mode.display.position.y=position
    else:
        mode.dmPelsWidth=mode.dmPelsHeight=0
        mode.mode.display.position.x=mode.mode.display.position.y=0
    code=ctypes.windll.user32.ChangeDisplaySettingsExW(device,ctypes.byref(mode),None,0,None)
    if code!=0 and enabled:
        # Some IddCx drivers cannot reattach through the legacy GDI API;
        # restore the Windows extended topology through DisplayConfig instead.
        if current:
            raise RuntimeError(f'Windows 不支持 {width}×{height}，请先点击“更新手机比例配置”：{code}')
        extend_desktop()
        code=ctypes.windll.user32.ChangeDisplaySettingsExW(device,ctypes.byref(mode),None,0,None)
        if code:
            raise RuntimeError(f'Windows 不支持 {width}×{height}，请先点击“更新手机比例配置”：{code}')
    elif code!=0:
        raise RuntimeError(f'Windows 副屏配置失败：{code}')
    import time
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        result=monitors()
        updated=next((m for m in result if m['device']==device),None)
        if not enabled and not updated: return result
        if enabled and updated and (updated['width'],updated['height'],updated['left'],updated['top']) == (width,height,*position):
            return result
        time.sleep(.1)
    raise RuntimeError('Windows 副屏拓扑没有更新')

def click(x, y, button='left'):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    flags = (0x0002, 0x0004) if button == 'left' else (0x0008, 0x0010)
    for flag in flags:
        ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)

def key(code):
    allowed = {'enter': 13, 'escape': 27, 'backspace': 8, 'space': 32,
               'left': 37, 'up': 38, 'right': 39, 'down': 40}
    value = allowed[code]
    ctypes.windll.user32.keybd_event(value, 0, 0, 0)
    ctypes.windll.user32.keybd_event(value, 0, 2, 0)

def pointer(action, x, y):
    if action not in ('down','move','up'):
        return
    if x is not None:
        ctypes.windll.user32.SetCursorPos(int(x),int(y))
    if action == 'down': ctypes.windll.user32.mouse_event(0x0002,0,0,0,0)
    if action == 'up': ctypes.windll.user32.mouse_event(0x0004,0,0,0,0)


def return_phone_cursor_to_main():
    """Keep the PC cursor visible when our virtual desktop becomes a panel."""
    from ctypes import wintypes
    with physical_pixels():
        available=monitors(); device=virtual_display_device()
        phone=next((m for m in available if m['device']==device),None)
        main=next((m for m in available if m['primary']),None)
        point=wintypes.POINT()
        if not phone or not main or not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)): return
        if phone['left']<=point.x<phone['left']+phone['width'] and phone['top']<=point.y<phone['top']+phone['height']:
            x=max(main['left']+8,min(point.x,main['left']+main['width']-8))
            y=max(main['top']+8,min(point.y,main['top']+main['height']-8))
            ctypes.windll.user32.SetCursorPos(x,y)

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        _register_current_user(sys.argv[2])
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
