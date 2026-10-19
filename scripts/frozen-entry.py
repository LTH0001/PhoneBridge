"""PyInstaller entry point; all helper modes share the normal argument parser."""
from phonebridge.__main__ import main

if __name__=='__main__':
    raise SystemExit(main() or 0)
