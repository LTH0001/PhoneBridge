"""Per-source Windows scaling; only PhoneBridge's non-primary display is writable.

ABI reference: lihas/windows-DPI-scaling-sample (Unlicense), DpiHelper.
The -3/-4 DisplayConfig operations are undocumented; validate every response and
fail closed on unsupported Windows versions. Never use global custom scaling.
"""
import ctypes as c
from ctypes import wintypes as w
from . import windows

SCALES=(100,125,150,175,200,225,250,300,350,400,450,500)
class LUID(c.Structure): _fields_=[('low',w.DWORD),('high',w.LONG)]
class Rational(c.Structure): _fields_=[('numerator',w.UINT),('denominator',w.UINT)]
class Source(c.Structure): _fields_=[('adapter',LUID),('id',w.UINT),('mode',w.UINT),('flags',w.UINT)]
class Target(c.Structure):
    _fields_=[('adapter',LUID),('id',w.UINT),('mode',w.UINT),('output',w.UINT),('rotation',w.UINT),
              ('scaling',w.UINT),('refresh',Rational),('scanline',w.UINT),('available',w.BOOL),('flags',w.UINT)]
class DisplayPath(c.Structure): _fields_=[('source',Source),('target',Target),('flags',w.UINT)]
class Mode(c.Structure): _fields_=[('type',w.UINT),('id',w.UINT),('adapter',LUID),('data',c.c_uint64*6)]
class Header(c.Structure): _fields_=[('type',w.UINT),('size',w.UINT),('adapter',LUID),('id',w.UINT)]
class SourceName(c.Structure): _fields_=[('header',Header),('name',w.WCHAR*32)]
class ScaleGet(c.Structure): _fields_=[('header',Header),('minimum',w.INT),('current',w.INT),('maximum',w.INT)]
class ScaleSet(c.Structure): _fields_=[('header',Header),('relative',w.INT)]

def sources():
    assert (c.sizeof(DisplayPath),c.sizeof(Mode),c.sizeof(Header),c.sizeof(ScaleGet),c.sizeof(ScaleSet))==(72,64,20,32,24)
    api=c.windll.user32
    for _ in range(3):
        count,modes=w.UINT(),w.UINT()
        code=api.GetDisplayConfigBufferSizes(2,c.byref(count),c.byref(modes))
        if code: raise OSError(code,'无法查询显示缩放')
        if count.value>64 or modes.value>256: raise RuntimeError('显示配置超出安全范围')
        paths=(DisplayPath*count.value)(); mode_data=(Mode*modes.value)()
        code=api.QueryDisplayConfig(2,c.byref(count),paths,c.byref(modes),mode_data,None)
        if code==122: continue
        if code: raise OSError(code,'无法读取显示配置')
        result={}
        for path in paths[:count.value]:
            name=SourceName(); name.header=Header(1,c.sizeof(name),path.source.adapter,path.source.id)
            if api.DisplayConfigGetDeviceInfo(c.byref(name))==0:
                result[name.name]=(path.source.adapter,path.source.id)
        return result
    raise RuntimeError('显示配置正在变化，请稍后重试')

def scaling(device):
    adapter,source_id=sources()[device]
    packet=ScaleGet(); packet.header=Header(0xfffffffd,c.sizeof(packet),adapter,source_id)
    code=c.windll.user32.DisplayConfigGetDeviceInfo(c.byref(packet))
    if code: raise OSError(code,'Windows 不支持此显示器的独立 DPI 缩放')
    base=-packet.minimum
    if not 0<=base<len(SCALES) or not 0<=base+packet.maximum<len(SCALES) or not 0<=base+packet.current<len(SCALES):
        raise RuntimeError('Windows 返回了未知的 DPI 范围')
    return {'current':SCALES[base+packet.current],'recommended':SCALES[base],
            'maximum':SCALES[base+packet.maximum],'minimum':100}

def set_phone_scaling(percent):
    device=windows.virtual_display_device()
    monitor=next((m for m in windows.monitors() if m['device']==device),None)
    if not monitor or monitor['primary']: raise RuntimeError('只能调整已启用的非主屏 PhoneBridge 副屏')
    before_main=next(m for m in windows.monitors() if m['primary'])
    info=scaling(device)
    percent=int(percent)
    if percent not in SCALES or not info['minimum']<=percent<=info['maximum']:
        raise ValueError(f'Windows 此模式最多支持 {info["maximum"]}% 缩放，无法设置 {percent}%')
    adapter,source_id=sources()[device]
    packet=ScaleSet(); packet.header=Header(0xfffffffc,c.sizeof(packet),adapter,source_id)
    packet.relative=SCALES.index(percent)-SCALES.index(info['recommended'])
    code=c.windll.user32.DisplayConfigSetDeviceInfo(c.byref(packet))
    if code: raise OSError(code,'无法应用副屏 DPI 缩放')
    result=scaling(device)
    if result['current']!=percent: raise RuntimeError('副屏 DPI 缩放未生效')
    if next(m for m in windows.monitors() if m['primary'])!=before_main:
        raise RuntimeError('主屏配置意外发生变化，请检查 Windows 显示设置')
    return result
