#!/usr/bin/env python3
"""Discover the stock Android UI font slots for the current ROM.

The scanner is intentionally read-only. It runs while the module is being installed, before the
new LuoShu overlay is mounted, and records only replaceable UI text slots. Explicit family mappings
come from the stock fonts XML. OEM files that bypass fonts.xml are admitted only by conservative
filename heuristics and the existing font_check.sh validator.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from fontTools.ttLib import TTFont

SCHEMA = "device-font-inventory-v1"
INVENTORY_REVISION = 1
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}
LOGICAL_FONT_ROOTS = (
    ("system", Path("/system/fonts")),
    ("system_ext", Path("/system_ext/fonts")),
    ("product", Path("/product/fonts")),
    ("my_product", Path("/my_product/fonts")),
    ("vendor", Path("/vendor/fonts")),
)
MIRROR_PREFIXES = (
    Path("/debug_ramdisk/.magisk/mirror"),
    Path("/sbin/.magisk/mirror"),
    Path("/data/adb/magisk/mirror"),
)
UI_FAMILY_PREFIXES = (
    "sans-serif",
    "system-ui",
    "system-sans",
    "roboto",
    "google-sans",
    "googlesans",
    "mi-sans",
    "misans",
    "sys-sans",
    "syssans",
    "sysfont",
    "oplus-sans",
    "oplussans",
    "oppo-sans",
    "opposans",
    "coloros-sans",
)
DENY_FAMILY_TOKENS = ("serif", "mono", "emoji", "symbol", "icon", "math", "music")
SANS_SERIF_UI_SUFFIX_TOKENS = {
    "thin", "extralight", "extra-light", "light", "regular", "normal", "book", "medium",
    "semibold", "semi-bold", "bold", "extrabold", "extra-bold", "black", "heavy",
    "condensed", "compact", "smallcaps", "small-caps", "display", "text", "flex", "static",
}
DENY_FILE_TOKENS = ("emoji", "icon", "symbol", "math", "music", "serif")
HEURISTIC_PATTERNS = (
    re.compile(r"^MiSans(?:VF(?:_Overlay)?|LatinVF|TCVF|L3)\.(?:ttf|otf|ttc|otc)$", re.I),
    re.compile(r"^(?:100|200|300|350|400|500|600|700|800|900)\.ttf$", re.I),
    re.compile(
        r"^(?:Sys(?:Sans|Font)|OppoSans|Opposans|OPSans|OPlusSans|GoogleSans(?:Text|Flex)?|"
        r"Roboto(?:Flex|Static)?|SourceSansPro|DIN(?:Pro|Condensed)?|OPPODIN(?:Condensed)?)[A-Za-z0-9_.-]*"
        r"\.(?:ttf|otf|ttc|otc)$",
        re.I,
    ),
)
WEIGHT_WORDS = {
    "thin": 100,
    "extralight": 200,
    "ultralight": 200,
    "light": 300,
    "regular": 400,
    "normal": 400,
    "book": 400,
    "medium": 500,
    "semibold": 600,
    "demibold": 600,
    "bold": 700,
    "extrabold": 800,
    "ultrabold": 800,
    "black": 900,
    "heavy": 900,
}


class InventoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class FontRoot:
    partition: str
    logical: Path
    actual: Path


def _getprop(name: str) -> str:
    try:
        result = subprocess.run(
            ["getprop", name],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def current_build_key(explicit: str | None = None) -> tuple[str, str, str]:
    fingerprint = _getprop("ro.build.fingerprint")
    display_id = _getprop("ro.build.display.id")
    key = (explicit or fingerprint or display_id or "unknown").strip()
    return key, fingerprint, display_id


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def validate_inventory(data: dict[str, Any], expected_key: str | None = None) -> None:
    if data.get("schema") != SCHEMA or data.get("state") != "ready":
        raise InventoryError("设备字体清单格式无效")
    try:
        revision = int(data.get("inventoryRevision", 0))
    except (TypeError, ValueError) as error:
        raise InventoryError("设备字体清单版本无效") from error
    if revision != INVENTORY_REVISION:
        raise InventoryError("设备字体清单版本已过期")
    build_key = str(data.get("buildKey", ""))
    if expected_key and expected_key != "unknown" and build_key != expected_key:
        raise InventoryError("系统构建指纹已经变化")
    slots = data.get("slots")
    main_slot = data.get("mainSlot")
    main_path = str(data.get("mainSlotPath", main_slot.get("path", "") if isinstance(main_slot, dict) else ""))
    if not isinstance(slots, dict) or not slots or len(slots) > 2048 or not isinstance(main_slot, dict):
        raise InventoryError("设备字体清单没有可用槽位")
    try:
        declared_count = int(data.get("slotCount", len(slots)))
    except (TypeError, ValueError) as error:
        raise InventoryError("设备字体清单槽位数量无效") from error
    if declared_count != len(slots) or main_path not in slots:
        raise InventoryError("设备字体清单槽位索引不完整")

    allowed_prefixes = tuple(f"{logical}/" for _partition, logical in LOGICAL_FONT_ROOTS)
    for logical, entry in slots.items():
        if not isinstance(logical, str) or not logical.startswith(allowed_prefixes) or not isinstance(entry, dict):
            raise InventoryError("设备字体清单包含越界槽位")
        if str(entry.get("path", logical)) != logical:
            raise InventoryError("设备字体清单槽位路径不一致")
        if str(entry.get("format", "")) not in {"TTF", "OTF", "TTC"}:
            raise InventoryError("设备字体清单包含无效字体格式")
        slot_metrics = entry.get("metrics")
        slot_hhea = slot_metrics.get("hhea") if isinstance(slot_metrics, dict) else None
        try:
            slot_upem = int(slot_metrics.get("upem", 0)) if isinstance(slot_metrics, dict) else 0
            slot_ascent = int(slot_hhea.get("ascent", 0)) if isinstance(slot_hhea, dict) else 0
            slot_descent = int(slot_hhea.get("descent", 0)) if isinstance(slot_hhea, dict) else 0
        except (TypeError, ValueError) as error:
            raise InventoryError("设备字体清单槽位度量无效") from error
        if slot_upem <= 0 or slot_ascent <= 0 or slot_descent >= 0:
            raise InventoryError("设备字体清单槽位基线无效")

    indexed_main = slots[main_path]
    if str(main_slot.get("slotName", "")) != str(indexed_main.get("slotName", "")):
        raise InventoryError("设备字体清单主槽位不一致")
    metrics = main_slot.get("metrics")
    hhea = metrics.get("hhea") if isinstance(metrics, dict) else None
    try:
        upem = int(metrics.get("upem", 0)) if isinstance(metrics, dict) else 0
        ascent = int(hhea.get("ascent", 0)) if isinstance(hhea, dict) else 0
        descent = int(hhea.get("descent", 0)) if isinstance(hhea, dict) else 0
    except (TypeError, ValueError) as error:
        raise InventoryError("设备字体清单主槽位度量无效") from error
    if upem <= 0 or ascent <= 0 or descent >= 0:
        raise InventoryError("设备字体清单主槽位基线无效")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_ui_family(name: str) -> bool:
    lowered = name.strip().lower().replace("_", "-")
    if not lowered or any(token in lowered for token in DENY_FAMILY_TOKENS):
        return False
    if lowered == "sans-serif":
        return True
    if lowered.startswith("sans-serif-"):
        suffix = lowered.removeprefix("sans-serif-")
        parts = [part for part in suffix.split("-") if part]
        return bool(parts) and all(part in SANS_SERIF_UI_SUFFIX_TOKENS for part in parts)
    return any(
        lowered == prefix or lowered.startswith(prefix + "-")
        for prefix in UI_FAMILY_PREFIXES
        if prefix != "sans-serif"
    )


def _infer_weight(name: str, declared: str | None = None) -> int:
    if declared:
        try:
            value = int(declared)
        except ValueError:
            value = 0
        if 1 <= value <= 1000:
            return value
    stem = Path(name).stem.lower().replace("-", "_")
    numeric = re.search(r"(?:^|_)(100|200|300|350|400|500|600|700|800|900)(?:_|$)", stem)
    if numeric:
        return int(numeric.group(1))
    compact = stem.replace("_", "")
    for word, weight in sorted(WEIGHT_WORDS.items(), key=lambda item: -len(item[0])):
        if word in compact:
            return weight
    return 400


def _safe_nonnegative_int(value: str | None, default: int = 0) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _font_format(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            magic = stream.read(4)
    except OSError as error:
        raise InventoryError(f"无法读取字体文件：{path}") from error
    if magic in (b"\x00\x01\x00\x00", b"true", b"\x00\x02\x00\x00"):
        return "TTF"
    if magic == b"OTTO":
        return "OTF"
    if magic == b"ttcf":
        return "TTC"
    raise InventoryError(f"无法识别字体格式：{path}")


def _read_metrics(path: Path, face_index: int = 0) -> tuple[str, dict[str, Any]]:
    fmt = _font_format(path)
    kwargs: dict[str, Any] = {"lazy": True, "recalcTimestamp": False}
    if fmt == "TTC":
        kwargs["fontNumber"] = max(0, face_index)
    try:
        font = TTFont(str(path), **kwargs)
    except Exception as error:  # fontTools raises several format-specific exceptions
        raise InventoryError(f"fontTools 无法解析字体：{path.name}: {error}") from error
    try:
        if "head" not in font or "hhea" not in font or "OS/2" not in font:
            raise InventoryError(f"字体缺少 head/hhea/OS2：{path.name}")
        head = font["head"]
        hhea = font["hhea"]
        os2 = font["OS/2"]
        upem = int(head.unitsPerEm)
        ascent = int(hhea.ascent)
        descent = int(hhea.descent)
        if upem <= 0 or ascent <= 0 or descent >= 0:
            raise InventoryError(f"字体基线数值异常：{path.name}")
        metrics = {
            "upem": upem,
            "ascent": ascent,
            "descent": descent,
            "hhea": {
                "ascent": ascent,
                "descent": descent,
                "lineGap": int(getattr(hhea, "lineGap", 0)),
            },
            "os2": {
                "typoAscender": int(getattr(os2, "sTypoAscender", 0)),
                "typoDescender": int(getattr(os2, "sTypoDescender", 0)),
                "typoLineGap": int(getattr(os2, "sTypoLineGap", 0)),
                "winAscent": int(getattr(os2, "usWinAscent", 0)),
                "winDescent": int(getattr(os2, "usWinDescent", 0)),
            },
        }
    finally:
        font.close()
    return fmt, metrics


def _font_check(path: Path, script: Path) -> str:
    if not script.is_file():
        raise InventoryError("font_check.sh 不存在")
    shell = "/system/bin/sh" if Path("/system/bin/sh").is_file() else shutil.which("sh")
    if not shell:
        raise InventoryError("找不到可执行 Shell")
    try:
        result = subprocess.run(
            [shell, str(script), "--json", str(path), "text"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise InventoryError(f"font_check.sh 执行失败：{path.name}") from error
    if result.returncode != 0:
        raise InventoryError(f"font_check.sh 拒绝隐藏槽位：{path.name}")
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as error:
        raise InventoryError(f"font_check.sh 输出无效：{path.name}") from error
    if not payload.get("valid") or payload.get("format") not in {"TTF", "OTF", "TTC"}:
        raise InventoryError(f"font_check.sh 未通过：{path.name}")
    return str(payload["format"])


def _overlay_risk(module: Path | None) -> bool:
    if not module or not module.is_dir():
        return False
    try:
        active = (module / "config/active_font.conf").read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return False
    if not active or active == "default":
        return False
    for relative in ("system/fonts", "system_ext/fonts", "product/fonts", "my_product/fonts", "vendor/fonts"):
        root = module / relative
        if root.is_dir() and any(path.suffix.lower() in FONT_EXTENSIONS for path in root.iterdir() if path.is_file()):
            return True
    return False


def _pick_actual_root(logical: Path, explicit: Path | None, overlay_risk: bool) -> Path:
    if explicit is not None:
        return explicit
    if overlay_risk:
        for prefix in MIRROR_PREFIXES:
            candidate = prefix / logical.relative_to("/")
            if candidate.is_dir():
                return candidate
        raise InventoryError(f"旧版字体覆盖仍在活动，无法安全读取原厂目录：{logical}")
    return logical


def _resolve_roots(args: argparse.Namespace, overlay_risk: bool) -> tuple[list[FontRoot], Path]:
    explicit = {
        "system": args.system_fonts,
        "system_ext": args.system_ext_fonts,
        "product": args.product_fonts,
        "my_product": args.my_product_fonts,
        "vendor": args.vendor_fonts,
    }
    roots = [
        FontRoot(partition, logical, _pick_actual_root(logical, explicit[partition], overlay_risk))
        for partition, logical in LOGICAL_FONT_ROOTS
    ]
    system_etc = _pick_actual_root(Path("/system/etc"), args.system_etc, overlay_risk)
    return roots, system_etc


def _resolve_file(name: str, roots: Iterable[FontRoot]) -> tuple[FontRoot, Path] | None:
    stripped = name.strip()
    if not stripped:
        return None
    candidate_path = Path(stripped)
    basename = candidate_path.name
    if basename in {"", ".", ".."} or "/" in basename:
        return None
    if candidate_path.is_absolute():
        for root in roots:
            try:
                relative = candidate_path.relative_to(root.logical)
            except ValueError:
                continue
            actual = root.actual / relative
            if actual.is_file():
                return root, actual
    for root in roots:
        actual = root.actual / basename
        if actual.is_file():
            return root, actual
    return None


def _logical_path(root: FontRoot, actual: Path) -> str:
    return str(root.logical / actual.relative_to(root.actual))


def _parse_xml_mappings(xml_paths: Iterable[Path], roots: list[FontRoot]) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    families: dict[str, list[str]] = {}
    all_entries: dict[str, dict[str, Any]] = {}
    aliases: list[tuple[str, str]] = []
    for xml_path in xml_paths:
        if not xml_path.is_file():
            continue
        try:
            document = ET.parse(xml_path)
        except (OSError, ET.ParseError):
            continue
        for node in document.getroot().iter():
            tag = _local_name(node.tag)
            if tag == "alias":
                alias_name = (node.get("name") or "").strip()
                target_name = (node.get("to") or "").strip()
                if alias_name and target_name:
                    aliases.append((alias_name, target_name))
                continue
            if tag != "family":
                continue
            family_name = (node.get("name") or "").strip()
            family_language = (node.get("lang") or "").strip()
            family_is_ui = not family_language and _is_ui_family(family_name)
            for font_node in node:
                if _local_name(font_node.tag) != "font":
                    continue
                raw_name = (font_node.text or "").strip()
                resolved = _resolve_file(raw_name, roots)
                if not resolved:
                    continue
                root, actual = resolved
                logical = _logical_path(root, actual)
                families.setdefault(family_name, [])
                if logical not in families[family_name]:
                    families[family_name].append(logical)
                candidate = all_entries.setdefault(
                    logical,
                    {
                        "slotName": actual.name,
                        "path": logical,
                        "partition": root.partition,
                        "actualPath": str(actual),
                        "source": "xml",
                        "families": [],
                        "weight": _infer_weight(actual.name, font_node.get("weight")),
                        "style": (font_node.get("style") or "normal").strip() or "normal",
                        "faceIndex": _safe_nonnegative_int(font_node.get("index"), 0),
                        "uiEligible": family_is_ui,
                    },
                )
                if family_name and family_name not in candidate["families"]:
                    candidate["families"].append(family_name)
                if family_is_ui and not candidate.get("uiEligible", False):
                    candidate["weight"] = _infer_weight(actual.name, font_node.get("weight"))
                    candidate["style"] = (font_node.get("style") or "normal").strip() or "normal"
                    candidate["faceIndex"] = _safe_nonnegative_int(font_node.get("index"), 0)
                if family_is_ui:
                    candidate["uiEligible"] = True

    unresolved = list(aliases)
    for _round in range(len(aliases) + 1):
        if not unresolved:
            break
        next_round: list[tuple[str, str]] = []
        changed = False
        for alias_name, target_name in unresolved:
            target_paths = families.get(target_name)
            if target_paths:
                families[alias_name] = list(target_paths)
                changed = True
            else:
                next_round.append((alias_name, target_name))
        unresolved = next_round
        if not changed:
            break

    slots: dict[str, dict[str, Any]] = {}
    for family_name, paths in families.items():
        if not _is_ui_family(family_name):
            continue
        for logical in paths:
            candidate = all_entries.get(logical)
            if not candidate or not candidate.get("uiEligible", False):
                continue
            entry = slots.setdefault(logical, {**candidate, "families": list(candidate.get("families", []))})
            entry.pop("uiEligible", None)
            if family_name not in entry["families"]:
                entry["families"].append(family_name)
    return families, slots


def _heuristic_candidate(name: str) -> bool:
    lowered = name.lower()
    if any(token in lowered for token in DENY_FILE_TOKENS):
        return False
    return any(pattern.fullmatch(name) for pattern in HEURISTIC_PATTERNS)


def _add_heuristic_slots(slots: dict[str, dict[str, Any]], roots: list[FontRoot], font_check: Path) -> None:
    for root in roots:
        if not root.actual.is_dir():
            continue
        for actual in sorted(root.actual.iterdir(), key=lambda item: item.name.lower()):
            if not actual.is_file() or actual.suffix.lower() not in FONT_EXTENSIONS or not _heuristic_candidate(actual.name):
                continue
            logical = _logical_path(root, actual)
            if logical in slots:
                continue
            try:
                checked_format = _font_check(actual, font_check)
            except InventoryError:
                continue
            slots[logical] = {
                "slotName": actual.name,
                "path": logical,
                "partition": root.partition,
                "actualPath": str(actual),
                "source": "heuristic",
                "families": [],
                "weight": _infer_weight(actual.name),
                "style": "italic" if "italic" in actual.stem.lower() else "normal",
                "faceIndex": 0,
                "validatedBy": "font_check.sh",
                "validatedFormat": checked_format,
            }


def _populate_metrics(slots: dict[str, dict[str, Any]]) -> None:
    rejected: list[str] = []
    for logical, entry in slots.items():
        try:
            fmt, metrics = _read_metrics(Path(entry["actualPath"]), int(entry.get("faceIndex", 0)))
        except (InventoryError, OSError, ValueError):
            rejected.append(logical)
            continue
        entry["format"] = fmt
        entry["metrics"] = metrics
        entry.pop("actualPath", None)
    for logical in rejected:
        slots.pop(logical, None)


def _pick_main_slot(slots: dict[str, dict[str, Any]], families: dict[str, list[str]]) -> tuple[str, dict[str, Any], str]:
    preferences = (
        ("MiSansVF.ttf", "hyperos"),
        ("SysSans-Hans-Regular.ttf", "coloros"),
        ("SysFont-Hans-Regular.ttf", "coloros"),
        ("Roboto-Regular.ttf", "aosp"),
    )
    for filename, rom in preferences:
        for logical, entry in slots.items():
            if entry.get("slotName") == filename:
                return logical, entry, rom
    for family_name in ("sans-serif", "system-ui", "google-sans-text"):
        candidates = [
            (logical, slots[logical])
            for logical in families.get(family_name, [])
            if logical in slots
        ]
        if candidates:
            logical, entry = min(candidates, key=lambda item: (abs(int(item[1].get("weight", 400)) - 400), item[0]))
            return logical, entry, "generic"
    if not slots:
        raise InventoryError("没有发现可替换的系统 UI 字体槽位")
    logical = sorted(slots)[0]
    return logical, slots[logical], "generic"


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def scan(args: argparse.Namespace) -> int:
    output: Path = args.output
    build_key, fingerprint, display_id = current_build_key(args.build_key)
    existing = _load_json(output)
    if not args.force and existing is not None:
        try:
            validate_inventory(existing, build_key)
        except InventoryError:
            output.unlink(missing_ok=True)
        else:
            print(json.dumps({"status": "reused", "buildKey": build_key, "slotCount": len(existing["slots"])}, ensure_ascii=False))
            return 0
    elif output.exists() and existing is None:
        output.unlink(missing_ok=True)

    overlay_module = args.overlay_module
    risk = _overlay_risk(overlay_module)
    roots, system_etc = _resolve_roots(args, risk)
    xml_paths = [system_etc / "fonts.xml", system_etc / "font_fallback.xml"]
    families, slots = _parse_xml_mappings(xml_paths, roots)
    _add_heuristic_slots(slots, roots, args.font_check)
    _populate_metrics(slots)
    main_path, main_entry, rom = _pick_main_slot(slots, families)
    inventory = {
        "schema": SCHEMA,
        "inventoryRevision": INVENTORY_REVISION,
        "state": "ready",
        "buildKey": build_key,
        "buildFingerprint": fingerprint,
        "buildDisplayId": display_id,
        "generatedAt": int(time.time()),
        "romKind": rom,
        "sourceRoots": [
            {"partition": root.partition, "logical": str(root.logical), "actual": str(root.actual)}
            for root in roots
            if root.actual.is_dir()
        ],
        "xmlSources": [str(path) for path in xml_paths if path.is_file()],
        "families": {name: paths for name, paths in sorted(families.items()) if name and paths},
        "slots": {logical: slots[logical] for logical in sorted(slots)},
        "slotCount": len(slots),
        "mainSlotPath": main_path,
        "mainSlot": {**main_entry, "path": main_path},
    }
    validate_inventory(inventory, build_key)
    _atomic_write(output, inventory)
    print(json.dumps({"status": "ok", "buildKey": build_key, "slotCount": len(slots), "mainSlot": main_entry["slotName"], "romKind": rom}, ensure_ascii=False))
    return 0


def load_inventory(path: Path, expected_key: str | None = None) -> dict[str, Any]:
    data = _load_json(path)
    if data is None:
        raise InventoryError("设备字体清单不存在或无法解析")
    validate_inventory(data, expected_key)
    return data


def list_slots(args: argparse.Namespace) -> int:
    expected = args.build_key
    if not expected:
        key, _fingerprint, _display = current_build_key(None)
        expected = None if key == "unknown" else key
    data = load_inventory(args.output, expected)
    for logical, entry in sorted(data["slots"].items()):
        fields = (
            logical,
            str(entry.get("slotName", Path(logical).name)),
            str(entry.get("partition", "system")),
            str(entry.get("format", "")),
            str(int(entry.get("weight", 400))),
            str(entry.get("style", "normal")),
            str(entry.get("source", "xml")),
        )
        print("\t".join(value.replace("\t", " ").replace("\n", " ") for value in fields))
    return 0


def validate_command(args: argparse.Namespace) -> int:
    expected = args.build_key
    if not expected:
        key, _fingerprint, _display = current_build_key(None)
        expected = None if key == "unknown" else key
    data = load_inventory(args.output, expected)
    print(json.dumps({"status": "ok", "buildKey": data["buildKey"], "slotCount": len(data["slots"]), "mainSlot": data["mainSlot"]["slotName"]}, ensure_ascii=False))
    return 0


def default_output() -> Path:
    return Path(__file__).resolve().parent.parent / "config/device_font_inventory.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--scan", action="store_true", help="扫描原厂字体并写入清单（默认）")
    action.add_argument("--list", action="store_true", help="以 TSV 输出可替换槽位")
    action.add_argument("--validate", action="store_true", help="验证现有清单")
    parser.add_argument("--output", type=Path, default=default_output())
    parser.add_argument("--build-key")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--font-check", type=Path, default=Path(__file__).with_name("font_check.sh"))
    parser.add_argument("--overlay-module", type=Path)
    parser.add_argument("--system-fonts", type=Path)
    parser.add_argument("--system-ext-fonts", type=Path)
    parser.add_argument("--product-fonts", type=Path)
    parser.add_argument("--my-product-fonts", type=Path)
    parser.add_argument("--vendor-fonts", type=Path)
    parser.add_argument("--system-etc", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.list:
            return list_slots(args)
        if args.validate:
            return validate_command(args)
        return scan(args)
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
