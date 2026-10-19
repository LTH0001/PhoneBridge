"""Read-only PDH wildcard counters; invalid/first samples remain None."""
import ctypes as c
from ctypes import wintypes as w
import math
import re
import time
import psutil

class ValueUnion(c.Union):_fields_=[('double',c.c_double),('large',c.c_longlong)]
class CounterValue(c.Structure):_fields_=[('status',w.DWORD),('value',ValueUnion)]
class Item(c.Structure):_fields_=[('name',w.LPWSTR),('formatted',CounterValue)]

class Counters:
    def __init__(self,paths):
        self.dll=c.WinDLL('pdh');self.query=c.c_void_p();self.handles={};self.errors={}
        definitions={'PdhOpenQueryW':([w.LPCWSTR,c.c_size_t,c.POINTER(c.c_void_p)],w.LONG),
            'PdhAddEnglishCounterW':([c.c_void_p,w.LPCWSTR,c.c_size_t,c.POINTER(c.c_void_p)],w.LONG),
            'PdhCollectQueryData':([c.c_void_p],w.LONG),'PdhCloseQuery':([c.c_void_p],w.LONG),
            'PdhGetFormattedCounterArrayW':([c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.POINTER(w.DWORD),c.c_void_p],w.LONG),
            'PdhGetFormattedCounterValue':([c.c_void_p,w.DWORD,c.c_void_p,c.POINTER(CounterValue)],w.LONG)}
        for name,(args,ret) in definitions.items():getattr(self.dll,name).argtypes=args;getattr(self.dll,name).restype=ret
        if self.dll.PdhOpenQueryW(None,0,c.byref(self.query)):raise RuntimeError('Windows 性能计数器未就绪')
        for key,path in paths.items():
            handle=c.c_void_p();code=self.dll.PdhAddEnglishCounterW(self.query,path,0,c.byref(handle))
            if code:self.errors[key]=f'性能计数器不可用 0x{code&0xffffffff:08x}'
            else:self.handles[key]=handle
        self.dll.PdhCollectQueryData(self.query)
    def sample(self):
        result={}
        if self.dll.PdhCollectQueryData(self.query):return result
        for key,handle in self.handles.items():
            size=w.DWORD();count=w.DWORD();fmt=0x200|0x8000 # DOUBLE | NOCAP100: process sums are capped only after aggregation.
            self.dll.PdhGetFormattedCounterArrayW(handle,fmt,c.byref(size),c.byref(count),None)
            if not 0<size.value<=8*1024*1024:
                single=CounterValue()
                if not self.dll.PdhGetFormattedCounterValue(handle,fmt,None,c.byref(single)) and single.status in (0,1) and math.isfinite(single.value.double) and single.value.double>=0:
                    result[key]={'_Total':single.value.double}
                continue
            buffer=c.create_string_buffer(size.value)
            if self.dll.PdhGetFormattedCounterArrayW(handle,fmt,c.byref(size),c.byref(count),buffer):continue
            if count.value>size.value//c.sizeof(Item):continue
            items=c.cast(buffer,c.POINTER(Item));values={}
            for i in range(count.value):
                item=items[i];number=item.formatted.value.double
                if item.formatted.status in (0,1) and math.isfinite(number) and number>=0:values[item.name]=number
            result[key]=values
        return result
    def close(self):
        if self.query:self.dll.PdhCloseQuery(self.query);self.query=None

def aggregate_engines(values):
    # Sum per-process contributions to one physical engine, then choose the
    # busiest engine of a type. Never add independent 3D/compute engines together.
    pattern=r'luid_0x([0-9a-f]+)_0x([0-9a-f]+)_phys_(\d+)_eng_(\d+)_engtype_(.+)'
    engines={};groups={}
    for name,value in values.items():
        match=re.search(pattern,name,re.I)
        if not match or not math.isfinite(value) or value<0:continue
        hi,lo,physical,engine,kind=match.groups();key=(int(hi,16),int(lo,16),int(physical),int(engine),kind.casefold())
        engines[key]=engines.get(key,0)+value
    for (hi,lo,physical,engine,kind),value in engines.items():
        item=groups.setdefault((hi,lo,physical),{})
        item[kind]=max(item.get(kind,0),min(100,value))
    return groups

DISK_PATHS={'read_mbps':'Disk Read Bytes/sec','write_mbps':'Disk Write Bytes/sec',
            'read_latency_ms':'Avg. Disk sec/Read','write_latency_ms':'Avg. Disk sec/Write',
            'read_iops':'Disk Reads/sec','write_iops':'Disk Writes/sec','idle_percent':'% Idle Time','queue_length':'Current Disk Queue Length'}

