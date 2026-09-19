#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import font_inventory as inventory  # noqa: E402
import font_inventory_scan_v3 as scanner  # noqa: E402
import stock_inventory_scan as stock  # noqa: E402


def main() -> int:
    assert stock.scanner.SCANNER_REVISION == 3, "manual/install scan must use the full v3 inventory"
    installer = (ROOT / ".luoshu-runtime/customize-v227.sh").read_text(encoding="utf-8")
    service = (ROOT / "service.sh").read_text(encoding="utf-8")
    post_mount = (ROOT / "post-mount.sh").read_text(encoding="utf-8")
    manager = (ROOT / "common/font_manager.sh").read_text(encoding="utf-8")
    assert "stock_inventory_scan_pending" in installer
    assert "原厂视图来源：直接" in installer
    assert "LUOSHU_STOCK_SCAN_STRICT=1" in installer
    assert "source=flash-preflight" in installer
    assert "inventoryDigest=%s" in installer
    assert "targetsDigest=%s" in installer
    assert "刷入前字体槽位扫描失败" in installer
    assert "本次安装已中止" in installer
    assert 'cp -f "$OLD_MOD/config/device_font_inventory.json"' not in installer
    assert "action stock_scan" in service
    assert "LUOSHU_STOCK_VIEW_VERIFIED=1" in post_mount
    assert 'rm -f "$MODDIR/config/stock_inventory_scan_pending"' in manager
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        module = temp / "module"
        (module / "config").mkdir(parents=True)
        (module / "config/active_font.conf").write_text("mix\n", encoding="utf-8")
        private_fonts = module / ".luoshu-payload/system/fonts"
        private_fonts.mkdir(parents=True)
        (private_fonts / "sentinel.ttf").write_bytes(b"overlay")
        assert stock._private_overlay_risk(module), "private payload must be treated as overlay risk"

        os.environ["LUOSHU_STOCK_VIEW_VERIFIED"] = "1"
        try:
            assert not stock._private_overlay_risk(module), "pre-mount stock namespace must be trusted"
        finally:
            os.environ.pop("LUOSHU_STOCK_VIEW_VERIFIED", None)

        (module / "config/active_font.conf").write_text("default\n", encoding="utf-8")
        assert not stock._private_overlay_risk(module), "default selection must not force overlay risk"

        logical = temp / "system/fonts"
        logical.mkdir(parents=True)
        private_logical = module / ".luoshu-payload" / logical.relative_to("/")
        private_logical.mkdir(parents=True)
        (private_logical / "active.ttf").write_bytes(b"overlay")
        (module / "config/active_font.conf").write_text("mix\n", encoding="utf-8")
        assert stock._private_overlay_risk(module)
        state_root = temp / "state"
        key = f"{logical.parts[1]}-{logical.parts[2]}"
        lower = state_root / "lower" / key
        lower.mkdir(parents=True)
        old_state = os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT")
        old_mirrors = inventory.MIRROR_PREFIXES
        try:
            os.environ["LUOSHU_SELF_MOUNT_STATE_ROOT"] = str(state_root)
            inventory.MIRROR_PREFIXES = ()
            stock._STOCK_VIEW_SOURCES.clear()
            resolved = stock._safe_pick_actual_root(logical, None, True)
            assert resolved == lower, (resolved, lower)
            assert stock._STOCK_VIEW_SOURCES[str(logical)]["view"] == "luoshu-lower"

            untouched = temp / "vendor/fonts"
            untouched.mkdir(parents=True)
            resolved_untouched = stock._safe_pick_actual_root(untouched, None, True)
            assert resolved_untouched == untouched, (resolved_untouched, untouched)
            assert stock._STOCK_VIEW_SOURCES[str(untouched)]["view"] == "direct-unoverlaid"

            verified = temp / "product/fonts"
            verified.mkdir(parents=True)
            os.environ["LUOSHU_STOCK_VIEW_VERIFIED"] = "1"
            try:
                resolved_verified = stock._safe_pick_actual_root(verified, None, False)
            finally:
                os.environ.pop("LUOSHU_STOCK_VIEW_VERIFIED", None)
            assert resolved_verified == verified
            assert stock._STOCK_VIEW_SOURCES[str(verified)]["view"] == "pre-mount-direct"

            lower.rmdir()

            proc1_root = temp / "proc1-root"
            pid1_lower = proc1_root / state_root.relative_to("/") / "lower" / key
            pid1_lower.mkdir(parents=True)
            old_proc1 = os.environ.get("LUOSHU_PROC1_ROOT")
            os.environ["LUOSHU_PROC1_ROOT"] = str(proc1_root)
            try:
                resolved_pid1 = stock._safe_pick_actual_root(logical, None, True)
                assert resolved_pid1 == pid1_lower, (resolved_pid1, pid1_lower)
                assert stock._STOCK_VIEW_SOURCES[str(logical)]["view"] == "pid1-luoshu-lower"
            finally:
                if old_proc1 is None:
                    os.environ.pop("LUOSHU_PROC1_ROOT", None)
                else:
                    os.environ["LUOSHU_PROC1_ROOT"] = old_proc1
            pid1_lower.rmdir()

            try:
                stock._safe_pick_actual_root(logical, None, True)
            except inventory.InventoryError as error:
                assert str(logical) in str(error), error
                assert "未找到可信原厂视图" in str(error), error
                assert stock._STOCK_VIEW_SOURCES[str(logical)]["view"] == "blocked"
            else:
                raise AssertionError("existing logical root without lower/mirror must be rejected")

            mirror_prefix = temp / "mirror"
            mirror_root = mirror_prefix / logical.relative_to("/")
            mirror_root.mkdir(parents=True)
            inventory.MIRROR_PREFIXES = (mirror_prefix,)
            resolved_mirror = stock._safe_pick_actual_root(logical, None, True)
            assert resolved_mirror == mirror_root, (resolved_mirror, mirror_root)
            assert stock._STOCK_VIEW_SOURCES[str(logical)]["view"] == "root-mirror"
            inventory.MIRROR_PREFIXES = ()

            missing = temp / "missing/fonts"
            resolved_missing = stock._safe_pick_actual_root(missing, None, True)
            assert resolved_missing == missing, (resolved_missing, missing)
            assert stock._STOCK_VIEW_SOURCES[str(missing)]["view"] == "missing-optional"

            written = {}
            stock._inject_stock_view_report(
                temp / "inventory.json",
                {"scanSummary": {}},
                lambda _path, data: written.update(data),
            )
            counts = written["scanSummary"]["stockViewSourceCounts"]
            assert counts["root-mirror"] == 1
            assert counts["direct-unoverlaid"] == 1
            assert counts["pre-mount-direct"] == 1
        finally:
            inventory.MIRROR_PREFIXES = old_mirrors
            if old_state is None:
                os.environ.pop("LUOSHU_SELF_MOUNT_STATE_ROOT", None)
            else:
                os.environ["LUOSHU_SELF_MOUNT_STATE_ROOT"] = old_state

        calls: list[tuple[Path, bool]] = []
        original_picker = inventory._pick_actual_root
        try:
            inventory._pick_actual_root = lambda logical, _explicit, risk: (
                calls.append((logical, risk)) or logical
            )
            args = SimpleNamespace(**{argument: None for _, _, argument in scanner.AUX_FONT_SPECS})
            scanner._resolve_aux_font_roots(args, True)
        finally:
            inventory._pick_actual_root = original_picker
        assert len(calls) == len(scanner.AUX_FONT_SPECS), calls
        assert all(risk for _, risk in calls), calls

    print("Stock inventory private-payload safety tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
