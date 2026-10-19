import collections
import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from . import proto
from .config import ROOT
from .cameras import preferred_camera
from .media import CameraSink, AudioSink
from .display import DesktopSender
from .files import PhoneFiles
from .transport import Transport, BridgeError, adb_run, devices

PACKAGE = 'com.phonebridge.app'

class Bridge:
    def __init__(self, config):
        self.config = config
        self.transport = None
        self.serial = ''
        self.caps = {}
        self.connection = '未连接'
        self.logs = collections.deque(maxlen=200)
        self.events = queue.Queue()
        self.lock = threading.RLock()
        self.samples_lock = threading.Lock()
        self.samples, self.sensor_counts, self.sensor_started, self.desired_sensors = {}, {}, {}, {}
        self.camera = CameraSink(config['softcam'], self.log)
        self.audio = AudioSink(self.log)
        self.desktop = DesktopSender(self)
        self.files = PhoneFiles(self)
        self.processes = {}
        self.async_errors = {}
        self.desired_camera = self.desired_audio = None
        self.desired_display = None
        self.panel_visible = False
        self.panel_restore = None
        self.panel_credentials = None
        self.auto_reconnect = False
        self.wireless = False
        self.accessory = False
        self.panel_rpc = None
        self.wireless_revoke = None
        self.shutdown_event = threading.Event()
        self.monitor = threading.Thread(target=self._monitor, daemon=True, name='pb-reconnect')
        self.monitor.start()

    def log(self, message):
        item = {'time': time.strftime('%H:%M:%S'), 'message': str(message)}
        self.logs.append(item)
        self.events.put(item)

    @property
    def connected(self):
        return bool(self.transport and not self.transport.closed.is_set())

    def detect(self):
        return devices(self.config['adb'])

    def detect_wired(self, include_adb=False):
        from .usb_setup import discover
        # Native-only discovery must not start ADB when an accessory is found.
        # The GUI explicitly opts in to ADB: an AOA descriptor does not prove
        # its data interface is usable (another driver may own interface 0).
        # Never hide an authorized ADB connection behind an experimental entry.
        found = discover()
        if found and not include_adb:
            return found
        adb = self.detect()
        if include_adb:
            adb = sorted(adb, key=lambda device: device.get('state') != 'device')
        return adb+found

    def connect_wired(self, selected=''):
        from .usb_setup import prepare
        with self.lock:
            if self.connected:
                return self.status()
            # An explicitly chosen ADB serial must not be hidden by a native
            # USB candidate representing another interface of the same phone.
            if selected and not selected.startswith(('usb:','usb-error:')):
                return self.connect(selected)
            found = self.detect_wired()
            if selected:
                found = [d for d in found if d['serial'] == selected]
            if len(found) != 1:
                raise BridgeError('请刷新并选择一台手机；未检测到支持的 USB 设备或存在多台设备')
            target = found[0]
            if target.get('transport') == 'accessory':
                device = prepare(target['serial'])
                return self.connect_accessory(device)
            return self.connect(target['serial'])

    def adb(self, *args, timeout=20):
        if self.accessory:raise BridgeError('USB 外设模式不使用 ADB；该开发功能尚未迁移')
        if self.wireless:raise BridgeError('无线模式不使用 ADB；该开发功能仅支持 USB')
        return adb_run(self.config['adb'], self.serial, *args, timeout=timeout)

    def attach_wireless(self,transport):
        with self.lock:
            if self.connected:raise BridgeError('已有手机连接')
            self.transport=transport;self.wireless=True;self.serial='wireless'
            self.caps=self.request(proto.T_GET_CAPABILITIES,expect=proto.T_CAPABILITIES)
            self.connection='无线 TLS 已连接';self.auto_reconnect=False
            self.log('无线四通道已认证，未使用 ADB')

    def launch_phone(self,page,**extras):
        if self.wireless or self.accessory:return self.request(0xb0,{'page':page,**extras},0xb1)
        activity={'panel':'DashboardActivity','display':'DisplayActivity','main':'MainActivity'}[page]
        args=[]
        for key,value in extras.items():args.extend(['--ez' if isinstance(value,bool) else '--es',key,str(value).lower() if isinstance(value,bool) else str(value)])
        return self.adb('shell','am','start','--activity-clear-top','--activity-single-top','-n',PACKAGE+'/.'+activity,*args)

    def connect(self, serial=''):
        with self.lock:
            if self.connected:
                return self.status()
            self.wireless=False
            self.accessory=False
            found = [d for d in self.detect() if d['state'] == 'device']
            serial = serial or self.serial or self.config.get('serial') or (found[0]['serial'] if len(found) == 1 else '')
            if not serial or not any(d['serial'] == serial for d in found):
                raise BridgeError('请选择已授权的手机；若未授权，请在手机允许 USB 调试')
            self.serial = serial
            if not self.adb('shell', 'pm', 'path', PACKAGE):
                raise BridgeError('请先安装 PhoneBridge 手机 App')
            self.adb('shell', 'am', 'start', '-n', PACKAGE + '/.MainActivity')
            error = None
            for attempt in range(4):
                t = Transport(self.config['adb'], serial, self._frame, self._disconnected)
                try:
                    t.connect()
                    self.transport = t
                    self.caps = t.request(proto.T_GET_CAPABILITIES, expect=proto.T_CAPABILITIES, timeout=30)
                    self.connection = '已连接'
                    self.auto_reconnect = True
                    self.log(f'已连接 {self.caps.get("android", {}).get("model", serial)}，USB 四通道就绪')
                    return self.status()
                except Exception as exc:
                    error = exc
                    t.close()
                    time.sleep(.4)
            raise BridgeError(f'连接失败：{error}')

    def connect_accessory(self, device=None):
        from .accessory import devices,AccessoryTransport
        with self.lock:
            if self.connected:raise BridgeError('请先断开当前传输')
            found=[device] if device is not None else devices()
            if len(found)!=1:raise BridgeError('需要恰好一台已进入 AOA 的手机；请先完成 USB 模式检测与手机授权')
            if not self.panel_rpc:raise BridgeError('面板 API 未就绪')
            transport=AccessoryTransport(found[0],self._frame,self._disconnected,self.panel_rpc)
            try:
                transport.connect();self.transport=transport;self.accessory=True;self.wireless=False;self.serial='accessory'
                self.caps=self.request(proto.T_GET_CAPABILITIES,expect=proto.T_CAPABILITIES)
                self.connection='USB 外设已连接（免调试）';self.auto_reconnect=False
                self.log('AOA USB bulk 已连接，未使用 ADB / 网络')
                return self.status()
            except Exception:
                transport.close();self.transport=None;self.accessory=False;raise

    def install(self, serial=None):
        with self.lock:
            found = [d for d in self.detect() if d['state'] == 'device']
            selected=serial or self.serial
            if not selected and len(found)==1:selected=found[0]['serial']
            if not selected or selected not in {d['serial'] for d in found}:
                raise BridgeError('请先选择已授权的手机，并在手机上允许 USB 调试')
            apk = ROOT / 'android/app/build/phonebridge.apk'
            if not apk.exists():
                raise BridgeError('APK 尚未构建，请运行 scripts/build-android.ps1')
            self.log('正在安装手机 App，请在手机确认安装')
            reconnect=self.auto_reconnect
            self.auto_reconnect=False
            try:
                adb_run(self.config['adb'],selected,'shell','input','keyevent','KEYCODE_WAKEUP')
                return {'result': adb_run(self.config['adb'],selected,'install', '--no-incremental', '-r', str(apk), timeout=120)}
            finally:self.auto_reconnect=reconnect

    def request(self, kind, data=None, expect=None):
        if not self.connected:
            raise BridgeError('请先连接 PhoneBridge')
        return self.transport.request(kind, data, expect)

    def _frame(self, frame):
        kind, sid, seq, ts, flags, payload = frame
        if kind == proto.T_ERROR:
            self.async_errors[sid] = payload.decode('utf-8', errors='replace')
            self.log(f'手机流错误：{self.async_errors[sid]}')
            return
        if kind == proto.T_VIDEO_FRAME:
            self.camera.feed(payload)
        elif kind == proto.T_AUDIO_PACKET:
            self.audio.feed(payload)
        elif kind == proto.T_SENSOR_EVENT:
            if len(payload) == 16 and not payload.startswith(b'{'):
                import struct
                typ, x, y, z = struct.unpack('<ifff', payload)
                value = {'type': typ, 'values': [x, y, z], 'accuracy': None, 'timestamp_ns': ts}
            else:
                value = json.loads(payload)
            typ = str(value['type'])
            value['sequence'] = seq
            value['received_ns'] = time.monotonic_ns()
            with self.samples_lock:
                self.samples[typ] = value
                self.sensor_counts[typ] = self.sensor_counts.get(typ, 0) + 1
        elif kind == 0x2002:
            self.desktop.input(json.loads(payload))

    def camera_start(self, camera_id=None, width=1280, height=720, fps=30, virtual=False):
        with self.lock:
            if camera_id is None:
                selected = preferred_camera(self.caps.get('camera', []), self.config.get('default_camera_facing', 'FRONT'))
                if selected is None:
                    raise BridgeError('未发现可用摄像头，请先连接手机')
                camera_id = selected['id']
            self.camera_stop()
            if virtual:
                from .windows import camera_registered
                if not camera_registered():
                    raise BridgeError('虚拟摄像头尚未注册，请先点击“注册虚拟摄像头”')
            self.camera.start(virtual)
            self.async_errors.pop(2, None)
            try:
                self.request(proto.T_CAMERA_OPEN, {'cameraId': str(camera_id), 'width': int(width), 'height': int(height),
                             'fps': int(fps), 'bitrateKbps': 6000}, proto.T_CAMERA_OPEN_RESULT)
                deadline = time.monotonic() + 10
                while not self.camera.frames and not self.camera.error and 2 not in self.async_errors and time.monotonic() < deadline:
                    time.sleep(.05)
                if not self.camera.frames or self.camera.error:
                    raise BridgeError(self.camera.error or self.async_errors.get(2) or '未收到可解码的摄像头画面；请检查手机相机权限/配置')
                self.desired_camera = {'camera_id': str(camera_id), 'width': int(width), 'height': int(height),
                                       'fps': int(fps), 'virtual': virtual}
                self.log(f'摄像头 {camera_id}：{width}×{height}，' + ('Windows 虚拟摄像头输出' if virtual else '预览'))
                return self.camera.status()
            except Exception:
                self.camera_stop()
                raise

    def camera_stop(self):
        with self.lock:
            self.desired_camera = None
            if self.connected and self.camera.thread:
                try:
                    self.request(proto.T_CAMERA_CLOSE, expect=proto.T_CAMERA_OPEN_RESULT)
                finally:
                    self.camera.stop()
            else:
                self.camera.stop()
            return self.camera.status()

    def mic_start(self, device=None):
        with self.lock:
            self.mic_stop()
            self.audio.start(device)
            self.async_errors.pop(3, None)
            try:
                self.request(proto.T_MIC_START, {'sampleRate': 48000, 'channels': 1}, proto.T_MIC_START_RESULT)
                deadline = time.monotonic() + 8
                while not self.audio.packets and not self.audio.error and 3 not in self.async_errors and time.monotonic() < deadline:
                    time.sleep(.05)
                if not self.audio.packets or self.audio.error:
                    raise BridgeError(self.audio.error or self.async_errors.get(3) or '手机麦克风没有输出音频')
                self.desired_audio = {'device': device}
                self.log('手机麦克风已开始实时输出，48 kHz / 16 bit / 单声道')
                return self.audio.status()
            except Exception:
                self.mic_stop()
                raise

    def mic_stop(self):
        with self.lock:
            self.desired_audio = None
            if self.connected and self.audio.thread:
                try:
                    self.request(proto.T_MIC_STOP, expect=proto.T_MIC_START_RESULT)
                finally:
                    self.audio.stop()
            else:
                self.audio.stop()
            return self.audio.status()

    def sensor_start(self, sensor=4, rate=100):
        with self.lock:
            typ = int(proto.SENSORS.get(sensor, sensor))
            rate = int(rate)
            if not 1 <= rate <= 1000:
                raise BridgeError('采样频率应为 1–1000 Hz')
            result = self.request(proto.T_SENSOR_START, {'sensor': typ, 'rateHz': rate}, proto.T_SENSOR_START_RESULT)
            with self.samples_lock:
                self.sensor_counts[str(typ)] = 0
                self.sensor_started[str(typ)] = time.monotonic()
            self.desired_sensors[typ] = rate
            self.log(f'传感器 {typ}，请求 {rate} Hz')
            return result

    def sensor_stop(self, sensor=4):
        with self.lock:
            typ = int(proto.SENSORS.get(sensor, sensor))
            self.desired_sensors.pop(typ, None)
            if self.connected:
                self.request(proto.T_SENSOR_STOP, {'sensor': typ}, proto.T_SENSOR_START_RESULT)
            return {'ok': True}

    def sensor_values(self):
        with self.samples_lock:
            now = time.monotonic()
            return {k: {**v, 'events': self.sensor_counts.get(k, 0),
                        'measured_hz': round(self.sensor_counts.get(k, 0) / max(now-self.sensor_started.get(k, now), .001), 1),
                        'active': int(k) in self.desired_sensors}
                    for k, v in self.samples.items()}

    def control(self, action, **kwargs):
        allowed = {'home': 'KEYCODE_HOME', 'back': 'KEYCODE_BACK', 'wake': 'KEYCODE_WAKEUP',
                   'volume_up': 'KEYCODE_VOLUME_UP', 'volume_down': 'KEYCODE_VOLUME_DOWN'}
        if action in allowed:
            return {'result': self.adb('shell', 'input', 'keyevent', allowed[action])}
        if action == 'torch':
            return self.request(proto.T_TORCH_ON if kwargs.get('on') else proto.T_TORCH_OFF,
                                expect=proto.T_SENSOR_START_RESULT)
        if action == 'vibrate':
            ms = int(kwargs.get('ms', 200))
            if not 1 <= ms <= 5000:
                raise BridgeError('振动时长应为 1–5000 毫秒')
            return self.request(proto.T_VIBRATE, {'duration_ms': ms}, proto.T_SENSOR_START_RESULT)
        raise BridgeError('不支持的控制操作')

    def screen_start(self):
        with self.lock:
            if not self.serial:
                raise BridgeError('请先连接手机')
            if 'screen' in self.processes and self.processes['screen'].poll() is None:
                return {'ok': True}
            p = subprocess.Popen([self.config['scrcpy'], '--serial=' + self.serial, '--no-audio',
                                  '--window-title=PhoneBridge — 手机屏幕', '--port=27200:27210'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.processes['screen'] = p
            self.log('手机屏幕窗口已打开；可通过键鼠操作，剪贴板由 scrcpy 同步')
            return {'ok': True, 'pid': p.pid}

    def screen_stop(self):
        p = self.processes.pop('screen', None)
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(2)
        return {'ok': True}

    def status(self):
        return {'connected': self.connected, 'serial': self.serial, 'connection': self.connection,'transport':'accessory' if self.accessory else 'wireless' if self.wireless else 'usb',
                'camera': self.camera.status(), 'microphone': self.audio.status(),
                'sensors': self.sensor_values(),
                'screen': bool(self.processes.get('screen') and self.processes['screen'].poll() is None),
                'native_display': self.desktop.status(),
                'panel_visible':self.panel_visible,
                'auto_reconnect': self.auto_reconnect,
                'accessory_stats':self.transport.status() if self.accessory and self.transport else None}

    def _disconnected(self, message):
        if self.wireless_revoke:self.wireless_revoke()
        self.connection = '已断开，等待重新连接'
        self.camera.stop()
        self.audio.stop()
        self.desktop.stop()
        self._detach_display()
        self.log(message)

    def _monitor(self):
        while not self.shutdown_event.wait(3):
            if not self.auto_reconnect:
                continue
            try:
                with self.lock:
                    if self.connected:
                        self.request(proto.T_GET_STATUS, expect=proto.T_STATUS)
                    else:
                        desired_camera, desired_audio = self.desired_camera, self.desired_audio
                        desired_display = self.desired_display
                        desired_sensors = dict(self.desired_sensors)
                        self.connect(self.serial)
                        for typ, rate in desired_sensors.items():
                            self.sensor_start(typ, rate)
                        if desired_camera:
                            self.camera_start(**desired_camera)
                        if desired_audio:
                            self.mic_start(**desired_audio)
                        if desired_display and not self.panel_visible:
                            self.display_start(**desired_display)
                        if self.panel_visible and self.panel_restore:
                            self.panel_restore()
            except Exception:
                pass

    def disconnect(self):
        with self.lock:
            if self.wireless_revoke:self.wireless_revoke()
            self.auto_reconnect = False
            self.desired_camera = self.desired_audio = None
            self.desired_display = None
            self.panel_visible = False
            self.desired_sensors.clear()
            if self.transport:
                self.transport.close()
                self.transport = None
            self.camera.stop()
            self.audio.stop()
            self.desktop.stop()
            self._detach_display()
            self.screen_stop()
            self.connection = '未连接'
            self.wireless=False
            self.accessory=False
            return self.status()

    def display_start(self, extended=True, desktop_width=None, layout=None, dpi_scale=None, **options):
        with self.lock:
            if not self.connected: raise BridgeError('请先连接手机')
            self.panel_visible=False
            options.setdefault('touch',self.config.get('display_touch',True))
            options.setdefault('quality',self.config.get('display_quality','sharp'))
            try:
                if extended:
                    from .windows import set_virtual_display, virtual_display_device
                    from .layout import phone_desktop_size
                    desktop_width=desktop_width or self.config.get('display_desktop_width',640)
                    layout=layout or self.config.get('display_layout','below-left')
                    width,height=phone_desktop_size(self.caps.get('display',{}),desktop_width)
                    if self.desktop.thread: self.desktop.stop()
                    available=set_virtual_display(True,width,height,layout)
                    device=virtual_display_device()
                    if dpi_scale is not None:
                        from .dpi import set_phone_scaling
                        set_phone_scaling(dpi_scale)
                        from .windows import monitors
                        available=monitors()
                    options['monitor']=next(m['id'] for m in available if m['device']==device)
                result=self.desktop.start(**options)
                self.desired_display={'extended':extended,'desktop_width':desktop_width,'layout':layout,'dpi_scale':dpi_scale,**options}
                return result
            except Exception:
                self.desktop.stop()
                self.desired_display=None
                if extended:
                    try: set_virtual_display(False)
                    except Exception as exc: self.log(f'副屏启动失败后回收提示：{exc}')
                else: self._detach_display()
                raise

    def display_stop(self):
        with self.lock:
            self.panel_visible=False
            self.desktop.stop()
            self.desired_display=None
            if self.connected: self.request(0xa2, expect=0xa1)
            self.launch_phone('main')
            self._detach_display()
            return {'ok':True}

    def _detach_display(self):
        if not self.desktop.monitor:
            return
        try:
            from .windows import virtual_display_device,set_virtual_display
            if self.desktop.monitor.get('device')==virtual_display_device(): set_virtual_display(False)
        except Exception as exc:
            self.log(f'副屏关闭提示：{exc}')

    def close(self):
        self.disconnect()
        self.shutdown_event.set()
