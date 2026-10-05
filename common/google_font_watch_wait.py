#!/usr/bin/env python3
"""Retired event-wait compatibility entry.

Font maintenance is now an explicit, supervised one-shot operation. Returning
the former deadline status immediately keeps older callers compatible without
an inotify handle, /proc scan, sleep, or idle font process.
"""
from __future__ import annotations


def main() -> int:
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
