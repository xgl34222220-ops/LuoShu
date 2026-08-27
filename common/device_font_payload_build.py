#!/usr/bin/env python3
# Packaging contract marker: device-font-payload-v1
"""Per-device builder plus HyperOS physical slots that bypass fonts.xml."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import device_font_payload_build_base as _base
from device_font_payload_build_base import *  # noqa: F401,F403

_ORIGINAL_BUILD_SIGNATURE = _base.build_signature
_ORIGINAL_BUILD_PAYLOAD = _base.build_payload
_HYPEROS_DIRECT = re.compile(
    r"^(?:MiSans(?:VF(?:_Overlay)?|LatinVF|TCVF|L3|Clock[A-Za-z0-9_.-]*)|"
    r"Mitype[A-Za-z0-9_.-]*|MiClock[A-Za-z0-9_.-]*|AndroidClock[A-Za-z0-9_.-]*|Clockopia|"
    r"GoogleSans(?:Text|Flex)?[A-Za-z0-9_.-]*|Roboto(?:Flex|Static)?[A-Za-z0-9_.-]*|"
    r"SourceSansPro[A-Za-z0-9_.-]*|(?:100|200|300|350|400|500|600|700|800|900))"
    r"\.(?:ttf|otf|ttc|otc)$", re.I
)
_DENY = ("italic", "oblique", "emoji", "symbol", "icon", "serif", "math", "music")
_ROOTS = ("system", "system_ext", "product", "mi_ext", "my_product", "vendor", "odm", "oem", "cust", "hw_product")


def build_signature(slot: dict[str, Any], source_profile: dict[str, Any], source_weight: int) -> str:
    return _ORIGINAL_BUILD_SIGNATURE(slot, source_profile, source_weight)


def _weight(name: str) -> int:
    lower = name.lower().replace("-", "").replace("_", "")
    hit = re.search(r"(?:^|[^0-9])(100|200|300|350|400|500|600|700|800|900)(?:[^0-9]|$)", name)
    if hit:
        return int(hit.group(1))
    for token, value in (("thin",100),("extralight",200),("light",300),("medium",500),("semibold",600),("bold",700),("extrabold",800),("black",900)):
        if token in lower:
            return value
    return 400


def _roles(name: str) -> list[str]:
    lower = name.lower()
    if any(token in lower for token in _DENY) or not _HYPEROS_DIRECT.fullmatch(name):
        return []
    if "clock" in lower:
        return ["clock", "global-ui"]
    if "mono" in lower:
        return ["mono", "global-ui"]
    if lower.startswith("mitype"):
        return ["display", "global-ui"]
    return ["global-ui"]


def _stock_file(module: Path, partition: str, name: str) -> Path | None:
    logical = Path("/") / partition / "fonts" / name
    state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
    lower = state_root / "lower" / f"{partition}-fonts" / name
    if lower.is_file():
        return lower
    for prefix in (Path("/debug_ramdisk/.magisk/mirror"), Path("/sbin/.magisk/mirror"), Path("/data/adb/magisk/mirror")):
        candidate = prefix / partition / "fonts" / name
        if candidate.is_file():
            return candidate
    if (module / partition / "fonts" / name).exists():
        return None
    return logical if logical.is_file() else None


def _enrich_hyperos(template: dict[str, Any]) -> dict[str, Any]:
    module = Path(__file__).resolve().parent.parent
    slots = template.get("slots") if isinstance(template.get("slots"), list) else []
    existing = {str(item.get("resolvedPath", "")) for item in slots if isinstance(item, dict)}
    candidates: list[tuple[str, str, Path, list[str]]] = []
    hyperos_marker = False
    for partition in _ROOTS:
        lower_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount")) / "lower" / f"{partition}-fonts"
        live_root = Path("/") / partition / "fonts"
        names: set[str] = set()
        for root in (lower_root, live_root):
            if not root.is_dir():
                continue
            try:
                names.update(item.name for item in root.iterdir() if item.is_file())
            except OSError:
                pass
        for name in sorted(names):
            roles = _roles(name)
            if not roles:
                continue
            if name.lower().startswith(("misans", "mitype", "miclock")):
                hyperos_marker = True
            logical = str(Path("/") / partition / "fonts" / name)
            if logical in existing:
                continue
            stock = _stock_file(module, partition, name)
            if stock is not None:
                candidates.append((partition, name, stock, roles))
    if not hyperos_marker:
        return template
    for partition, name, stock, roles in candidates:
        logical = str(Path("/") / partition / "fonts" / name)
        try:
            profile = _base.template_engine.inspect_font(stock, -1, hash_fonts=False)
        except Exception:
            continue
        slots.append({
            "family": f"physical-{name}", "familyNormalized": f"physical-{name}".lower(),
            "familyAttributes": {}, "sourceXml": "", "declared": name, "postScriptName": "",
            "weight": _weight(name), "style": "normal", "index": 0, "axes": "",
            "roles": roles, "replaceable": True, "resolvedPath": logical,
            "directPhysical": True, "font": profile,
        })
        existing.add(logical)
    template["slots"] = slots
    summary = template.setdefault("summary", {})
    summary["slots"] = len(slots)
    summary["replaceable"] = sum(1 for item in slots if item.get("replaceable"))
    summary["directPhysical"] = sum(1 for item in slots if item.get("directPhysical"))
    return template


def build_payload(template, source_dir, source_prefix, output_dir, manifest_path):
    return _ORIGINAL_BUILD_PAYLOAD(_enrich_hyperos(template), source_dir, source_prefix, output_dir, manifest_path)


_base.build_signature = build_signature
_base.build_payload = build_payload


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
