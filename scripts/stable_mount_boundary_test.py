#!/usr/bin/env python3
"""Reject any accidental changes to the actual 1.1.1 mounting/commit engine."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'scripts/stable_mount_sha256.json').read_text())
for name, expected in manifest['files'].items():
    actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    assert actual == expected, f'Stable mount boundary changed: {name}'
print(f"Stable mount boundary: {len(manifest['files'])} files match {manifest['tag']} ({manifest['commit']}).")
