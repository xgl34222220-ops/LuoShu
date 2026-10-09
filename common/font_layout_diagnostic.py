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
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
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
# Default text routes whose Latin/digit glyphs apps actually draw with. A report
# that spends its slot budget on payload-only aliases absent from the ROM (e.g.
# 100.ttf..900.ttf) cannot show whether these routes are stock or replaced.
LATIN_ROUTE_NAMES = frozenset({
    "misansvf_overlay.ttf", "misanslatinvf.ttf", "roboto-regular.ttf", "robotostatic-regular.ttf",
    "robotoflex-regular.ttf", "googlesans-regular.ttf", "googlesanstext-regular.ttf",
    "syssans-en-regular.ttf", "sysfont-regular.ttf", "droidsans.ttf",
})
ROUTE_TARGET = re.compile(r"/(?:(?:system|system_ext|product|vendor|odm|oem|mi_ext|my_product|hw_product|cust)/fonts"
                          r"|data/system/fonts/theme_webview|data/system/theme/fonts)/[A-Za-z0-9_.+-]{1,120}")
CJK_ROUTING_REASONS = {"stock-coverage-refresh-pending", "specialized-slot", "stock-han-slot",
                       "not-latin-ui-slot", "no-staged-cjk-fallback", "stock-latin-primary"}

MIX_LOG_BYTES = 256 * 1024
MIX_EVENT_LIMIT = 256
MIX_REQUEST = re.compile(r"mix-request-[0-9]{1,12}-[0-9]{1,12}")
MIX_OUTER = re.compile(r"(?:auto-mix|axes)-[0-9]{1,12}-[0-9]{1,12}")
MIX_TASK = re.compile(r"(?:auto-mix|axes|mix)-[0-9]{1,12}-[0-9]{1,12}(?:\.(?:apply|monitor))?")
MIX_BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
MIX_COMPONENTS = {"prepare", "composite", "fixed-apply", "finalize", "worker"}
MIX_PHASES = {"prepare", "cache_lookup", "cold_composite_runner", "validate", "cache_publish",
              "reuse_output", "source_validate", "map_payload", "local_commit", "child_start",
              "wait_child_cleanup", "worker_finalize", "safe_apply", "finalize_lock", "complete_hyperos",
              "complete_coloros", "next_commit", "live_mount", "finalize_release"}
MIX_UNITS = {"cjk", "latin", "digit", "fixed", *(f"w{n}" for n in range(100, 901, 100))}
MIX_WEIGHTS = {"fixed", *(str(n) for n in range(100, 901, 100))}
MIX_METHODS = {"probe", "miss", "cold", "receipt-hit", "legacy-validated-hit", "same-source",
               "copy", "prepare", "apply", "wait", "finalize", "skipped"}
MIX_FIELDS = {"schema", "request", "outer", "task", "boot", "start", "component", "phase",
              "unit", "weight", "clock", "event", "method", "uptimeSeconds"}


def _mix_object(pairs: list[tuple[str, object]]) -> dict:
    if len({name for name, _ in pairs}) != len(pairs):
        raise ValueError("duplicate record fields")
    return dict(pairs)


def _mix_read(path: Path, limit: int, module: Path | None = None, tail: bool = False) -> tuple[bytes, bool]:
    """One regular, bounded file. Never read FIFOs or outside module aliases."""
    if module is not None and module.resolve() not in path.resolve().parents:
        raise ValueError("outside diagnostic scope")
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("regular file required")
        truncated = info.st_size > limit
        if truncated and not tail:
            raise ValueError("oversize record")
        if truncated:
            stream.seek(info.st_size - limit)
        data = stream.read(limit)
        if truncated:
            data = data.partition(b"\n")[2]
        return data, truncated


def _mix_uptime(value: str) -> int:
    if re.fullmatch(r"[0-9]{1,10}\.[0-9]{1,3}", value) is None:
        raise ValueError("invalid clock")
    seconds, fraction = value.split(".")
    return int(seconds) * 1000 + int((fraction + "000")[:3])


