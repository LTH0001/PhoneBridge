"""Authorized USB/ADB shared storage access. No root or permission bypass."""
import os
import posixpath
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from .transport import BridgeError

def shared_path(path='/sdcard'):
    path = str(path)
    if '\x00' in path or '\\' in path:
        raise ValueError('无效的手机路径')
    path = posixpath.normpath(path)
    for root in ('/sdcard', '/storage/emulated/0'):
        if path == root or path.startswith(root + '/'):
            return path
    raise ValueError('仅支持手机共享存储；其他应用私有数据和系统目录不开放')


class PhoneFiles:
    def __init__(self, bridge): self.bridge = bridge

    def _path(self, path):
        if not self.bridge.connected: raise BridgeError('请先连接手机')
        path = shared_path(path)
        actual = self.bridge.adb('shell', 'realpath ' + shlex.quote(path))
        if not (actual == '/storage/emulated/0' or actual.startswith('/storage/emulated/0/')):
            raise ValueError('路径指向共享存储之外')
        return actual

    def list(self, path='/sdcard'):
        actual = self._path(path)
        # NUL-delimited output safely preserves Unicode, whitespace and newlines.
        # Avoid following symlinks; user-controlled names are never shell code.
        script = ('test -d ' + shlex.quote(actual) + ' || exit 1; '
                  'find ' + shlex.quote(actual) + " -mindepth 1 -maxdepth 1 -print0 | "
                  "while IFS= read -r -d '' f; do "
                  '[ -L "$f" ] && continue; '
                  'if [ -d "$f" ]; then k=d; else k=f; fi; '
                  's=$(stat -c %s "$f") || continue; '
                  "printf '%s\\0%s\\0%s\\0' \"$k\" \"$s\" \"$f\"; "
                  'n=$((n+1)); [ "$n" -ge 2000 ] && break; done; true')
        raw = self.bridge.adb('shell', script, timeout=45)
        parts = raw.split('\x00')
        entries = []
        for index in range(0, len(parts)-2, 3):
            kind, size, remote = parts[index:index+3]
            entries.append({'name': posixpath.basename(remote), 'path': remote,
                            'directory': kind == 'd', 'size': int(size)})
        entries.sort(key=lambda entry: (not entry['directory'], entry['name'].casefold()))
        return {'path': actual, 'entries': entries, 'truncated': len(entries) >= 2000}

    def download(self, path, destination):
        actual = self._path(path)
        self.bridge.adb('shell', 'test -f ' + shlex.quote(actual) + ' && test -r ' + shlex.quote(actual))
        name = posixpath.basename(actual)
        if re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith(('.', ' ')) or name.split('.')[0].upper() in {
                'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
            raise ValueError('文件名不适合 Windows，请先在手机修改文件名')
        folder = Path(destination).resolve()
        if not folder.is_dir(): raise ValueError('请选择已存在的电脑目标文件夹')
        target = folder / name
        if target.exists(): raise ValueError('电脑已有同名文件，不会覆盖，请选择其他文件夹')
        fd, temporary = tempfile.mkstemp(prefix='.phonebridge-', suffix='.part', dir=folder)
        os.close(fd)
        try:
            self.bridge.adb('pull', actual, temporary, timeout=300)
            # Exclusive creation guards against overwriting an intervening file.
            with target.open('xb') as output, open(temporary, 'rb') as source:
                shutil.copyfileobj(source, output)
            return {'path': str(target), 'size': target.stat().st_size}
        finally:
            Path(temporary).unlink(missing_ok=True)

    def permissions(self):
        if not self.bridge.connected: raise BridgeError('请先连接手机')
        package = self.bridge.adb('shell', 'dumpsys package com.phonebridge.app')
        granted = {name: value == 'true' for name,value in
                   re.findall(r'(android\.permission\.[A-Z_]+): granted=(true|false)', package)}
        return {'transport': '已授权 USB 调试 / ADB', 'shared_storage': True,
                'permissions': granted, 'private_app_data': False, 'root': False,
                'note': '文件/相册访问走已授权 USB 调试，不等于授予所有 Android 权限。微信聊天库、银行应用数据等受系统隔离。'}
