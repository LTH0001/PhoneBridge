"""Read-only host sampler; elevated CPU sensor access is isolated separately."""
import copy
import ctypes as c
import os
import threading
import time
import winreg
from pathlib import Path
from .cpu_temperature import read_temperature
from .performance import Performance
from .gpu_identity import adapter_addresses,match_adapter

class Utilization(c.Structure): _fields_=[('gpu',c.c_uint),('memory',c.c_uint)]
class MemoryInfo(c.Structure): _fields_=[('total',c.c_ulonglong),('free',c.c_ulonglong),('used',c.c_ulonglong)]
class PciInfo(c.Structure):_fields_=[('legacy',c.c_char*16),('domain',c.c_uint),('bus',c.c_uint),('device',c.c_uint),('device_id',c.c_uint),('subsystem_id',c.c_uint),('bus_id',c.c_char*32)]

class Nvidia:
    def __init__(self):
        path=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/nvml.dll'
        self.dll=c.CDLL(str(path))
        self._bind('nvmlInit_v2',[])
        self._bind('nvmlShutdown',[])
        self._bind('nvmlDeviceGetCount_v2',[c.POINTER(c.c_uint)])
        self._bind('nvmlDeviceGetHandleByIndex_v2',[c.c_uint,c.POINTER(c.c_void_p)])
        self._bind('nvmlDeviceGetName',[c.c_void_p,c.c_char_p,c.c_uint])
        self._bind('nvmlDeviceGetUtilizationRates',[c.c_void_p,c.POINTER(Utilization)])
        self._bind('nvmlDeviceGetMemoryInfo',[c.c_void_p,c.POINTER(MemoryInfo)])
        self._bind('nvmlDeviceGetTemperature',[c.c_void_p,c.c_uint,c.POINTER(c.c_uint)])
        self._bind('nvmlDeviceGetPowerUsage',[c.c_void_p,c.POINTER(c.c_uint)])
        self._bind('nvmlDeviceGetClockInfo',[c.c_void_p,c.c_uint,c.POINTER(c.c_uint)])
        self.optional=set()
        for name,args in [('nvmlDeviceGetPciInfo_v3',[c.c_void_p,c.POINTER(PciInfo)]),
            ('nvmlDeviceGetEncoderUtilization',[c.c_void_p,c.POINTER(c.c_uint),c.POINTER(c.c_uint)]),
            ('nvmlDeviceGetDecoderUtilization',[c.c_void_p,c.POINTER(c.c_uint),c.POINTER(c.c_uint)])]:
            if hasattr(self.dll,name):self._bind(name,args);self.optional.add(name)
        if self.dll.nvmlInit_v2(): raise RuntimeError('NVIDIA NVML 初始化失败')
        self.closed=False
        self.adapters=[];self.adapters_updated=0

    def _bind(self,name,args):
        function=getattr(self.dll,name); function.argtypes=args; function.restype=c.c_int

    def sample(self,engine_groups=None):
        if time.monotonic()-self.adapters_updated>30:
            try:self.adapters=adapter_addresses()
            except Exception:self.adapters=[]
            self.adapters_updated=time.monotonic()
        count=c.c_uint()
        if self.dll.nvmlDeviceGetCount_v2(c.byref(count)): raise RuntimeError('显卡枚举失败')
        if count.value>16: raise RuntimeError('显卡数量超出安全范围')
        result=[]
        for index in range(count.value):
            handle=c.c_void_p()
            if self.dll.nvmlDeviceGetHandleByIndex_v2(index,c.byref(handle)): continue
            name=c.create_string_buffer(96)
            self.dll.nvmlDeviceGetName(handle,name,len(name))
            usage=Utilization(); memory=MemoryInfo(); temperature=c.c_uint(); power=c.c_uint()
            utilization_ok=self.dll.nvmlDeviceGetUtilizationRates(handle,c.byref(usage))==0
            memory_ok=self.dll.nvmlDeviceGetMemoryInfo(handle,c.byref(memory))==0
            temp_ok=self.dll.nvmlDeviceGetTemperature(handle,0,c.byref(temperature))==0
            power_ok=self.dll.nvmlDeviceGetPowerUsage(handle,c.byref(power))==0
            core_clock=c.c_uint();memory_clock=c.c_uint()
            core_clock_ok=self.dll.nvmlDeviceGetClockInfo(handle,0,c.byref(core_clock))==0
            memory_clock_ok=self.dll.nvmlDeviceGetClockInfo(handle,2,c.byref(memory_clock))==0
            pci=PciInfo();bus_id=''
            if 'nvmlDeviceGetPciInfo_v3' in self.optional and self.dll.nvmlDeviceGetPciInfo_v3(handle,c.byref(pci))==0:bus_id=pci.bus_id.decode('ascii',errors='replace')
            luid=match_adapter(bus_id,self.adapters)
            groups=[value for key,value in (engine_groups or {}).items() if key[:2]==luid]
            group=groups[0] if len(groups)==1 else {}
            engines={'three_d_percent':group.get('3d'),'copy_percent':group.get('copy'),'compute_percent':group.get('compute'),
                     'video_encode_percent':None,'video_decode_percent':None,
                     'source':'3D/复制：Windows GPU Engine；视频：NVIDIA NVML',
                     'note':'' if group else 'Windows 引擎尚未就绪或无法唯一对应物理显卡'}
            for kind,fn in [('encode','nvmlDeviceGetEncoderUtilization'),('decode','nvmlDeviceGetDecoderUtilization')]:
                value=c.c_uint();period=c.c_uint()
                if fn in self.optional and getattr(self.dll,fn)(handle,c.byref(value),c.byref(period))==0:engines['video_'+kind+'_percent']=min(100,value.value)
            result.append({'index':index,'name':name.value.decode('utf-8',errors='replace'),
                           'pci_bus_id':bus_id,'engines':engines,
                           'load_percent':usage.gpu if utilization_ok else None,
                           'temperature_c':temperature.value if temp_ok else None,
                           'memory_used_mb':round(memory.used/1048576) if memory_ok else None,
                           'memory_total_mb':round(memory.total/1048576) if memory_ok else None,
                           'core_clock_mhz':core_clock.value if core_clock_ok else None,
                           'memory_clock_mhz':memory_clock.value if memory_clock_ok else None,
                           'memory_load_percent':usage.memory if utilization_ok else None,
                           'power_w':round(power.value/1000,1) if power_ok else None})
        return result

    def close(self):
        if not self.closed: self.closed=True; self.dll.nvmlShutdown()

