"""Read-only DXGI LUID -> PCI address mapping; no GPU index/order guessing."""
import ctypes as c
from ctypes import wintypes as w
import uuid

class Luid(c.Structure):_fields_=[('low',w.DWORD),('high',w.LONG)]
class Desc(c.Structure):
    _fields_=[('name',w.WCHAR*128),('vendor',w.UINT),('device',w.UINT),('subsystem',w.UINT),('revision',w.UINT),
              ('video_memory',c.c_size_t),('system_memory',c.c_size_t),('shared_memory',c.c_size_t),('luid',Luid),('flags',w.UINT)]
class OpenAdapter(c.Structure):_fields_=[('luid',Luid),('handle',w.UINT)]
class Query(c.Structure):_fields_=[('handle',w.UINT),('type',c.c_int),('data',c.c_void_p),('size',w.UINT)]
class Address(c.Structure):_fields_=[('bus',w.UINT),('device',w.UINT),('function',w.UINT)]
class CloseAdapter(c.Structure):_fields_=[('handle',w.UINT)]

def physical_pci(address):
    """Reject the sentinel address used by indirect/virtual DXGI views."""
    return 0<=address[0]<=255 and 0<=address[1]<=31 and 0<=address[2]<=7

def method(obj,index,ret,args):
    table=c.cast(obj,c.POINTER(c.POINTER(c.c_void_p))).contents
    return c.WINFUNCTYPE(ret,c.c_void_p,*args)(table[index])
def adapter_addresses():
    dxgi=c.WinDLL('dxgi');gdi=c.WinDLL('gdi32');factory=c.c_void_p()
    dxgi.CreateDXGIFactory1.argtypes=[c.c_void_p,c.POINTER(c.c_void_p)];dxgi.CreateDXGIFactory1.restype=w.LONG
    iid=(c.c_ubyte*16).from_buffer_copy(uuid.UUID('770aae78-f26f-4dba-a829-253c83d1b387').bytes_le)
    if dxgi.CreateDXGIFactory1(c.byref(iid),c.byref(factory))<0:raise RuntimeError('DXGI 枚举不可用')
    for name,structure in [('D3DKMTOpenAdapterFromLuid',OpenAdapter),('D3DKMTQueryAdapterInfo',Query),('D3DKMTCloseAdapter',CloseAdapter)]:
        fn=getattr(gdi,name);fn.argtypes=[c.POINTER(structure)];fn.restype=w.LONG
    result=[]
    try:
        for i in range(32):
            adapter=c.c_void_p()
            if method(factory,12,w.LONG,[w.UINT,c.POINTER(c.c_void_p)])(factory,i,c.byref(adapter))<0:break
            try:
                desc=Desc()
                if method(adapter,10,w.LONG,[c.POINTER(Desc)])(adapter,c.byref(desc))<0:continue
                opened=OpenAdapter(desc.luid,0)
                if gdi.D3DKMTOpenAdapterFromLuid(c.byref(opened))<0:continue
                try:
                    address=Address();query=Query(opened.handle,6,c.cast(c.byref(address),c.c_void_p),c.sizeof(address))
                    if gdi.D3DKMTQueryAdapterInfo(c.byref(query))>=0:
                        if desc.flags&2 or not physical_pci((address.bus,address.device,address.function)):continue
                        result.append({'name':desc.name,'vendor':desc.vendor,'pci':(address.bus,address.device,address.function),
                                       'dedicated_total_mb':round(desc.video_memory/1048576),
                                       'shared_total_mb':round(desc.shared_memory/1048576),
                                       'luid':(desc.luid.high&0xffffffff,desc.luid.low)})
                finally:gdi.D3DKMTCloseAdapter(c.byref(CloseAdapter(opened.handle)))
            finally:method(adapter,2,w.ULONG,[])(adapter)
    finally:method(factory,2,w.ULONG,[])(factory)
    return result

def match_adapter(bus_id,adapters):
    import re
    match=re.fullmatch(r'([0-9a-f]+):([0-9a-f]+):([0-9a-f]+)\.([0-9a-f]+)',bus_id,re.I)
    if not match or int(match.group(1),16)!=0:return None # DXGI address has no PCI segment; do not guess nonzero domains.
    address=tuple(int(s,16) for s in match.groups()[1:])
    candidates=[a for a in adapters if a['vendor']==0x10de and a['pci']==address]
    return candidates[0]['luid'] if len(candidates)==1 else None
