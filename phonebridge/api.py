import hmac
import io
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .config import ROOT, data_root
from . import __version__
from . import windows
from .telemetry import HostTelemetry
from .music import MusicController
from .playback import PlaybackController
from .lyrics import LyricsController
from .system_info import SystemInfo

class LocalAPI:
    def __init__(self, bridge, port=8765):
        self.bridge = bridge
        self.token = secrets.token_urlsafe(32)
        self.display_enabled = False
        self.display_touch = False
        self.display_monitor = 0
        self.desktop_jpeg = None
        self.display_bounds = None
        self.closed = threading.Event()
        self.close_lock = threading.Lock()
        self.wireless_server=None
        from .apk_install import ApkInstaller
        self.apk_installer=ApkInstaller(bridge)
        from .remote_input import RemoteInput
        self.remote_input=RemoteInput(bridge)
        from .speech import LocalSpeech
        self.speech=LocalSpeech(self.remote_input)
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def authorized(self):
                parsed = urlparse(self.path)
                supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
                if not supplied:
                    supplied = parse_qs(parsed.query).get('token', [''])[0]
                if not hmac.compare_digest(supplied, api.token):
                    self.respond(401, {'error': '需要本机 API 访问令牌'})
                    return False
                return True

            def respond(self, code, data, content_type='application/json; charset=utf-8'):
                body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', content_type)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy','no-referrer')
                if content_type=='application/vnd.android.package-archive':
                    self.send_header('Content-Disposition','attachment; filename="PhoneBridge-Android.apk"')
                if urlparse(self.path).path=='/setup':
                    self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                if urlparse(self.path).path=='/setup':
                    self.respond(200,(ROOT/'phonebridge/setup.html').read_bytes(),'text/html; charset=utf-8')
                    return
                if not self.authorized():
                    return
                path = urlparse(self.path).path
                if path == '/api/status':
                    self.respond(200, {**bridge.status(), 'version': __version__, 'display': api.display_enabled})
                elif path=='/api/apk/devices':
                    try:self.respond(200,{'devices':api.apk_installer.devices()})
                    except Exception as exc:self.respond(400,{'error':str(exc)})
                elif path=='/api/apk/status':
                    self.respond(200,api.apk_installer.status())
                elif path=='/api/apk/download':
                    apk=ROOT/'android/app/build/phonebridge.apk'
                    if not apk.is_file():self.respond(404,{'error':'安装包不存在，请重新下载完整软件包'})
                    else:self.respond(200,apk.read_bytes(),'application/vnd.android.package-archive')
                elif path == '/api/capabilities':
                    self.respond(200, bridge.caps)
                elif path == '/api/sensors':
                    self.respond(200, bridge.sensor_values())
                elif path == '/api/audio-devices':
                    self.respond(200, bridge.audio.devices())
                elif path == '/api/display/monitors':
                    self.respond(200, windows.monitors())
                elif path == '/api/logs':
                    self.respond(200, list(bridge.logs))
                elif path == '/api/dashboard/status':
                    self.respond(200, api.panel_status())
                elif path == '/api/playback/status':
                    self.respond(200, api.playback.status())
                elif path == '/api/music/lyrics':
                    self.respond(200, api.lyrics.status())
                elif path == '/api/music/art':
                    key=parse_qs(urlparse(self.path).query).get('key',[''])[0]
                    artwork=api.music.artwork(key)
                    self.respond(200 if artwork else 404,artwork,'image/jpeg')
                elif path == '/api/permissions':
                    try: self.respond(200, bridge.files.permissions())
                    except Exception as exc: self.respond(400, {'error': str(exc)})
                elif path == '/camera.jpg':
                    self.respond(200 if bridge.camera.jpeg else 503, bridge.camera.jpeg or b'', 'image/jpeg')
                elif path == '/desktop.jpg':
                    self.respond(200 if api.desktop_jpeg and api.display_enabled else 503,
                                 api.desktop_jpeg if api.display_enabled and api.desktop_jpeg else b'', 'image/jpeg')
                elif path == '/phone':
                    self.respond(200, (ROOT/'phonebridge/phone.html').read_bytes(), 'text/html; charset=utf-8')
                else:
                    self.respond(404, {'error': '不存在的接口'})

            def do_POST(self):
                if not self.authorized():
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    limit=700000 if urlparse(self.path).path=='/api/speech/recognize' else 65536
                    if not 0 <= size <= limit:
                        self.respond(413, {'error': '请求过大'})
                        return
                    body = json.loads(self.rfile.read(size) or b'{}')
                    path = urlparse(self.path).path
                    if not isinstance(body,dict):raise ValueError('请求必须为 JSON 对象')
                    if path=='/api/apk/install':
                        if self.headers.get('Authorization','')!='Bearer '+api.token:
                            self.respond(403,{'error':'USB 安装要求请求头中的访问令牌'});return
                        origin=self.headers.get('Origin')
                        if origin and origin!=f'http://127.0.0.1:{api.port}':
                            self.respond(403,{'error':'仅允许从本机安装页面发起'});return
                        self.respond(202,api.apk_installer.start(body.get('serial'),body.get('confirmed')))
                        return
                    actions = {
                        '/api/speech/recognize':lambda:api.speech.recognize(**body),
                        '/api/speech/start':lambda:api.speech.start(**body),
                        '/api/speech/chunk':lambda:api.speech.chunk(**body),
                        '/api/speech/finish':lambda:api.speech.finish(**body),
                        '/api/input/begin':lambda:api.remote_input.begin(**body),
                        '/api/input/end':lambda:api.remote_input.end(**body),
                        '/api/input/events':lambda:api.remote_input.events(**body),
                        '/api/input/text':lambda:api.remote_input.text(**body),
                        '/api/input/desktop':lambda:api.remote_input.desktop(**body),
                        '/api/input/previous':lambda:api.remote_input.previous(**body),
                        '/api/accessory/connect': lambda: bridge.connect_accessory(),
                        '/api/wireless/pair': lambda: api.pair_wireless(body.get('address','')),
                        '/api/wireless/stop': api.stop_wireless,
                        '/api/connect': lambda: bridge.connect_wired(body.get('serial', '')),
                        '/api/disconnect': bridge.disconnect,
                        '/api/camera/start': lambda: bridge.camera_start(**body),
                        '/api/camera/stop': bridge.camera_stop,
                        '/api/camera/register-system': lambda: windows.register_camera_system(),
                        '/api/dashboard/start': api.start_panel,
                        '/api/dashboard/enter': api.enter_panel,
                        '/api/dashboard/desktop': api.resume_desktop,
                        '/api/music/control': lambda: api.music.action(**body),
                        '/api/playback/control': lambda: api.playback.action(**body),
                        '/api/music/lyrics': lambda: api.lyrics.request(**body),
                        '/api/dashboard/detail': lambda: api.telemetry.detail(**body),
                        '/api/system/status': lambda: api.system.status(**body),
                        '/api/system/process': lambda: api.system.process_detail(**body),
                        '/api/files/list': lambda: bridge.files.list(**body),
                        '/api/files/download': lambda: bridge.files.download(**body),
                        '/api/mic/start': lambda: bridge.mic_start(body.get('device')),
                        '/api/mic/stop': bridge.mic_stop,
                        '/api/sensor/start': lambda: bridge.sensor_start(**body),
                        '/api/sensor/stop': lambda: bridge.sensor_stop(**body),
                        '/api/control': lambda: bridge.control(**body),
                        '/api/screen/start': bridge.screen_start,
                        '/api/screen/stop': bridge.screen_stop,
                        '/api/display/start': lambda: api.start_display(**body),
                        '/api/display/stop': api.stop_display,
                        '/api/display/input': lambda: api.display_input(**body),
                        '/api/display/native-start': lambda: bridge.display_start(**body),
                        '/api/display/native-stop': bridge.display_stop,
                        '/api/display/extend': lambda: windows.set_virtual_display(True),
                        '/api/display/driver': lambda: windows.display_driver(body.get('action','status')),
                        '/api/shutdown': api.shutdown,
                    }
                    if path not in actions:
                        self.respond(404, {'error': '不存在的接口'})
                        return
                    self.respond(200, actions[path]())
                except Exception as exc:
                    self.respond(400, {'error': str(exc)})

        class ExclusiveHTTPServer(ThreadingHTTPServer):
            allow_reuse_address=False
            def server_bind(self):
                if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                    self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
                super().server_bind()
        self.server = ExclusiveHTTPServer(('127.0.0.1', int(port)), Handler)
        self.port = self.server.server_port
        self.telemetry=HostTelemetry()
        self.music=MusicController(bridge.config.get('music_path','QQMusic.exe'))
        self.playback=PlaybackController()
        self.lyrics=LyricsController(self.music,bridge.config.get('lyrics_network_allowed',False))
        self.system=SystemInfo()
        bridge.panel_credentials={'url':f'http://127.0.0.1:{self.port}','token':self.token}
        bridge.panel_restore=self.start_panel
        # Reuse the same strict panel endpoint allowlist; never export the local API token.
        from .wireless import WirelessServer
        panel_proxy=WirelessServer.__new__(WirelessServer);panel_proxy.api=self
        bridge.panel_rpc=panel_proxy.rpc
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name='pb-local-api')
        self.thread.start()
        threading.Thread(target=self._capture, daemon=True, name='pb-desktop-capture').start()
        runtime=data_root(ROOT)/'runtime';runtime.mkdir(parents=True,exist_ok=True)
        (runtime/'api.json').write_text(json.dumps({'url': f'http://127.0.0.1:{self.port}',
                                                       'token': self.token}), 'utf-8')

    def start_display(self, monitor=0, touch=False):
        self.display_monitor = int(monitor)
        available = windows.monitors()
        if not 0 <= self.display_monitor < len(available):
            raise ValueError('选择的 Windows 显示器不存在')
        self.display_bounds = available[self.display_monitor]
        self.bridge.adb('reverse', f'tcp:{self.port}', f'tcp:{self.port}')
        self.display_touch = bool(touch)
        self.display_enabled = True
        url = f'http://127.0.0.1:{self.port}/phone?token={self.token}'
        result = self.bridge.adb('shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', url)
        self.bridge.log('电脑画面已发送到手机浏览器' + ('，触控回传已开启' if touch else ''))
        return {'ok': True, 'url': url, 'monitors': available, 'extended': len(available) > 1, 'launch': result}

    def stop_display(self):
        self.display_enabled = self.display_touch = False
        self.desktop_jpeg = None
        if self.closed.is_set() or not self.bridge.panel_visible:
            try: self.bridge.adb('reverse', '--remove', f'tcp:{self.port}')
            except Exception: pass
        return {'ok': True}

    def display_input(self, action, x=0, y=0, code='enter'):
        if not self.display_enabled or not self.display_touch:
            raise ValueError('触控回传未开启')
        if action == 'click':
            b = self.display_bounds
            x, y = float(x), float(y)
            if not 0 <= x <= 1 or not 0 <= y <= 1:
                raise ValueError('无效触控位置')
            windows.click(b['left'] + min(int(x*b['width']), b['width']-1),
                          b['top'] + min(int(y*b['height']), b['height']-1))
        elif action == 'key':
            windows.key(code)
        else:
            raise ValueError('未知输入')
        return {'ok': True}

    def _capture(self):
        from PIL import ImageGrab
        while not self.closed.wait(.1):
            if not self.display_enabled or not self.display_bounds:
                continue
            try:
                b = self.display_bounds
                image = ImageGrab.grab(bbox=(b['left'], b['top'], b['left']+b['width'], b['top']+b['height']), all_screens=True)
                image.thumbnail((1600, 1000))
                buf = io.BytesIO()
                image.save(buf, 'JPEG', quality=75)
                self.desktop_jpeg = buf.getvalue()
            except Exception as exc:
                self.display_enabled = False
                self.bridge.log(f'电脑画面发送失败：{exc}')

    def close(self):
        with self.close_lock:
            if self.closed.is_set():
                return
            self.closed.set()
            self.remote_input.close()
            self.stop_wireless()
            self.stop_display()
            self.server.shutdown()
            self.server.server_close()
            self.telemetry.close()
            self.music.close()
            self.playback.close()
            self.lyrics.close()
            self.system.close()
            self.bridge.panel_restore=None

    def panel_status(self):
        return {'connected':self.bridge.connected,'panel_visible':self.bridge.panel_visible,
                  'transport':'accessory' if self.bridge.accessory else 'wireless' if self.bridge.wireless else 'usb',
                  'host':self.telemetry.status(),'music':self.music.status(),'playback':self.playback.status()}

    def enter_panel(self):
        with self.bridge.lock:
            if self.closed.is_set(): raise ValueError('控制台正在关闭')
            if not self.bridge.connected: raise ValueError('请先连接手机')
            if not (getattr(self.bridge,'wireless',False) or getattr(self.bridge,'accessory',False)):self.bridge.adb('reverse',f'tcp:{self.port}',f'tcp:{self.port}')
            if not self.bridge.panel_visible:
                self.bridge.desktop.stop()
                self.bridge.request(0xa2,expect=0xa1)
                self.bridge.panel_visible=True
                try: windows.return_phone_cursor_to_main()
                except Exception: pass
            return {'ok':True,'panel_visible':True}

    def start_panel(self):
        with self.bridge.lock:
            self.enter_panel()
            self.bridge.launch_phone('panel',**({} if self.bridge.wireless or self.bridge.accessory else {'api_url':f'http://127.0.0.1:{self.port}','api_token':self.token}))
            self.bridge.log('手机控制面板已打开；原生触摸按钮可控制 QQ 音乐，桌面视频暂停')
            return {'ok':True,'panel_visible':True}

    def resume_desktop(self):
        with self.bridge.lock:
            if self.closed.is_set(): raise ValueError('控制台正在关闭')
            options=dict(self.bridge.desired_display or {})
            options.update(touch=True)
            options.setdefault('max_width',3840)
            options.setdefault('desktop_width',self.bridge.config.get('display_desktop_width',800))
            options.setdefault('layout',self.bridge.config.get('display_layout','below-left'))
            options.setdefault('dpi_scale',175 if options['desktop_width']==2404 else 100)
            return self.bridge.display_start(**options)

    def shutdown(self):
        def worker():
            self.close()
            self.bridge.close()
        threading.Thread(target=worker, daemon=True).start()
        return {'ok': True}

    def pair_wireless(self,address):
        from .wireless import WirelessServer
        self.stop_wireless()
        self.bridge.disconnect()
        self.wireless_server=WirelessServer(self,address)
        self.bridge.wireless_revoke=self.wireless_server.close
        return {'invitation':self.wireless_server.invitation(),'expires_seconds':120,'port':self.wireless_server.port}

    def stop_wireless(self):
        if self.wireless_server:
            self.wireless_server.close();self.wireless_server=None
            self.bridge.wireless_revoke=None
            if self.bridge.wireless:self.bridge.disconnect()
        return {'ok':True}