def build_disks(samples,volumes):
    names=set().union(*(v.keys() for k,v in samples.items() if k in DISK_PATHS)) if samples else set()
    result=[]
    for name in sorted(names):
        match=re.match(r'^(\d+)(?:\s|$)',name)
        if not match:continue # exclude _Total, never count both individual and total throughput.
        letters=re.findall(r'[A-Za-z]:',name)
        mounted=[volumes[s.upper()] for s in letters if s.upper() in volumes]
        item={'index':int(match.group(1)),'name':'磁盘 '+name,'volumes':mounted,'source':'Windows PhysicalDisk / PDH'}
        for key in DISK_PATHS:
            value=samples.get(key,{}).get(name)
            if value is not None:
                if key.endswith('_mbps'):value/=1048576
                if key.endswith('_latency_ms'):value*=1000
            item[key]=round(value,3) if value is not None else None
        item['load_percent']=round(max(0,min(100,100-item.pop('idle_percent'))),1) if item.get('idle_percent') is not None else None
        item.pop('idle_percent',None)
        for direction in ('read','write'):
            if item[direction+'_iops']==0:item[direction+'_latency_ms']=None
        busy=[(item[d+'_iops'],item[d+'_latency_ms']) for d in ('read','write') if item[d+'_iops'] is not None and item[d+'_iops']>0]
        item['response_latency_ms']=round(sum(rate*latency for rate,latency in busy)/sum(rate for rate,latency in busy),3) if busy and all(latency is not None for rate,latency in busy) else None
        item['free_gb']=round(sum(v['free_gb'] for v in mounted),1) if mounted else None
        item['total_gb']=round(sum(v['total_gb'] for v in mounted),1) if mounted else None
        result.append(item)
    return sorted(result,key=lambda disk:disk['index'])

class Performance:
    def __init__(self):
        paths={key:r'\PhysicalDisk(*)\%s'%counter for key,counter in DISK_PATHS.items()}
        paths['gpu']=r'\GPU Engine(*)\Utilization Percentage'
        paths['gpu_dedicated']=r'\GPU Adapter Memory(*)\Dedicated Usage'
        paths['gpu_shared']=r'\GPU Adapter Memory(*)\Shared Usage'
        for key,name in {'standby_core':'Standby Cache Core Bytes','standby_normal':'Standby Cache Normal Priority Bytes',
                         'standby_reserve':'Standby Cache Reserve Bytes','modified':'Modified Page List Bytes'}.items():
            paths[key]=chr(92)+'Memory'+chr(92)+name
        self.counters=Counters(paths);self.volumes={};self.volumes_updated=0
    def sample(self):
        raw=self.counters.sample()
        if time.monotonic()-self.volumes_updated>=10:
            volumes={};get_type=c.windll.kernel32.GetDriveTypeW;get_type.argtypes=[w.LPCWSTR];get_type.restype=w.UINT
            for partition in psutil.disk_partitions():
                if get_type(partition.mountpoint) not in (2,3):continue # no network probes or optical-drive spin-up.
                try:
                    usage=psutil.disk_usage(partition.mountpoint);key=partition.device[:2].upper()
                    volumes[key]={'mount':key,'free_gb':round(usage.free/1073741824,2),'total_gb':round(usage.total/1073741824,2)}
                except OSError:continue
            self.volumes=volumes;self.volumes_updated=time.monotonic()
        gpu_memory={}
        for key,label in (('gpu_dedicated','dedicated_mb'),('gpu_shared','shared_mb')):
            for name,value in raw.get(key,{}).items():
                match=re.search(r'luid_0x([0-9a-f]+)_0x([0-9a-f]+)_phys_(\d+)',name,re.I)
                if match:gpu_memory.setdefault(tuple(int(v,16) if i<2 else int(v) for i,v in enumerate(match.groups())),{})[label]=round(value/1048576,2)
        cache=[next(iter(raw.get(key,{}).values()),None) for key in ('standby_core','standby_normal','standby_reserve','modified')]
        return {'gpu':aggregate_engines(raw.get('gpu',{})),'gpu_memory':gpu_memory,
                'cached_gb':round(sum(cache)/1073741824,3) if all(v is not None for v in cache) else None,
                'disks':build_disks(raw,self.volumes),'errors':dict(self.counters.errors)}
    def close(self):self.counters.close()
