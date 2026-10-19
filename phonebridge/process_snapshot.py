"""Public Win32 metadata calls only; never read process/ kernel memory contents."""
import ctypes as c
from ctypes import wintypes as w

class Entry(c.Structure):
    _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',c.c_size_t),
              ('module',w.DWORD),('threads',w.DWORD),('ppid',w.DWORD),('priority',w.LONG),
              ('flags',w.DWORD),('name',w.WCHAR*260)]
class Memory(c.Structure):
    _fields_=[('size',w.DWORD),('faults',w.DWORD)]+[(name,c.c_size_t) for name in
        ('peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]

def seconds(value):return ((value.dwHighDateTime<<32)|value.dwLowDateTime)/10_000_000

def read_processes():
    dll=c.WinDLL('kernel32',use_last_error=True)
    signatures={'CreateToolhelp32Snapshot':([w.DWORD,w.DWORD],w.HANDLE),
        'Process32FirstW':([w.HANDLE,c.POINTER(Entry)],w.BOOL),'Process32NextW':([w.HANDLE,c.POINTER(Entry)],w.BOOL),
        'OpenProcess':([w.DWORD,w.BOOL,w.DWORD],w.HANDLE),'CloseHandle':([w.HANDLE],w.BOOL),
        'GetProcessTimes':([w.HANDLE]+[c.POINTER(w.FILETIME)]*4,w.BOOL),
        'K32GetProcessMemoryInfo':([w.HANDLE,c.POINTER(Memory),w.DWORD],w.BOOL)}
    for name,(args,result) in signatures.items():getattr(dll,name).argtypes=args;getattr(dll,name).restype=result
    snapshot=dll.CreateToolhelp32Snapshot(2,0)
    if snapshot==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
    rows=[];entry=Entry();entry.size=c.sizeof(entry)
    try:
        more=dll.Process32FirstW(snapshot,c.byref(entry))
        while more and len(rows)<8192:
            created=cpu=memory=None
            handle=dll.OpenProcess(0x1010,False,entry.pid) # QueryLimitedInformation | VM_READ (memory counters only).
            if handle:
                try:
                    creation,exit_time,kernel,user=(w.FILETIME() for _ in range(4))
                    if dll.GetProcessTimes(handle,c.byref(creation),c.byref(exit_time),c.byref(kernel),c.byref(user)):
                        created=seconds(creation)-11644473600;cpu=seconds(kernel)+seconds(user)
                    counters=Memory();counters.size=c.sizeof(counters)
                    if dll.K32GetProcessMemoryInfo(handle,c.byref(counters),c.sizeof(counters)):memory=round(counters.working/1048576,1)
                finally:dll.CloseHandle(handle)
            rows.append({'pid':entry.pid,'ppid':entry.ppid,'name':entry.name,'threads':entry.threads,
                         'create_time':created,'cpu_seconds':cpu,'memory_mb':memory})
            more=dll.Process32NextW(snapshot,c.byref(entry))
    finally:dll.CloseHandle(snapshot)
    return rows
