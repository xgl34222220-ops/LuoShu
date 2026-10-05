#!/usr/bin/env python3
"""Engine diagnostic bundle: device-side export and host-side replay round trip."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

import dataclasses

import font_role_shadow
import luoshu_engine
import font_fixtures as composite
import font_fixtures as fixture


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-diag-") as raw:
        temp = Path(raw)
        topology, _roles, stocks, xml_map = composite.build_device(temp / "device")
        moddir = temp / "module"
        config = moddir / "config"
        (config / "font-config-source" / "system").mkdir(parents=True)
        (moddir / "logs").mkdir()
        (moddir / "module.prop").write_text("id=LuoShu\nversion=test\nversionCode=1\n", encoding="utf-8")
        (moddir / "logs" / "fontswitch.log").write_text("universal prepare start font=mix\n", encoding="utf-8")
        (config / "active_font.conf").write_text("mix\n", encoding="utf-8")
        shutil.copy(xml_map["/system/etc/fonts.xml"], config / "font-config-source" / "system" / "fonts.xml")
        roles, shadow = font_role_shadow.build(topology)
        for name, value in (("device_font_topology.json", topology), ("device_font_roles.json", roles),
                            ("device_font_shadow_plan.json", shadow)):
            (config / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

        # Stock bytes live in the pre-mount lower snapshot, as on a device with a font active.
        lower = temp / "self-mount"
        for logical, stock in stocks.items():
            target = lower / "lower" / "system-fonts" / Path(logical).name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(stock, target)

        public = temp / "sdcard" / "fonts"
        public.mkdir(parents=True)
        cjk, latin, digit = public / "UserCJK.ttf", public / "UserLatin.ttf", public / "UserDigit.ttf"
        composite.make_cjk_font(cjk, family="User CJK", variable=True, pentagon=True)
        fixture.make_font(latin, family="User Latin", variable=True, triangle=True)
        fixture.make_font(digit, family="User Digit", advance=560)
        # The last switch on the device: its report records the source fonts.
        spec = {"mode": "composite", "roles": {
            "cjk": {"files": [str(cjk)], "mode": "auto"},
            "latin": {"files": [str(latin)], "mode": "auto"},
            "digit": {"files": [str(digit)], "mode": "fixed", "axes": {"wght": 500}},
        }}
        build_dir = config / "luoshu-engine-build"
        _manifest, device_report = luoshu_engine.build(
            topology, spec, build_dir / "payload", temp / "device-cache", xml_root=config / "font-config-source")
        (build_dir / "report.json").write_text(json.dumps(device_report), encoding="utf-8")

        # Hollowing keeps everything the engine inspects: style, axes, coverage.
        import luoshu_diagnostics
        keep_points = luoshu_diagnostics._keep_codepoints()
        fullwidth_points = set(range(0xFF21, 0xFF3B)) | set(range(0xFF41, 0xFF5B))
        assert fullwidth_points <= keep_points
        # Give fullwidth English independent cmap entries, with no ASCII alias
        # that could accidentally retain their outlines in a lite bundle.
        from fontTools.ttLib import TTFont
        fullwidth_source = temp / "Fullwidth.ttf"
        fixture.make_font(fullwidth_source, family="Fullwidth English")
        with TTFont(fullwidth_source) as font:
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap = dict(table.cmap)
                    for point in fullwidth_points:
                        table.cmap[point] = table.cmap.pop(point - 0xFEE0)
            font.save(fullwidth_source)
        fullwidth_hollow = temp / "FullwidthHollow.ttf"
        luoshu_diagnostics._hollow(fullwidth_source, fullwidth_hollow, keep_points)
        with TTFont(fullwidth_source) as original, TTFont(fullwidth_hollow) as hollow_font:
            for point in fullwidth_points:
                original_glyph = original["glyf"][original.getBestCmap()[point]]
                hollow_glyph = hollow_font["glyf"][hollow_font.getBestCmap()[point]]
                assert hollow_glyph.numberOfContours > 0, hex(point)
                assert original_glyph.getCoordinates(original["glyf"]) == hollow_glyph.getCoordinates(hollow_font["glyf"]), hex(point)
        # Real pre-mount snapshots retain ROM symlinks. Reading such a link
        # through pathlib can escape into the active overlay; resolve all hops
        # inside lower/mirror instead, or record a missing stock snapshot.
        aliases = temp / "aliases" / "lower"
        (aliases / "system-fonts").mkdir(parents=True)
        (aliases / "product-fonts").mkdir()
        stock_bytes = b"original-stock"
        (aliases / "system-fonts" / "MiSansVF.ttf").write_bytes(stock_bytes)
        absolute = aliases / "system-fonts" / "MiSans-Regular.ttf"
        absolute.symlink_to("/system/fonts/MiSansVF.ttf")
        relative = aliases / "system-fonts" / "MiSans-Medium.ttf"
        relative.symlink_to("MiSans-Regular.ttf")
        (aliases / "product-fonts" / "Cross.ttf").write_bytes(b"cross-partition-stock")
        (aliases / "system-fonts" / "Cross.ttf").symlink_to("../../product/fonts/Cross.ttf")
        (aliases / "system-fonts" / "Physical.ttf").symlink_to("../product-fonts/Cross.ttf")
        for name in ("MiSans-Regular.ttf", "MiSans-Medium.ttf"):
            found = luoshu_diagnostics._resolve_stock(f"/system/fonts/{name}", aliases.parent, False)
            assert found is not None and found[0] == "lower", name
            assert found[1].read_bytes() == stock_bytes, found
        for name in ("Cross.ttf", "Physical.ttf"):
            found = luoshu_diagnostics._resolve_stock(f"/system/fonts/{name}", aliases.parent, False)
            assert found is not None and found[1].read_bytes() == b"cross-partition-stock", name
        overlay = temp / "live-overlay.ttf"
        overlay.write_bytes(b"current-custom-payload")
        unsafe = aliases / "system-fonts" / "Unsafe.ttf"
        unsafe.symlink_to(overlay)
        assert unsafe.is_file() and unsafe.read_bytes() == b"current-custom-payload"
        assert luoshu_diagnostics._resolve_stock("/system/fonts/Unsafe.ttf", aliases.parent, False) is None
        (aliases / "system-fonts" / "Theme.ttf").symlink_to("/data/system/theme/fonts/Roboto-Regular.ttf")
        assert luoshu_diagnostics._resolve_stock("/system/fonts/Theme.ttf", aliases.parent, False) is None
        (aliases / "system-fonts" / "Cycle.ttf").symlink_to("Cycle.ttf")
        assert luoshu_diagnostics._resolve_stock("/system/fonts/Cycle.ttf", aliases.parent, False) is None
        (aliases / "system-fonts" / "Nested").symlink_to(temp)
        assert luoshu_diagnostics._resolve_stock("/system/fonts/Nested/live-overlay.ttf", aliases.parent, False) is None
        # Mirrors rebase absolute ROM links just like lower does.
        mirror = temp / "mirror"
        (mirror / "system/fonts").mkdir(parents=True)
        (mirror / "system/fonts/Original.ttf").write_bytes(stock_bytes)
        (mirror / "system/fonts/Alias.ttf").symlink_to("/system/fonts/Original.ttf")
        found = luoshu_diagnostics._snapshot_file("/system/fonts/Alias.ttf", mirror, lower_layout=False)
        assert found is not None and found.read_bytes() == stock_bytes
        (mirror / "data/system/theme/fonts").mkdir(parents=True)
        (mirror / "data/system/theme/fonts/Theme.ttf").write_bytes(b"current-theme-font")
        (mirror / "system/fonts/Theme.ttf").symlink_to("/data/system/theme/fonts/Theme.ttf")
        assert luoshu_diagnostics._snapshot_file("/system/fonts/Theme.ttf", mirror, lower_layout=False) is None
        hollow = temp / "hollow.ttf"
        luoshu_diagnostics._hollow(cjk, hollow, luoshu_diagnostics._keep_codepoints())

        def profiled(path: Path) -> list[dict]:
            return [{key: value for key, value in dataclasses.asdict(face).items()
                     if key not in {"path", "identity"}} for face in luoshu_engine._inspect(path)]

        assert profiled(hollow) == profiled(cjk)
        assert hollow.stat().st_size < cjk.stat().st_size

        bundle = temp / "out" / "bundle.zip"
        exported = subprocess.run(
            [sys.executable, str(ROOT / "common" / "luoshu_diagnostics.py"),
             "--moddir", str(moddir), "--output", str(bundle), "--lower-root", str(lower)],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert exported.returncode == 0, exported.stdout + exported.stderr
        result = json.loads(exported.stdout)
        assert result["status"] == "ok", result
        assert result["data"]["stockCount"] == len(stocks), result
        assert result["data"]["sourceCount"] == 3, result

        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
            index = json.loads(archive.read("index.json"))
        assert "config/font-config-source/system/fonts.xml" in names
        assert "logs/fontswitch.log" in names
        assert index["activeFont"] == "mix"
        assert index["mode"] == "lite"
        assert all(entry["hollow"] for entry in [*index["stock"].values(), *index["sources"].values()]), index
        assert {entry["origin"] for entry in index["stock"].values()} == {"lower"}, index["stock"]
        assert all(entry["file"] in names for entry in index["stock"].values())

        # The full bundle ships the fonts byte for byte, including ROM files with
        # 1970 mtimes (ColorOS), which zip rejects unless timestamps are clamped.
        for path in (lower / "lower" / "system-fonts").iterdir():
            os.utime(path, (0, 0))
        full = subprocess.run(
            [sys.executable, str(ROOT / "common" / "luoshu_diagnostics.py"), "--full",
             "--moddir", str(moddir), "--output", str(temp / "out" / "full.zip"), "--lower-root", str(lower)],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert full.returncode == 0, full.stdout + full.stderr
        with zipfile.ZipFile(temp / "out" / "full.zip") as archive:
            full_index = json.loads(archive.read("index.json"))
            roboto = full_index["stock"]["/system/fonts/Roboto-Regular.ttf"]
            assert full_index["mode"] == "full" and roboto["hollow"] is False
            assert archive.read(roboto["file"]) == stocks["/system/fonts/Roboto-Regular.ttf"].read_bytes()

        # A font is active, so the live /system/fonts view (LuoShu's overlay) is never read.
        missing_lower = subprocess.run(
            [sys.executable, str(ROOT / "common" / "luoshu_diagnostics.py"),
             "--moddir", str(moddir), "--output", str(temp / "out" / "nolower.zip"),
             "--lower-root", str(temp / "absent")],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert missing_lower.returncode == 0, missing_lower.stdout + missing_lower.stderr
        assert json.loads(missing_lower.stdout)["data"]["stockCount"] == 0
        with zipfile.ZipFile(temp / "out" / "nolower.zip") as archive:
            missing_index = json.loads(archive.read("index.json"))
            assert len(missing_index["stockSkipped"]) == len(stocks), missing_index
            assert {item["reason"] for item in missing_index["stockSkipped"]} == {"no-stock-snapshot"}

        # A live payload reachable through a lower symlink must not be shipped
        # under the stock label, even if the source is otherwise a valid font.
        broken_slot = lower / "lower" / "system-fonts" / "Roboto-Regular.ttf"
        broken_slot.unlink()
        broken_slot.symlink_to(latin)
        unsafe_export = subprocess.run(
            [sys.executable, str(ROOT / "common" / "luoshu_diagnostics.py"), "--full",
             "--moddir", str(moddir), "--output", str(temp / "out" / "unsafe.zip"), "--lower-root", str(lower)],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert unsafe_export.returncode == 0, unsafe_export.stdout + unsafe_export.stderr
        with zipfile.ZipFile(temp / "out" / "unsafe.zip") as archive:
            unsafe_index = json.loads(archive.read("index.json"))
            assert "/system/fonts/Roboto-Regular.ttf" not in unsafe_index["stock"], unsafe_index
            assert {"path": "/system/fonts/Roboto-Regular.ttf", "reason": "no-stock-snapshot"} in unsafe_index["stockSkipped"]
            assert "stock/system/fonts/Roboto-Regular.ttf" not in archive.namelist()

        replay = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "replay_diagnostics.py"), str(bundle),
             "--work", str(temp / "replay")],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert replay.returncode == 0, replay.stdout + replay.stderr
        assert "RESULT: PASS" in replay.stdout, replay.stdout
        assert f"replaced: {len(device_report['replaced'])}" in replay.stdout, replay.stdout

    print("luoshu_diagnostics_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
