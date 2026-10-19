"""Public-source allowlist; installed dependencies and local data stay private."""
import os
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parent.parent
EXACT = {'.gitignore', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
         'CONTRIBUTING.md', 'SECURITY.md', 'CHANGELOG.md', 'requirements.txt',
         'requirements-build.txt', 'constraints-windows-py313.txt', 'start.bat', 'start.ps1',
         'android/app/AndroidManifest.xml', 'vendor/README.md'}
SCRIPTS = {'setup.ps1', 'java-tools.ps1', 'build-android.ps1', 'build-mf-camera.ps1',
           'build-windows.py', 'frozen-entry.py', 'check-panel-gestures.ps1',
           'release_source.py', 'audit-source.py', 'package-source.py',
           'fetch-dependencies.py', 'dependencies.json', 'cpu-temperature.ps1',
           'CpuTemperature.cs', 'display-driver.ps1', 'vdd_settings.xml',
           'install-mf-camera.ps1', 'register-camera-system.ps1',
           'setup-temperature.ps1', 'wireless-firewall.ps1', 'install-audio.ps1',
           'usb-accessory.py'}
DOCS = {'BUILDING.md', 'DEPENDENCIES.md', 'ARCHITECTURE.md', 'RELEASING.md'}
PREFIXES = ('phonebridge/', 'android/app/src/', 'android/app/res/',
            'native/mf-camera/', 'assets/brand/', 'tests/', '.github/')
EXTENSIONS = {'.py', '.java', '.xml', '.c', '.cpp', '.cs', '.h', '.hpp',
              '.def', '.cmake', '.txt', '.html', '.svg', '.md', '.yml', '.yaml'}
EXCLUDED = {'build', 'runtime', '__pycache__', '.git', '.venv', 'dist', 'node_modules', 'local'}


def allowed(name):
    path = Path(name)
    if path.is_absolute() or any(p in EXCLUDED or p == '..' for p in path.parts):
        return False
    name = path.as_posix()
    if name in EXACT:
        return True
    if name.startswith('scripts/'):
        return name.removeprefix('scripts/') in SCRIPTS
    if name.startswith('docs/'):
        return name.removeprefix('docs/') in DOCS
    return name.startswith(PREFIXES) and path.suffix.lower() in EXTENSIONS


def is_link(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0)
                                   & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))


def files(root=ROOT):
    root = Path(root).resolve()
    result = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = [d for d in dirs if d not in EXCLUDED and not is_link(base/d)]
        if base == root/'vendor':
            dirs[:] = []
        for name in names:
            path = base/name
            if allowed(path.relative_to(root).as_posix()):
                if is_link(path):
                    raise ValueError('Source link is not allowed: '+str(path.relative_to(root)))
                result.append(path)
    return sorted(result)


RULES = {
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'personal-windows-path': re.compile(r'[A-Za-z]:[/\\]Users[/\\](?!Public\b|Example\b)[^\s/\\]+', re.I),
    'legacy-workspace': re.compile('AAA'+'中转站|dsh'+'web', re.I),
    'embedded-usb-serial': re.compile(r'USB\\VID_[0-9A-F]{4}&PID_[0-9A-F]{4}\\[0-9A-Z]{10,}', re.I),
}


def audit(root=ROOT):
    root = Path(root).resolve()
    selected = files(root)
    problems = []
    for path in selected:
        name = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            for rule, pattern in RULES.items():
                if pattern.search(line):
                    problems.append(f'{name}:{number}: {rule}')
    for required in EXACT:
        if not (root/required).is_file():
            problems.append(required+': missing required source file')
    return selected, problems
