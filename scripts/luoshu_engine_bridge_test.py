#!/usr/bin/env python3
"""luoshu_engine.sh end to end: prepare and stage single and composite fonts."""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

import font_fixtures as composite
import font_fixtures as fixture
import luoshu_payload as payload_format


def sh(moddir: Path, *args: str, env: dict | None = None) -> tuple[int, str]:
    merged = dict(os.environ, MODDIR=str(moddir), LUOSHU_PYTHON=sys.executable,
                  LUOSHU_PUBLIC_DIR=str(moddir.parent / "sdcard"), PYTHONPATH=os.pathsep.join(filter(None, [str(moddir / "common"), os.environ.get("PYTHONPATH", "")])),
                  **(env or {}))
    done = subprocess.run(["sh", str(moddir / "common/luoshu_engine.sh"), *args], check=False, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=merged)
    return done.returncode, done.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-engine-bridge-") as raw:
        temp = Path(raw)
        topology, _roles, _stocks, xml_map = composite.build_device(temp / "device")
        moddir = temp / "module"
        shutil.copytree(ROOT / "common", moddir / "common",
                        ignore=shutil.ignore_patterns("python", "__pycache__", "legacy_v14_4"))
        config = moddir / "config"
        (config / "font-config-source" / "system").mkdir(parents=True)
        shutil.copy(xml_map["/system/etc/fonts.xml"], config / "font-config-source/system/fonts.xml")
        (config / "device_font_topology.json").write_text(json.dumps(topology), encoding="utf-8")
        (config / "active_font.conf").write_text("OldFont\n", encoding="utf-8")
        fonts = temp / "sdcard" / "fonts"
        fonts.mkdir(parents=True)
        composite.make_cjk_font(fonts / "UserSans.ttf", family="User Sans", variable=True, pentagon=True)
        fixture.make_font(fonts / "UserLatin.ttf", family="User Latin", variable=True)
        fixture.make_font(fonts / "UserDigit.ttf", family="User Digit", advance=560)
        progress = temp / "progress.conf"

        rc, out = sh(moddir, "prepare", "UserSans", env={"LUOSHU_SWITCH_PROGRESS_FILE": str(progress)})
        assert rc == 0 and '"status":"ok"' in out, out
        assert "正在生成字体" in progress.read_text(encoding="utf-8")
        rc, out = sh(moddir, "stage", "OtherFont")
        assert rc != 0, "stage must refuse a build for another family"
        # HyperOS theme font: the stage builds its replacement for the boot-time bind.
        theme = temp / "theme" / "Roboto-Regular.ttf"
        theme.parent.mkdir()
        router = temp / "theme_webview" / "Roboto-Regular.ttf"
        router.parent.mkdir()
        fixture.make_font(router, family="Theme Stub")
        theme.symlink_to(router)
        theme_env = {"LUOSHU_THEME_FONT_TARGET": str(theme), "LUOSHU_THEME_FONT_ROUTER": str(router)}
        rc, out = sh(moddir, "stage", "UserSans", env=theme_env)
        assert rc == 0 and '"pipeline":"luoshu-engine-v3"' in out, out
        next_root = moddir / ".luoshu-payload-next"
        manifest = json.loads((next_root / ".luoshu-runtime/deployment/deployment.json").read_text(encoding="utf-8"))
        view_dir = config / "hyperos-theme-font-early"
        early_manifest = view_dir / (manifest["deploymentId"].split(":", 1)[1][:32] + ".mounts")
        routes = early_manifest.read_text(encoding="utf-8").splitlines()
        view = view_dir / routes[0].split("|")[0]
        assert view.is_file() and view.stat().st_size > theme.stat().st_size, list(view.parent.glob("*"))
        assert len(routes) == 1 and routes[0].split("|")[1] == str(router), routes
        assert theme.is_symlink(), "stage must retain framework routing symlinks"
        payload_format.validate_payload_integrity(manifest, next_root)
        state = dict(line.split("=", 1) for line in
                     (config / "universal-font-next.conf").read_text(encoding="utf-8").splitlines())
        assert state["font"] == "UserSans" and state["previousFont"] == "OldFont"
        assert state["deploymentId"] == manifest["deploymentId"]
        assert (config / "active_font.conf").read_text(encoding="utf-8").strip() == "UserSans"
        assert "pipeline=luoshu-engine-v3" in (config / "text_reboot_required.conf").read_text(encoding="utf-8")
        assert (next_root / "system/fonts/Roboto-Regular.ttf").is_file()

        # Composite from the App's saved role assignment.
        (config / "universal-composite.conf").write_text(
            "cjk=UserSans\nlatin=UserLatin\ndigit=UserDigit\n"
            "cjkAxes=wght=400\nlatinAxes=wght=400\ndigitAxes=wght=500\n"
            "cjkMode=auto\nlatinMode=auto\ndigitMode=fixed\n", encoding="utf-8")
        rc, out = sh(moddir, "prepare", "mix")
        assert rc == 0 and '"status":"ok"' in out, out
        # Two real framework paths can coexist with different layout metrics.
        theme.unlink()
        fixture.make_font(theme, family="Theme Direct", advance=510)
        rc, out = sh(moddir, "stage", "mix", env=theme_env)
        assert rc == 0, out
        manifest = json.loads((next_root / ".luoshu-runtime/deployment/deployment.json").read_text(encoding="utf-8"))
        payload_format.validate_payload_integrity(manifest, next_root)
        state = dict(line.split("=", 1) for line in
                     (config / "universal-font-next.conf").read_text(encoding="utf-8").splitlines())
        # The queued UserSans request does not change which payload is live.
        assert state["font"] == "mix" and state["previousFont"] == "OldFont", state
        map_path = config / "hyperos-theme-font-early" / (manifest["deploymentId"].split(":", 1)[1][:32] + ".mounts")
        routes = map_path.read_text(encoding="utf-8").splitlines()
        assert len(routes) == 2 and {line.split("|")[1] for line in routes} == {str(theme), str(router)}, routes

        # A corrupt existing theme must block staging, preserve the already
        # queued deployment, and return a visible error instead of false success.
        prior_state = (config / "universal-font-next.conf").read_bytes()
        prior_map = map_path.read_bytes()
        prior_views = {line.split("|")[0]: (view_dir / line.split("|")[0]).read_bytes() for line in routes}
        rc, out = sh(moddir, "prepare", "mix")
        assert rc == 0, out
        rebuilt = json.loads((config / "luoshu-engine-build/deployment.json").read_text(encoding="utf-8"))
        assert rebuilt["deploymentId"] == manifest["deploymentId"], "regression must rebuild the queued deployment id"
        # First target changes its layout contract and builds successfully;
        # the second target then fails. Old map and both old views stay valid.
        from fontTools.ttLib import TTFont
        with TTFont(theme) as changed:
            changed["hhea"].ascent += 75
            changed.save(theme)
        router.write_bytes(b"invalid-theme")
        rc, out = sh(moddir, "stage", "mix", env=theme_env)
        assert rc != 0 and "主题字体视图生成失败" in out, out
        assert (config / "universal-font-next.conf").read_bytes() == prior_state
        assert map_path.read_bytes() == prior_map
        for line in routes:
            name, _target, digest = line.split("|")
            actual = (view_dir / name).read_bytes()
            assert actual == prior_views[name] and hashlib.sha256(actual).hexdigest() == digest
        payload_format.validate_payload_integrity(manifest, next_root)

        # Missing fonts fail with a message and stage nothing new.
        rc, out = sh(moddir, "prepare", "NoSuchFont")
        assert rc != 0 and "找不到字体家族" in out, out
    print("luoshu_engine_bridge_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
