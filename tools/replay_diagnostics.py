#!/usr/bin/env python3
"""Replay a device engine diagnostic bundle on the host (HOST_ONLY).

Takes the zip written by common/luoshu_diagnostics.py and runs the current
Universal Font Engine over the device's real inputs:

  roles (re-classified from the device topology) -> source profile (rebuilt
  from the bundled source fonts) -> FontPlan -> XML route -> compile ->
  deployment -> cutover gate

and prints which slots fail and why. Nothing touches the host system.

  python3 tools/replay_diagnostics.py LuoShu-engine-XXX.zip [--profile NAME] [--work DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "common"
sys.path.insert(0, str(COMMON))

import font_source_profile  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _family_key(family: str) -> str:
    return hashlib.sha256(family.encode("utf-8")).hexdigest()[:24]


def _run(stage: str, args: list[str], env: dict[str, str]) -> tuple[int, dict[str, Any] | None, str, float]:
    started = time.monotonic()
    done = subprocess.run(
        [sys.executable, *args], check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    elapsed = time.monotonic() - started
    parsed = None
    for line in reversed(done.stdout.strip().splitlines()):
        try:
            parsed = json.loads(line)
            break
        except ValueError:
            continue
    text = (done.stdout + done.stderr).strip()
    print(f"[{stage}] rc={done.returncode} {elapsed:.1f}s", flush=True)
    if done.returncode != 0:
        print("  " + text[-1500:].replace("\n", "\n  "))
    return done.returncode, parsed, text, elapsed


def _axes_text(axes: dict[str, Any]) -> str:
    return ",".join(f"{tag}={value}" for tag, value in sorted((axes or {}).items()))


def _pick_profile(config: Path, wanted: str | None) -> Path:
    profiles = sorted((config / "source-font-profiles").glob("*.json"))
    if not profiles:
        raise SystemExit("诊断包里没有源字体 Profile：请先在手机上切换一次字体再导出")
    if wanted:
        for path in profiles:
            if wanted in {path.stem, path.name, _family_key(wanted)}:
                return path
        raise SystemExit(f"找不到 Profile：{wanted}")
    return max(profiles, key=lambda path: int(_load(path).get("generatedAt") or 0))


def _rebuild_profile(device_profile: Path, sources: dict[str, Any], bundle_root: Path, output: Path) -> None:
    data = _load(device_profile)
    remap: dict[str, Path] = {}
    for item in data.get("files") or []:
        original = str(item.get("sourcePath") or "")
        entry = sources.get(original)
        if entry is None:
            raise SystemExit(f"诊断包缺少源字体：{original}")
        remap[original] = bundle_root / entry["file"]
    composite = data.get("composite")
    if isinstance(composite, dict):
        role_fonts: dict[str, list[Path]] = {}
        for item in data.get("files") or []:
            roles = sorted({role for face in item.get("faces") or [] for role in face.get("assignedRoles") or []})
            for role in roles:
                role_fonts.setdefault(role, []).append(remap[item["sourcePath"]])
        specs = composite.get("roles") or {}
        profile = font_source_profile.build(
            [], role_fonts,
            {role: str(spec.get("mode") or "auto") for role, spec in specs.items()},
            {role: _axes_text(spec.get("axes") or {}) for role, spec in specs.items()},
        )
    else:
        profile = font_source_profile.build(list(remap.values()))
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--profile", help="profile file stem or family name; default: newest")
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()

    work = args.work or Path(tempfile.mkdtemp(prefix="luoshu-replay-"))
    bundle_root = work / "bundle"
    out = work / "replay"
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.bundle) as bundle:
        bundle.extractall(bundle_root)
    index = _load(bundle_root / "index.json")
    config = bundle_root / "config"
    print(f"device: {json.dumps(index.get('device'), ensure_ascii=False)}")
    print(f"module: {index.get('module')} active={index.get('activeFont')!r}")
    print(f"stock files: {len(index.get('stock') or {})} skipped: {len(index.get('stockSkipped') or [])}")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(COMMON) + os.pathsep + env.get("PYTHONPATH", "")
    # Never let the compiler fall back to host paths or an expired deadline.
    env["LUOSHU_SELF_MOUNT_STATE_ROOT"] = str(work / "no-self-mount")
    env.pop("LUOSHU_UNIVERSAL_DEADLINE", None)

    topology = config / "device_font_topology.json"
    roles = out / "device_font_roles.json"
    shadow = out / "device_font_shadow_plan.json"
    rc, _, _, _ = _run("roles", [str(COMMON / "font_role_shadow.py"), "--topology", str(topology),
                                 "--roles-output", str(roles), "--plan-output", str(shadow)], env)
    if rc:
        return 1

    device_profile = _pick_profile(config, args.profile)
    print(f"profile: {device_profile.name}")
    profile = out / "source_profile.json"
    _rebuild_profile(device_profile, index.get("sources") or {}, bundle_root, profile)

    plan = out / "font_plan.json"
    rc, _, _, _ = _run("plan", [str(COMMON / "universal_font_plan.py"), "--topology", str(topology),
                                "--roles", str(roles), "--source-profile", str(profile), "--output", str(plan)], env)
    if rc:
        return 1

    route = out / "route_plan.json"
    rc, _, _, _ = _run("route", [str(COMMON / "minimal_xml_router.py"), "--font-plan", str(plan),
                                 "--snapshot-root", str(config / "font-config-source"), "--output", str(route)], env)
    if rc:
        return 1

    stock_map = out / "stock_map.json"
    stock_map.write_text(json.dumps({
        logical: str(bundle_root / entry["file"]) for logical, entry in (index.get("stock") or {}).items()
    }, ensure_ascii=False), encoding="utf-8")
    artifacts = out / "artifacts.json"
    rc, _, _, compile_time = _run("compile", [
        str(COMMON / "universal_font_compiler.py"), "--font-plan", str(plan), "--route-plan", str(route),
        "--stock-map", str(stock_map), "--output-dir", str(out / "artifacts"), "--manifest", str(artifacts),
    ], env)
    if artifacts.is_file():
        manifest = _load(artifacts)
        blocked = [item for item in manifest.get("artifacts") or [] if item.get("status") == "blocked"]
        modes: dict[str, int] = {}
        for item in manifest.get("artifacts") or []:
            modes[str(item.get("mode"))] = modes.get(str(item.get("mode")), 0) + 1
        print(f"artifacts: {len(manifest.get('artifacts') or [])} modes={modes} blocked={len(blocked)}")
        for item in blocked:
            print(f"  BLOCKED {item.get('targetPath')} role={item.get('role')} reason={item.get('reason')}")
    if rc:
        return 1

    deployment = out / "deployment.json"
    payload = out / "payload"
    rc, _, _, _ = _run("deploy", [
        str(COMMON / "universal_font_deployment.py"), "--font-plan", str(plan), "--route-plan", str(route),
        "--artifact-manifest", str(artifacts), "--payload-root", str(payload), "--manifest", str(deployment),
    ], env)
    if rc:
        return 1

    rc, gate, text, _ = _run("gate", [
        str(COMMON / "universal_font_cutover_gate.py"), "--font-plan", str(plan), "--route-plan", str(route),
        "--artifact-manifest", str(artifacts), "--deployment", str(deployment), "--payload-root", str(payload),
    ], env)
    print("  " + text[-2000:].replace("\n", "\n  "))
    eligible = rc == 0 and '"eligible":true' in text.replace(" ", "")
    print(f"RESULT: {'PASS' if eligible else 'FAIL'} (compile {compile_time:.0f}s on host) work={work}")
    return 0 if eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