def _mix_event(line: str, boot: str) -> dict:
    if len(line) > 600 or not line.startswith("[MIX-PHASE] "):
        raise ValueError("invalid event")
    pairs = [word.split("=", 1) for word in line.split()[1:]]
    if any(len(pair) != 2 for pair in pairs) or len({pair[0] for pair in pairs}) != len(pairs):
        raise ValueError("invalid fields")
    event = dict(pairs)
    expected = MIX_FIELDS | ({"elapsedMs", "result"} if event.get("event") == "end" else set())
    if (set(event) != expected or event.get("event") not in {"begin", "end"}
            or event.get("schema") != "1" or event.get("clock") != "proc-uptime"
            or event.get("boot") != boot or MIX_BOOT.fullmatch(boot) is None
            or MIX_REQUEST.fullmatch(event.get("request", "")) is None
            or MIX_OUTER.fullmatch(event.get("outer", "")) is None
            or MIX_TASK.fullmatch(event.get("task", "")) is None
            or re.fullmatch(r"[0-9]{1,20}|unknown", event.get("start", "")) is None
            or event.get("component") not in MIX_COMPONENTS or event.get("phase") not in MIX_PHASES
            or event.get("unit") not in MIX_UNITS or event.get("weight") not in MIX_WEIGHTS
            or event.get("method") not in MIX_METHODS):
        raise ValueError("untrusted event")
    event["clockMs"] = _mix_uptime(event["uptimeSeconds"])
    if event["event"] == "end":
        if (re.fullmatch(r"[0-9]{1,8}", event["elapsedMs"]) is None
                or int(event["elapsedMs"]) > 86400000 or event["result"] not in {"ok", "failed"}):
            raise ValueError("invalid result")
    return event


def _mix_total(module: Path, outer: str, starts: set[str], boot: str) -> dict:
    result = {"status": "unavailable", "scope": "backend-task-including-cleanup", "clock": "python-monotonic"}
    if len(starts) != 1 or "unknown" in starts:
        return result
    name = "auto_multiweight_worker.pid" if outer.startswith("auto-mix-") else "axes_worker.pid"
    try:
        payload, _ = _mix_read(module / ".luoshu-state/tasks" / (name + ".cleanup.json"), 16384, module)
        receipt = json.loads(payload, object_pairs_hook=_mix_object)
        duration = receipt.get("durationSeconds")
        code = receipt.get("result")
        if (receipt.get("schema") != "task-cleanup-v2" or receipt.get("task") != outer
                or receipt.get("boot") != boot or receipt.get("start") not in starts
                or type(duration) not in {int, float} or not 0 <= duration <= 86400 or not math.isfinite(duration)
                or type(code) is not int or not 0 <= code <= 255 or type(receipt.get("cleaned")) is not bool):
            return result
        if receipt["cleaned"] and (receipt.get("leftoverPids") != [] or receipt.get("cleanupErrors", []) != []):
            return result
        reasons = {"completed", "cancelled", "timeout", "parent-exited", "launch-failed", "parent-cleanup"}
        result.update(status="available", durationSeconds=duration, result=code, cleaned=receipt["cleaned"],
                      reason=allowed_label(receipt.get("reason"), reasons))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return result


