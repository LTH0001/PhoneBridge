import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def find_music():
    """Resolve this PC's installation; never inherit the developer's drive."""
    if os.name=='nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\QQMusic.exe',0,winreg.KEY_READ|view) as key:
                        candidate=Path(winreg.QueryValueEx(key,None)[0].strip('"'))
                        if candidate.is_file() and candidate.name.casefold()=='qqmusic.exe':return str(candidate)
                except OSError:pass
    for base in ('LOCALAPPDATA','ProgramFiles','ProgramFiles(x86)'):
        for suffix in ('Tencent/QQMusic/QQMusic.exe','QQMusic/QQMusic.exe'):
            candidate=Path(os.environ.get(base,''))/suffix
            if candidate.is_file():return str(candidate)
    return 'QQMusic.exe'
def data_root(asset_root=ROOT):
    # Frozen app assets may live in a read-only installation directory. Never
    # write tokens/preferences beside the executable or into the bundle.
    if getattr(sys,'frozen',False):
        return Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'PhoneBridge'
    return Path(asset_root)

CONFIG_FILE = data_root() / 'config.local.json'

def load():
    cfg = json.loads(CONFIG_FILE.read_text('utf-8')) if CONFIG_FILE.exists() else {}
    cfg.setdefault('adb', str(ROOT / 'vendor/scrcpy/adb.exe'))
    cfg.setdefault('scrcpy', str(ROOT / 'vendor/scrcpy/scrcpy.exe'))
    cfg.setdefault('softcam', str(ROOT / 'vendor/softcam.dll'))
    cfg.setdefault('toolchain', str(ROOT / 'build-toolchain'))
    cfg.setdefault('serial', '')
    cfg.setdefault('api_port', 8765)
    cfg.setdefault('default_camera_facing', 'FRONT')
    cfg.setdefault('display_layout', 'below-left')
    cfg.setdefault('display_desktop_width', 640)
    cfg.setdefault('display_quality','sharp')
    cfg.setdefault('display_touch',True)
    cfg.setdefault('music_path',find_music())
    cfg.setdefault('lyrics_network_allowed',False)
    return cfg


def save_camera_facing(facing):
    # Merge only this preference; keep unrelated local tool paths and settings.
    facing = str(facing).upper()
    if facing not in ('FRONT', 'BACK', 'EXTERNAL'):
        raise ValueError('未知摄像头类型')
    save_preferences(default_camera_facing=facing)


def save_preferences(**preferences):
    cfg = json.loads(CONFIG_FILE.read_text('utf-8')) if CONFIG_FILE.exists() else {}
    cfg.update(preferences)
    temporary = CONFIG_FILE.with_suffix('.json.tmp')
    CONFIG_FILE.parent.mkdir(parents=True,exist_ok=True)
    temporary.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
    temporary.replace(CONFIG_FILE)

