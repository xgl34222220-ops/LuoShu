#!/usr/bin/env python3
"""Replay a device diagnostic bundle with the current engine (HOST_ONLY).

Takes the zip written by common/luoshu_diagnostics.py (App logs page, or
'洛书 诊断') and runs engine v3 over the device's real inputs: its font
topology, stock XML snapshots, stock collection files and the user's source
fonts of the last switch. Prints what would be replaced, what keeps the stock
font and why, which XML files change, and how long it takes on this machine.

  python3 tools/replay_diagnostics.py LuoShu-engine-XXX.zip [--work DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import luoshu_engine  # noqa: E402
import luoshu_payload  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _remap_spec(spec: dict[str, Any], sources: dict[str, Any], bundle_root: Path) -> dict[str, Any]:
    def remap(path: str) -> str:
        entry = sources.get(path)
        if entry is None:
            raise SystemExit(f"诊断包缺少源字体：{path}")
        return str(bundle_root / entry["file"])

    if spec.get("mode") == "composite":
        roles = {}
        for role, item in (spec.get("roles") or {}).items():
            roles[role] = dict(item, files=[remap(path) for path in item.get("files") or []])
        return {"mode": "composite", "roles": roles}
    return {"mode": "single", "files": [remap(path) for path in spec.get("files") or []]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()

    work = args.work or Path(tempfile.mkdtemp(prefix="luoshu-replay-"))
    bundle_root = work / "bundle"
    with zipfile.ZipFile(args.bundle) as bundle:
        bundle.extractall(bundle_root)
    index = _load(bundle_root / "index.json")
    config = bundle_root / "config"
    print(f"device: {json.dumps(index.get('device'), ensure_ascii=False)}")
    print(f"module: {index.get('module')} active={index.get('activeFont')!r} mode={index.get('mode', 'full')}")

    report_path = config / "luoshu-engine-build" / "report.json"
    if not report_path.is_file():
        raise SystemExit("诊断包里没有字体引擎记录：请先在手机上切换一次字体再导出")
    device_report = _load(report_path)
    spec = _remap_spec(device_report.get("sources") or {}, index.get("sources") or {}, bundle_root)
    stock_paths = {logical: bundle_root / entry["file"] for logical, entry in (index.get("stock") or {}).items()}
    print(f"device result: replaced={len(device_report.get('replaced') or [])} "
          f"kept={len(device_report.get('keptStock') or [])} seconds={device_report.get('seconds')}")

    started = time.monotonic()
    try:
        manifest, report = luoshu_engine.build(
            _load(config / "device_font_topology.json"), spec, work / "payload", work / "cache",
            xml_root=config / "font-config-source", stock_paths=stock_paths, live_root=None,
        )
    except (luoshu_engine.EngineError, luoshu_payload.DeploymentError) as error:
        print(f"RESULT: FAIL {error}")
        return 1
    print(f"replaced: {len(report['replaced'])}")
    for item in report["replaced"]:
        print(f"  {item['path']} role={item['role']} variable={item['variable']} faces={item['faces']}")
    print(f"kept stock: {len(report['keptStock'])}")
    for item in report["keptStock"]:
        print(f"  KEPT {item['path']} reason={item['reason']}")
    for item in report["xml"]:
        print(f"  XML {item['sourceXml']} nodes={item['nodes']}")
    size = sum(item["bytes"] for item in manifest["files"]) / 1e6
    print(f"RESULT: PASS files={manifest['summary']['fileCount']} payload={size:.0f}MB "
          f"stats={report['stats']} host={time.monotonic() - started:.1f}s work={work}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
