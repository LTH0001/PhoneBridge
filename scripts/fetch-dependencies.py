"""Fetch a pinned asset on request. Never install, execute or extract it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def checked_target(root, name):
    root = Path(root).resolve()
    target = root/name
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Invalid dependency target')
    if not target.resolve().is_relative_to(root/'vendor'):
        raise ValueError('Dependency target must stay inside vendor')
    for part in (target, *target.parents):
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Dependency target contains a link')
    return target


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(item, dry_run=False):
    target = checked_target(ROOT, item['path'])
    if not item['url'].startswith('https://'):
        raise ValueError('HTTPS required')
    if target.exists():
        if digest(target) != item['sha256']:
            raise ValueError('Existing file has wrong hash; inspect manually: '+item['path'])
        print(item['path']+': verified')
        return
    if dry_run:
        print(item['path']+': download required (dry run)')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='PhoneBridge-dependency-') as temporary:
        download = Path(temporary)/'download'
        with urllib.request.urlopen(item['url'], timeout=60) as response, download.open('wb') as output:
            if not response.geturl().startswith('https://'):
                raise ValueError('Non-HTTPS redirect rejected')
            shutil.copyfileobj(response, output)
        if digest(download) != item['sha256']:
            raise ValueError('Download hash mismatch: '+item['path'])
        with target.open('xb') as output, download.open('rb') as source:
            shutil.copyfileobj(source, output)
    print(item['path']+': downloaded and verified; see docs/DEPENDENCIES.md for licenses')


def main():
    items = json.loads((ROOT/'scripts/dependencies.json').read_text())['downloads']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dependency', choices=sorted(items))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    fetch(items[args.dependency], args.dry_run)


if __name__ == '__main__':
    main()
