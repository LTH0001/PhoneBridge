"""Android Open Accessory USB bulk transport. Never installs/replaces a driver."""
import json
import queue
import struct
import threading
import time
from . import proto
from .transport import BridgeError, CommandError, MAX_PAYLOAD

MANUFACTURER='PhoneBridge'
MODEL='PhoneBridge USB'
AOA_VENDOR=0x18d1
AOA_PRODUCTS=(0x2d00,0x2d01)

def backend():
    import usb.backend.libusb1,libusb_package
    value=usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
    if value is None:raise BridgeError('libusb 后端不可用，请检查安装包')
    return value

def devices():
    import usb.core
    return list(usb.core.find(find_all=True,backend=backend(),idVendor=AOA_VENDOR,
                             custom_match=lambda d:d.idProduct in AOA_PRODUCTS))

def probe(device):
    data=bytes(device.ctrl_transfer(0xc0,51,0,0,2,timeout=1500))
    if len(data)!=2:raise BridgeError('设备返回无效 AOA 协议版本')
    version=int.from_bytes(data,'little')
    if version not in (1,2):raise BridgeError('手机不支持 AOA 1/2')
    return version

def switch(device):
    """Explicit caller action only. USB re-enumeration interrupts MTP/ADB."""
    probe(device)
    # Not pretending to own an unregistered website/domain.
    for index,value in enumerate((MANUFACTURER,MODEL,'PhoneBridge wired peripherals','1.0','','PhoneBridge-USB')):
        device.ctrl_transfer(0x40,52,0,index,value.encode()+b'\0',timeout=1500)
    device.ctrl_transfer(0x40,53,0,0,b'',timeout=1500)

class FrameBuffer:
    def __init__(self):self.data=bytearray()
    def feed(self,data):
        self.data.extend(data);result=[]
        while len(self.data)>=36:
            magic,version,kind,sid,seq,ts,flags,size=proto.HEADER.unpack_from(self.data)
            if magic!=proto.MAGIC or version!=1 or sid not in (1,2,3,4,5) or size>MAX_PAYLOAD:
                raise BridgeError('无效 USB 外设协议帧')
            if len(self.data)<36+size:break
            result.append((kind,sid,seq,ts,flags,bytes(self.data[36:36+size])))
            del self.data[:36+size]
        return result

class AccessoryTransport:
    def __init__(self,device,on_frame,on_disconnect,rpc):
        self.device=device;self.on_frame=on_frame;self.on_disconnect=on_disconnect;self.rpc=rpc
        self.closed=threading.Event();self.command_lock=threading.RLock();self.write_lock=threading.Lock()
        self.responses=queue.Queue(8);self.rpc_jobs=queue.Queue(8);self.seq=0;self.interface=None
        self.tx_bytes=self.rx_bytes=self.rx_frames=0;self.last_error=''

    def connect(self):
        import usb.util
        configuration=self.device.get_active_configuration()
        interface=next((i for i in configuration if i.bInterfaceNumber==0),None)
        if interface is None:raise BridgeError('AOA 外设接口 0 不可用；不会访问 ADB 接口')
        self.in_ep=next((e for e in interface if usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_IN and usb.util.endpoint_type(e.bmAttributes)==usb.util.ENDPOINT_TYPE_BULK),None)
        self.out_ep=next((e for e in interface if usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_OUT and usb.util.endpoint_type(e.bmAttributes)==usb.util.ENDPOINT_TYPE_BULK),None)
        if self.in_ep is None or self.out_ep is None:raise BridgeError('AOA bulk 端点缺失')
        usb.util.claim_interface(self.device,0);self.interface=0
        threading.Thread(target=self._read,daemon=True,name='pb-aoa-read').start()
        threading.Thread(target=self._rpc_worker,daemon=True,name='pb-aoa-panel').start()
        self.request(proto.T_GET_STATUS,expect=proto.T_STATUS,timeout=20)
        return self

    def _send(self,data):
        with self.write_lock:
            if self.closed.is_set():raise BridgeError('USB 外设已断开')
            for offset in range(0,len(data),65536):
                part=data[offset:offset+65536]
                if self.out_ep.write(part,timeout=2500)!=len(part):raise BridgeError('USB 写入不完整')
                self.tx_bytes+=len(part)

    def request(self,kind,data=None,expect=None,timeout=15):
        with self.command_lock:
            self.seq+=1
            try:
                self._send(proto.frame_json(kind,1,self.seq,data or {}))
                response=self.responses.get(timeout=timeout)
                if response is None:raise BridgeError('USB 外设已断开')
                if response[0] not in (expect,proto.T_ERROR):raise BridgeError('USB 控制响应不匹配')
                result=json.loads(response[5])
                if response[0]==proto.T_ERROR or result.get('ok') is False:raise CommandError(result.get('error','手机命令失败'))
                return result
            except queue.Empty as exc:
                self.last_error=f'USB 控制响应超时（命令 0x{kind:04x}，等待 {timeout:g} 秒）；请确认手机 USB 外设授权并打开 PhoneBridge'
                self.close()
                raise BridgeError(self.last_error) from exc
            except CommandError:raise
            except Exception:
                self.close();raise

    def _read(self):
        import usb.core
        buffer=FrameBuffer()
        try:
            while not self.closed.is_set():
                try:data=bytes(self.in_ep.read(65536,timeout=1000))
                except usb.core.USBTimeoutError:continue
                self.rx_bytes+=len(data)
                for frame in buffer.feed(data):
                    self.rx_frames+=1
                    if frame[1]==1:self.responses.put_nowait(frame)
                    elif frame[1]==5 and frame[0]==0xc0:self.rpc_jobs.put_nowait(frame)
                    elif frame[1] in (2,3,4):self.on_frame(frame)
                    else:raise BridgeError('USB 通道无效')
        except Exception as exc:
            if not self.closed.is_set():self.last_error=type(exc).__name__+': '+str(exc);self.close();self.on_disconnect('USB 外设通道中断：'+self.last_error)

    def _rpc_worker(self):
        while not self.closed.is_set():
            try:frame=self.rpc_jobs.get(timeout=.5)
            except queue.Empty:continue
            try:result=self.rpc(json.loads(frame[5]))
            except Exception:result={'error':'USB 面板请求失败'}
            try:self._send(proto.frame(0xc1,5,frame[2],0,0,json.dumps(result,ensure_ascii=False).encode()))
            except Exception as exc:
                self.last_error=type(exc).__name__+': '+str(exc);self.close();self.on_disconnect('USB 面板回传中断：'+self.last_error);return

    def status(self):return {'tx_bytes':self.tx_bytes,'rx_bytes':self.rx_bytes,'rx_frames':self.rx_frames,'error':self.last_error}

    def send_video(self,payload,sequence,timestamp_ns):self._send(proto.frame(0x2001,2,sequence,timestamp_ns,16,payload))

    def close(self):
        if self.closed.is_set():return
        self.closed.set()
        try:self.responses.put_nowait(None)
        except queue.Full:pass
        # Let the bounded USB read return before releasing the claimed handle.
        def release():
            import usb.util
            time.sleep(1.1)
            try:usb.util.dispose_resources(self.device)
            except Exception:pass
        threading.Thread(target=release,daemon=True).start()
