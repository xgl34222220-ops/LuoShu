#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import font_inventory as inventory  # noqa: E402
import stock_inventory_scan as stock  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        module = temp / "module"
        (module / "config").mkdir(parents=True)
        (module / "config/active_font.conf").write_text("mix\n", encoding="utf-8")
        private_fonts = module / ".luoshu-payload/system/fonts"
        private_fonts.mkdir(parents=True)
        (private_fonts / "sentinel.ttf").write_bytes(b"overlay")
        assert stock._private_overlay_risk(module), "private payload must be treated as overlay risk"

        (module / "config/active_font.conf").write_text("default\n", encoding="utf-8")
        assert not stock._private_overlay_risk(module), "default selection must not force overlay risk"

        logical = temp / "system/fonts"
        logical.mkdir(parents=True)
        state_root = temp / "state"
        lower = state_root / "lower/tmp-system"
        lower.mkdir(parents=True)
        old_state = os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT")
        old_mirrors = inventory.MIRROR_PREFIXES
        try:
            os.environ["LUOSHU_SELF_MOUNT_STATE_ROOT"] = str(state_root)
            inventory.MIRROR_PREFIXES = ()
            resolved = stock._safe_pick_actual_root(logical, None, True)
            assert resolved == lower, (resolved, lower)

            for child in lower.iterdir():
                if child.is_file():
                    child.unlink()
            lower.rmdir()
            try:
                stock._safe_pick_actual_root(logical, None, True)
            except inventory.InventoryError:
                pass
            else:
                raise AssertionError("existing logical root without lower/mirror must be rejected")

            missing = temp / "missing/fonts"
            resolved_missing = stock._safe_pick_actual_root(missing, None, True)
            assert resolved_missing == missing, (resolved_missing, missing)
        finally:
            inventory.MIRROR_PREFIXES = old_mirrors
            if old_state is None:
                os.environ.pop("LUOSHU_SELF_MOUNT_STATE_ROOT", None)
            else:
                os.environ["LUOSHU_SELF_MOUNT_STATE_ROOT"] = old_state

    print("Stock inventory private-payload safety tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
