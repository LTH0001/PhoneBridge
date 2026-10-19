"""Offline package smoke check: never connects USB, records media or installs."""
import importlib
import json
import sys
from .config import ROOT,data_root

def run():
    from . import __version__
    checks={}
    for name in ('av','numpy','sounddevice','PIL.Image','cv2','psutil','pycaw.pycaw',
                 'cryptography','qrcode','usb.core','libusb_package','tkinter','vosk',
                 'winrt.windows.media.control','winrt.windows.storage.streams',
                 'winrt.windows.devices.enumeration'):
        try:
            importlib.import_module(name);checks[name]={'ok':True}
        except Exception as exc:
            checks[name]={'ok':False,'error':type(exc).__name__+': '+str(exc)}
    try:
        import av
        from .accessory import backend
        backend()  # Load libusb only; no USB enumeration, probe or mode switch.
        av.CodecContext.create('h264','r');av.CodecContext.create('libx264','w')
        checks['native-codecs-and-usb']={'ok':True}
    except Exception as exc:
        checks['native-codecs-and-usb']={'ok':False,'error':str(exc)}
    checks['phone-web-asset']={'ok':(ROOT/'phonebridge/phone.html').is_file()}
    checks['apk-setup-web-asset']={'ok':(ROOT/'phonebridge/setup.html').is_file()}
    checks['offline-speech-model']={'ok':(ROOT/'vendor/vosk-model-small-cn-0.22/am/final.mdl').is_file()}
    report={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),
            'checks':checks,'ok':all(c['ok'] for c in checks.values()),
            'note':'依赖自检不代表手机连接、驱动安装或免调试验收通过。'}
    destination=data_root()/'runtime/self-check.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if sys.stdout:print(json.dumps(report,ensure_ascii=False))
    return 0 if report['ok'] else 1
