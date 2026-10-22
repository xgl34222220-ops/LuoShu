#!/usr/bin/env python3
"""Read-only per-process font audit: which font *files* a process actually maps.

Since Android 12 normal Apps receive system fonts through a shared-memory font map
from system_server, so a `.ttf/.otf/.ttc` path inside an App's `/proc/<pid>/maps`
means that process opened the file itself (MIUI FontUtils/VFUtils, theme fonts,
Chromium/WebView reading fonts.xml, APK-private fonts).  For each audited process
this helper lists the mapped font files, takes the file identity (`dev:ino`) that
the kernel reports in maps -- the inode that was really loaded, even if a mount
changed afterwards -- and compares it with LuoShu's private payload files.

Classes per mapped file:

* ``luoshu``  -- the mapped inode is a LuoShu payload file;
* ``stock``   -- a partition font (`/system/fonts`, `/product/fonts`, ...) that is
  not a LuoShu payload inode.  ``onReplacedSlot`` marks the strongest gap: LuoShu
  replaced that very slot (or the path now resolves to LuoShu) but the process
  still maps the original inode;
* ``theme``   -- `/data/system/theme/...` or `/data/system/fonts/...`;
* ``updatable`` -- FontManagerService `/data/fonts/files`;
* ``other``   -- App-private or unknown locations (only the basename is reported).

Output is a flat `key=value` conf.  Nothing is modified: maps and stat only.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA = "luoshu-font-audit-v1"
FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")
SAFE_TOKEN = re.compile(r"[^A-Za-z0-9._@#+/:-]")
MAX_ENTRIES = 256
MAX_LISTED = 24
MAX_PAYLOAD_FILES = 4096
# Processes whose stock mappings are expected by design (font server, Chromium reading
# fonts.xml for every script): only stock inodes on slots LuoShu replaced count as a gap.
SERVER_LIKE = ("systemServer", "webview")
_PARTITION_FONT_RE = re.compile(
    r"^/(?:system(?:/(?:product|system_ext|vendor))?|system_ext|product|vendor|odm|oem|mi_ext|cust"
    r"|my_[a-z_]+|oplus_[a-z_]+|hw_product|apex/[^/]+)/(?:.*/)?fonts?/[^/]+$"
)
_MAPS_RE = re.compile(r"^\s*([0-9a-fA-F]+)-([0-9a-fA-F]+)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+):([0-9a-fA-F]+)\s+(\d+)\s*(.*)$")

Identity = tuple[int, int]
StatFn = Callable[[str], "os.stat_result | Any"]


def safe_token(value: str, limit: int = 160) -> str:
    return SAFE_TOKEN.sub("_", str(value or ""))[:limit]


def ident_str(identity: Identity | None) -> str:
    if not identity:
        return "none"
    dev, ino = identity
    return f"{os.major(dev)}.{os.minor(dev)}:{ino}"


def is_font_path(path: str) -> bool:
    base = path.split(" (deleted)", 1)[0].strip()
    return base.lower().endswith(FONT_SUFFIXES)


# ---------------------------------------------------------------- maps
def parse_maps(text: str) -> tuple[list[dict[str, Any]], int]:
    """Return ([{path, identity, deleted}], memfdFontSegments) for mapped font files."""
    seen: dict[tuple[str, Identity], dict[str, Any]] = {}
    memfd = 0
    for line in (text or "").splitlines():
        match = _MAPS_RE.match(line)
        if not match:
            continue
        path = match.group(8).strip()
        if not path:
            continue
        lowered = path.lower()
        if ("memfd:" in lowered or "ashmem" in lowered) and "font" in lowered:
            memfd += 1
            continue
        if not path.startswith("/") or not is_font_path(path):
            continue
        deleted = path.endswith(" (deleted)")
        clean = path[: -len(" (deleted)")] if deleted else path
        ino = int(match.group(7))
        dev = os.makedev(int(match.group(5), 16), int(match.group(6), 16))
        identity: Identity = (dev, ino)
        key = (clean, identity)
        if key not in seen and len(seen) < MAX_ENTRIES:
            seen[key] = {"path": clean, "identity": identity if ino else None, "deleted": deleted}
    return list(seen.values()), memfd


# ---------------------------------------------------------------- payload identity
def _rel_variants(path: str) -> list[str]:
    rel = path.lstrip("/")
    variants = [rel]
    for prefix in ("system/product/", "system/system_ext/", "system/vendor/"):
        if rel.startswith(prefix):
            variants.append(rel[len("system/"):])
    for part in ("product/", "system_ext/", "vendor/"):
        if rel.startswith(part):
            variants.append("system/" + rel)
    return variants


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class PayloadIndex:
    """LuoShu payload files under `<module>/.luoshu-payload`, keyed by identity and rel path."""

    def __init__(self, module: Path | None, stat: StatFn = os.stat) -> None:
        self.ids: set[Identity] = set()
        self.by_rel: dict[str, dict[str, Any]] = {}
        self.names: set[str] = set()
        self._stat = stat
        root = (module / ".luoshu-payload") if module else None
        if root is None or not root.is_dir():
            return
        count = 0
        for dirpath, _dirs, files in os.walk(root):
            for name in sorted(files):
                if not name.lower().endswith(FONT_SUFFIXES):
                    continue
                full = Path(dirpath) / name
                try:
                    st = stat(str(full))
                except OSError:
                    continue
                rel = str(full.relative_to(root)).replace(os.sep, "/")
                identity = (st.st_dev, st.st_ino)
                self.ids.add(identity)
                self.by_rel[rel] = {"path": full, "identity": identity, "size": st.st_size}
                self.names.add(name.lower())
                count += 1
                if count >= MAX_PAYLOAD_FILES:
                    return

    def __len__(self) -> int:
        return len(self.by_rel)

    def slot_for(self, device_path: str) -> dict[str, Any] | None:
        for rel in _rel_variants(device_path):
            if rel in self.by_rel:
                return self.by_rel[rel]
        return None

    def same_content(self, device_path: str, visible: Path) -> bool:
        """Content fallback (overlay mounts report another dev): equal size and sha256."""
        slot = self.slot_for(device_path)
        if not slot:
            return False
        try:
            if self._stat(str(visible)).st_size != slot["size"]:
                return False
            return _sha256(visible) == _sha256(slot["path"])
        except OSError:
            return False


def visible_path(device_path: str, visible_root: str = "/") -> Path:
    root = visible_root or "/"
    if root == "/":
        return Path(device_path)
    return Path(root.rstrip("/")) / device_path.lstrip("/")


def stat_identity(path: Path, stat: StatFn = os.stat) -> Identity | None:
    try:
        st = stat(str(path))  # follows symlinks: same as `stat -L`
    except OSError:
        return None
    return (st.st_dev, st.st_ino)


# ---------------------------------------------------------------- classify
def location_class(path: str) -> str:
    if path.startswith("/data/fonts/"):
        return "updatable"
    if path.startswith("/data/system/theme/") or path.startswith("/data/system/fonts/"):
        return "theme"
    if _PARTITION_FONT_RE.match(path):
        return "stock"
    return "other"


def classify(entries: Iterable[dict[str, Any]], payload: PayloadIndex, visible_root: str = "/",
             stat: StatFn = os.stat) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in entries:
        path = entry["path"]
        mapped = entry.get("identity")
        current = stat_identity(visible_path(path, visible_root), stat)
        if mapped is not None:
            is_luoshu = mapped in payload.ids
        else:
            is_luoshu = current in payload.ids if current else False
        item = dict(entry, current=current, kind="luoshu" if is_luoshu else location_class(path),
                    onReplacedSlot=False)
        if not is_luoshu and item["kind"] in ("stock", "theme"):
            replaced = payload.slot_for(path) is not None or (current is not None and current in payload.ids)
            if mapped is not None and current is not None and current != mapped and current in payload.ids:
                item["reason"] = "loaded-before-mount"
            elif replaced:
                item["reason"] = "stock-inode"
            item["onReplacedSlot"] = replaced
        result.append(item)
    return result


def summarize(name: str, items: list[dict[str, Any]], memfd: int) -> dict[str, str]:
    def paths(kind: str) -> str:
        chosen = [i for i in items if i["kind"] == kind]
        if kind == "other":
            listed = [os.path.basename(i["path"]) for i in chosen]
        else:
            listed = [f"{i['path']}@{ident_str(i.get('identity'))}" for i in chosen]
        return ";".join(safe_token(p) for p in listed[:MAX_LISTED]) or "none"

    stock = [i for i in items if i["kind"] == "stock"]
    replaced = [i for i in items if i.get("onReplacedSlot")]
    return {
        f"{name}.state": "ok",
        f"{name}.loadedFonts": str(len(items)),
        f"{name}.luoshuHits": str(sum(1 for i in items if i["kind"] == "luoshu")),
        f"{name}.stockHits": str(len(stock)),
        f"{name}.stockOnReplacedSlot": str(len(replaced)),
        f"{name}.themeHits": str(sum(1 for i in items if i["kind"] == "theme")),
        f"{name}.updatableHits": str(sum(1 for i in items if i["kind"] == "updatable")),
        f"{name}.otherHits": str(sum(1 for i in items if i["kind"] == "other")),
        f"{name}.memfdFontSegments": str(memfd),
        f"{name}.luoshuPaths": paths("luoshu"),
        f"{name}.stockPaths": paths("stock"),
        f"{name}.replacedSlotStockPaths": ";".join(
            safe_token(f"{i['path']}@{ident_str(i.get('identity'))}:{i.get('reason', 'stock-inode')}")
            for i in replaced[:MAX_LISTED]) or "none",
        f"{name}.themePaths": paths("theme"),
        f"{name}.otherFiles": paths("other"),
    }


def verdict(report: dict[str, str], audited: list[str], payload_files: int) -> str:
    if payload_files == 0:
        return "inactive:no-payload"
    if not audited:
        return "unknown:no-process-readable"
    gaps: list[str] = []
    for name in audited:
        stock = int(report.get(f"{name}.stockHits", "0") or 0)
        slot = int(report.get(f"{name}.stockOnReplacedSlot", "0") or 0)
        counted = slot if name in SERVER_LIKE else stock
        if counted or slot:
            gaps.append(f"{name}={stock}/{slot}")
    return "ok" if not gaps else "gap:" + ",".join(gaps)


# ---------------------------------------------------------------- report
def _parse_targets(values: list[str]) -> list[tuple[str, str, str]]:
    """`name=pid` or `name=pid@package`; pid may be empty when not running."""
    result = []
    for raw in values or []:
        name, _, rest = raw.partition("=")
        pid, _, package = rest.partition("@")
        name = re.sub(r"[^A-Za-z]", "", name)
        if name:
            result.append((name, pid.strip(), package.strip()))
    return result


# A process that exits between the pid listing and the maps read is not an
# unreadable process: /proc/<pid> is gone (ENOENT), the task is dying (ESRCH),
# or the pid now belongs to another program.
EXITED_ERRNOS = frozenset({errno.ENOENT, errno.ESRCH})


def _process_name(proc_root: Path, pid: str) -> str:
    return (proc_root / pid / "cmdline").read_bytes().split(b"\0", 1)[0].decode("utf-8", "replace")


def process_exited(proc_root: Path, pid: str, package: str = "", error: OSError | None = None) -> bool:
    if error is not None and error.errno in EXITED_ERRNOS:
        return True
    try:
        if not (proc_root / pid).is_dir():
            return True
    except OSError:
        return False
    if not package:
        return False
    try:
        name = _process_name(proc_root, pid)
    except OSError as exc:
        return exc.errno in EXITED_ERRNOS
    # Zombies show an empty cmdline; a reused pid shows another program.
    return not name or name.split(":", 1)[0] != package.split(":", 1)[0]


def _errno_name(error: OSError) -> str:
    return errno.errorcode.get(error.errno or 0, error.__class__.__name__)


def build_report(args: argparse.Namespace, stat: StatFn = os.stat) -> dict[str, str]:
    payload = PayloadIndex(args.module, stat)
    report: dict[str, str] = {"schema": SCHEMA, "time": str(int(time.time())),
                              "payloadFiles": str(len(payload))}
    audited: list[str] = []
    targets = _parse_targets(args.target)
    for name, pid, package in targets:
        if package:
            report[f"{name}.package"] = safe_token(package, 96)
        if not pid.isdigit():
            report[f"{name}.state"] = "not-running"
            continue
        maps = Path(args.proc_root) / pid / "maps"
        try:
            text = maps.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            if process_exited(Path(args.proc_root), pid, package, exc):
                report[f"{name}.state"] = "exited"
            else:
                report[f"{name}.state"] = "maps-unreadable"
                report[f"{name}.mapsError"] = _errno_name(exc)
            continue
        if not text.strip() and process_exited(Path(args.proc_root), pid, package):
            report[f"{name}.state"] = "exited"
            continue
        entries, memfd = parse_maps(text)
        items = classify(entries, payload, args.visible_root, stat)
        report.update(summarize(name, items, memfd))
        audited.append(name)
    report["audited"] = ",".join(audited) or "none"
    report["fontAudit"] = verdict(report, audited, len(payload))
    return report


def render(report: dict[str, str]) -> str:
    head = [k for k in ("schema", "time", "fontAudit", "audited", "payloadFiles") if k in report]
    rest = [k for k in report if k not in head]
    return "".join(f"{key}={report[key]}\n" for key in head + rest)


def atomic_write(text: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    try:
        temporary.chmod(0o644)
    except OSError:
        pass
    temporary.replace(output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", action="append", default=[],
                        help="name=pid[@package]; empty pid means not running")
    parser.add_argument("--proc-root", default="/proc")
    parser.add_argument("--module", type=Path)
    parser.add_argument("--visible-root", default="/")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args)
    except Exception as exc:  # diagnostics must never break the caller
        report = {"schema": SCHEMA, "time": str(int(time.time())),
                  "fontAudit": "unknown:helper-error-" + safe_token(exc.__class__.__name__, 48)}
    text = render(report)
    if args.output:
        try:
            atomic_write(text, args.output)
        except OSError:
            pass
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
