"""Audit public source and Git-visible files without printing secret values."""
import subprocess
from release_source import ROOT, allowed, audit


def main():
    selected, problems = audit()
    if (ROOT/'.git').exists():
        result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                                cwd=ROOT, capture_output=True, check=True)
        for name in result.stdout.decode('utf-8').split('\0'):
            if name and not allowed(name):
                problems.append(name+': Git-visible file is outside public allowlist')
    for problem in problems:
        print(problem)
    print(f'Public-source audit: {len(selected)} files, {len(problems)} findings. Not a legal or complete secret audit.')
    return bool(problems)


if __name__ == '__main__':
    raise SystemExit(main())