class HostTelemetry:
    def __init__(self):
        self.lock=threading.Lock(); self.closed=threading.Event()
        self.value={'updated_at':None,'cpu':{'name':'CPU','load_percent':None,'temperature_c':None},
                    'memory':{},'gpus':[],'error':''}
        self.history=[]
        self.thread=threading.Thread(target=self._sample,name='pb-host-telemetry',daemon=True)
        self.thread.start()

    def _sample(self):
        gpu=None; performance=None;error=''
        try:
            import psutil
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                    name=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
            except OSError: name='CPU'
            psutil.cpu_percent()
            psutil.cpu_percent(percpu=True)
            try: gpu=Nvidia()
            except Exception as exc: error=str(exc)
            try:performance=Performance()
            except Exception:pass
            while not self.closed.is_set():
                memory=psutil.virtual_memory()
                frequency=psutil.cpu_freq();swap=psutil.swap_memory()
                try:extra=performance.sample() if performance else {'gpu':{},'disks':[],'errors':{'performance':'性能计数器不可用'}}
                except Exception:extra={'gpu':{},'disks':[],'errors':{'performance':'性能采样暂不可用'}}
                try: devices=gpu.sample(extra['gpu']) if gpu else []
                except Exception as exc: devices=[]; error=str(exc)
                value={'updated_at':time.time(),'cpu':{'name':name,'load_percent':psutil.cpu_percent(),
                       'core_load_percent':psutil.cpu_percent(percpu=True),'physical_cores':psutil.cpu_count(logical=False),
                       'logical_processors':psutil.cpu_count(),'frequency_mhz':round(frequency.current) if frequency else None,
                       'process_count':len(psutil.pids()),'uptime_seconds':round(time.time()-psutil.boot_time()),
                       **read_temperature()},
                       'memory':{'load_percent':memory.percent,'used_gb':round(memory.used/1073741824,1),
                                 'total_gb':round(memory.total/1073741824,1),
                                 'available_gb':round(memory.available/1073741824,1),
                                 'cached_gb':round(memory.cached/1073741824,1) if hasattr(memory,'cached') else None,
                                 'swap_used_gb':round(swap.used/1073741824,1),'swap_total_gb':round(swap.total/1073741824,1)},'gpus':devices,'disks':extra['disks'],
                       'performance_errors':extra['errors'],'error':error}
                point={'time':value['updated_at'],'cpu':value['cpu']['load_percent'],'memory':memory.percent,
                       'gpus':[{'index':g['index'],'load_percent':g['load_percent'],'temperature_c':g['temperature_c'],'engines':g['engines']} for g in devices],
                       'disks':[{'index':d['index'],**{key:d[key] for key in ('load_percent','read_mbps','write_mbps','read_latency_ms','write_latency_ms')}} for d in extra['disks']]}
                with self.lock:
                    self.history.append(point);self.history=self.history[-60:]
                    self.value=value
                if self.closed.wait(1): break
        except Exception as exc:
            with self.lock: self.value['error']=str(exc)
        finally:
            if gpu: gpu.close()
            if performance:performance.close()

    def status(self):
        with self.lock: return copy.deepcopy(self.value)

    def detail(self,kind,index=0):
        if kind not in ('cpu','memory','gpu','disk'):raise ValueError('未知硬件详情')
        if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<16:raise ValueError('无效显卡编号')
        with self.lock:
            value=copy.deepcopy(self.value)
            history=copy.deepcopy(self.history)
        if kind in ('gpu','disk'):
            collection='gpus' if kind=='gpu' else 'disks'
            metric=next((g for g in value.get(collection,[]) if g['index']==index),None)
            if metric is None:raise ValueError('设备已不可用')
            points=[{'time':p['time'],**next((g for g in p.get(collection,[]) if g['index']==index),{'load_percent':None})} for p in history]
        else:
            metric=value[kind];points=[{'time':p['time'],'load_percent':p[kind]} for p in history]
        return {'kind':kind,'index':index,'metric':metric,'history':points,'error':value['error']}

    def close(self):
        self.closed.set(); self.thread.join(3)
