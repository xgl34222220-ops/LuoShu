#!/usr/bin/env python3
"""Safe manual stock-font inventory wrapper for LuoShu private payload mode."""
from __future__ import annotations

import os
from pathlib import Path

import font_inventory as inventory
import font_inventory_scan_v3 as scanner


_ACTIVE_OVERLAY_MODULE: Path | None = None
_STOCK_VIEW_SOURCES: dict[str, dict[str, str]] = {}


def _record_stock_view(logical: Path, view: str, actual: Path, detail: str = "") -> None:
    _STOCK_VIEW_SOURCES[str(logical)] = {
        "logical": str(logical),
        "view": view,
        "actual": str(actual),
        "detail": detail,
    }


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _mirror_view_name(prefix: Path) -> str:
    value = str(prefix).lower()
    if ".magisk/mirror" in value or "/magisk/mirror" in value:
        return "magisk-mirror"
    if "ksu" in value or "kernelsu" in value:
        return "kernelsu-mirror"
    if "apatch" in value or "/ap/" in value:
        return "apatch-mirror"
    return "root-mirror"


def _inject_stock_view_report(path: Path, data: dict, writer) -> None:
    if isinstance(data, dict):
        records = [dict(_STOCK_VIEW_SOURCES[key]) for key in sorted(_STOCK_VIEW_SOURCES)]
        data["stockViewSources"] = records
        counts: dict[str, int] = {}
        for item in records:
            view = item.get("view", "unknown")
            counts[view] = counts.get(view, 0) + 1
        summary = data.setdefault("scanSummary", {})
        if isinstance(summary, dict):
            summary["stockViewSourceCounts"] = dict(sorted(counts.items()))
    writer(path, data)


def _private_root_overlaid(logical: Path) -> bool:
    module = _ACTIVE_OVERLAY_MODULE
    if module is None:
        return False
    relative = logical.relative_to("/")
    for payload in (module / ".luoshu-payload", module / ".luoshu-payload-next", module):
        root = payload / relative
        if not root.is_dir():
            continue
        try:
            if any(path.is_file() for path in root.iterdir()):
                return True
        except OSError:
            continue
    return False


def _private_overlay_risk(module: Path | None) -> bool:
    global _ACTIVE_OVERLAY_MODULE
    _ACTIVE_OVERLAY_MODULE = None
    # LuoShu's early boot hook sets this only immediately before self-mount, while
    # skip_mount/skip_mountify still leave the logical ROM roots stock-visible.
    if os.environ.get("LUOSHU_STOCK_VIEW_VERIFIED", "").strip() == "1":
        return False
    if not module or not module.is_dir():
        return False
    try:
        active = (module / "config/active_font.conf").read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        active = ""
    if not active or active == "default":
        return False
    _ACTIVE_OVERLAY_MODULE = module

    payload_roots = (
        module / ".luoshu-payload",
        module / ".luoshu-payload-next",
        module,
    )
    for payload in payload_roots:
        for partition, logical in inventory.LOGICAL_FONT_ROOTS:
            font_dir = payload / logical.relative_to("/")
            if not font_dir.is_dir():
                continue
            try:
                if any(
                    path.is_file() and path.suffix.lower() in inventory.FONT_EXTENSIONS
                    for path in font_dir.iterdir()
                ):
                    return True
            except OSError:
                continue
    # An active non-default selection must still be treated as overlay risk even if
    # its private payload is temporarily hidden from this process namespace.
    return True


def _safe_pick_actual_root(logical: Path, explicit: Path | None, overlay_risk: bool) -> Path:
    if explicit is not None:
        _record_stock_view(logical, "explicit", explicit)
        return explicit

    verified = os.environ.get("LUOSHU_STOCK_VIEW_VERIFIED", "").strip() == "1"
    if not overlay_risk:
        _record_stock_view(logical, "pre-mount-direct" if verified else "direct", logical)
        return logical

    # Overlay risk is per partition, not global. A custom system/fonts payload
    # does not make an untouched vendor/fonts tree unsafe to scan directly.
    if _ACTIVE_OVERLAY_MODULE is not None and not _private_root_overlaid(logical):
        if not _safe_exists(logical):
            _record_stock_view(logical, "missing-optional", logical)
            return logical
        _record_stock_view(logical, "direct-unoverlaid", logical)
        return logical

    attempted: list[str] = []
    parts = logical.parts
    proc1_root = Path(os.environ.get("LUOSHU_PROC1_ROOT", "/proc/1/root"))
    if len(parts) >= 3 and parts[0] == "/":
        state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
        lower = state_root / "lower" / f"{parts[1]}-{parts[2]}"
        attempted.append(str(lower))
        if _safe_is_dir(lower):
            _record_stock_view(logical, "luoshu-lower", lower)
            return lower
        if state_root.is_absolute():
            pid1_lower = proc1_root / state_root.relative_to("/") / "lower" / f"{parts[1]}-{parts[2]}"
            attempted.append(str(pid1_lower))
            if _safe_is_dir(pid1_lower):
                _record_stock_view(logical, "pid1-luoshu-lower", pid1_lower)
                return pid1_lower

    for prefix in inventory.MIRROR_PREFIXES:
        candidate = prefix / logical.relative_to("/")
        attempted.append(str(candidate))
        if _safe_is_dir(candidate):
            _record_stock_view(logical, _mirror_view_name(prefix), candidate, str(prefix))
            return candidate
        if prefix.is_absolute():
            pid1_candidate = proc1_root / prefix.relative_to("/") / logical.relative_to("/")
            attempted.append(str(pid1_candidate))
            if _safe_is_dir(pid1_candidate):
                _record_stock_view(logical, "pid1-" + _mirror_view_name(prefix), pid1_candidate, str(prefix))
                return pid1_candidate

    # A ROM is not required to expose every optional OEM partition. Missing logical
    # roots are harmless; an existing root without a verifiable stock view is not.
    if not _safe_exists(logical):
        _record_stock_view(logical, "missing-optional", logical)
        return logical

    detail = "checked=" + ",".join(attempted)
    _record_stock_view(logical, "blocked", logical, detail)
    raise inventory.InventoryError(
        f"字体覆盖仍在活动，分区 {logical} 未找到可信原厂视图"
        f"（已检查 LuoShu lower 与 Root mirror）"
    )


def main() -> int:
    _STOCK_VIEW_SOURCES.clear()
    inventory._overlay_risk = _private_overlay_risk
    inventory._pick_actual_root = _safe_pick_actual_root
    original_writer = inventory._atomic_write
    inventory._atomic_write = lambda path, data: _inject_stock_view_report(path, data, original_writer)
    try:
        return scanner.main()
    finally:
        inventory._atomic_write = original_writer


if __name__ == "__main__":
    raise SystemExit(main())
