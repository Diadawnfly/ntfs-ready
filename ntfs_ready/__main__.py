"""Run with python3 -m ntfs_ready; never launch the entire CLI with sudo."""
from .cli import main

if __name__ == '__main__':
    raise SystemExit(main())
