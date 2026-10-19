import argparse
import ctypes
import signal
import time
import sys
from .config import load, ROOT, data_root
from .core import Bridge
from .api import LocalAPI
from .instance import AppInstance

def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    parser = argparse.ArgumentParser(description='PhoneBridge 手机外设控制中心')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--connect', action='store_true')
    parser.add_argument('--self-check',action='store_true',help='只检查打包依赖，不连接手机或安装驱动')
    parser.add_argument('--register-directshow',metavar='DLL',help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_check:
        from .self_check import run
        return run()
    if args.register_directshow:
        from .windows import _register_current_user
        _register_current_user(args.register_directshow)
        return 0
    instance = AppInstance(str(data_root()),activate=not args.headless)
    if not instance.primary:
        if sys.stdout:print('PhoneBridge 已在运行，已请求显示现有窗口。' if not args.headless else 'PhoneBridge 已在运行。')
        instance.close()
        return 0
    bridge = api = None
    try:
        bridge = Bridge(load())
        api = LocalAPI(bridge, bridge.config['api_port'])
        if args.connect:
            bridge.connect_wired()
        if args.headless:
            if sys.stdout:print(f'PhoneBridge API ready on http://127.0.0.1:{api.port}', flush=True)
            while not bridge.shutdown_event.is_set():
                if instance.take_activation():
                    break
                time.sleep(.5)
        if not bridge.shutdown_event.is_set():
            from .gui import ControlCenter
            ControlCenter(bridge, api, activation=instance).mainloop()
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        if getattr(exc,'winerror',None) != 10048:
            raise
        message='本机 API 端口已被其他进程或旧版 PhoneBridge 占用；请退出旧版后重试。未终止任何进程。'
        if args.headless:
            if sys.stderr:print(message,file=sys.stderr)
        else:
            ctypes.windll.user32.MessageBoxW(None,message,'PhoneBridge 无法启动',0x10)
        return 1
    finally:
        if api:api.close()
        if bridge:bridge.close()
        instance.close()

if __name__ == '__main__':
    raise SystemExit(main() or 0)
