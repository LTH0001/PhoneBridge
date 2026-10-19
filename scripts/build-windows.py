"""Build a LOCAL development onedir bundle, not a signed public installer.

Allowlisted assets only. No private config/tokens/keys, unknown Softcam DLL,
driver installers, automatic elevation, device changes or public upload.
"""
import datetime
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import sys
import zipfile
import argparse

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from phonebridge import __version__

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onefile',action='store_true',help='Build one self-extracting EXE with embedded APK and dependency assets')
    options=parser.parse_args()
    if os.name!='nt' or sys.maxsize<=2**32:
        raise SystemExit('Build requires 64-bit Windows Python.')
    import PyInstaller.__main__
    if metadata.version('pyinstaller')!='6.22.3':
        raise SystemExit('Install build requirement: pyinstaller==6.22.3')
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    build=ROOT/'runtime'/'build-windows'/stamp
    output=ROOT/'dist'/f'PhoneBridge-{__version__}-dev-windows-{"onefile-" if options.onefile else ""}{stamp}'
    archive=output.parent/(output.name+'.zip')
    if build.exists() or output.exists() or archive.exists():
        raise SystemExit('Build target already exists; refusing to overwrite.')
    build.mkdir(parents=True);output.mkdir(parents=True)
    args=[str(ROOT/'scripts/frozen-entry.py'),'--name','PhoneBridge','--onefile' if options.onefile else '--onedir',
          '--windowed','--noupx','--paths',str(ROOT),'--distpath',str(output),
          '--workpath',str(build/'work'),'--specpath',str(build)]
    assets=['phonebridge/phone.html','phonebridge/setup.html','README.md','LICENSE','THIRD_PARTY_NOTICES.md',
        'docs/BUILDING.md','docs/DEPENDENCIES.md','docs/ARCHITECTURE.md','docs/RELEASING.md',
        'android/app/build/phonebridge.apk',
        'native/mf-camera/build/PhoneBridgeMF.dll',
        'native/mf-camera/build/PhoneBridgeMFRegister.exe',
        'native/mf-camera/build/PhoneBridgeMFProbe.exe',
        'vendor/mf-camera-reference/LICENSE','vendor/scrcpy',
        'vendor/vdd-source/LICENSE','vendor/vdd-package/Dependencies/devcon.exe',
        'vendor/vdd-package/SignedDrivers/x86/VDD',
        'vendor/librehardwaremonitor','vendor/temperature-licenses','vendor/vosk-model-small-cn-0.22']
    assets.extend('scripts/'+name for name in (
        'cpu-temperature.ps1','CpuTemperature.cs','display-driver.ps1','vdd_settings.xml',
        'install-mf-camera.ps1','register-camera-system.ps1','setup-temperature.ps1',
        'wireless-firewall.ps1'))
    for name in assets:
        source=ROOT/name
        if not source.exists() or source.is_symlink():
            raise SystemExit('Required verified asset is missing: '+name)
        target=Path(name) if source.is_dir() else Path(name).parent
        args.extend(['--add-data',str(source)+os.pathsep+target.as_posix()])
    # Preserve installed dependency license texts without sweeping up runtime,
    # home directories, certificate stores or arbitrary local binaries.
    versions={}
    for distribution in metadata.distributions():
        name=distribution.metadata.get('Name','unknown')
        versions[name]=distribution.version
        for relative in distribution.files or ():
            parts=Path(str(relative)).parts
            if not any(p.lower().endswith('.dist-info') for p in parts):continue
            if not any(p.lower().startswith(('license','copying','notice')) for p in parts):continue
            source=Path(distribution.locate_file(relative))
            if source.is_file() and not source.is_symlink():
                args.extend(['--add-data',str(source)+os.pathsep+f'licenses/python/{name}'])
    for package in ('av','numpy','PIL','cv2','sounddevice','winrt','pycaw','comtypes',
                    'cryptography','qrcode','usb','libusb_package','vosk'):
        args.extend(['--collect-all',package])
    args.extend(['--hidden-import','usb.backend.libusb1'])
    for module in ('pytest','IPython','notebook','torch','tensorflow','scipy','pandas','matplotlib'):
        args.extend(['--exclude-module',module])
    print('Building local development executable; no USB/driver operation is performed.',flush=True)
    PyInstaller.__main__.run(args)
    package=output if options.onefile else output/'PhoneBridge'
    executable=package/'PhoneBridge.exe'
    if options.onefile:
        executable=package/f'PhoneBridge-{__version__}-windows-x64.exe'
        (package/'PhoneBridge.exe').rename(executable)
    import shutil
    if not options.onefile:
        shutil.copy2(ROOT/'android/app/build/phonebridge.apk',package/'PhoneBridge-Android.apk')
    (package/'BUILD-DEPENDENCIES.json').write_text(json.dumps(versions,indent=2),encoding='utf-8')
    (package/'READ-ME-FIRST.txt').write_text(
        'PhoneBridge '+__version__+' / 桌面改版免安装体验包\n\n'+
        ('单文件 EXE：APK 与许可已嵌入，首次启动解压可能较慢；可在软件内导出/安装手机 APK。未签名，不能绕过系统安全提示。\n' if options.onefile else '双击 PhoneBridge.exe，无需另行安装 Python。Android APK 位于 _internal/android/app/build/phonebridge.apk。\n')+
        ('手机 APK 已内嵌，可在软件内导出到另一台 Android 手机确认安装。\n' if options.onefile else '同目录 PhoneBridge-Android.apk 可复制到另一台 Android 手机确认安装。\n')+
        '当前稳定路径：手机开启 USB 调试（不需要无线调试），插线并允许自己的电脑，选择已授权手机后连接。\n'+
        ('单文件版无需另带 _internal 文件夹；部分品牌需另装官方 ADB 驱动。推荐 Windows 11 x64。\n' if options.onefile else '请完整解压并保留 _internal 文件夹；部分品牌需另装官方 ADB 驱动。推荐 Windows 11 x64。\n')+
        '免调试 AOA 仍有本机 Code 10 / USB 枚举故障，尚未通过即插即用验收。\n'
        '本包不是已完成的安装器，不自动安装任何驱动，不绕过手机或 Windows 授权。\n'
        '首次使用系统摄像头、副屏、CPU 温度仍需各自的系统组件与管理员确认。\n'
        '不含旧版来源未确认的 Softcam DLL；系统摄像头使用项目原生 MF 后端。\n'
        '运行数据位于 %LOCALAPPDATA%/PhoneBridge；不含作者个人配置、API 令牌或签名私钥。\n'
        '自有代码采用 MIT；第三方许可独立适用。来源与依赖分发审计、发布签名尚未完成，仅本地测试，不公开发布。\n'
        '详见 _internal/docs/BUILDING.md 和 _internal/THIRD_PARTY_NOTICES.md。\n',encoding='utf-8')
    hashes={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(package.rglob('*')) if p.is_file()}
    (package/'SHA256-MANIFEST.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print('Executable built; creating developer archive.',flush=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as stream:
        for path in sorted(package.rglob('*')):
            if path.is_file():stream.write(path,'PhoneBridge/'+path.relative_to(package).as_posix())
    print(json.dumps({'executable':str(executable),'archive':str(archive),
                      'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}),flush=True)

if __name__=='__main__':
    main()
