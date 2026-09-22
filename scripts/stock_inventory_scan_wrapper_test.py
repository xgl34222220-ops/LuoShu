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
import font_inventory_scan as scanner  # noqa: E402
import stock_inventory_scan as stock  # noqa: E402


def main() -> int:
    assert stock.scanner.SCANNER_REVISION == 6, "manual/install scan must use the full v6 generic inventory"
    installer = (ROOT / ".luoshu-runtime/compat/v227/customize.sh").read_text(encoding="utf-8")
    wrapper = (ROOT / "customize.sh").read_text(encoding="utf-8")
    service = (ROOT / "service.sh").read_text(encoding="utf-8")
    post_mount = (ROOT / "post-mount.sh").read_text(encoding="utf-8")
    manager = (ROOT / "common/font_manager.sh").read_text(encoding="utf-8")
    assert "stock_inventory_scan_pending" in installer
    assert "LUOSHU_FRESH_STOCK_SCAN=1" in installer
    assert "LUOSHU_FRESH_STOCK_SCAN=1" in post_mount
    assert "已中止本次更新" not in installer
    assert "旧字体负载" in installer and "继续安装并重新扫描本机字体槽位" in installer
    assert "兼容迁移视图" in wrapper
    assert "abort '无法读取旧版洛书私有字体负载'" not in wrapper
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

        # A directory with only child file mounts can be recovered by a
        # non-recursive parent bind. A directory-level mount cannot.
        mountinfo = temp / "mountinfo"
        child_target = logical / "active.ttf"
        mountinfo.write_text(
            f"10 1 0:1 / {child_target} rw - ext4 /dev/fake rw\n",
            encoding="utf-8",
        )
        old_mountinfo = os.environ.get("LUOSHU_MOUNTINFO")
        os.environ["LUOSHU_MOUNTINFO"] = str(mountinfo)
        try:
            assert stock._child_mount_targets(logical) == [str(child_target)]
            mountinfo.write_text(
                f"10 1 0:1 / {logical} rw - overlay KSU rw\n"
                f"11 10 0:1 / {child_target} rw - ext4 /dev/fake rw\n",
                encoding="utf-8",
            )
            assert stock._child_mount_targets(logical) == []
        finally:
            if old_mountinfo is None:
                os.environ.pop("LUOSHU_MOUNTINFO", None)
            else:
                os.environ["LUOSHU_MOUNTINFO"] = old_mountinfo

        state_root = temp / "state"
        key = f"{logical.parts[1]}-{logical.parts[2]}"
        lower = state_root / "lower" / key
        lower.mkdir(parents=True)
        old_state = os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT")
        old_mirrors = inventory.MIRROR_PREFIXES
        try:
            os.environ["LUOSHU_SELF_MOUNT_STATE_ROOT"] = str(state_root)
            inventory.MIRROR_PREFIXES = ()
            resolved = stock._safe_pick_actual_root(logical, None, True)
            assert resolved == lower, (resolved, lower)

            untouched = temp / "vendor/fonts"
            untouched.mkdir(parents=True)
            resolved_untouched = stock._safe_pick_actual_root(untouched, None, True)
            assert resolved_untouched == untouched, (resolved_untouched, untouched)

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

        # Regression for the real in-place-update failure: the resolved stock
        # font root may be /data/.../lower/product-fonts. Walking upward from
        # that directory must never be treated as the /product partition census.
        # A whole-partition stock mirror must win and expose nested OEM roots.
        product_lower = temp / "state/lower/product-fonts"
        product_lower.mkdir(parents=True, exist_ok=True)
        (product_lower / "Roboto-Regular.ttf").write_bytes(b"stock-regular")
        mirror_root = temp / "mirror"
        mirror_product = mirror_root / "product"
        (mirror_product / "fonts").mkdir(parents=True)
        (mirror_product / "vivo/fonts").mkdir(parents=True)
        (mirror_product / "fonts/Roboto-Regular.ttf").write_bytes(b"stock-regular")
        (mirror_product / "vivo/fonts/VivoFont.ttf").write_bytes(b"stock-vivo")
        (module / ".luoshu-payload/product/fonts").mkdir(parents=True, exist_ok=True)
        (module / ".luoshu-payload/product/fonts/Roboto-Regular.ttf").write_bytes(b"overlay")
        (module / "config/active_font.conf").write_text("mix\n", encoding="utf-8")
        assert stock._private_overlay_risk(module)

        old_mirrors = inventory.MIRROR_PREFIXES
        old_resolver = scanner.PARTITION_CENSUS_ROOT_RESOLVER
        try:
            inventory.MIRROR_PREFIXES = (mirror_root,)
            scanner.PARTITION_CENSUS_ROOT_RESOLVER = stock._safe_partition_census_root
            roots = [
                inventory.FontRoot(
                    "product", Path("/product/fonts"), product_lower
                )
            ]
            bases = scanner._partition_scan_bases(roots)
            assert bases == [("product", Path("/product"), mirror_product)], bases
            census = {
                str(logical)
                for _partition, logical, _actual in scanner._partition_font_census(roots)
            }
            assert "/product/fonts/Roboto-Regular.ttf" in census, census
            assert "/product/vivo/fonts/VivoFont.ttf" in census, census
            assert not any("/state/lower/" in logical for logical in census), census
        finally:
            scanner.PARTITION_CENSUS_ROOT_RESOLVER = old_resolver
            inventory.MIRROR_PREFIXES = old_mirrors

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
