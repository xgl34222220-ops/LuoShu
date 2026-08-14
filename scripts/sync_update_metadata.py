#!/usr/bin/env python3
"""Generate the standard Magisk-compatible LuoShu update JSON for one release."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def artifact_version(version: str) -> str:
    value = version.strip()
    if not value:
        raise ValueError("version is empty")
    if not value.startswith("v"):
        value = f"v{value}"
    return re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip("-")


def build_metadata(
    *,
    repository: str,
    version: str,
    version_code: int,
    tag: str,
    notes_file: str,
) -> dict[str, object]:
    if "/" not in repository or repository.startswith("/") or repository.endswith("/"):
        raise ValueError("repository must be owner/name")
    if version_code <= 0:
        raise ValueError("versionCode must be positive")
    tag = tag.strip()
    if not tag:
        raise ValueError("tag is empty")
    artifact = artifact_version(version)
    release_root = f"https://github.com/{repository}/releases/download/{tag}"
    return {
        "version": version.strip(),
        "versionCode": version_code,
        "zipUrl": f"{release_root}/LuoShu-{artifact}.zip",
        "changelog": f"https://raw.githubusercontent.com/{repository}/{tag}/{notes_file}",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--version-code", required=True, type=int)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--notes-file", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metadata = build_metadata(
        repository=args.repository,
        version=args.version,
        version_code=args.version_code,
        tag=args.tag,
        notes_file=args.notes_file,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
