"""Bounded, read-only host inventory and task-manager baseline field coverage.

No driver installation, kernel memory access, shell input from the API, or
process mutation. Missing provider values remain None, never invented zeros.
"""
import copy
import ctypes as c
from ctypes import wintypes as w
import json
import math
import os
import socket
import subprocess
import tempfile
import threading
import time
import psutil
import xml.etree.ElementTree as ET

GIB=1073741824


class CacheDescriptor(c.Structure):
    _fields_=[('level',c.c_ubyte),('associativity',c.c_ubyte),('line_size',w.WORD),('size',w.DWORD),('kind',w.DWORD)]
class ProcessorUnion(c.Union):
    _fields_=[('cache',CacheDescriptor),('reserved',c.c_ulonglong*2)]
class LogicalProcessor(c.Structure):
    _fields_=[('mask',c.c_size_t),('relationship',w.DWORD),('info',ProcessorUnion)]


def cpu_topology():
    # Legacy API is group-limited; refuse partial totals on >64 logical CPUs.
    if (psutil.cpu_count() or 0)>64:return {}
    kernel=c.WinDLL('kernel32');function=kernel.GetLogicalProcessorInformation
    function.argtypes=[c.c_void_p,c.POINTER(w.DWORD)];function.restype=w.BOOL
    length=w.DWORD();function(None,c.byref(length))
    if not 0<length.value<=1024*1024:return {}
    data=c.create_string_buffer(length.value)
    if not function(data,c.byref(length)) or length.value%c.sizeof(LogicalProcessor):return {}
    records=c.cast(data,c.POINTER(LogicalProcessor));result={'sockets':0};caches={1:0,2:0,3:0}
    for i in range(length.value//c.sizeof(LogicalProcessor)):
        record=records[i]
        if record.relationship==3:result['sockets']+=1
        if record.relationship==2 and record.info.cache.level in caches:caches[record.info.cache.level]+=record.info.cache.size
    for level,size in caches.items():result[f'l{level}_cache_mb']=round(size/1048576,3) if size else None
    return result


class PerformanceInfo(c.Structure):
    _fields_=[('cb',w.DWORD)]+[(n,c.c_size_t) for n in (
        'CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable',
        'SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[
        ('HandleCount',w.DWORD),('ProcessCount',w.DWORD),('ThreadCount',w.DWORD)]


def kernel_snapshot():
    info=PerformanceInfo();info.cb=c.sizeof(info)
    function=c.WinDLL('psapi').GetPerformanceInfo
    function.argtypes=[c.POINTER(PerformanceInfo),w.DWORD];function.restype=w.BOOL
    if not function(c.byref(info),info.cb):return {}
    result={key:round(getattr(info,field)*info.PageSize/GIB,3) for key,field in {
        'commit_used_gb':'CommitTotal','commit_limit_gb':'CommitLimit','commit_peak_gb':'CommitPeak',
        'physical_total_gb':'PhysicalTotal','physical_available_gb':'PhysicalAvailable',
        'system_cache_gb':'SystemCache','paged_pool_gb':'KernelPaged','nonpaged_pool_gb':'KernelNonpaged'}.items()}
    result.update(process_count=int(info.ProcessCount),thread_count=int(info.ThreadCount),handle_count=int(info.HandleCount))
    return result


INVENTORY_SCRIPT=r'''
[Console]::OutputEncoding=[Text.UTF8Encoding]::new();$ErrorActionPreference='Stop';
function Q($class,$props){try{@(Get-CimInstance -ClassName $class | Select-Object -Property $props)}catch{@()}}
$processors=@(Q 'Win32_Processor' @('Name','SocketDesignation','MaxClockSpeed','NumberOfCores','NumberOfLogicalProcessors','VirtualizationFirmwareEnabled','VMMonitorModeExtensions','L2CacheSize','L3CacheSize'));
$computer=@(Q 'Win32_ComputerSystem' @('HypervisorPresent'));
$memory=@(Q 'Win32_PhysicalMemory' @('Capacity','ConfiguredClockSpeed','SMBIOSMemoryType','FormFactor','DeviceLocator','Manufacturer','PartNumber'));
$arrays=@(Q 'Win32_PhysicalMemoryArray' @('MemoryDevices','MaxCapacityEx'));
$cache=@(Q 'Win32_CacheMemory' @('Level','InstalledSize','Purpose'));
$disks=@(Q 'Win32_DiskDrive' @('Index','Model','Size','FirmwareRevision','InterfaceType','MediaType'));
$storage=@();try{$storage=@(Get-Disk | ForEach-Object {@{Number=$_.Number;BusType=[string]$_.BusType;PartitionStyle=[string]$_.PartitionStyle;IsBoot=$_.IsBoot;IsSystem=$_.IsSystem;HealthStatus=[string]$_.HealthStatus}})}catch{};
$network=@();try{$network=@(Get-NetAdapter -IncludeHidden | ForEach-Object {@{Name=$_.Name;Description=$_.InterfaceDescription;Type=[string]$_.PhysicalMediaType;DriverVersion=$_.DriverVersion}})}catch{};
$pages=@(Q 'Win32_PageFileUsage' @('Name','AllocatedBaseSize','CurrentUsage','PeakUsage'));
$video=@();foreach($v in @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue)){
  $bus=$null;$address=$null;
  try{$bus=(Get-PnpDeviceProperty -InstanceId $v.PNPDeviceID -KeyName DEVPKEY_Device_BusNumber -ErrorAction Stop).Data;
      $address=(Get-PnpDeviceProperty -InstanceId $v.PNPDeviceID -KeyName DEVPKEY_Device_Address -ErrorAction Stop).Data}catch{}
  $video+=@{Name=$v.Name;DriverVersion=$v.DriverVersion;DriverDate=if($v.DriverDate){$v.DriverDate.ToString('yyyy-MM-dd')}else{$null};Bus=$bus;Address=$address;VideoProcessor=$v.VideoProcessor}
};
$npu=@();try{$npu=@(Get-CimInstance Win32_PnPEntity -Filter "Name LIKE '%AI Boost%' OR Name LIKE '% NPU%' OR Name LIKE 'NPU%' OR Name LIKE '%Neural%' OR Name LIKE '% IPU%'" | Select-Object Name,Manufacturer,Status)}catch{};
@{processors=$processors;computer=$computer;memory=$memory;arrays=$arrays;cache=$cache;disks=$disks;storage=$storage;pages=$pages;video=$video;npu=$npu;network=$network}|ConvertTo-Json -Depth 6 -Compress
'''


def inventory():
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',INVENTORY_SCRIPT],
        capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode or len(result.stdout)>1024*1024:raise RuntimeError('硬件档案采集失败')
    value=json.loads(result.stdout.decode('utf-8-sig'))
    if not isinstance(value,dict):raise ValueError('无效硬件档案')
    return value


def positive(value):
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>0 else None


def sum_known(values):
    values=list(values)
    return sum(values) if values and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in values) else None


def parse_dxdiag(text):
    root=ET.fromstring(text)
    return {'directx_version':root.findtext('SystemInformation/DirectXVersion'),
            'gpus':[{'name':d.findtext('CardName'),'driver_model':d.findtext('DriverModel'),
                     'ddi_version':d.findtext('DDIVersion'),'feature_levels':d.findtext('FeatureLevels')}
                    for d in root.findall('DisplayDevices/DisplayDevice')][:32]}


def dxdiag():
    from pathlib import Path
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/dxdiag.exe'
    with tempfile.TemporaryDirectory(prefix='PhoneBridge-dxdiag-') as directory:
        target=Path(directory)/'report.xml'
        subprocess.run([str(executable),'/dontskip','/whql:off','/x',str(target)],timeout=50,
                       capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
        if not target.is_file() or target.stat().st_size>10*1024*1024:raise ValueError('DXDiag report unavailable')
        return parse_dxdiag(target.read_bytes())


def network_sample(previous,now,counts,addresses,stats):
    result=[];next_previous={}
    for index,name in enumerate(sorted(counts)[:16]):
        value=counts[name];old=previous.get(name);next_previous[name]=(now,value.bytes_sent,value.bytes_recv)
        def rate(current,position):
            if not old or now<=old[0] or current<old[position]:return None
            return round((current-old[position])*8/(now-old[0])/1000000,4)
        state=stats.get(name);items=addresses.get(name,[])
        result.append({'index':index,'name':name,'send_mbps':rate(value.bytes_sent,1),'receive_mbps':rate(value.bytes_recv,2),
            'sent_gb':round(value.bytes_sent/GIB,3),'received_gb':round(value.bytes_recv/GIB,3),
            'packets_sent':value.packets_sent,'packets_received':value.packets_recv,
            'errors_in':value.errin,'errors_out':value.errout,'drops_in':value.dropin,'drops_out':value.dropout,
            'is_up':state.isup if state else None,'link_mbps':positive(state.speed) if state else None,'mtu':state.mtu if state else None,
            'ipv4':[a.address for a in items if a.family==socket.AF_INET],
            'ipv6':[a.address for a in items if a.family==socket.AF_INET6],
            'mac':[a.address for a in items if a.family==psutil.AF_LINK]})
    return result,next_previous


class HardwareDetails:
    def __init__(self):
        self.lock=threading.Lock();self.closed=threading.Event();self.value={};self.error='硬件档案正在读取';self.previous={}
        try:self.native_cpu=cpu_topology()
        except (OSError,AttributeError):self.native_cpu={}
        self.thread=threading.Thread(target=self._run,name='pb-hardware-inventory',daemon=True);self.thread.start()
    def _run(self):
        while not self.closed.is_set():
            try:
                value=inventory()
                from .gpu_identity import adapter_addresses
                try:value['adapters']=adapter_addresses()
                except Exception:value['adapters']=[]
                with self.lock:self.value=value;self.error=''
                if not self.closed.is_set():
                    try:
                        value['dxdiag']=dxdiag()
                        with self.lock:self.value=copy.deepcopy(value)
                    except (OSError,ValueError,subprocess.SubprocessError):pass
            except Exception as error:
                with self.lock:self.error=str(error)[:180]
            self.closed.wait(300)
    def enrich(self,value,extra):
        with self.lock:static=copy.deepcopy(self.value);error=self.error
        cpu=value['cpu'];memory=value['memory'];processors=static.get('processors',[])
        cpu['sockets']=len(processors) if processors else None
        cpu['base_frequency_mhz']=positive(processors[0].get('MaxClockSpeed')) if processors else None
        cpu['virtualization_enabled']=processors[0].get('VirtualizationFirmwareEnabled') if processors else None
        cpu['virtualization_firmware_reported']=cpu['virtualization_enabled']
        cpu['hypervisor_present']=static.get('computer',[{}])[0].get('HypervisorPresent') if static.get('computer') else None
        if cpu['hypervisor_present'] is True:cpu['virtualization_enabled']=True
        for level,name in ((3,'l1_cache_mb'),(4,'l2_cache_mb'),(5,'l3_cache_mb')):
            total=sum_known(positive(x.get('InstalledSize')) for x in static.get('cache',[]) if x.get('Level')==level)
            cpu[name]=round(total/1024,3) if total is not None else None
        # SMBIOS can expose the same shared L3 cache more than once. Prefer
        # the OS cache topology; never sum ambiguous duplicate WMI records.
        for key,name in (('L2CacheSize','l2_cache_mb'),('L3CacheSize','l3_cache_mb')):
            size=sum_known(positive(p.get(key)) for p in processors)
            cpu[name]=round(size/1024,3) if size is not None else None
        cpu.update(self.native_cpu)
        cpu['inventory_note']=error
        try:
            kernel=kernel_snapshot();cpu.update({k:kernel[k] for k in ('process_count','thread_count','handle_count') if k in kernel})
            memory.update({k:v for k,v in kernel.items() if k not in ('process_count','thread_count','handle_count')})
        except (OSError,AttributeError):pass
        modules=static.get('memory',[]);installed=sum_known(positive(m.get('Capacity')) for m in modules)
        memory['modules']=[{k:m.get(k) for k in ('Capacity','ConfiguredClockSpeed','SMBIOSMemoryType','FormFactor','DeviceLocator','Manufacturer','PartNumber')} for m in modules]
        memory['installed_gb']=round(installed/GIB,3) if installed else None
        memory['hardware_reserved_gb']=round(max(0,installed/GIB-memory.get('physical_total_gb',memory['total_gb'])),3) if installed else None
        memory['slots_used']=len(modules) if modules else None
        memory['slots_total']=sum_known(positive(a.get('MemoryDevices')) for a in static.get('arrays',[]))
        memory['speed_mhz']=min((positive(m.get('ConfiguredClockSpeed')) for m in modules),default=None) if modules and all(positive(m.get('ConfiguredClockSpeed')) for m in modules) else None
        factors={8:'DIMM',12:'SO-DIMM',0:'未知'}
        memory['form_factor']=' / '.join(sorted({factors.get(m.get('FormFactor'),'规格代码 '+str(m.get('FormFactor'))) for m in modules})) if modules else None
        memory['inventory_note']=error
        value['gpus']=merge_gpus(value['gpus'],static.get('adapters',[]),static.get('video',[]),extra.get('gpu',{}),extra.get('gpu_memory',{}))
        for gpu in value['gpus']:
            gpu['directx_version']=static.get('dxdiag',{}).get('directx_version')
            candidates=[d for d in static.get('dxdiag',{}).get('gpus',[]) if (d.get('name') or '').casefold()==gpu['name'].casefold()]
            # Only attach identical, static capability metadata; never match
            # live counters by model name or assume Task Manager index order.
            for key in ('driver_model','ddi_version','feature_levels'):
                values={d.get(key) for d in candidates}
                gpu[key]=next(iter(values)) if len(values)==1 else None
        for disk in value.get('disks',[]):
            info=next((d for d in static.get('disks',[]) if d.get('Index')==disk['index']),{})
            storage=next((d for d in static.get('storage',[]) if d.get('Number')==disk['index']),{})
            disk.update(model=info.get('Model'),firmware=info.get('FirmwareRevision'),physical_size_gb=round(int(info['Size'])/GIB,3) if info.get('Size') else None,
                bus_type=str(storage['BusType']) if storage.get('BusType') is not None else info.get('InterfaceType'),
                partition_style=str(storage['PartitionStyle']) if storage.get('PartitionStyle') is not None else None,
                system_disk=storage.get('IsSystem'),boot_disk=storage.get('IsBoot'),health=str(storage['HealthStatus']) if storage.get('HealthStatus') is not None else None,
                page_file=any(str(p.get('Name',''))[:2].upper() in [v['mount'].upper() for v in disk.get('volumes',[])] for p in static.get('pages',[])) if 'pages' in static else None)
        try:value['networks'],self.previous=network_sample(self.previous,time.monotonic(),psutil.net_io_counters(pernic=True),psutil.net_if_addrs(),psutil.net_if_stats())
        except (OSError,psutil.Error):value['networks']=[]
        for network in value['networks']:
            adapter=next((n for n in static.get('network',[]) if n.get('Name')==network['name']),{})
            network.update(connection_type=adapter.get('Type'),description=adapter.get('Description'),driver_version=adapter.get('DriverVersion'))
        value['npus']=[{'index':i,'name':n.get('Name'),'manufacturer':n.get('Manufacturer'),'status':n.get('Status'),'load_percent':None,
            'note':'已识别 NPU；此驱动尚未提供可验证的利用率、显存与引擎计数器，不以 GPU/CPU 占用替代。'} for i,n in enumerate(static.get('npu',[])[:16])]
        return value
    def close(self):self.closed.set();self.thread.join(1)


def merge_gpus(nvidia,adapters,drivers,engines,memory):
    from .gpu_identity import match_adapter
    result=copy.deepcopy(nvidia);used=set()
    for gpu in result:
        luid=match_adapter(gpu.get('pci_bus_id',''),adapters)
        if luid is not None:used.add(luid);gpu['_luid']=luid
    for adapter in adapters:
        luid=tuple(adapter['luid'])
        if luid in used:continue
        index=next((i for i in range(16) if all(g['index']!=i for g in result)),None)
        if index is None:break
        matches=[g for key,g in engines.items() if key[:2]==luid];group=matches[0] if len(matches)==1 else {}
        result.append({'index':index,'name':adapter['name'],'_luid':luid,'load_percent':max(group.values()) if group else None,
            'temperature_c':None,'memory_used_mb':None,'memory_total_mb':adapter.get('dedicated_total_mb'),
            'memory_load_percent':None,'power_w':None,'core_clock_mhz':None,'memory_clock_mhz':None,
            'engines':{'three_d_percent':group.get('3d'),'copy_percent':group.get('copy'),'compute_percent':group.get('compute'),
                'video_encode_percent':group.get('videoencode'),'video_decode_percent':group.get('videodecode'),
                'source':'Windows GPU Engine / DXGI','note':'利用率为最忙引擎，不将独立引擎相加。'}})
    for gpu in result:
        luid=gpu.pop('_luid',None)
        adapter=next((a for a in adapters if tuple(a['luid'])==luid),{})
        groups=[m for key,m in memory.items() if key[:2]==luid]
        mem=groups[0] if len(groups)==1 else {}
        gpu['dedicated_used_mb']=mem.get('dedicated_mb');gpu['shared_used_mb']=mem.get('shared_mb')
        gpu['dedicated_total_mb']=adapter.get('dedicated_total_mb');gpu['shared_total_mb']=adapter.get('shared_total_mb')
        pci=adapter.get('pci');candidates=[d for d in drivers if pci is not None and d.get('Bus')==pci[0] and d.get('Address') is not None and ((int(d['Address'])>>16)&0xffff,int(d['Address'])&0xffff)==tuple(pci[1:])]
        driver=candidates[0] if len(candidates)==1 else {}
        gpu['driver_version']=driver.get('DriverVersion');gpu['driver_date']=driver.get('DriverDate')
        gpu['pci_location']='bus %d / device %d / function %d'%tuple(pci) if pci is not None else gpu.get('pci_bus_id')
    return result


BASELINE={
    'cpu':('load_percent','frequency_mhz','base_frequency_mhz','sockets','physical_cores','logical_processors','virtualization_enabled','l1_cache_mb','l2_cache_mb','l3_cache_mb','process_count','thread_count','handle_count','uptime_seconds'),
    'memory':('used_gb','available_gb','compressed_gb','commit_used_gb','commit_limit_gb','cached_gb','paged_pool_gb','nonpaged_pool_gb','speed_mhz','slots_used','slots_total','form_factor','hardware_reserved_gb'),
    'gpu':('load_percent','dedicated_used_mb','dedicated_total_mb','shared_used_mb','shared_total_mb','driver_version','driver_date','directx_version','pci_location','temperature_c'),
    'disk':('load_percent','response_latency_ms','read_mbps','write_mbps','physical_size_gb','total_gb','system_disk','page_file','bus_type'),
    'network':('send_mbps','receive_mbps','name','link_mbps','ipv4','ipv6','connection_type'),
    'npu':('load_percent','dedicated_used_mb','shared_used_mb','driver_version','driver_date','pci_location'),
}


def fields(kind,metric):
    rows=[]
    def row(key,label,unit='',section='概览',value=...):
        value=metric.get(key) if value is ... else value
        if isinstance(value,list):value=' / '.join(map(str,value)) if value else None
        if isinstance(value,float) and not math.isfinite(value):value=None
        reasons={'compressed_gb':'当前采集器尚未接入压缩内存计数器','directx_version':'等待 DXDiag 能力查询','driver_model':'等待 DXDiag / 驱动元数据',
                 'ddi_version':'等待 DXDiag 能力查询','feature_levels':'等待 DXDiag 能力查询'}
        rows.append({'key':key,'label':label,'value':value,'unit':unit,'section':section,
                     'available':value is not None,'note':reasons.get(key,'系统/驱动未提供，或仍在预热') if value is None else ''})
    schemas={
        'cpu':[('load_percent','利用率','%'),('frequency_mhz','速度（系统报告）','MHz'),('base_frequency_mhz','基准频率（固件报告）','MHz'),('temperature_c','CPU 封装温度','°C'),('sockets','插槽',''),('physical_cores','物理核心',''),('logical_processors','逻辑处理器',''),('virtualization_enabled','固件虚拟化已启用',''),('l1_cache_mb','L1 缓存','MiB'),('l2_cache_mb','L2 缓存','MiB'),('l3_cache_mb','L3 缓存','MiB'),('process_count','进程',''),('thread_count','线程',''),('handle_count','句柄',''),('uptime_seconds','运行时间','秒'),('temperature_source','温度来源',''),('temperature_note','温度采集说明','')],
        'memory':[('used_gb','使用中','GiB'),('compressed_gb','其中压缩内存','GiB'),('available_gb','可用','GiB'),('total_gb','可用物理总量','GiB'),('installed_gb','已安装内存','GiB'),('commit_used_gb','已提交','GiB'),('commit_limit_gb','提交上限','GiB'),('commit_peak_gb','提交峰值','GiB'),('cached_gb','缓存（备用+修改列表）','GiB'),('system_cache_gb','系统文件缓存（不同口径）','GiB'),('paged_pool_gb','分页缓冲池','GiB'),('nonpaged_pool_gb','非分页缓冲池','GiB'),('speed_mhz','配置频率（固件报告）','MHz'),('slots_used','已用插槽',''),('slots_total','总插槽',''),('form_factor','外形规格',''),('hardware_reserved_gb','硬件保留','GiB'),('swap_used_gb','交换区已用','GiB'),('swap_total_gb','交换区总量','GiB')],
        'gpu':[('load_percent','GPU 利用率','%'),('temperature_c','温度','°C'),('dedicated_used_mb','专用 GPU 内存已用','MiB'),('dedicated_total_mb','专用 GPU 内存总量','MiB'),('shared_used_mb','共享 GPU 内存已用','MiB'),('shared_total_mb','共享 GPU 内存总量','MiB'),('memory_used_mb','NVML 显存已用','MiB'),('memory_total_mb','NVML/硬件显存总量','MiB'),('memory_load_percent','显存读写忙碌度','%'),('core_clock_mhz','核心频率','MHz'),('memory_clock_mhz','显存频率','MHz'),('power_w','功耗','W'),('driver_version','驱动版本',''),('driver_date','驱动日期',''),('directx_version','DirectX / 功能级别',''),('driver_model','驱动模型 WDDM',''),('pci_location','物理位置','')],
        'disk':[('model','型号',''),('load_percent','活动时间','%'),('response_latency_ms','平均响应时间','ms'),('read_mbps','读取速度','MiB/s'),('write_mbps','写入速度','MiB/s'),('read_latency_ms','读取延迟','ms'),('write_latency_ms','写入延迟','ms'),('read_iops','读取 IOPS','次/秒'),('write_iops','写入 IOPS','次/秒'),('queue_length','当前队列',''),('physical_size_gb','物理容量','GiB'),('total_gb','分区合计容量','GiB'),('free_gb','剩余空间','GiB'),('system_disk','系统磁盘',''),('boot_disk','引导磁盘',''),('page_file','包含分页文件',''),('bus_type','总线类型',''),('partition_style','分区样式',''),('firmware','固件版本',''),('health','Windows 健康状态','')],
        'network':[('name','适配器名称',''),('is_up','连接已启用',''),('send_mbps','发送速度','Mbps'),('receive_mbps','接收速度','Mbps'),('link_mbps','协商链路速率','Mbps'),('connection_type','连接类型',''),('ipv4','IPv4',''),('ipv6','IPv6',''),('mac','MAC',''),('mtu','MTU','bytes'),('sent_gb','累计发送','GiB'),('received_gb','累计接收','GiB'),('packets_sent','发送包',''),('packets_received','接收包',''),('errors_in','接收错误',''),('errors_out','发送错误',''),('drops_in','接收丢弃',''),('drops_out','发送丢弃','')],
        'npu':[('name','NPU 名称',''),('manufacturer','制造商',''),('status','系统状态',''),('load_percent','利用率','%'),('dedicated_used_mb','专用内存','MiB'),('shared_used_mb','共享内存','MiB'),('driver_version','驱动版本',''),('driver_date','驱动日期',''),('pci_location','物理位置',''),('note','采集说明','')],
    }
    for key,label,unit in schemas[kind]:row(key,label,unit)
    if kind=='cpu':
        row('name','处理器型号',value=metric.get('name'))
        row('hypervisor_present','Hypervisor 正在运行',value=metric.get('hypervisor_present'))
        row('virtualization_firmware_reported','固件虚拟化原始报告',value=metric.get('virtualization_firmware_reported'))
        for i,load in enumerate(metric.get('core_load_percent',[])):row('core_'+str(i),'逻辑处理器 '+str(i+1),'%','各逻辑处理器',load)
        for i,core in enumerate(metric.get('cores',[])):row('temperature_'+str(i),core.get('name','核心'),'°C','核心温度',core.get('temperature_c'))
    if kind=='gpu':
        row('ddi_version','Direct3D DDI 版本',section='驱动能力')
        row('feature_levels','Direct3D 功能级别',section='驱动能力')
        for key,label in [('three_d_percent','3D / 渲染'),('video_encode_percent','视频编码'),('video_decode_percent','视频解码'),('copy_percent','复制'),('compute_percent','Compute')]:row(key,label,'%','引擎分项',metric.get('engines',{}).get(key))
        row('engine_source','分项来源','','引擎分项',metric.get('engines',{}).get('source'))
    if kind=='memory':
        for i,module in enumerate(metric.get('modules',[])):
            section='内存条 '+str(i+1)
            for key,label,unit in [('DeviceLocator','插槽',''),('Manufacturer','厂商',''),('PartNumber','型号',''),('ConfiguredClockSpeed','配置频率','MHz'),('SMBIOSMemoryType','SMBIOS 类型代码',''),('FormFactor','规格代码','')]:row('module_'+str(i)+'_'+key,label,unit,section,module.get(key))
    if kind=='disk':
        for i,volume in enumerate(metric.get('volumes',[])):
            for key,label,unit in [('mount','挂载点',''),('free_gb','剩余','GiB'),('total_gb','容量','GiB')]:row('volume_'+str(i)+'_'+key,label,unit,'分区 '+volume['mount'],volume.get(key))
    return rows
