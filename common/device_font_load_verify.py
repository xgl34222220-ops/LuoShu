#!/usr/bin/env python3
"""Deep verification for a generated LuoShu device font payload.

A visible mount proves only that bytes reached Android's namespace.  The result is
reported as verified only when the mounted payload is intact, its global UI face
still has complete text coverage, and FontManagerService names a generated LuoShu
file or family.  Mount-only evidence remains unverified.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont

PAYLOAD_SCHEMA = "device-font-payload-v1"
OVERLAY_SCHEMA = "device-font-overlay-v1"
SCHEMA = "device-font-load-verification-v2"
CJK = tuple(map(ord, "一丁七万三上下不与中为主人了二于五人今从他会但你作使入全国其分到前力十又只可同后和在地大天好学家小年心我日时有来民生的看种行要见言这"))
LATIN = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGITS = tuple(map(ord, "0123456789"))


class VerifyError(RuntimeError):
    pass


def normalize(value: str) -> str:
    return re.sub(r"[\s_-]+", "-", str(value or "").strip().lower()).strip("-")


def safe_family(slot: dict[str, Any]) -> str:
    family = str(slot.get("familyNormalized") or slot.get("family") or "luoshu-slot")
    safe = "".join(char if char.isalnum() else "-" for char in family).strip("-") or "LuoShuSlot"
    return f"luoshuslot-{safe.lower()}-{int(slot.get('weight') or 400)}"


def load_json(path: Path, schema: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != schema:
        raise VerifyError(f"不支持的清单：{path.name} schema={value.get('schema')!r}")
    return value


def load_mounts(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = raw.split("|", 5)
        if len(parts) != 6:
            continue
        relative, visible, status, expected_hash, actual_hash, size = parts
        result.append({
            "relative": relative,
            "visible": visible,
            "status": status,
            "expectedSha256": expected_hash,
            "actualSha256": actual_hash,
            "bytes": int(size) if size.isdigit() else 0,
        })
    return result


def dynamic_families(overlay: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for report in overlay.get("dynamic") or []:
        if not isinstance(report, dict):
            continue
        for family in report.get("removedFamilies") or []:
            value = normalize(str(family))
            if value and value not in result:
                result.append(value)
    return result


def usable_ratio(font: TTFont, probes: tuple[int, ...]) -> tuple[float, int]:
    cmap = font.getBestCmap() or {}
    glyph_order = set(font.getGlyphOrder())
    names: set[str] = set()
    hits = 0
    for codepoint in probes:
        glyph = cmap.get(codepoint)
        if not glyph or glyph == ".notdef" or glyph not in glyph_order:
            continue
        hits += 1
        names.add(glyph)
    return (hits / len(probes) if probes else 1.0), len(names)


def verify_global_coverage(payload: dict[str, Any], mounts: list[dict[str, Any]]) -> dict[str, Any]:
    wanted = {
        str(slot.get("generatedFile"))
        for slot in payload.get("slots") or []
        if isinstance(slot, dict)
        and "global-ui" in {str(role) for role in slot.get("roles") or []}
        and slot.get("generatedFile")
    }
    checked: list[str] = []
    failed: list[str] = []
    seen: set[str] = set()
    for mount in mounts:
        relative = str(mount.get("relative") or "")
        if Path(relative).name not in wanted or mount.get("status") != "ok":
            continue
        fingerprint = str(mount.get("actualSha256") or relative)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        visible = Path(str(mount.get("visible") or ""))
        try:
            font = TTFont(str(visible), lazy=True, recalcTimestamp=False)
            try:
                cjk_ratio, cjk_unique = usable_ratio(font, CJK)
                latin_ratio, _ = usable_ratio(font, LATIN)
                digit_ratio, _ = usable_ratio(font, DIGITS)
            finally:
                font.close()
            valid = (
                cjk_ratio >= 0.95
                and cjk_unique >= max(12, int(len(CJK) * cjk_ratio * 0.75))
                and latin_ratio == 1.0
                and digit_ratio == 1.0
            )
        except Exception:
            valid = False
        checked.append(relative)
        if not valid:
            failed.append(relative)
        if len(checked) >= 8:
            break
    return {"checked": checked, "failed": failed}


def verify(
    payload: dict[str, Any],
    overlay: dict[str, Any],
    font_dump: str,
    mounts: list[dict[str, Any]],
    active_font: str,
    engine: dict[str, str],
) -> dict[str, Any]:
    copied = overlay.get("copiedFonts") if isinstance(overlay.get("copiedFonts"), list) else []
    expected_paths = {
        str(item.get("path"))
        for item in copied
        if isinstance(item, dict) and item.get("path")
    }
    mount_by_rel = {str(item.get("relative")): item for item in mounts}
    missing_mounts = sorted(path for path in expected_paths if path not in mount_by_rel)
    bad_mounts = sorted(
        path for path in expected_paths
        if path in mount_by_rel and mount_by_rel[path].get("status") != "ok"
    )

    generated_files = sorted({
        str(slot.get("generatedFile"))
        for slot in payload.get("slots") or []
        if isinstance(slot, dict) and slot.get("generatedFile")
    })
    slot_names = sorted({
        safe_family(slot)
        for slot in payload.get("slots") or []
        if isinstance(slot, dict) and slot.get("generatedFile")
    })
    dynamic = dynamic_families(overlay)
    dump_lower = font_dump.lower()
    normalized_dump = normalize(dump_lower)
    file_hits = sorted(name for name in generated_files if name.lower() in dump_lower)
    slot_hits = sorted(name for name in slot_names if name in dump_lower)
    dynamic_hits = sorted(name for name in dynamic if name in normalized_dump or name in dump_lower.replace("_", "-"))
    dynamic_missing = sorted(set(dynamic) - set(dynamic_hits))
    coverage = verify_global_coverage(payload, mounts)

    reasons: list[str] = []
    state = "unverified"
    mode = "mount-only"
    if not expected_paths:
        reasons.append("visible-font-manifest-empty")
    if missing_mounts:
        state, mode = "failed", "compatibility"
        reasons.append("visible-mount-evidence-missing")
    if bad_mounts:
        state, mode = "failed", "compatibility"
        reasons.append("visible-font-hash-mismatch")
    if coverage["failed"]:
        state, mode = "failed", "compatibility"
        reasons.append("runtime-global-face-incomplete")

    font_manager_confirmed = bool(file_hits or slot_hits)
    mount_confirmed = bool(expected_paths) and not missing_mounts and not bad_mounts
    if not font_dump.strip():
        reasons.append("font-manager-dump-unavailable")
    elif not font_manager_confirmed:
        reasons.append("generated-font-not-found-in-font-manager-dump")

    if dynamic_missing:
        if font_dump.strip() and font_manager_confirmed:
            state, mode = "failed", "compatibility"
            reasons.append("dynamic-family-not-loaded")
        else:
            reasons.append("dynamic-family-unconfirmed")

    if state != "failed":
        if mount_confirmed and font_manager_confirmed:
            # Keep the historical `aligned` public mode so existing App builds
            # understand the stronger verifier without treating it as unknown.
            state, mode = "verified", "aligned"
            reasons.append("font-manager-confirmed-generated-font")
        elif mount_confirmed:
            state, mode = "unverified", "mount-only"
            reasons.append("visible-mounts-do-not-prove-font-selection")
        else:
            state, mode = "unverified", "compatibility"

    summary = overlay.get("summary") if isinstance(overlay.get("summary"), dict) else {}
    return {
        "schema": SCHEMA,
        "state": state,
        "mode": mode,
        "activeFont": active_font,
        "time": int(time.time()),
        "engine": engine,
        "summary": {
            "expectedVisibleFonts": len(expected_paths),
            "mountEvidence": len(mounts),
            "missingMounts": len(missing_mounts),
            "badMounts": len(bad_mounts),
            "generatedFiles": len(generated_files),
            "fontManagerFileHits": len(file_hits),
            "fontManagerSlotHits": len(slot_hits),
            "dynamicFamilies": len(dynamic),
            "dynamicFamilyHits": len(dynamic_hits),
            "coverageSlotsChecked": len(coverage["checked"]),
            "coverageSlotsFailed": len(coverage["failed"]),
            "mappedSlots": int(summary.get("mappedSlots") or 0),
        },
        "reasons": reasons,
        "missingMounts": missing_mounts,
        "badMounts": bad_mounts,
        "fontManagerFileHits": file_hits,
        "fontManagerSlotHits": slot_hits,
        "dynamicFamilies": dynamic,
        "dynamicFamilyHits": dynamic_hits,
        "dynamicFamilyMissing": dynamic_missing,
        "coverageChecked": coverage["checked"],
        "coverageFailed": coverage["failed"],
    }


def parse_engine(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key and value:
                result[key] = value
    return result


def atomic_write(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument("--font-dump", required=True, type=Path)
    parser.add_argument("--mount-evidence", required=True, type=Path)
    parser.add_argument("--engine-state", required=True, type=Path)
    parser.add_argument("--active-font", default="unknown")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = verify(
            load_json(args.payload, PAYLOAD_SCHEMA),
            load_json(args.overlay, OVERLAY_SCHEMA),
            args.font_dump.read_text(encoding="utf-8", errors="replace") if args.font_dump.is_file() else "",
            load_mounts(args.mount_evidence),
            args.active_font,
            parse_engine(args.engine_state),
        )
        atomic_write(result, args.output)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0 if result["state"] == "verified" else 2
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "state": "failed",
            "mode": "compatibility",
            "activeFont": args.active_font,
            "time": int(time.time()),
            "reasons": ["verifier-error"],
            "message": str(exc) or exc.__class__.__name__,
        }
        try:
            atomic_write(result, args.output)
        except Exception:
            pass
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
