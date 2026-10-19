"""Bounded local diagnostics. No process mutation, kernel memory or elevation."""
import copy
import platform
import sys
import threading
import time
import psutil
from .process_snapshot import read_processes

class SystemInfo:
    def __init__(self):
        self.lock=threading.Lock();self.closed=threading.Event();self.previous={}
        v=sys.getwindowsversion()
        self.system={'kernel':'Windows NT','kernel_version':f'{v.major}.{v.minor}.{v.build}',
                     'architecture':platform.machine(),'python_bits':64 if sys.maxsize>2**32 else 32,
                     'logical_processors':psutil.cpu_count(),'boot_time':psutil.boot_time(),
                     'note':'普通权限只读；受保护进程字段可能不可读。CPU 按全机逻辑处理器归一化。'}
        self.value={'system':self.system,'processes':[],'updated_at':0,'error':''}
        self.thread=threading.Thread(target=self._run,name='pb-system-info',daemon=True);self.thread.start()
    def _sample(self):
        now=time.monotonic();previous={};rows=[];threads=handles=0
        for data in read_processes():
            pid=data['pid'];created=data.get('create_time');cpu=data.get('cpu_seconds')
            load=None;key=(pid,created)
            if cpu is not None and created is not None:
                seconds=cpu;old=self.previous.get(key);previous[key]=(now,seconds)
                if old and now>old[0]:load=round(max(0,min(100,100*(seconds-old[1])/(now-old[0])/(psutil.cpu_count() or 1))),1)
            memory=data.get('memory_mb');thread_count=data.get('threads');handle_count=None
            if pid==0:load=None # Idle time is not process CPU consumption.
            threads+=thread_count or 0;handles+=handle_count or 0
            rows.append({'pid':pid,'ppid':data.get('ppid'),'name':(data.get('name') or '不可读')[:160],
                         'created_at':created,'status':data.get('status'),'threads':thread_count,'handles':handle_count,
                         'memory_mb':memory,'cpu_percent':load})
            if len(rows)>=8192:break
        self.previous=previous
        return {'system':{**self.system,'uptime_seconds':round(time.time()-self.system['boot_time']),
                          'process_count':len(rows),'threads_readable_total':threads,'handles_readable_total':None},
                'processes':rows,'updated_at':time.time(),'error':''}
    def _run(self):
        while not self.closed.is_set():
            try:
                value=self._sample()
                with self.lock:self.value=value
            except Exception as error:
                with self.lock:self.value['error']=str(error)[:160]
            self.closed.wait(1)
    def status(self,query='',page=0,limit=40,sort='memory'):
        if not isinstance(query,str) or len(query)>80:raise ValueError('无效进程搜索')
        if type(page) is not int or not 0<=page<=2048 or type(limit) is not int or not 1<=limit<=100:raise ValueError('无效页码或页大小')
        if sort not in ('memory','cpu','pid'):raise ValueError('未知进程排序')
        with self.lock:value=copy.deepcopy(self.value)
        rows=[p for p in value.pop('processes') if query.casefold() in p['name'].casefold() or query==str(p['pid'])]
        key={'memory':'memory_mb','cpu':'cpu_percent','pid':'pid'}[sort]
        rows.sort(key=lambda p:(p.get(key) is not None,p.get(key) or 0),reverse=sort!='pid')
        return {**value,'total':len(rows),'page':page,'limit':limit,'sort':sort,'processes':rows[page*limit:(page+1)*limit]}
    def process_detail(self,pid,created_at):
        if type(pid) is not int or not 0<pid<2**32:raise ValueError('无效 PID')
        if type(created_at) not in (int,float) or not 0<created_at<2**40:raise ValueError('无法验证进程身份')
        with self.lock:
            row=next((copy.deepcopy(p) for p in self.value['processes'] if p['pid']==pid and p['created_at']==created_at),None)
        if not row:raise ValueError('进程快照已改变，请刷新再点开')
        process=psutil.Process(pid)
        if abs(process.create_time()-created_at)>.001:raise ValueError('PID 已被其他进程复用，请刷新')
        info=process.as_dict(attrs=['status','num_threads','num_handles'],ad_value=None)
        row.update(status=info['status'],threads=info['num_threads'],handles=info['num_handles'])
        return row
    def close(self):self.closed.set();self.thread.join(3)
