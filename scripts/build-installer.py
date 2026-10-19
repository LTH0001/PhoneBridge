"""Wrap a verified onefile build in a per-user Inno Setup installer.

No compiler download, elevation, driver installation or Git upload is performed.
The caller must provide Inno Setup 6.7+ and the onefile EXE to package.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from phonebridge import __version__


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def validate_bundle(executable,apk):
    """Reject stale/wrong APKs; never silently wrap an arbitrary executable."""
    from PyInstaller.archive.readers import CArchiveReader
    reader=CArchiveReader(str(executable))
    names={name.replace('\\','/'):name for name in reader.toc}
    target='android/app/build/phonebridge.apk'
    if target not in names:
        raise ValueError('Expected a PhoneBridge onefile EXE with embedded APK')
    if hashlib.sha256(reader.extract(names[target])).hexdigest()!=sha256(apk):
        raise ValueError('Embedded APK differs from current APK; rebuild the onefile EXE')
    for required in ('LICENSE','THIRD_PARTY_NOTICES.md'):
        if required not in names or reader.extract(names[required])!=(ROOT/required).read_bytes():
            raise ValueError('Missing or stale embedded notice: '+required)
    if executable.name!=f'PhoneBridge-{__version__}-windows-x64.exe':
        raise ValueError('Input EXE filename does not match the source version')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--iscc',type=Path,required=True)
    parser.add_argument('--chinese-language',type=Path,help='Optional compatible ChineseSimplified.isl')
    parser.add_argument('--chinese-license',type=Path,help='License for the optional Chinese translation')
    args=parser.parse_args()
    if os.name!='nt':raise SystemExit('Windows build required')
    if not re.fullmatch(r'\d+\.\d+\.\d+',__version__):raise SystemExit('Invalid version')
    exe=args.exe.resolve();compiler=args.iscc.resolve();apk=ROOT/'android/app/build/phonebridge.apk'
    for path in (exe,compiler,apk):
        if not path.is_file() or path.is_symlink():raise SystemExit('Required regular file missing: '+str(path))
    validate_bundle(exe,apk)
    if args.chinese_language and (not args.chinese_license or not args.chinese_license.is_file()):
        raise SystemExit('--chinese-license is required with --chinese-language')
    compiler_license=compiler.parent/'license.txt'
    if not compiler_license.is_file():raise SystemExit('Inno Setup license.txt is missing')
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    stage=ROOT/'runtime/build-installer'/stamp
    output=ROOT/'dist'/f'PhoneBridge-{__version__}-dev-setup-{stamp}'
    stage.mkdir(parents=True,exist_ok=False);output.mkdir(parents=True,exist_ok=False)
    for source,name in ((exe,'PhoneBridge.exe'),(apk,'PhoneBridge-Android.apk'),(ROOT/'LICENSE','LICENSE'),(ROOT/'THIRD_PARTY_NOTICES.md','THIRD_PARTY_NOTICES.md')):
        shutil.copy2(source,stage/name)
    notices='Inno Setup - https://jrsoftware.org/\n\n'+compiler_license.read_text(encoding='utf-8-sig')
    if args.chinese_language:
        notices+='\n\nChinese Simplified translation - https://github.com/kira-96/Inno-Setup-Chinese-Simplified-Translation\n\n'+args.chinese_license.read_text(encoding='utf-8-sig')
    (stage/'INSTALLER-LICENSES.txt').write_text(notices,encoding='utf-8-sig')
    (stage/'INSTALL-NOTES.txt').write_text(
        'PhoneBridge '+__version__+' - 开发预览版 / Development preview\n\n'
        '可选择安装位置，并选择是否创建桌面快捷方式；开始菜单入口默认创建。\n'
        '安装程序无需管理员权限；若要安装到受保护目录，请选择有写入权限的位置。\n'
        '运行数据保存在 %LOCALAPPDATA%\\PhoneBridge，升级与卸载均保留。\n'
        '更新前请先退出旧版 PhoneBridge。卸载不会自动卸载共享驱动。\n'
        '安装器不会安装驱动、开启自启动、修改防火墙或绕过手机授权。\n'
        '手机仍需单独确认 APK 安装。当前推荐 USB 调试连接，AOA/无线为实验功能。\n'
        '未签名；第三方分发与干净机器兼容性验证尚未全部完成。\n'
        'Choose an install directory and optional desktop shortcut. Start menu entries are included.\n'
        'Close PhoneBridge before updating. User data and shared drivers are not removed on uninstall.\n'
        'No drivers, autostart, firewall changes or Android authorization bypass are performed.\n'
        'Unsigned development preview. Review third-party notices before redistribution.\n',encoding='utf-8-sig')
    command=[str(compiler),'/DAppVersion='+__version__,'/DPayloadDir='+str(stage),'/DOutputDir='+str(output)]
    if args.chinese_language:
        language=args.chinese_language.resolve()
        if not language.is_file():raise SystemExit('Chinese language file missing')
        command.append('/DChineseLanguage='+str(language))
    command.append(str(ROOT/'scripts/phonebridge-setup.iss'))
    subprocess.run(command,check=True)
    setup=output/f'PhoneBridge-Setup-{__version__}-windows-x64.exe'
    manifest={'version':__version__,'setup':setup.name,'sha256':sha256(setup),
              'input_exe_sha256':sha256(exe),'apk_sha256':sha256(apk),'signed':False,
              'compiler_sha256':sha256(compiler),'created_at':stamp}
    (output/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(manifest['sha256']+'  '+setup.name+'\n',encoding='ascii')
    print(json.dumps({'installer':str(setup),'sha256':manifest['sha256']},ensure_ascii=True))


if __name__=='__main__':main()
