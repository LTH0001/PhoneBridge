"""Windows desktop capture -> low-delay H.264 -> native Android decoder."""
import threading
import time
from fractions import Fraction
from . import windows
from .transport import BridgeError

class DesktopSender:
    def __init__(self, bridge):
        self.bridge = bridge
        self.stop_event = threading.Event()
        self.thread = None
        self.frames = self.bytes = 0
        self.error = ''
        self.touch = False
        self.mouse_down = False
        self.monitor = None
        self.started = 0
        self.width = self.height = 0
        self.target_fps = 30
        self.input_events = 0
        self.quality = 'sharp'
        self.timings = {}

    def start(self, monitor=0, touch=False, max_width=3840, fps=30, quality='sharp'):
        self.stop()
        all_monitors = windows.monitors()
        if not 0 <= int(monitor) < len(all_monitors):
            raise BridgeError('请选择可用的 Windows 显示器')
        if not 5 <= int(fps) <= 60 or not 320 <= int(max_width) <= 3840:
            raise BridgeError('副屏参数范围：5–60 fps / 320–3840 最大宽度')
        self.monitor = all_monitors[int(monitor)]
        if quality not in ('sharp','balanced'): raise BridgeError('未知副屏画质档位')
        self.quality = quality
        from .layout import phone_desktop_size
        if quality == 'sharp':
            display=self.bridge.caps.get('display',{})
            native=max(int(display.get('width',2404)),int(display.get('height',1080)))
            self.width,self.height=phone_desktop_size(display,min(native,int(max_width)))
        else:
            factor = min(1., int(max_width) / self.monitor['width'])
            self.width = int(self.monitor['width']*factor)//2*2
            self.height = int(self.monitor['height']*factor)//2*2
        self.touch = bool(touch)
        self.target_fps = int(fps)
        self.bridge.request(0xa0, {'width':self.width,'height':self.height}, 0xa1)
        credentials=self.bridge.panel_credentials or {}
        self.bridge.launch_phone('display',touch=bool(touch),**({'api_url':credentials['url'],'api_token':credentials['token']} if credentials and not (self.bridge.wireless or self.bridge.accessory) else {}))
        self.frames = self.bytes = 0; self.error = ''
        self.timings = {'processing_ms':0.,'encoding_ms':0.,'send_ms':0.}
        self.started = time.monotonic()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name='pb-desktop-h264')
        self.thread.start()
        deadline = time.monotonic() + 12
        while not self.frames and not self.error and time.monotonic() < deadline:
            time.sleep(.05)
        if not self.frames or self.error:
            self.stop()
            raise BridgeError(self.error or '副屏编码未启动')
        self.bridge.log(f'原生副屏：桌面 {self.monitor["width"]}×{self.monitor["height"]} → {self.width}×{self.height} H.264 / USB / {quality}')
        return self.status()

    def _run(self):
        capture = None
        pixel_context=windows.physical_pixels()
        pixel_context.__enter__()
        try:
            import av
            m = self.monitor
            capture = av.open('desktop',format='gdigrab',options={
                'framerate':str(self.target_fps),'offset_x':str(m['left']), 'offset_y':str(m['top']),
                'video_size':f"{m['width']}x{m['height']}", 'draw_mouse':'1'})
            encoder = av.CodecContext.create('libx264','w')
            encoder.width = self.width; encoder.height = self.height
            encoder.pix_fmt = 'yuv420p'; encoder.time_base = Fraction(1, self.target_fps)
            encoder.framerate = Fraction(self.target_fps, 1)
            encoder.thread_count = 4
            parameters=f'keyint={self.target_fps}:min-keyint={self.target_fps}:bframes=0:repeat-headers=1:annexb=1'
            if self.quality == 'sharp':
                encoder.options={'preset':'veryfast','tune':'zerolatency','crf':'16',
                                 'x264-params':parameters+':vbv-maxrate=24000:vbv-bufsize=6000'}
            else:
                encoder.bit_rate=8000000
                encoder.options={'preset':'ultrafast','tune':'zerolatency','x264-params':parameters}
            encoder.open()
            if self.quality == 'sharp':
                import cv2
                cv2.setNumThreads(4)
            for frame in capture.decode(video=0):
                if self.stop_event.is_set(): break
                processing_start=time.perf_counter()
                if self.quality == 'sharp' and (m['width']!=self.width or m['height']!=self.height):
                    # Lanczos + mild unsharp mask preserves the selected desktop
                    # size while avoiding the phone Surface's blurry enlargement.
                    import cv2
                    # OpenCV's multithreaded Lanczos is substantially faster
                    # on GDI frames than this build's libswscale RGB path.
                    pixels=cv2.resize(frame.to_ndarray(format='bgr24'),(self.width,self.height),
                                      interpolation=cv2.INTER_LANCZOS4)
                    blurred=cv2.GaussianBlur(pixels,(0,0),.8)
                    pixels=cv2.addWeighted(pixels,1.35,blurred,-.35,0)
                    frame=av.VideoFrame.from_ndarray(pixels,format='bgr24')
                # Enlargement has already used Lanczos; this is only a color
                # conversion, so avoid an expensive unnecessary Lanczos pass.
                frame = frame.reformat(self.width,self.height,format='yuv420p',interpolation='FAST_BILINEAR')
                frame.pts = self.frames; frame.time_base = encoder.time_base
                encoding_start=time.perf_counter()
                packets=encoder.encode(frame)
                sending_start=time.perf_counter()
                for packet in packets:
                    data = bytes(packet)
                    self.bridge.transport.send_video(data, self.frames+1, time.monotonic_ns())
                    self.bytes += len(data)
                self.frames += 1
                sending_end=time.perf_counter()
                for key,seconds in (('processing_ms',encoding_start-processing_start),('encoding_ms',sending_start-encoding_start),('send_ms',sending_end-sending_start)):
                    self.timings[key]+=seconds*1000
        except Exception as exc:
            if not self.stop_event.is_set():
                self.error = str(exc)
                self.bridge.log(f'副屏视频错误：{exc}')
        finally:
            try:
                if capture: capture.close()
            finally: pixel_context.__exit__(None,None,None)

    def input(self, data):
        if not self.touch or not self.monitor or not self.thread:
            return
        action = data.get('action')
        self.input_events += 1
        x,y = float(data.get('x',0)),float(data.get('y',0))
        if not 0 <= x <= 1 or not 0 <= y <= 1:
            return
        m=self.monitor
        windows.pointer(action,m['left']+min(int(x*m['width']),m['width']-1),
                        m['top']+min(int(y*m['height']),m['height']-1))
        self.mouse_down = action == 'down' or (self.mouse_down and action != 'up')

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(3)
        self.thread = None
        self.touch = False
        if self.mouse_down:
            windows.pointer('up',None,None)
            self.mouse_down = False

    def status(self):
        elapsed=max(time.monotonic()-self.started,.001)
        return {'running':bool(self.thread and self.thread.is_alive()),'frames':self.frames,
                'fps':round(self.frames/elapsed,1),'bytes':self.bytes,'mbps':round(self.bytes*8/elapsed/1000000,2),
                'width':self.width,'height':self.height,'error':self.error,'touch':self.touch,'input_events':self.input_events,
                'monitor':self.monitor,'quality':self.quality,'crf':16 if self.quality=='sharp' else None,
                'timings':{key:round(value/max(self.frames,1),2) for key,value in self.timings.items()}}
