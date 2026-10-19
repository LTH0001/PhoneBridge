"""Fixed-size, bounded, local pixel transport for the Windows MF media source."""
import ctypes
import mmap
import os
import struct
from pathlib import Path

WIDTH,HEIGHT,HEADER=1280,720,64
SIZE=HEADER+WIDTH*HEIGHT*4
ctypes.windll.kernel32.GetTickCount64.restype=ctypes.c_ulonglong
FRAME_FILE=Path(os.environ.get('ProgramData','C:/ProgramData'))/'PhoneBridge/CameraFrames/frame.bin'

class FrameWriter:
    def __init__(self,path=FRAME_FILE):
        self.file=Path(path).open('r+b')
        if os.fstat(self.file.fileno()).st_size!=SIZE:
            self.file.close();raise ValueError('MF 摄像头缓冲大小无效')
        self.mapping=mmap.mmap(self.file.fileno(),SIZE,access=mmap.ACCESS_WRITE)
        self.sequence=0
        self.clear()

    def send(self,frame):
        import numpy as np
        image=frame.reformat(width=WIDTH,height=HEIGHT,format='bgra').to_ndarray()
        pixels=np.ascontiguousarray(image).tobytes()
        if len(pixels)!=SIZE-HEADER:raise ValueError('MF 摄像头像素长度无效')
        self.sequence=(self.sequence+2)&0xfffffffe
        struct.pack_into('<IIIIQ',self.mapping,0,0x46434250,WIDTH,HEIGHT,self.sequence|1,ctypes.windll.kernel32.GetTickCount64())
        self.mapping[HEADER:]=pixels
        struct.pack_into('<I',self.mapping,12,self.sequence)

    def clear(self):
        self.mapping[:HEADER]=bytes(HEADER)
        self.mapping[HEADER:]=bytes(SIZE-HEADER)

    def close(self):
        self.clear();self.mapping.close();self.file.close()

def installed():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Classes\CLSID\{984AE39C-1B89-4F77-AA3F-80496422D661}\InprocServer32') as key:
            return Path(winreg.QueryValueEx(key,'')[0]).is_file() and FRAME_FILE.is_file()
    except OSError:return False

def register():
    import subprocess
    from .config import ROOT
    powershell=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result=subprocess.run([str(powershell),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/install-mf-camera.ps1')],
                          timeout=60,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError('原生摄像头注册未完成，请确认管理员弹窗或查看 MFCamera/setup.log')
    return {'requested':True,'installed':installed()}
