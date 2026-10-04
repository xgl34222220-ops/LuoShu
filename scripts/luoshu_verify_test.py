#!/usr/bin/env python3
"""Boot verification of an engine v3 payload through the Phase 8 bridge."""
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

import luoshu_engine as engine
import universal_composite_test as composite


def conf(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-verify-") as raw:
        temp = Path(raw)
        topology, _roles, _stocks, xml_map = composite.build_device(temp / "device")
        user = temp / "User.ttf"
        composite.make_cjk_font(user, family="User", variable=True, pentagon=True)
        moddir = temp / "module"
        shutil.copytree(ROOT / "common", moddir / "common",
                        ignore=shutil.ignore_patterns("python", "__pycache__", "legacy_v14_4"))
        live = moddir / ".luoshu-payload"
        manifest, _report = engine.build(topology, {"mode": "single", "files": [str(user)]}, live,
                                         temp / "cache", xml_map=xml_map)
        config = moddir / "config"
        config.mkdir()
        (config / "universal-font-runtime.conf").write_text(
            f"state=active\nfont=User\ndeploymentId={manifest['deploymentId']}\n"
            f"payloadDigest={manifest['payloadDigest']}\n", encoding="utf-8")
        (config / "universal-font-mount.conf").write_text(
            f"state=mounted\ndeploymentId={manifest['deploymentId']}\n", encoding="utf-8")
        # What the system sees once the overlay is mounted.
        visible = temp / "visible"
        for item in manifest["files"]:
            target = visible / item["logicalPath"].lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(live / item["payloadPath"], target)
        dump = temp / "dump.txt"
        dump.write_text("Font /system/fonts/Roboto-Regular.ttf\n", encoding="utf-8")

        def run() -> dict[str, str]:
            env = dict(os.environ, MODDIR=str(moddir), LUOSHU_PYTHON=sys.executable,
                       PYTHONPATH=str(moddir / "common"), LUOSHU_VERIFY_BOOT_COMPLETED="1",
                       LUOSHU_VERIFY_SETTLE_SECONDS="0", LUOSHU_VERIFY_STATE_ROOT=str(temp / "state"),
                       LUOSHU_VERIFY_FONT_DUMP=str(dump), LUOSHU_VERIFY_VISIBLE_ROOT=str(visible))
            subprocess.run(["sh", str(moddir / "common/universal_font_runtime_verify.sh"), "run"],
                           check=False, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return conf(config / "universal-font-runtime-verification.conf")

        result = run()
        assert result["grade"] == "PASS", result
        assert result["deploymentId"] == manifest["deploymentId"]
        report = json.loads((config / "universal-font-runtime-verification.json").read_text(encoding="utf-8"))
        assert report["engine"] == "luoshu-engine-v3"

        # A dump without the replaced files is only a warning (ROM formats differ).
        dump.write_text("nothing useful\n", encoding="utf-8")
        assert run()["grade"] == "WARN"

        # The system sees a different file than the deployment: FAIL (-> rollback).
        (visible / "system/fonts/Roboto-Regular.ttf").write_bytes(b"stock")
        result = run()
        assert result["grade"] == "FAIL", result
        assert result["reason"] == "visible-file-hash-mismatch:/system/fonts/Roboto-Regular.ttf", result

        # Runtime state from another deployment: FAIL.
        shutil.copy(live / "system/fonts/Roboto-Regular.ttf", visible / "system/fonts/Roboto-Regular.ttf")
        (config / "universal-font-runtime.conf").write_text("state=active\ndeploymentId=other\n", encoding="utf-8")
        assert run()["reason"] == "runtime-deployment-id-mismatch"
    print("luoshu_verify_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
