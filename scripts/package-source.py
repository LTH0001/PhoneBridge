"""Export audited source to a new folder and ZIP, without Git mutations."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
from release_source import audit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from phonebridge import __version__


def main():
    files, problems = audit()
    if problems:
        raise SystemExit('\n'.join(problems))
    output = ROOT/'dist'
    output.mkdir(exist_ok=True)
    name = f'PhoneBridge-{__version__}-github-source-{datetime.datetime.now():%Y%m%d-%H%M%S}'
    folder, archive = output/name, output/(name+'.zip')
    if folder.exists() or archive.exists():
        raise SystemExit('Output exists; refusing to overwrite.')
    folder.mkdir()
    hashes = {}
    for path in files:
        relative = path.relative_to(ROOT)
        target = folder/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    # Keep generated metadata alongside (not inside) the clean GitHub source tree.
    manifest = output/(name+'.manifest.json')
    with manifest.open('x', encoding='utf-8') as stream:
        json.dump(hashes, stream, indent=2)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as stream:
        for relative in sorted(hashes):
            stream.write(folder/relative, 'PhoneBridge/'+relative)
    print(json.dumps({'source_folder':str(folder), 'archive':str(archive),
                     'manifest':str(manifest), 'files':len(files),
                     'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
