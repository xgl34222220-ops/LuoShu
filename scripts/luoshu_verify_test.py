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
import font_fixtures as composite


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
        # Record rollback requests without staging device changes in the fixture.
        (moddir / "common/universal_font_cutover.sh").write_text(
            '#!/bin/sh\nprintf "%s\\n" "$1" >> "$MODDIR/rollback-invocations.txt"\n', encoding="utf-8")
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

        def retired_snapshot() -> Path:
            retired = moddir / ".luoshu-retired" / "universal-test"
            retired.mkdir(parents=True, exist_ok=True)
            (retired / "old-font.ttf").write_bytes(b"retained-font")
            (config / "universal-font-activated.conf").write_text(f"retired={retired}\n", encoding="utf-8")
            return retired

        def run(extra_env: dict[str, str] | None = None, *, collect_live: bool = False) -> dict[str, str]:
            env = dict(os.environ, MODDIR=str(moddir), LUOSHU_PYTHON=sys.executable,
                       PYTHONPATH=os.pathsep.join(filter(None, [str(moddir / "common"), os.environ.get("PYTHONPATH", "")])), LUOSHU_VERIFY_BOOT_COMPLETED="1",
                       LUOSHU_VERIFY_SETTLE_SECONDS="0", LUOSHU_VERIFY_STATE_ROOT=str(temp / "state"),
                       LUOSHU_VERIFY_FONT_DUMP=str(dump), LUOSHU_VERIFY_VISIBLE_ROOT=str(visible))
            if collect_live:
                env.pop("LUOSHU_VERIFY_FONT_DUMP", None)
            env.update(extra_env or {})
            finished = subprocess.run(["sh", str(moddir / "common/universal_font_runtime_verify.sh"), "run"],
                                      check=False, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result = conf(config / "universal-font-runtime-verification.conf")
            assert finished.returncode == (3 if result["grade"] == "FAIL" else 0), (finished, result)
            return result

        retired = retired_snapshot()
        result = run()
        assert result["grade"] == "PASS", result
        assert result["deploymentId"] == manifest["deploymentId"]
        report = json.loads((config / "universal-font-runtime-verification.json").read_text(encoding="utf-8"))
        assert report["engine"] == "luoshu-engine-v3"
        assert report["summary"]["fontManagerAvailable"] is True
        assert report["summary"]["payloadFilesVerified"] is True
        assert report["summary"]["appRenderingVerified"] is False
        assert report["summary"]["themeState"] == "unconfirmed"
        assert "theme-font-mount-unconfirmed" in report["notes"]
        assert "app-font-rendering-unverified" in report["notes"]
        assert retired.is_dir(), "unconfirmed theme must retain the rollback snapshot"

        # A dump without the replaced files is only a note (ROM formats differ;
        # HyperOS 3 lists no system file names): still PASS.
        dump.write_text("nothing useful\n", encoding="utf-8")
        assert run()["grade"] == "PASS"
        report = json.loads((config / "universal-font-runtime-verification.json").read_text(encoding="utf-8"))
        assert "font-manager-no-replaced-file-reference" in report["notes"], report

        # The real HyperOS dump is an error on stdout, not service evidence.
        # Retain valid payload evidence and avoid rolling back it over a failed
        # diagnostic query. A pathname in an error is not a positive hit either.
        for failed in (
            "cmd: Failure calling service font: Failed transaction (2147483646)\n",
            "cmd: Can't find service: font\n",
            "Exception occurred while executing: SecurityException /system/fonts/Roboto-Regular.ttf\n",
            "",
        ):
            dump.write_text(failed, encoding="utf-8")
            result = run()
            assert result["grade"] == "WARN", result
            report = json.loads((config / "universal-font-runtime-verification.json").read_text(encoding="utf-8"))
            assert report["failures"] == [], report
            assert report["summary"]["fontManagerAvailable"] is False, report
            assert report["summary"]["fontManagerHits"] == 0, report
            assert report["summary"]["payloadFilesVerified"] is True, report
            assert report["summary"]["appRenderingVerified"] is False, report
            assert result["fontManagerAvailable"] == "false", result
            assert result["payloadFilesVerified"] == "true", result
            assert result["appRenderingVerified"] == "false", result
            assert retired.is_dir(), "unconfirmed theme must retain the rollback snapshot"
            assert not (moddir / "rollback-invocations.txt").exists()

        dump.write_text("Font /system/fonts/Roboto-Regular.ttf\n", encoding="utf-8")
        mount_conf = config / "universal-font-mount.conf"
        valid_mount = f"state=mounted\ndeploymentId={manifest['deploymentId']}\n"
        mount_conf.write_text(valid_mount + "themeState=mounted\nthemeMounted=6\n", encoding="utf-8")
        assert run()["grade"] == "PASS"
        report = json.loads((config / "universal-font-runtime-verification.json").read_text(encoding="utf-8"))
        assert report["summary"]["themeState"] == "mounted", report
        assert report["summary"]["themeMounted"] == "6", report
        assert "theme-font-mount-unconfirmed" not in report["notes"], report
        assert not retired.exists(), "verified payload and theme may release the snapshot"

        retired = retired_snapshot()
        dump.write_text("cmd: Failure calling service font: Failed transaction (2147483646)\n", encoding="utf-8")
        assert run()["grade"] == "WARN"
        assert not retired.exists(), "a failed service query alone must not retain old payloads"
        assert not (moddir / "rollback-invocations.txt").exists()
        dump.write_text("Font /system/fonts/Roboto-Regular.ttf\n", encoding="utf-8")
        retired = retired_snapshot()
        mount_conf.write_text(valid_mount + "themeState=failed\nthemeMounted=0\nthemeError=namespace-unavailable\n", encoding="utf-8")
        assert run()["grade"] == "WARN"
        report = json.loads((config / "universal-font-runtime-verification.json").read_text(encoding="utf-8"))
        assert report["summary"]["payloadFilesVerified"] is True, report
        assert report["summary"]["themeError"] == "namespace-unavailable", report
        assert "theme-font-mount-failed" in report["warnings"], report
        assert retired.is_dir(), "failed theme mount must retain the rollback snapshot"
        assert not (moddir / "rollback-invocations.txt").exists()
        mount_conf.write_text(valid_mount + "themeState=not-applicable\n", encoding="utf-8")
        assert run()["grade"] == "PASS"
        assert not retired.exists()

        # cmd font dump can print an error and exit 0. Continue to font list
        # rather than treating that first nonempty stdout as a service dump.
        fake_bin = temp / "bin"
        fake_bin.mkdir()
        query_trace = temp / "query-trace.txt"
        cmd = fake_bin / "cmd"
        cmd.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$VERIFY_QUERY_TRACE"\n'
                       'if [ "$2" = dump ]; then echo "cmd: Failure calling service font: Failed transaction (2147483646)"; '
                       'else echo "Font /system/fonts/Roboto-Regular.ttf"; fi\n', encoding="utf-8")
        cmd.chmod(0o755)
        service_env = {"PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                       "VERIFY_QUERY_TRACE": str(query_trace)}
        assert run(service_env, collect_live=True)["grade"] == "PASS"
        assert query_trace.read_text(encoding="utf-8").splitlines() == ["font dump", "font list"]
        cmd.write_text('#!/bin/sh\necho "cmd: Failure calling service font: Failed transaction (2147483646)"; exit 1\n', encoding="utf-8")
        dumpsys = fake_bin / "dumpsys"
        dumpsys.write_text("#!/bin/sh\necho \"Can't find service: font\" >&2; exit 1\n", encoding="utf-8")
        dumpsys.chmod(0o755)
        retired = retired_snapshot()
        assert run(service_env, collect_live=True)["grade"] == "WARN"
        assert not retired.exists(), "file and theme evidence remain valid after all queries fail"
        assert not (moddir / "rollback-invocations.txt").exists()

        # The system sees a different file than the deployment: FAIL (-> rollback).
        (visible / "system/fonts/Roboto-Regular.ttf").write_bytes(b"stock")
        result = run()
        assert result["grade"] == "FAIL", result
        assert result["reason"] == "visible-file-hash-mismatch:/system/fonts/Roboto-Regular.ttf", result
        assert (moddir / "rollback-invocations.txt").read_text(encoding="utf-8").splitlines() == ["rollback-from-fail"]

        # Runtime state from another deployment: FAIL.
        shutil.copy(live / "system/fonts/Roboto-Regular.ttf", visible / "system/fonts/Roboto-Regular.ttf")
        (config / "universal-font-runtime.conf").write_text("state=active\ndeploymentId=other\n", encoding="utf-8")
        assert run()["reason"] == "runtime-deployment-id-mismatch"
        assert (moddir / "rollback-invocations.txt").read_text(encoding="utf-8").splitlines() == ["rollback-from-fail"] * 2
    print("luoshu_verify_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
