#!/usr/bin/env python3
"""Read-only, bounded font evidence for an explicitly requested diagnostic.

An active payload, this process's mount namespace and an app's chosen Typeface
are different observations. This report never treats one as proof of another.
Only stable system slot names, numeric font measurements and allowlisted APK
font resource names are exported; font names, build identifiers and user paths
are deliberately omitted.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import tempfile
import time
import zipfile

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from font_inventory import LOGICAL_FONT_ROOTS, MIRROR_PREFIXES, validate_inventory
from font_slot_coverage import valid_coverage

SCHEMA = "luoshu-font-layout-diagnostic-v1"
PROBES = "中永国岁你好AHIx01247"
PACKAGES = ("com.android.deskclock", "com.duokan.phone.remotecontroller",
            "com.tencent.mobileqq", "com.coolapk.market")
MAX_EXTRA_SLOTS = 24
MAX_FONT_BYTES = 128 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024
SLOT_NAME = re.compile(r"[A-Za-z0-9_.+-]{1,120}\.(?:ttf|otf|ttc|otc)", re.I)
KEY_NAME = re.compile(r"^(?:MiSans|Mitype|MiClock|AndroidClock|Clockopia|Roboto|"
                      r"GoogleSans|SysSans|SysFont|OppoSans|OPlusSans|OPSans|"
                      r"DIN|OPPODIN|NotoSansCJK|SourceHanSans|[1-9]00\.)", re.I)
METRIC_FIELDS = {
    "head": ("xMin", "yMin", "xMax", "yMax", "flags", "lowestRecPPEM"),
    "hhea": ("ascent", "descent", "lineGap"),
    "os2": ("fsSelection", "typoAscender", "typoDescender", "typoLineGap",
            "winAscent", "winDescent"),
}
COVERAGE_FIELDS = ("hasHan", "hasLatin", "hanCount", "latinCount", "unicodeCount", "cjkPunctuation")
CJK_ROUTING_REASONS = {"stock-coverage-refresh-pending", "specialized-slot", "stock-han-slot",
                       "not-latin-ui-slot", "no-staged-cjk-fallback", "stock-latin-primary",
                       "oem-direct-full-coverage", "routing-fallback-full-coverage"}
BASELINE_REASONS = {"stock-probe", "stock-probe-unavailable", "invalid-probe-upem",
                    "unsafe-probe-shift", "shared-probe-missing", "zero-shift",
                    "non-glyf-source", "no-simple-outlines"}


class BudgetExpired(BaseException):
    """Escape fontTools' broad exception handlers when the total budget expires."""


def safe_slot(value: object) -> bool:
    if not isinstance(value, str):
        return False
    path = PurePosixPath(value)
    return (str(path) == value and path.parent in {root for _, root in LOGICAL_FONT_ROOTS}
            and SLOT_NAME.fullmatch(path.name) is not None)


def metrics_only(value: dict) -> dict:
    result = {"upem": int(value["upem"])}
    for table, names in METRIC_FIELDS.items():
        if isinstance(value.get(table), dict):
            result[table] = {name: int(value[table][name]) for name in names if name in value[table]}
    coverage = value.get("coverage")
    if valid_coverage(coverage):
        result["coverage"] = {name: coverage[name] for name in COVERAGE_FIELDS}
    return result


def allowed_label(value: object, allowed: set[str]) -> str:
    return value if isinstance(value, str) and value in allowed else "unknown"


def load_json(path: Path) -> dict:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("oversize JSON")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


def command(args: list[str], timeout: float = 0.6) -> tuple[str, str]:
    try:
        result = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=timeout, check=False)
        if result.returncode:
            return "unavailable", ""
        return "ok", result.stdout[:65536]
    except subprocess.TimeoutExpired:
        return "timeout", ""
    except OSError:
        return "unavailable", ""


def current_build_key() -> str:
    # Used only for equality checking. Never return this value in the report.
    for prop in ("ro.build.fingerprint", "ro.build.display.id"):
        status, value = command(["getprop", prop], 0.4)
        if status == "ok" and value.strip():
            return value.strip()
    return ""


