#!/usr/bin/env python3
"""luoshu_engine.sh end to end: prepare and stage single and composite fonts."""
from __future__ import annotations

import json
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
        rc, out = sh(moddir, "stage", "UserSans")
        assert rc == 0 and '"pipeline":"luoshu-engine-v3"' in out, out
        next_root = moddir / ".luoshu-payload-next"
        manifest = json.loads((next_root / ".luoshu-runtime/deployment/deployment.json").read_text(encoding="utf-8"))
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
        rc, out = sh(moddir, "stage", "mix")
        assert rc == 0, out
        manifest = json.loads((next_root / ".luoshu-runtime/deployment/deployment.json").read_text(encoding="utf-8"))
        payload_format.validate_payload_integrity(manifest, next_root)
        state = dict(line.split("=", 1) for line in
                     (config / "universal-font-next.conf").read_text(encoding="utf-8").splitlines())
        # The queued UserSans request does not change which payload is live.
        assert state["font"] == "mix" and state["previousFont"] == "OldFont", state

        # Missing fonts fail with a message and stage nothing new.
        rc, out = sh(moddir, "prepare", "NoSuchFont")
        assert rc != 0 and "找不到字体家族" in out, out
    print("luoshu_engine_bridge_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
