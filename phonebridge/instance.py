"""Per-workspace Windows instance gate and non-destructive GUI activation.

A second launch must not create Bridge resources, rotate API credentials, kill
the first process, or bind a fallback port. A headless owner can show its GUI.
"""
import ctypes
import hashlib
import os


class AppInstance:
    def __init__(self, workspace, activate=True, kernel=None):
        self.kernel = kernel
        self.handles = []
        self.primary = True
        if kernel is None and os.name != 'nt':
            return
        self.kernel = kernel or ctypes.WinDLL('kernel32', use_last_error=True)
        key = hashlib.sha256(os.path.normcase(os.path.realpath(workspace)).encode('utf-8')).hexdigest()[:24]
        name = 'Local\\PhoneBridge-' + key
        k = self.kernel
        k.CreateMutexW.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
        k.CreateMutexW.restype = ctypes.c_void_p
        k.CreateEventW.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_wchar_p]
        k.CreateEventW.restype = ctypes.c_void_p
        k.SetEvent.argtypes = [ctypes.c_void_p]
        k.WaitForSingleObject.argtypes = [ctypes.c_void_p,ctypes.c_uint32]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        mutex = k.CreateMutexW(None,False,name)
        error = ctypes.get_last_error()
        if not mutex:
            raise ctypes.WinError(error)
        self.handles.append(mutex)
        self.primary = error != 183  # ERROR_ALREADY_EXISTS
        self.event = k.CreateEventW(None,False,False,name+'-activate')
        if not self.event:
            error = ctypes.get_last_error();self.close()
            raise ctypes.WinError(error)
        self.handles.append(self.event)
        if not self.primary and activate:
            k.SetEvent(self.event)

    def take_activation(self):
        return bool(self.kernel and self.primary and self.kernel.WaitForSingleObject(self.event,0) == 0)

    def close(self):
        for handle in reversed(self.handles):
            self.kernel.CloseHandle(handle)
        self.handles.clear()
