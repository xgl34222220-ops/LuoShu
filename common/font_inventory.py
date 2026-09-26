#!/usr/bin/env python3
"""Discover the stock Android UI font slots for the current ROM.

The scanner is intentionally read-only. It runs while the module is being installed, before the
new LuoShu overlay is mounted, and records every measured text/font-face contract. XML contributes
usage, language and variation metadata; physical files are classified by cmap and font tables.
The replacement engine matches these contracts to the actual selected source font.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import hashlib
import json
import math
import os
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from fontTools.ttLib import TTFont
from font_slot_coverage import summarize_coverage, unicode_codepoints, valid_coverage

SCHEMA = "device-font-inventory-v1"
INVENTORY_REVISION = 1
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}
LOGICAL_FONT_ROOTS = (
    ("system", Path("/system/fonts")),
    ("system_ext", Path("/system_ext/fonts")),
    ("product", Path("/product/fonts")),
    ("my_product", Path("/my_product/fonts")),
    ("vendor", Path("/vendor/fonts")),
    ("odm", Path("/odm/fonts")),
    ("oem", Path("/oem/fonts")),
    ("my_engineering", Path("/my_engineering/fonts")),
    ("my_company", Path("/my_company/fonts")),
    ("my_preload", Path("/my_preload/fonts")),
    ("my_region", Path("/my_region/fonts")),
    ("my_stock", Path("/my_stock/fonts")),
    ("oplus_product", Path("/oplus_product/fonts")),
    ("oplus_engineering", Path("/oplus_engineering/fonts")),
    ("oplus_version", Path("/oplus_version/fonts")),
    ("oplus_region", Path("/oplus_region/fonts")),
    ("mi_ext", Path("/mi_ext/fonts")),
    ("cust", Path("/cust/fonts")),
    ("hw_product", Path("/hw_product/fonts")),
)
MIRROR_PREFIXES = (
    Path("/debug_ramdisk/.magisk/mirror"),
    Path("/sbin/.magisk/mirror"),
    Path("/data/adb/magisk/mirror"),
)
# Family labels describe usage; they never identify a ROM or select filenames.
DENY_FAMILY_TOKENS = ("emoji", "symbol", "icon", "math", "music", "dingbat")
SANS_SERIF_UI_SUFFIX_TOKENS = {
    "thin", "extralight", "extra-light", "light", "regular", "normal", "book", "medium",
    "semibold", "semi-bold", "bold", "extrabold", "extra-bold", "black", "heavy",
    "condensed", "compact", "smallcaps", "small-caps", "display", "text", "flex", "static",
}
# Kept as empty compatibility exports for external diagnostics. Filename text
# is not evidence that a font is safe or unsafe to replace.
GENERIC_DENY_FILE_TOKENS = ()
GENERIC_DENY_STYLE_TOKENS = ()

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


def _metric_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not a font metric")
    result = int(value)
    if not isinstance(value, (int, str)) and value != result:
        raise ValueError("font metric must be an integer")
    return result


def _validate_metrics(metrics: Any) -> None:
    """Validate stored design units without discarding zero-descender clock fonts.

    OpenType hhea ascent/descent are signed FWORD values, not glyph bounds.
    A slot whose designed lower extent is the baseline can legitimately use 0.
    Require the field explicitly: a missing descent must not become a valid 0.
    """
    try:
        upem = _metric_int(metrics["upem"])
        ascent = _metric_int(metrics["hhea"]["ascent"])
        descent = _metric_int(metrics["hhea"]["descent"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise InventoryError("设备字体清单槽位度量无效") from error
    if not 16 <= upem <= 16384 or not 0 < ascent <= 32767 or not -32768 <= descent <= 0:
        raise InventoryError("设备字体清单槽位基线无效")
    # The bounding box is additive diagnostic data. Inventories captured by an
    # older scanner remain usable; never synthesize bounds from line metrics.
    if "head" in metrics:
        try:
            head = metrics["head"]
            bounds = {name: _metric_int(head[name]) for name in ("xMin", "yMin", "xMax", "yMax")}
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise InventoryError("设备字体清单槽位字形边界无效") from error
        if (any(not -32768 <= value <= 32767 for value in bounds.values())
                or bounds["xMin"] > bounds["xMax"] or bounds["yMin"] > bounds["yMax"]):
            raise InventoryError("设备字体清单槽位字形边界无效")
    if "coverage" in metrics and not valid_coverage(metrics["coverage"]):
        raise InventoryError("设备字体清单槽位字符覆盖无效")


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

    discovered = data.get("discoveredPartitions", [])
    if not isinstance(discovered, list) or len(discovered) > 16:
        raise InventoryError("设备字体清单动态分区无效")
    known_partitions = {partition for partition, _logical in LOGICAL_FONT_ROOTS}
    denied_partitions = {
        "acct", "apex", "cache", "config", "data", "data_mirror", "debug_ramdisk",
        "dev", "linkerconfig", "metadata", "mnt", "proc", "sdcard", "storage",
        "sys", "tmp", "vendor_dlkm", "odm_dlkm", "system_dlkm",
    }
    dynamic_prefixes: list[str] = []
    for value in discovered:
        if not isinstance(value, str):
            raise InventoryError("设备字体清单动态分区无效")
        partition = value.strip()
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_]{0,63}", partition)
                or partition in known_partitions
                or partition.lower() in denied_partitions):
            raise InventoryError("设备字体清单动态分区越界")
        prefix = f"/{partition}/fonts/"
        if prefix not in dynamic_prefixes:
            dynamic_prefixes.append(prefix)
    nested = data.get("discoveredFontRoots", [])
    if not isinstance(nested, list) or len(nested) > 128:
        raise InventoryError("设备字体清单嵌套字体根无效")
    allowed_partitions = known_partitions | set(discovered)
    nested_prefixes: list[str] = []
    seen_nested: set[tuple[str, str]] = set()
    for item in nested:
        if not isinstance(item, dict):
            raise InventoryError("设备字体清单嵌套字体根无效")
        partition = str(item.get("partition", "")).strip()
        relative = str(item.get("relative", "")).strip().strip("/")
        logical_root = str(item.get("logical", "")).strip()
        mount_key = str(item.get("mountKey", "")).strip()
        parts = [part for part in relative.split("/") if part]
        expected_mount_key = (
            f"{partition}-nested-"
            + hashlib.sha256(f"{partition}/{relative}".encode("utf-8")).hexdigest()[:16]
        )
        if (
            partition not in allowed_partitions
            or not relative
            or relative in {"fonts", "font", "etc"}
            or not parts
            or any(part in (".", "..") for part in parts)
            or any(re.fullmatch(r"[A-Za-z0-9._+-]{1,96}", part) is None for part in parts)
            or logical_root != f"/{partition}/{relative}"
            or mount_key != expected_mount_key
        ):
            raise InventoryError("设备字体清单嵌套字体根越界")
        identity = (partition, relative)
        if identity in seen_nested:
            raise InventoryError("设备字体清单嵌套字体根重复")
        seen_nested.add(identity)
        nested_prefixes.append(logical_root.rstrip("/") + "/")

    allowed_prefixes = (
        *(f"{logical}/" for _partition, logical in LOGICAL_FONT_ROOTS),
        *dynamic_prefixes,
        *nested_prefixes,
    )
    for logical, entry in slots.items():
        if not isinstance(logical, str) or not logical.startswith(allowed_prefixes) or not isinstance(entry, dict):
            raise InventoryError("设备字体清单包含越界槽位")
        if (str(entry.get("path", logical)) != logical
                or str(Path(os.path.abspath(os.path.normpath(logical)))) != logical):
            raise InventoryError("设备字体清单槽位路径不一致")
        if str(entry.get("format", "")) not in {"TTF", "OTF", "TTC"}:
            raise InventoryError("设备字体清单包含无效字体格式")
        _validate_metrics(entry.get("metrics"))
        if "faces" in entry:
            faces = entry["faces"]
            if (not isinstance(faces, list) or not 1 <= len(faces) <= 256
                    or any(not isinstance(face, dict) or face.get("faceIndex") != index
                           for index, face in enumerate(faces))):
                raise InventoryError("设备字体清单集合索引无效")
            for face in faces:
                _validate_metrics(face.get("metrics"))
            if not 0 <= int(entry.get("faceIndex", 0)) < len(faces):
                raise InventoryError("设备字体清单主字体面越界")

    indexed_main = slots[main_path]
    if str(main_slot.get("slotName", "")) != str(indexed_main.get("slotName", "")):
        raise InventoryError("设备字体清单主槽位不一致")
    _validate_metrics(main_slot.get("metrics"))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_ui_family(name: str) -> bool:
    tokens = set(re.split(r"[^a-z0-9]+", name.strip().lower()))
    return bool(name.strip()) and not tokens.intersection(DENY_FAMILY_TOKENS)


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


_METRICS_CACHE: dict[tuple[int, ...], tuple[str, dict[str, Any]]] | None = None
_STOCK_DIGEST_CACHE: dict[tuple[int, ...], str] | None = None


@contextmanager
def _scan_metrics_cache():
    """Keep shared stock faces once per scan, never across ROM refreshes."""
    global _METRICS_CACHE, _STOCK_DIGEST_CACHE
    previous = _METRICS_CACHE
    previous_digests = _STOCK_DIGEST_CACHE
    _METRICS_CACHE = {}
    _STOCK_DIGEST_CACHE = {}
    try:
        yield
    finally:
        _METRICS_CACHE = previous
        _STOCK_DIGEST_CACHE = previous_digests


def _stock_file_digest(path: Path) -> str:
    """Pin the immutable stock bytes, including outlines, once per scan inode."""
    status = path.stat()
    identity = (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns)
    if _STOCK_DIGEST_CACHE is not None and identity in _STOCK_DIGEST_CACHE:
        return _STOCK_DIGEST_CACHE[identity]
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise InventoryError("原厂字体在扫描期间发生变化")
    result = digest.hexdigest()
    if _STOCK_DIGEST_CACHE is not None:
        _STOCK_DIGEST_CACHE[identity] = result
    return result


def _read_metrics(path: Path, face_index: int = 0) -> tuple[str, dict[str, Any]]:
    try:
        status = path.stat()
        key = (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns,
               status.st_ctime_ns, face_index)
    except OSError as error:
        raise InventoryError(f"无法读取字体文件：{path}") from error
    if _METRICS_CACHE is not None and key in _METRICS_CACHE:
        return copy.deepcopy(_METRICS_CACHE[key])
    result = _read_metrics_uncached(path, face_index)
    if _METRICS_CACHE is not None:
        _METRICS_CACHE[key] = copy.deepcopy(result)
    return result


def _cmap_metrics(font: TTFont) -> dict[str, Any]:
    """Character facts that can be shared by byte-identical cmap/glyph orders."""
    from fontTools.unicodedata import category as unicode_category, script as unicode_script
    points = frozenset(unicode_codepoints(font))
    letter_scripts: dict[str, int] = {}
    point_digest = hashlib.sha256()
    for point in sorted(points):
        point_digest.update(struct.pack(">I", point))
        character = chr(point)
        if unicode_category(character).startswith("L"):
            script = unicode_script(character)
            letter_scripts[script] = letter_scripts.get(script, 0) + 1
    return {"points": points, "letterScripts": letter_scripts,
            "coverage": summarize_coverage(font, points=points),
            "digitCount": sum(0x30 <= point <= 0x39 or 0xFF10 <= point <= 0xFF19 for point in points),
            "privateUseCount": sum(unicode_category(chr(point)) == "Co" for point in points),
            "cmapSha256": hashlib.sha256(font.reader["cmap"]).hexdigest(),
            "codepointSha256": point_digest.hexdigest()}


def _read_metrics_uncached(path: Path, face_index: int = 0, *, _font: TTFont | None = None,
                           _cmap: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:

    fmt = _font_format(path)
    kwargs: dict[str, Any] = {"lazy": True, "recalcTimestamp": False}
    if fmt == "TTC":
        kwargs["fontNumber"] = max(0, face_index)
    try:
        font = _font if _font is not None else TTFont(str(path), **kwargs)
    except Exception as error:  # fontTools raises several format-specific exceptions
        raise InventoryError(f"fontTools 无法解析字体：{path.name}: {error}") from error
    try:
        if "head" not in font or "hhea" not in font or "OS/2" not in font:
            raise InventoryError(f"字体缺少 head/hhea/OS2：{path.name}")
        head = font["head"]
        hhea = font["hhea"]
        os2 = font["OS/2"]
        # isFixedPitch is a scalar in the post header. Reading it through the
        # table object would unnecessarily decode thousands of glyph names.
        post_data = font.reader["post"] if "post" in font else None
        fixed_pitch = bool(struct.unpack_from(">I", post_data, 12)[0]) if post_data is not None else False
        # Reuse the already decoded cmap: a language tag cannot tell whether a
        # physical face is a general UI font or a script fallback with ASCII.
        cmap = _cmap if _cmap is not None else _cmap_metrics(font)
        family_tokens = set()
        if "name" in font:
            for record in font["name"].names:
                if record.nameID in {1, 16}:
                    try:
                        family_tokens.update(re.split(r"[^a-z0-9]+", record.toUnicode().lower()))
                    except (UnicodeError, ValueError):
                        continue
        symbol_metadata = (int(getattr(os2, "sFamilyClass", 0)) >> 8 == 12
                           or int(getattr(getattr(os2, "panose", None), "bFamilyType", 0)) == 5
                           or bool(family_tokens.intersection({"icon", "icons", "symbol", "symbols",
                                                              "emoji", "math", "dingbat", "dingbats", "fontawesome"})))
        upem = int(head.unitsPerEm)
        ascent = int(hhea.ascent)
        descent = int(hhea.descent)
        metrics = {
            "upem": upem,
            # Optional identity evidence: older revision-9 inventories remain
            # usable through verified lower/mirror views. No rescan is needed
            # merely to obtain these newer, stronger stock-byte proofs.
            "stockCmapSha256": cmap["cmapSha256"],
            "stockCodepointSha256": cmap["codepointSha256"],
            "coverage": copy.deepcopy(cmap["coverage"]),
            "weightClass": int(getattr(os2, "usWeightClass", 400)),
            "variationAxes": {axis.axisTag: {"min": axis.minValue, "default": axis.defaultValue,
                               "max": axis.maxValue} for axis in font["fvar"].axes} if "fvar" in font else {},
            "fontTraits": {
                "letterScripts": dict(cmap["letterScripts"]),
                "symbol": symbol_metadata,
                "digitCount": cmap["digitCount"],
                "privateUseCount": cmap["privateUseCount"],
                "color": any(tag in font for tag in ("COLR", "CBDT", "sbix", "SVG ")),
                "italic": bool(int(getattr(os2, "fsSelection", 0)) & 1
                               or int(getattr(head, "macStyle", 0)) & 2),
                "monospaced": fixed_pitch,
            },
            "ascent": ascent,
            "descent": descent,
            "head": {
                "xMin": int(head.xMin),
                "yMin": int(head.yMin),
                "xMax": int(head.xMax),
                "yMax": int(head.yMax),
                "flags": int(head.flags),
                "lowestRecPPEM": int(head.lowestRecPPEM),
            },
            "hhea": {
                "ascent": ascent,
                "descent": descent,
                "lineGap": int(getattr(hhea, "lineGap", 0)),
            },
            "os2": {
                "fsSelection": int(getattr(os2, "fsSelection", 0)),
                "typoAscender": int(getattr(os2, "sTypoAscender", 0)),
                "typoDescender": int(getattr(os2, "sTypoDescender", 0)),
                "typoLineGap": int(getattr(os2, "sTypoLineGap", 0)),
                "winAscent": int(getattr(os2, "usWinAscent", 0)),
                "winDescent": int(getattr(os2, "usWinDescent", 0)),
            },
        }
        _validate_metrics(metrics)
    except InventoryError:
        raise
    except Exception as error:
        # Lazy fonts can open successfully but fail only when a malformed cmap,
        # head, or metrics table is decoded. Reject that file, not the ROM scan.
        raise InventoryError(f"字体表损坏：{path.name}: {error}") from error
    finally:
        if _font is None:
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
    for _partition, logical in LOGICAL_FONT_ROOTS:
        root = module / logical.relative_to("/")
        if root.is_dir() and any(path.suffix.lower() in FONT_EXTENSIONS for path in root.iterdir() if path.is_file()):
            return True
    return False


def _pick_actual_root(logical: Path, explicit: Path | None, overlay_risk: bool) -> Path:
    if explicit is not None:
        return explicit
    if overlay_risk:
        parts = logical.parts
        if len(parts) >= 3 and parts[0] == "/":
            state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
            lower = state_root / "lower" / f"{parts[1]}-{parts[2]}"
            if lower.is_dir():
                return lower
        for prefix in MIRROR_PREFIXES:
            candidate = prefix / logical.relative_to("/")
            if candidate.is_dir():
                return candidate
        raise InventoryError(f"字体覆盖仍在活动且没有可验证的原厂 lower/mirror：{logical}")
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
        FontRoot(partition, logical, _pick_actual_root(logical, explicit.get(partition), overlay_risk))
        for partition, logical in LOGICAL_FONT_ROOTS
    ]
    system_etc = _pick_actual_root(Path("/system/etc"), args.system_etc, overlay_risk)
    return roots, system_etc


def _font_root_names(root: FontRoot) -> tuple[Path, ...]:
    """Logical partition aliases also accepted by the partition-aware scanner."""
    aliases = {
        Path("/system/fonts"): (Path("/system/font"),),
        Path("/system_ext/fonts"): (Path("/system/system_ext/fonts"),),
        Path("/product/fonts"): (Path("/system/product/fonts"),),
        Path("/my_product/fonts"): (Path("/system/my_product/fonts"),),
        Path("/vendor/fonts"): (Path("/system/vendor/fonts"),),
    }
    return (root.logical, *aliases.get(root.logical, ()))


def _stock_font_path(root: FontRoot, actual: Path, roots: Iterable[FontRoot]) -> Path:
    """Resolve each font link inside the selected stock views, never the live ROM.

    A stock /system/fonts directory can contain absolute links to /product/fonts.
    Opening those links normally escapes a lower/mirror directory and can read the
    active replacement. Resolve in the logical namespace, remapping every link hop
    to its partition's selected stock root before touching another filesystem node.
    """
    def lexical(path: Path) -> Path:
        return Path(os.path.abspath(os.path.normpath(str(path))))

    selected = list(roots)
    if root not in selected:
        raise InventoryError("字体不属于本次验证的原厂目录")
    try:
        relative = lexical(actual).relative_to(lexical(root.actual))
    except ValueError as error:
        raise InventoryError("字体路径超出原厂目录") from error
    logical = lexical(root.logical / relative)
    views: list[tuple[Path, Path]] = []
    for candidate in selected:
        try:
            stock = candidate.actual.resolve(strict=True)
            if stock.is_dir():
                views.extend((lexical(name), stock) for name in _font_root_names(candidate))
        except (OSError, RuntimeError):
            continue
    views.sort(key=lambda item: len(item[0].parts), reverse=True)
    visited: set[Path] = set()
    for _hop in range(41):
        if logical in visited:
            raise InventoryError("原厂字体符号链接存在环路")
        visited.add(logical)
        for logical_root, stock_root in views:
            try:
                parts = logical.relative_to(logical_root).parts
            except ValueError:
                continue
            break
        else:
            raise InventoryError(f"原厂字体链接离开已验证的字体分区：{logical}")
        if not parts:
            raise InventoryError("原厂字体路径指向目录")
        physical = stock_root
        for index, component in enumerate(parts):
            physical = physical / component
            try:
                mode = physical.lstat().st_mode
                if stat.S_ISLNK(mode):
                    target = Path(os.readlink(physical))
                    parent = logical_root.joinpath(*parts[:index])
                    logical = lexical((target if target.is_absolute() else parent / target)
                                      .joinpath(*parts[index + 1:]))
                    break
            except OSError as error:
                raise InventoryError(f"无法读取原厂字体路径：{logical}") from error
            if index == len(parts) - 1:
                if not stat.S_ISREG(mode):
                    raise InventoryError("原厂字体不是普通文件")
                return physical
            if not stat.S_ISDIR(mode):
                raise InventoryError("原厂字体路径包含非目录节点")
    raise InventoryError("原厂字体符号链接层数过多")


def _resolve_file(name: str, roots: Iterable[FontRoot]) -> tuple[FontRoot, Path] | None:
    stripped = name.strip()
    if not stripped:
        return None
    candidate_path = Path(stripped)
    basename = candidate_path.name
    if basename in {"", ".", ".."} or "/" in basename:
        return None
    selected = list(roots)
    if candidate_path.is_absolute():
        for root in selected:
            for logical_root in _font_root_names(root):
                try:
                    relative = candidate_path.relative_to(logical_root)
                except ValueError:
                    continue
                actual = root.actual / relative
                try:
                    _stock_font_path(root, actual, selected)
                    return root, actual
                except InventoryError:
                    return None
        return None
    for root in selected:
        actual = root.actual / candidate_path
        try:
            _stock_font_path(root, actual, selected)
            return root, actual
        except InventoryError:
            continue
    return None


def _logical_path(root: FontRoot, actual: Path) -> str:
    return str(root.logical / actual.relative_to(root.actual))


def _language_text_slot_candidate(name: str, language: str, family_is_ui: bool,
                                  metrics: dict[str, Any]) -> bool:
    return _generic_text_slot_candidate(name, metrics)


def _parse_xml_mappings(xml_paths: Iterable[Path], roots: list[FontRoot], *,
                        roots_by_xml: dict[Path, list[FontRoot]] | None = None,
                        logical_xmls: dict[Path, str] | None = None,
                        protected_paths: set[str] | None = None) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    """Record font use, language and face contracts without a vendor allow-list."""
    families: dict[str, list[str]] = {}
    entries: dict[str, dict[str, Any]] = {}
    aliases: list[tuple[str, str]] = []
    protected: set[str] = set()
    for xml_path in xml_paths:
        try:
            document = ET.parse(xml_path)
        except (OSError, ET.ParseError):
            continue
        selected_roots = (roots_by_xml or {}).get(xml_path, roots)
        source_xml = (logical_xmls or {}).get(xml_path, str(xml_path))
        for node in document.getroot().iter():
            tag = _local_name(node.tag)
            if tag == "alias":
                alias, target = (node.get("name") or "").strip(), (node.get("to") or "").strip()
                if alias and target:
                    aliases.append((alias, target))
                continue
            if tag != "family":
                continue
            legacy_names = [(child.text or "").strip() for nameset in node
                            if _local_name(nameset.tag) == "nameset" for child in nameset
                            if _local_name(child.tag) == "name" and (child.text or "").strip()]
            name = (node.get("name") or (legacy_names[0] if legacy_names else "")).strip()
            languages = (node.get("lang") or "").replace(",", " ").split()
            tokens = set(re.split(r"[^a-z0-9]+", name.lower()))
            specialized = bool(tokens.intersection(DENY_FAMILY_TOKENS))
            font_nodes = [child for child in node if _local_name(child.tag) == "font"]
            for fileset in node:
                if _local_name(fileset.tag) == "fileset":
                    font_nodes.extend(child for child in fileset if _local_name(child.tag) == "file")
            for font_node in font_nodes:
                resolved = _resolve_file((font_node.text or "").strip(), selected_roots)
                if not resolved:
                    continue
                root, actual = resolved
                logical = _logical_path(root, actual)
                try:
                    stock_file = _stock_font_path(root, actual, selected_roots)
                except InventoryError:
                    continue
                if specialized:
                    protected.add(logical)
                family_paths = families.setdefault(name, [])
                if logical not in family_paths:
                    family_paths.append(logical)
                fallback_for = (font_node.get("fallbackFor") or node.get("fallbackFor") or "").split()
                face_index = _safe_nonnegative_int(font_node.get("index"), 0)
                supported_axes = (font_node.get("supportedAxes") or "").replace(",", " ").split()
                axes = {}
                for axis in font_node:
                    if _local_name(axis.tag) == "axis":
                        try:
                            value = float(axis.get("stylevalue", ""))
                        except ValueError:
                            continue
                        if len(axis.get("tag", "")) == 4 and math.isfinite(value):
                            axes[axis.get("tag")] = value
                contract = {
                    "supportedAxes": supported_axes, "axes": axes,
                    "faceIndex": face_index,
                    "weight": _infer_weight(actual.name, font_node.get("weight")),
                    "style": (font_node.get("style") or "normal").strip() or "normal",
                    "families": list(dict.fromkeys(([name] if name else []) + legacy_names)),
                    "familyLanguages": list(languages),
                    "xmlFallback": not name or bool(fallback_for),
                    "fallbackFor": fallback_for,
                    "sourceXmls": [source_xml],
                }
                reference = {**contract}
                contract["xmlReferences"] = [reference]
                for legacy_name in legacy_names[1:]:
                    legacy_paths = families.setdefault(legacy_name, [])
                    if logical not in legacy_paths:
                        legacy_paths.append(logical)
                entry = entries.setdefault(logical, {
                    "slotName": actual.name, "path": logical, "partition": root.partition,
                    "actualPath": str(stock_file), "source": "xml", **contract,
                    "xmlFaces": {},
                })
                face = entry["xmlFaces"].setdefault(str(face_index), {**contract})
                for target in (entry, face):
                    for key in ("families", "familyLanguages", "fallbackFor", "sourceXmls", "supportedAxes"):
                        target[key] = list(dict.fromkeys([*target.get(key, []), *contract[key]]))
                    references = target.setdefault("xmlReferences", [])
                    if reference not in references:
                        references.append(reference)
                    target["xmlFallback"] = target.get("xmlFallback", False) or contract["xmlFallback"]
    unresolved = list(aliases)
    for _round in range(len(aliases) + 1):
        remaining = []
        for alias, target in unresolved:
            if target not in families:
                remaining.append((alias, target))
                continue
            families[alias] = list(families[target])
            for logical in families[target]:
                entry = entries.get(logical)
                if entry is None:
                    continue
                for face in (entry, *entry["xmlFaces"].values()):
                    if target in face.get("families", []) and alias not in face["families"]:
                        face["families"].append(alias)
        if len(remaining) == len(unresolved):
            break
        unresolved = remaining
    if protected_paths is not None:
        protected_paths.update(protected)
    return families, entries


def _generic_font_name_candidate(name: str) -> bool:
    return Path(name).suffix.lower() in FONT_EXTENSIONS


def _text_face_reason(metrics: dict[str, Any], *, declared_text: bool = False) -> str:
    traits = metrics.get("fontTraits", {})
    if traits.get("color"):
        return "color-font"
    if traits.get("symbol"):
        return "symbol-font-metadata"
    coverage = metrics.get("coverage")
    if not valid_coverage(coverage):
        return "invalid-cmap"
    letters = sum(traits.get("letterScripts", {}).values())
    digits = int(traits.get("digitCount", 0))
    if int(traits.get("privateUseCount", 0)) > max(128, letters * 4):
        return "private-use-symbol-font"
    if letters or (digits > 0 and coverage["unicodeCount"] <= 128):
        return ""
    return "non-text-cmap"


def _generic_text_slot_candidate(name: str, metrics: dict[str, Any]) -> bool:
    return not _text_face_reason(metrics)


def _collection_count(path: Path) -> int:
    with path.open("rb") as stream:
        header = stream.read(12)
    if header[:4] != b"ttcf":
        return 1
    if len(header) != 12:
        raise InventoryError("字体集合头损坏")
    count = struct.unpack_from(">I", header, 8)[0]
    if not 1 <= count <= 256:
        raise InventoryError("字体集合面数无效")
    return count


def _add_heuristic_slots(slots: dict[str, dict[str, Any]], roots: list[FontRoot], font_check: Path,
                         protected_paths: set[str] | None = None) -> None:
    # Legacy callers share the canonical measured scan, never a filename list.
    _add_verified_text_slots(slots, roots, protected_paths)


def _add_verified_text_slots(slots: dict[str, dict[str, Any]], roots: list[FontRoot],
                             protected_paths: set[str] | None = None,
                             preserved_fonts: dict[str, dict[str, Any]] | None = None) -> None:
    """Measure every physical face. The engine decides whether the user's source
    satisfies its script/style/weight contract; scanner never guesses a ROM.
    """
    preserved = preserved_fonts if preserved_fonts is not None else {}
    for root in roots:
        if not root.actual.is_dir():
            continue
        try:
            candidates_set = {path for path in root.actual.rglob("*")
                if path.suffix.lower() in FONT_EXTENSIONS and (path.is_file() or path.is_symlink())}
            # XML is an authoritative font reference even when the filename has
            # an unusual suffix; the sfnt parser remains the content gate.
            for logical, entry in slots.items():
                if entry.get("source") == "xml" and Path(logical).is_relative_to(root.logical):
                    actual = root.actual / Path(logical).relative_to(root.logical)
                    if actual.is_file() or actual.is_symlink():
                        candidates_set.add(actual)
            candidates = sorted(candidates_set, key=lambda item: str(item).lower())
        except OSError:
            continue
        for actual in candidates:
            logical = _logical_path(root, actual)
            if logical in (protected_paths or ()):
                preserved[logical] = {"reason": "xml-symbol-family"}
                slots.pop(logical, None)
                continue
            previous = slots.get(logical, {})
            try:
                stock_file = _stock_font_path(root, actual, roots)
                stock_digest = _stock_file_digest(stock_file)
                faces = []
                for index in range(_collection_count(stock_file)):
                    fmt, metrics = _read_metrics(stock_file, index)
                    contract = previous.get("xmlFaces", {}).get(str(index), {})
                    reason = _text_face_reason(metrics, declared_text=bool(contract))
                    traits = metrics.get("fontTraits", {})
                    face = {
                        **contract, "faceIndex": index, "format": fmt, "metrics": metrics,
                        "stockSource": {"sha256": stock_digest,
                                        "cmapSha256": metrics["stockCmapSha256"]},
                        "weight": contract.get("weight", metrics.get("weightClass", 400)),
                        "style": contract.get("style", "italic" if traits.get("italic") else "normal"),
                        "replacementRole": "text" if traits.get("letterScripts") else "digits",
                        "requiresScripts": sorted(key for key in traits.get("letterScripts", {})
                                                  if key not in {"Zyyy", "Zinh"}),
                        "families": contract.get("families", []),
                        "familyLanguages": contract.get("familyLanguages", []),
                        "xmlFallback": contract.get("xmlFallback", False),
                        "fallbackFor": contract.get("fallbackFor", []),
                        "sourceXmls": contract.get("sourceXmls", []),
                        "fallbackReachable": False, "fallbackTargets": [],
                        "supportedAxes": contract.get("supportedAxes", []),
                        "axes": contract.get("axes", {}), "xmlReferences": contract.get("xmlReferences", []),
                    }
                    if reason:
                        face["preservedReason"] = reason
                    faces.append(face)
            except (InventoryError, OSError, ValueError) as error:
                preserved[logical] = {"reason": "unreadable-stock-font", "detail": str(error)}
                slots.pop(logical, None)
                continue
            usable = [face for face in faces if not face.get("preservedReason")]
            if not usable:
                preserved[logical] = {"reason": faces[0]["preservedReason"], "faces": faces}
                slots.pop(logical, None)
                continue
            selected = min(usable, key=lambda face: (
                not any(tag == "zh" or tag.startswith("zh-") for tag in face["familyLanguages"]),
                -int(face["metrics"]["coverage"]["hanCount"]),
                not bool(face["xmlReferences"]), face["faceIndex"]))
            slots[logical] = {
                **previous, **selected,
                "slotName": actual.name, "path": logical, "partition": root.partition,
                "source": previous.get("source", "verified-scan"),
                "validatedBy": "fontTools-universal-stock-scan", "validatedFormat": fmt,
                "faces": faces,
            }
            slots[logical].pop("actualPath", None)
            slots[logical].pop("xmlFaces", None)
            # The path-level fields retain all XML uses; selected face metadata
            # remains independent in faces[] (particularly important for TTC).
            for key in ("families", "familyLanguages", "fallbackFor", "sourceXmls", "supportedAxes"):
                slots[logical][key] = list(dict.fromkeys(value for face in faces for value in face[key]))
            slots[logical]["xmlFallback"] = any(face["xmlFallback"] for face in faces)
            slots[logical]["xmlReferences"] = [ref for face in faces for ref in face["xmlReferences"]]
            preserved.pop(logical, None)
    for logical, entry in slots.items():
        for face in entry.get("faces", [entry]):
            targets = []
            for fallback_path, fallback in slots.items():
                if fallback_path == logical:
                    continue
                for fallback_face in fallback.get("faces", [fallback]):
                    if (not fallback_face.get("xmlFallback")
                            or not fallback_face.get("metrics", {}).get("coverage", {}).get("hasHan")
                            or not set(face.get("sourceXmls", [])) & set(fallback_face.get("sourceXmls", []))):
                        continue
                    required = fallback_face.get("fallbackFor", [])
                    if required and not set(required) & set(face.get("families", [])):
                        continue
                    targets.append(fallback_path)
                    break
            face["fallbackTargets"] = sorted(set(targets))
            face["fallbackReachable"] = bool(targets)
        selected = next((face for face in entry.get("faces", []) if face["faceIndex"] == entry["faceIndex"]), entry)
        entry["fallbackTargets"] = selected.get("fallbackTargets", [])
        entry["fallbackReachable"] = selected.get("fallbackReachable", False)


def _populate_metrics(slots: dict[str, dict[str, Any]]) -> None:
    rejected: list[str] = []
    for logical, entry in slots.items():
        try:
            if entry.get("format") in {"TTF", "OTF", "TTC"} and isinstance(entry.get("metrics"), dict):
                _validate_metrics(entry["metrics"])
                entry.pop("actualPath", None)
                continue
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
    if not slots:
        raise InventoryError("没有发现可替换的系统文本字体槽位")
    # Prefer a normal regular XML UI face, then broad Han coverage. Names and
    # Android vendor properties never enter this ordering.
    logical = min(slots, key=lambda path: (
        slots[path].get("replacementRole") == "digits",
        slots[path].get("style", "normal") != "normal",
        abs(int(slots[path].get("weight", 400)) - 400),
        not any(name in {"sans-serif", "system-ui"} for name in slots[path].get("families", [])),
        slots[path].get("xmlFallback", False),
        -int(slots[path].get("metrics", {}).get("coverage", {}).get("hanCount", 0)),
        path,
    ))
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
    protected_paths: set[str] = set()
    families, slots = _parse_xml_mappings(xml_paths, roots, protected_paths=protected_paths)
    with _scan_metrics_cache():
        _add_verified_text_slots(slots, roots, protected_paths)
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