def collect_mix_timings(module: Path, fs_root: Path = Path("/")) -> dict:
    """No raw task, boot, absolute clock, source path or cleanup JSON escapes."""
    report = {"schema": "luoshu-mix-phase-diagnostic-v1", "status": "unavailable", "requests": [],
              "phaseClock": "proc-uptime", "phaseResolutionMs": 10, "phaseClockIncludesSuspend": True,
              "backendTotalExcludes": ["router-preflight", "app-observation", "phone-reboot"],
              "overlappingScopesAreNotAdditive": True, "maxLogBytes": MIX_LOG_BYTES,
              "maxEvents": MIX_EVENT_LIMIT, "maxRequests": 3, "truncated": False}
    try:
        boot_bytes, _ = _mix_read(fs_root / "proc/sys/kernel/random/boot_id", 64)
        boot = boot_bytes.decode("ascii").strip()
        data, truncated = _mix_read(module / "logs/fontswitch.log", MIX_LOG_BYTES, module, tail=True)
        records = []
        rejected = 0
        lines = data.decode("utf-8", errors="replace").splitlines()
        for line in lines:
            if not line.startswith("[MIX-PHASE] "):
                continue
            try:
                records.append(_mix_event(line, boot))
            except ValueError:
                rejected += 1
        report["rejectedEvents"] = rejected
        report["truncated"] = truncated or len(records) > MIX_EVENT_LIMIT
        records = records[-MIX_EVENT_LIMIT:]
        requests = list(dict.fromkeys(item["request"] for item in reversed(records)))[:3][::-1]
        for ordinal, request in enumerate(requests, 1):
            group = [item for item in records if item["request"] == request]
            outers = {item["outer"] for item in group}
            if len(outers) != 1:
                continue
            outer = next(iter(outers))
            phases = []
            pending = {}
            starts = {item["start"] for item in group if item["task"] == outer}
            for event in group:
                key = tuple(event[name] for name in ("task", "start", "component", "phase", "unit", "weight"))
                if event["event"] == "begin":
                    if key in pending:
                        phases[pending[key][0]]["status"] = "unavailable"
                    item = {name: event[name] for name in ("component", "phase", "unit", "weight", "method")}
                    item["status"] = "incomplete"
                    pending[key] = (len(phases), event["clockMs"])
                    phases.append(item)
                elif key in pending:
                    index, started = pending.pop(key)
                    elapsed = event["clockMs"] - started
                    if elapsed < 0 or elapsed != int(event["elapsedMs"]):
                        phases[index]["status"] = "unavailable"
                    else:
                        phases[index].update(status="complete" if event["result"] == "ok" else "failed",
                                             elapsedMs=elapsed, method=event["method"])
            backend = _mix_total(module, outer, starts, boot)
            report["requests"].append({"request": ordinal, "phases": phases, "backendTotal": backend,
                                       "safeSwitch": {"status": "unavailable", "scope": "safe-switch-worker",
                                                      "clock": "proc-uptime", "reason": "identity-not-associated"}})
        if report["requests"]:
            report["status"] = "available"
    except (OSError, ValueError, UnicodeError):
        pass
    return report


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
        slots = self.data.get("slots", {})

        def present(key: str) -> bool:
            # The ROM slot itself (a stock file or framework symlink), not a
            # payload-only alias that this device never loads.
            return key in slots or os.path.lexists(self.physical(key))

        def priority(key: str) -> tuple:
            name = PurePosixPath(key).name.lower()
            regular = not any(word in name for word in ("bold", "italic", "thin", "light", "black"))
            on_rom = present(key)
            return (0 if on_rom and name in LATIN_ROUTE_NAMES else 1 if on_rom else 2,
                    0 if "clock" in name else 1 if regular else 2,
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
        route = self.route(logical)
        if route:
            item["mountedRoute"] = route
        if entry:
            item["stock"]["glyphs"] = self.stock_glyphs(logical, face)

    def route(self, logical: str) -> dict | None:
        """Where a ROM symlink slot (e.g. HyperOS MiSansVF_Overlay) resolves now.

        Only fixed system font locations are named; anything else is "other".
        The profile under mountedInCollector is what this route actually reads.
        """
        path = self.physical(logical)
        if not path.is_symlink():
            return None
        try:
            resolved = Path(os.path.realpath(path))
            relative = "/" + resolved.relative_to(self.fs_root.resolve()).as_posix()
        except (OSError, ValueError):
            return {"status": "symlink", "target": "other"}
        target = relative if ROUTE_TARGET.fullmatch(relative) else "other"
        return {"status": "symlink", "target": target,
                "targetIsRegularFile": resolved.is_file() and not resolved.is_symlink()}

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
                    "cjkRoutingReason": allowed_label(item.get("cjkRoutingReason"), CJK_ROUTING_REASONS)}
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
            self.check_budget()
            self.report["mixTimings"] = collect_mix_timings(self.module, self.fs_root)
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