def probe_font(path: Path, face_index: int) -> dict:
    if path.stat().st_size > MAX_FONT_BYTES:
        return {"status": "too-large"}
    with path.open("rb") as stream:
        magic = stream.read(4)
    fmt = {b"ttcf": "TTC", b"OTTO": "OTF", b"\0\1\0\0": "TTF", b"true": "TTF"}.get(magic)
    if fmt is None:
        return {"status": "unsupported-format"}
    kwargs = {"fontNumber": face_index} if fmt == "TTC" else {}
    with TTFont(path, lazy=True, recalcBBoxes=False, recalcTimestamp=False, **kwargs) as font:
        result = {"status": "ok", "format": fmt, "faceIndex": face_index if fmt == "TTC" else 0,
                  "glyphLocation": "default", "metrics": {}, "probes": {}}
        if not all(tag in font for tag in ("head", "hhea", "OS/2")):
            return {"status": "missing-metric-tables", "format": fmt}
        head, hhea, os2 = font["head"], font["hhea"], font["OS/2"]
        result["metrics"] = {
            "upem": int(head.unitsPerEm),
            "head": {key: int(getattr(head, key)) for key in METRIC_FIELDS["head"]},
            "hhea": {key: int(getattr(hhea, key)) for key in METRIC_FIELDS["hhea"]},
            "os2": {key: int(getattr(os2, attr)) for key, attr in (
                ("fsSelection", "fsSelection"), ("typoAscender", "sTypoAscender"),
                ("typoDescender", "sTypoDescender"), ("typoLineGap", "sTypoLineGap"),
                ("winAscent", "usWinAscent"), ("winDescent", "usWinDescent"))},
        }
        if "fvar" in font:
            result["variableAxes"] = [{"tag": axis.axisTag, "default": axis.defaultValue,
                                       "min": axis.minValue, "max": axis.maxValue}
                                      for axis in font["fvar"].axes[:16]]
        cmap = font.getBestCmap() or {}
        glyphs = font.getGlyphSet()
        for char in PROBES:
            name = cmap.get(ord(char))
            if name is None or name not in glyphs:
                result["probes"][char] = {"status": "missing-glyph"}
                continue
            try:
                pen = BoundsPen(glyphs)
                glyphs[name].draw(pen)
                result["probes"][char] = {
                    "status": "ok" if pen.bounds is not None else "empty-glyph",
                    "bounds": list(pen.bounds) if pen.bounds is not None else None,
                    "advance": glyphs[name].width,
                }
            except Exception:
                result["probes"][char] = {"status": "probe-error"}
        return result


def apk_font_names(path: Path) -> dict:
    """List central-directory names only. Never decompress or execute APK entries."""
    try:
        size = path.stat().st_size
        if size > 512 * 1024 * 1024:
            return {"status": "too-large", "fontAssets": []}
        # Check EOCD before ZipFile allocates its central directory. ZIP64 and
        # unusually large/split archives are unnecessary for this diagnostic.
        with path.open("rb") as stream:
            stream.seek(max(0, size - 65557))
            tail = stream.read(65557)
        marker = tail.rfind(b"PK\x05\x06")
        if marker < 0 or len(tail) - marker < 22:
            return {"status": "invalid-archive", "fontAssets": []}
        eocd = tail[marker:marker + 22]
        count = int.from_bytes(eocd[10:12], "little")
        directory_size = int.from_bytes(eocd[12:16], "little")
        if count == 65535 or count > 40000 or directory_size > 12 * 1024 * 1024:
            return {"status": "archive-limit", "fontAssets": []}
        names = []
        truncated = False
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name = info.filename
                p = PurePosixPath(name)
                if (len(name) > 240 or not name.isprintable() or ".." in p.parts or
                        not (name.startswith("assets/") or name.startswith("res/font/")) or
                        p.suffix.lower() not in {".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"}):
                    continue
                if len(names) == 64:
                    truncated = True
                    break
                names.append(name)
        return {"status": "ok", "fontAssets": sorted(set(names)), "truncated": truncated}
    except (OSError, ValueError, zipfile.BadZipFile):
        return {"status": "unreadable-archive", "fontAssets": []}


