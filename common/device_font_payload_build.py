#!/usr/bin/env python3
"""Build a complete per-device font payload from captured stock slots.

The builder consumes the ROM template and LuoShu's prepared 100-900 source files.
Every slot is planned against the matching source weight, equivalent contracts are
deduplicated, and a failed build never replaces the previous complete cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import device_font_slot_build as slot_builder
import device_font_slot_plan as slot_planner
import device_font_template as template_engine

SCHEMA = "device-font-payload-v1"
TEMPLATE_SCHEMA = "device-font-template-v1"
WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)


class PayloadError(RuntimeError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def atomic_json(payload: dict[str, Any], output: Path, mode: int = 0o600) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_raw = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temporary = Path(temporary_raw)
    try:
        temporary.write_bytes(canonical(payload))
        os.chmod(temporary, mode)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def available_sources(source_dir: Path, prefix: str) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for weight in WEIGHTS:
        for suffix in (".ttf", ".otf", ".ttc", ".TTF", ".OTF", ".TTC"):
            candidate = source_dir / f"{prefix}-{weight}{suffix}"
            if candidate.is_file() and candidate.stat().st_size >= 1024:
                result[weight] = candidate
                break
    if not result:
        raise PayloadError(f"没有找到 {prefix}-100..900 字重源文件：{source_dir}")
    return result


def nearest_source(sources: dict[int, Path], weight: int) -> tuple[int, Path]:
    selected = min(sources, key=lambda item: (abs(item - weight), item > weight, item))
    return selected, sources[selected]


def source_profiles(sources: dict[int, Path]) -> dict[int, dict[str, Any]]:
    profiles: dict[int, dict[str, Any]] = {}
    by_identity: dict[tuple[int, int, int], dict[str, Any]] = {}
    for weight, path in sources.items():
        stat = path.stat()
        identity = (int(stat.st_dev), int(stat.st_ino), int(stat.st_size))
        profile = by_identity.get(identity)
        if profile is None:
            profile = template_engine.inspect_font(path, -1, hash_fonts=True)
            by_identity[identity] = profile
        profiles[weight] = profile
    return profiles


def build_signature(slot: dict[str, Any], source_profile: dict[str, Any], source_weight: int) -> str:
    signature = {
        "engine": slot_builder.SCHEMA,
        "sourceSha256": source_profile.get("sha256", ""),
        "sourceFaceIndex": source_profile.get("faceIndex", -1),
        "sourceWeight": source_weight,
        "targetWeight": slot.get("weight", 400),
        "style": slot.get("style", "normal"),
        "roles": sorted(slot.get("roles") or []),
        "lineContract": slot.get("lineContract", {}),
        "transforms": slot.get("transforms", {}),
        "advancePolicy": slot.get("targetAdvancePolicy", ""),
        "outlinePolicy": slot.get("targetOutlinePolicy", ""),
    }
    return hashlib.sha256(canonical(signature)).hexdigest()


def safe_slot_record(original: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "family": original.get("family", ""),
        "familyNormalized": original.get("familyNormalized", ""),
        "familyAttributes": original.get("familyAttributes", {}),
        "sourceXml": original.get("sourceXml", ""),
        "declared": original.get("declared", ""),
        "postScriptName": original.get("postScriptName", ""),
        "weight": original.get("weight", 400),
        "style": original.get("style", "normal"),
        "index": original.get("index", 0),
        "axes": original.get("axes", ""),
        "roles": original.get("roles", []),
        "replaceable": bool(original.get("replaceable")),
        "stockPath": original.get("resolvedPath", ""),
        "planStatus": plan.get("status", "unresolved"),
        "planReason": plan.get("reason", ""),
    }


def commit_directory(stage: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = output.with_name(f".{output.name}.previous.{os.getpid()}")
    shutil.rmtree(backup, ignore_errors=True)
    moved_old = False
    try:
        if output.exists():
            os.replace(output, backup)
            moved_old = True
        os.replace(stage, output)
        if moved_old:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if not output.exists() and moved_old and backup.exists():
            os.replace(backup, output)
        raise


def build_payload(
    template: dict[str, Any],
    source_dir: Path,
    source_prefix: str,
    output_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    if template.get("schema") != TEMPLATE_SCHEMA:
        raise PayloadError(f"不支持的设备模板：{template.get('schema')!r}")
    slots = template.get("slots") if isinstance(template.get("slots"), list) else []
    if not slots:
        raise PayloadError("设备模板没有字体槽")

    sources = available_sources(source_dir, source_prefix)
    profiles = source_profiles(sources)
    stage = output_dir.with_name(f".{output_dir.name}.stage.{os.getpid()}")
    shutil.rmtree(stage, ignore_errors=True)
    fonts_dir = stage / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    generated_by_signature: dict[str, dict[str, Any]] = {}
    manifest_slots: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    unsafe = 0
    unresolved = 0
    skipped = 0
    try:
        for index, original in enumerate(slots):
            if not isinstance(original, dict):
                continue
            target_weight = int(original.get("weight") or 400)
            source_weight, source_path = nearest_source(sources, target_weight)
            source_profile = profiles[source_weight]
            plan = slot_planner.slot_plan(original, source_profile)
            record = safe_slot_record(original, plan)
            record.update(
                {
                    "slotIndex": index,
                    "sourceWeight": source_weight,
                    "sourcePath": str(source_path),
                    "sourceSha256": source_profile.get("sha256", ""),
                }
            )
            status = plan.get("status")
            if status == "skipped":
                skipped += 1
                manifest_slots.append(record)
                continue
            if status == "unsafe":
                unsafe += 1
                manifest_slots.append(record)
                continue
            if status != "ready":
                unresolved += 1
                manifest_slots.append(record)
                continue

            signature = build_signature(plan, source_profile, source_weight)
            generated = generated_by_signature.get(signature)
            if generated is None:
                filename = f"LuoShuSlot-{signature[:20]}-{target_weight}.ttf"
                destination = fonts_dir / filename
                try:
                    report = slot_builder.build_slot(source_path, -1, plan, destination)
                except Exception as exc:
                    failure = {
                        "slotIndex": index,
                        "family": original.get("family", ""),
                        "weight": target_weight,
                        "message": str(exc) or exc.__class__.__name__,
                    }
                    failures.append(failure)
                    raise PayloadError(
                        f"槽位生成失败：{failure['family']} {target_weight}：{failure['message']}"
                    ) from exc
                generated = {
                    "signature": signature,
                    "filename": filename,
                    "path": str(destination),
                    "sourceWeight": source_weight,
                    "sourceSha256": source_profile.get("sha256", ""),
                    "bytes": destination.stat().st_size,
                    "report": report,
                    "references": 0,
                }
                generated_by_signature[signature] = generated
            generated["references"] += 1
            record.update(
                {
                    "signature": signature,
                    "generatedFile": generated["filename"],
                    "generatedBytes": generated["bytes"],
                    "plan": plan,
                }
            )
            manifest_slots.append(record)

        generated_files = sorted(generated_by_signature.values(), key=lambda item: item["filename"])
        if not generated_files:
            raise PayloadError("没有可安全生成的替换槽位")
        for item in generated_files:
            item["path"] = f"fonts/{item['filename']}"

        payload = {
            "schema": SCHEMA,
            "deviceFingerprint": template.get("fingerprint", ""),
            "templateSchema": TEMPLATE_SCHEMA,
            "sourcePrefix": source_prefix,
            "sourceDir": str(source_dir),
            "summary": {
                "slots": len(manifest_slots),
                "mapped": sum(1 for item in manifest_slots if item.get("generatedFile")),
                "uniqueFonts": len(generated_files),
                "deduplicatedReferences": sum(max(0, int(item["references"]) - 1) for item in generated_files),
                "unsafe": unsafe,
                "unresolved": unresolved,
                "skipped": skipped,
                "failures": len(failures),
            },
            "sources": {
                str(weight): {
                    "path": str(path),
                    "sha256": profiles[weight].get("sha256", ""),
                    "faceIndex": profiles[weight].get("faceIndex", -1),
                }
                for weight, path in sorted(sources.items())
            },
            "generated": generated_files,
            "slots": manifest_slots,
            "failures": failures,
        }
        atomic_json(payload, stage / "manifest.json")
        commit_directory(stage, output_dir)
        final_manifest = output_dir / "manifest.json"
        if manifest_path != final_manifest:
            atomic_json(payload, manifest_path)
        return payload
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--source-prefix", default="LuoShu")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = args.manifest or (args.output_dir / "manifest.json")
    try:
        template = json.loads(args.template.read_text(encoding="utf-8"))
        payload = build_payload(template, args.source_dir, args.source_prefix, args.output_dir, manifest)
        print(
            json.dumps(
                {"status": "ok", **payload["summary"], "output": str(args.output_dir), "manifest": str(manifest)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
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
