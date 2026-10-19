import ctypes
import io
import queue
import threading
import time
from pathlib import Path

def drain(q):
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            break

class CameraSink:
    def __init__(self, dll, log):
        self.dll_path, self.log = str(dll), log
        self.queue = queue.Queue(180)
        self.stop_event = threading.Event()
        self.thread = None
        self.frames = 0
        self.jpeg = None
        self.last_frame = None
        self.virtual = False
        self.mf_virtual = False
        self.virtual_requested = False
        self.width = self.height = 0
        self.error = ''
        self.started = 0

    def start(self, virtual=False):
        self.stop()
        drain(self.queue)
        self.frames = 0
        self.jpeg = self.last_frame = None
        self.error = ''
        self.virtual_requested = virtual
        self.started = time.monotonic()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name='pb-camera-decode')
        self.thread.start()

    def feed(self, payload):
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            # H.264 packets cannot be discarded arbitrarily: next keyframe
            # resynchronizes the decoder after the queue is flushed.
            drain(self.queue)
            self.log('摄像头解码跟不上，等待下一个关键帧')

    def _run(self):
        cam = None
        dll = None
        mf_writer = None
        try:
            import av
            import numpy as np
            decoder = av.CodecContext.create('h264', 'r')
            last_jpeg = 0
            while not self.stop_event.is_set():
                try:
                    data = self.queue.get(timeout=.2)
                except queue.Empty:
                    continue
                try:
                    decoded = decoder.decode(av.Packet(data))
                except av.error.InvalidDataError:
                    continue
                for frame in decoded:
                    self.width, self.height = frame.width, frame.height
                    self.frames += 1
                    self.last_frame = frame
                    if self.virtual_requested and mf_writer is None:
                        from .mf_camera import installed,FrameWriter
                        if installed(): mf_writer=FrameWriter();self.mf_virtual=True
                    if mf_writer: mf_writer.send(frame)
                    if self.virtual_requested and cam is None and Path(self.dll_path).is_file():
                        dll = ctypes.WinDLL(self.dll_path)
                        dll.scCreateCamera.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float]
                        dll.scCreateCamera.restype = ctypes.c_void_p
                        dll.scSendFrame.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                        dll.scDeleteCamera.argtypes = [ctypes.c_void_p]
                        cam = dll.scCreateCamera(frame.width, frame.height, 30.)
                        if not cam:
                            raise RuntimeError('虚拟摄像头已被其他发送端占用')
                        self.virtual = True
                    if self.virtual_requested and not cam and not mf_writer:
                        raise RuntimeError('系统摄像头输出尚未安装；请在电脑版注册 Windows 原生摄像头。本开发包不包含来源未确认的旧 DirectShow DLL。')
                    if cam:
                        # Softcam expects top-down BGR24 pixels.
                        pixels = np.ascontiguousarray(frame.to_ndarray(format='bgr24'))
                        dll.scSendFrame(cam, pixels.ctypes.data)
                    now = time.monotonic()
                    if now - last_jpeg >= .1:
                        image = frame.to_image()
                        image.thumbnail((960, 720))
                        buf = io.BytesIO()
                        image.save(buf, format='JPEG', quality=80)
                        self.jpeg = buf.getvalue()
                        last_jpeg = now
        except Exception as exc:
            self.error = str(exc)
            self.log(f'摄像头输出错误：{exc}')
        finally:
            if mf_writer: mf_writer.close()
            self.mf_virtual = False
            if cam:
                dll.scDeleteCamera(cam)
            self.virtual = False

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(3)
        self.thread = None

    def status(self):
        dt = max(time.monotonic() - self.started, .001)
        return {'frames': self.frames, 'fps': round(self.frames / dt, 1),
                'width': self.width, 'height': self.height, 'virtual': bool(self.virtual or self.mf_virtual),
                'mf_virtual':self.mf_virtual,
                'running': bool(self.thread and self.thread.is_alive()), 'error': self.error}

class AudioSink:
    def __init__(self, log):
        self.log = log
        self.queue = queue.Queue(20)
        self.stop_event = threading.Event()
        self.thread = None
        self.packets = self.bytes = 0
        self.level = 0.
        self.error = ''
        self.device = None

    def start(self, device=None):
        self.stop()
        drain(self.queue)
        self.packets = self.bytes = 0
        self.error = ''
        self.device = device
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name='pb-audio-output')
        self.thread.start()

    def feed(self, payload):
        self.packets += 1
        self.bytes += len(payload)
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            self.queue.get_nowait()
            self.queue.put_nowait(payload)

    def _run(self):
        try:
            import sounddevice as sd
            import numpy as np
            if self.device == -1:
                while not self.stop_event.is_set():
                    try:
                        pcm = self.queue.get(timeout=.2)
                    except queue.Empty:
                        continue
                    samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32)
                    self.level = float(np.sqrt(np.mean(samples ** 2)) / 32768.) if samples.size else 0.
                return
            with sd.RawOutputStream(samplerate=48000, channels=1, dtype='int16',
                                    device=self.device, blocksize=480, latency='low') as stream:
                while not self.stop_event.is_set():
                    try:
                        pcm = self.queue.get(timeout=.2)
                    except queue.Empty:
                        continue
                    samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32)
                    self.level = float(np.sqrt(np.mean(samples ** 2)) / 32768.) if samples.size else 0.
                    stream.write(pcm)
        except Exception as exc:
            self.error = str(exc)
            self.log(f'麦克风输出错误：{exc}')

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(3)
        self.thread = None

    @staticmethod
    def devices():
        import sounddevice as sd
        apis = sd.query_hostapis()
        return [{'id': i, 'name': d['name'], 'api': apis[d['hostapi']]['name'],
                 'output_channels': d['max_output_channels']}
                for i, d in enumerate(sd.query_devices()) if d['max_output_channels'] > 0]

    def status(self):
        return {'running': bool(self.thread and self.thread.is_alive()), 'packets': self.packets,
                'bytes': self.bytes, 'level': round(self.level, 4), 'device': self.device, 'error': self.error}