class Collector:
    def __init__(self, module: Path, fs_root: Path = Path("/"), budget: float = 12.0):
        self.module = module
        self.fs_root = fs_root
        self.deadline = time.monotonic() + max(0.01, min(budget, 15.0))
        self.cache: dict[tuple, str] = {}
        self.data: dict = {}
        self.report = {
            "schema": SCHEMA, "status": "complete", "inventory": {"status": "not-collected"},
            "selection": {"maxAdditionalSlots": MAX_EXTRA_SLOTS}, "slots": [], "profiles": [],
            "apps": [], "limitations": {
                "appSelectedTypefaceCollected": False, "appProcessMapsCollected": False,
                "providerCachesCollected": False, "variableGlyphLocation": "default",
                "mountedFontsScope": "collector-process-mount-namespace",
                "activePayloadScope": "current .luoshu-payload only; not proof of app usage",
                "apkAssetsScope": "candidate resources only; not proof of selected Typeface",
                "stockGlyphScope": "trusted lower/mirror only; unavailable sources stay missing",
            }, "errors": [],
        }

    def check_budget(self) -> None:
        if time.monotonic() >= self.deadline:
            raise BudgetExpired()

    def physical(self, logical: str) -> Path:
        return self.fs_root / logical.lstrip("/")

    def inventory(self) -> None:
        try:
            data = load_json(self.module / "config/device_font_inventory.json")
            validate_inventory(data)
        except FileNotFoundError:
            self.report["inventory"] = {"status": "missing"}
            self.report["status"] = "partial"
            return
        except Exception:
            self.report["inventory"] = {"status": "invalid"}
            self.report["status"] = "partial"
            return
        build_key = current_build_key()
        if not build_key or build_key != data.get("buildKey"):
            self.report["inventory"] = {"status": "build-mismatch" if build_key else "build-unverified"}
            self.report["status"] = "partial"
            return
        self.data = data
        main = data.get("mainSlotPath", data.get("mainSlot", {}).get("path"))
        self.report["inventory"] = {"status": "ready", "buildMatches": True,
                                    "mainSlot": main if safe_slot(main) else None}

    def selected_slots(self) -> list[str]:
        candidates = {key for key in self.data.get("slots", {}) if safe_slot(key)}
        for _, logical_root in LOGICAL_FONT_ROOTS:
            self.check_budget()
            for root in (self.physical(str(logical_root)),
                         self.module / ".luoshu-payload" / logical_root.relative_to("/")):
                try:
                    # No recursive walk and no source-font directory scan.
                    with os.scandir(root) as entries:
                        for count, entry in enumerate(entries):
                            if count >= 4096:
                                self.report["errors"].append("slot-directory-limit")
                                self.report["status"] = "partial"
                                break
                            key = str(logical_root / entry.name)
                            if safe_slot(key) and KEY_NAME.match(entry.name):
                                candidates.add(key)
                except OSError:
                    continue
        def priority(key: str) -> tuple:
            name = PurePosixPath(key).name.lower()
            regular = not any(word in name for word in ("bold", "italic", "thin", "light", "black"))
            return (0 if "clock" in name else 1 if regular else 2,
                    0 if key.startswith("/system/") else 1, key)
        main = self.report["inventory"].get("mainSlot")
        extra = sorted((key for key in candidates if key != main), key=priority)
        chosen = ([main] if main else []) + extra[:MAX_EXTRA_SLOTS]
        self.report["selection"].update(selectedCount=len(chosen), availableCount=len(candidates),
                                         omittedCount=max(0, len(candidates) - len(chosen)))
        return chosen

    def reference(self, path: Path, face: int) -> dict:
        self.check_budget()
        try:
            stat = path.stat()
            if not path.is_file():
                return {"status": "missing"}
            key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, face)
        except OSError:
            return {"status": "missing"}
        if key not in self.cache:
            ident = f"font-{len(self.cache) + 1}"
            profile = {"id": ident, "status": "interrupted"}
            self.cache[key] = ident
            self.report["profiles"].append(profile)
            try:
                profile.update(probe_font(path, face))
            except Exception:
                profile["status"] = "unreadable-font"
            if profile["status"] != "ok":
                self.report["status"] = "partial"
        return {"status": "observed", "profile": self.cache[key]}

    def stock_glyphs(self, logical: str, face: int) -> dict:
        p = PurePosixPath(logical)
        # Never read an inventory actualPath as stock: after reboot that path
        # may be overlaid. Only established read-only lower/mirror roots qualify.
        roots = [self.physical(f"/data/adb/luoshu/self-mount/lower/{p.parts[1]}-fonts")]
        roots.extend(self.physical(str(prefix / p.parent.relative_to("/"))) for prefix in MIRROR_PREFIXES)
        for root in roots:
            path = root / p.name
            if path.is_file() and not path.is_symlink():
                return self.reference(path, face)
        return {"status": "trusted-stock-file-unavailable"}

    def slot(self, logical: str, processing: dict) -> None:
        entry = self.data.get("slots", {}).get(logical, {})
        try:
            face = max(0, min(63, int(entry.get("faceIndex", 0))))
        except (TypeError, ValueError):
            face = 0
        item = {"slot": logical, "stock": {"status": "missing-inventory-slot"},
                "activePayload": {"status": "not-collected"},
                "mountedInCollector": {"status": "not-collected"},
                "processing": processing.get(logical, {"status": "not-reported"})}
        self.report["slots"].append(item)
        if entry:
            item["stock"] = {"status": "inventory-metrics", "metrics": metrics_only(entry["metrics"]),
                              "glyphs": {"status": "not-collected"}}
        item["activePayload"] = self.reference(self.module / ".luoshu-payload" / logical.lstrip("/"), face)
        item["mountedInCollector"] = self.reference(self.physical(logical), face)
        if entry:
            item["stock"]["glyphs"] = self.stock_glyphs(logical, face)

    def processing_report(self) -> dict:
        try:
            data = load_json(self.module / ".luoshu-payload/.luoshu-metrics-report.json")
            if data.get("schema") != "luoshu-slot-metrics-v1" or not isinstance(data.get("slots"), list):
                return {}
            result = {}
            for item in data["slots"][:2048]:
                if not isinstance(item, dict) or not safe_slot(item.get("slot")):
                    continue
                result[item["slot"]] = {"status": "reported",
                    "metricsSource": allowed_label(item.get("metricsSource"), {"stock", "fallback", "preserved"}),
                    "reason": allowed_label(item.get("reason"), {"missing-or-ineligible-stock-slot",
                        "invalid-stock-metrics", "collection-metrics-preserved"}),
                    "layoutBoundsSource": allowed_label(item.get("layoutBoundsSource"), {"stock", "source", "stock-line-descent"}),
                    "bitmapBaselineReason": allowed_label(item.get("bitmapBaselineReason"), {
                        "stock-preserved", "unproven-latin-ink-bounds", "latin-descender-would-clip",
                        "latin-ui-bottom-to-descent", "no-excess-bottom-padding"}),
                    "cjkRoutingSource": allowed_label(item.get("cjkRoutingSource"), {"stock-fallback", "source"}),
                    "cjkRoutingReason": allowed_label(item.get("cjkRoutingReason"), CJK_ROUTING_REASONS),
                    "baselineReason": allowed_label(item.get("baselineReason"), BASELINE_REASONS),
                    "baselineProbe": allowed_label(item.get("baselineProbe"), {"cjk", "digits", "latinCap"})}
                shift = item.get("baselineShift")
                if type(shift) is int and -32768 <= shift <= 32767:
                    result[item["slot"]]["baselineShift"] = shift
                glyphs = item.get("baselineGlyphs")
                if type(glyphs) is int and 0 <= glyphs <= 1000000:
                    result[item["slot"]]["baselineGlyphs"] = glyphs
                removed = item.get("removedCjkMappings")
                if type(removed) is int and 0 <= removed <= 0x110000:
                    result[item["slot"]]["removedCjkMappings"] = removed
                correction = item.get("bitmapBaselineCorrection")
                if type(correction) is int and 0 <= correction <= 32767:
                    result[item["slot"]]["bitmapBaselineCorrection"] = correction
            return result
        except Exception:
            return {}

    def apps(self) -> None:
        for package in PACKAGES:
            self.check_budget()
            app = {"package": package, "status": "not-collected", "apks": []}
            self.report["apps"].append(app)
            status, output = command(["pm", "path", package], 0.7)
            if status != "ok":
                app["status"] = status
                continue
            paths = [Path(line[8:]) for line in output.splitlines() if line.startswith("package:")]
            if not paths:
                app["status"] = "not-installed-or-unavailable"
                continue
            app["status"] = "ok"
            for index, path in enumerate(paths[:8]):
                self.check_budget()
                # PM supplies installed APK paths. Export no data-app token,
                # filesystem prefix or install path, only a numbered archive.
                allowed = ("/data/app/", "/system/", "/system_ext/", "/product/", "/vendor/",
                           "/my_product/", "/oplus_product/", "/mi_ext/")
                if (not str(path).startswith(allowed) or path.suffix.lower() != ".apk"
                        or ".." in path.parts):
                    app["apks"].append({"archive": index, "status": "unexpected-apk-path"})
                    continue
                app["apks"].append({"archive": index, **apk_font_names(self.physical(str(path)))})
            app["truncated"] = len(paths) > 8

    def collect(self, include_apps: bool = True) -> dict:
        previous = signal.getsignal(signal.SIGALRM)
        def expire(_signal, _frame):
            raise BudgetExpired()
        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, max(0.001, self.deadline - time.monotonic()))
        try:
            self.inventory()
            processing = self.processing_report()
            selected = self.selected_slots()
            # Preserve one important live profile before optional app evidence,
            # then inspect clock APK resources before many distinct CJK slots
            # can consume the budget. No font fallback is invented on timeout.
            if selected:
                self.slot(selected[0], processing)
            if include_apps:
                self.apps()
            for logical in selected[1:]:
                self.slot(logical, processing)
        except BudgetExpired:
            self.report["status"] = "partial"
            self.report["errors"].append("time-budget-exhausted")
        except Exception:
            self.report["status"] = "partial"
            self.report["errors"].append("collection-error")
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        self.report["profileCount"] = len(self.report["profiles"])
        self.report["selection"]["collectedCount"] = len(self.report["slots"])
        return self.report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/sdcard/LuoShu/reports/LuoShu-font-layout.json"))
    args = parser.parse_args()
    report = Collector(args.module).collect()
    temporary = None
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent,
                                         prefix=".font-layout-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, args.output)
        print(str(args.output))
        return 0
    except (OSError, ValueError):
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        print("font-layout-diagnostic-write-failed", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
