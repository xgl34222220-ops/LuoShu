#!/usr/bin/env python3
"""Validate a generated v2.2 per-device payload without trusting build logs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCHEMA = "device-font-payload-v1"
MIN_FONT_BYTES = 1024


class VerifyError(RuntimeError):
    pass


def safe_relative(value: Any) -> Path:
    text = str(value or "")
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise VerifyError(f"非法负载路径：{text!r}")
    return path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify(manifest: dict[str, Any], root: Path, strict: bool) -> dict[str, Any]:
    if manifest.get("schema") != SCHEMA:
        raise VerifyError(f"不支持的负载清单：{manifest.get('schema')!r}")
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    mapped = int(summary.get("mapped") or 0)
    unsafe = int(summary.get("unsafe") or 0)
    unresolved = int(summary.get("unresolved") or 0)
    failures = int(summary.get("failures") or 0)
    if mapped <= 0:
        raise VerifyError("负载没有可应用槽位")
    if strict and (unsafe or unresolved or failures):
        raise VerifyError(
            f"严格门禁拒绝负载：unsafe={unsafe} unresolved={unresolved} failures={failures}"
        )

    generated = manifest.get("generated") if isinstance(manifest.get("generated"), list) else []
    if not generated:
        raise VerifyError("负载没有生成字体")
    known: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for item in generated:
        if not isinstance(item, dict):
            raise VerifyError("生成字体记录格式错误")
        relative = safe_relative(item.get("path"))
        if relative.parts[0] != "fonts" or relative.suffix.lower() != ".ttf":
            raise VerifyError(f"生成字体不在受控目录：{relative}")
        path = root / relative
        if not path.is_file():
            raise VerifyError(f"生成字体不存在：{relative}")
        actual = path.stat().st_size
        expected = int(item.get("bytes") or 0)
        if actual < MIN_FONT_BYTES or actual != expected:
            raise VerifyError(f"生成字体大小不匹配：{relative} expected={expected} actual={actual}")
        signature = str(item.get("signature") or "")
        filename = str(item.get("filename") or "")
        if len(signature) != 64 or filename != relative.name:
            raise VerifyError(f"生成字体身份无效：{relative}")
        known[filename] = item
        total_bytes += actual

    mapped_slots = 0
    for slot in manifest.get("slots") or []:
        if not isinstance(slot, dict) or not slot.get("generatedFile"):
            continue
        filename = str(slot["generatedFile"])
        if filename not in known:
            raise VerifyError(f"槽位引用未知字体：{filename}")
        if slot.get("planStatus") != "ready":
            raise VerifyError(f"槽位状态与生成结果冲突：{slot.get('family', '')}")
        mapped_slots += 1
    if mapped_slots != mapped:
        raise VerifyError(f"槽位计数不匹配：summary={mapped} actual={mapped_slots}")

    return {
        "status": "ok",
        "mapped": mapped_slots,
        "uniqueFonts": len(known),
        "bytes": total_bytes,
        "unsafe": unsafe,
        "unresolved": unresolved,
        "failures": failures,
        "manifestSha256": digest(root / "manifest.json") if (root / "manifest.json").is_file() else "",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = verify(manifest, args.root, args.strict)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"status": "error", "message": str(exc) or exc.__class__.__name__},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
