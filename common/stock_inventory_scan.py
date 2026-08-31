#!/usr/bin/env python3
"""Safe manual stock-font inventory wrapper for LuoShu private payload mode."""
from __future__ import annotations

import os
from pathlib import Path

import font_inventory as inventory
import font_inventory_scan_v3 as scanner


_ACTIVE_OVERLAY_MODULE: Path | None = None


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
        return explicit
    if not overlay_risk:
        return logical
    # Overlay risk is per partition, not global. A custom system/fonts payload
    # does not make an untouched vendor/fonts tree unsafe to scan directly.
    if _ACTIVE_OVERLAY_MODULE is not None and not _private_root_overlaid(logical):
        return logical

    parts = logical.parts
    if len(parts) >= 3 and parts[0] == "/":
        state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
        lower = state_root / "lower" / f"{parts[1]}-{parts[2]}"
        if lower.is_dir():
            return lower

    for prefix in inventory.MIRROR_PREFIXES:
        candidate = prefix / logical.relative_to("/")
        if candidate.is_dir():
            return candidate

    # A ROM is not required to expose every optional OEM partition. Missing logical
    # roots are harmless; an existing root without a verifiable stock view is not.
    if not logical.exists():
        return logical
    raise inventory.InventoryError(f"字体覆盖仍在活动且没有可验证的原厂 lower/mirror：{logical}")


def main() -> int:
    inventory._overlay_risk = _private_overlay_risk
    inventory._pick_actual_root = _safe_pick_actual_root
    return scanner.main()


if __name__ == "__main__":
    raise SystemExit(main())
