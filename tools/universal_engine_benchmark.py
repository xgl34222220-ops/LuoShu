#!/usr/bin/env python3
"""Host benchmark for the Universal Font Engine Phase 2-6 pipeline.

Builds an Android-15-like fonts.xml where one variable stock file is referenced
by many <font> nodes (weights x widths) plus a CJK stock slot, then runs the
real role classifier, FontPlan, XML router and compiler with real fonts.

HOST_ONLY: numbers are desktop CPython timings, not Android ARM64 timings.

Usage:
  python3 tools/universal_engine_benchmark.py \
      --source User.ttf --latin-stock Roboto-VF.ttf --cjk-stock CJK-VF.ttf \
      [--weights 100,400,700] [--profile out.prof] [--work DIR] [--runs 1]
"""
from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import font_inventory  # noqa: E402
import font_role_shadow  # noqa: E402
import font_source_profile  # noqa: E402
import minimal_xml_router  # noqa: E402
import universal_font_compiler as compiler  # noqa: E402
import universal_font_plan  # noqa: E402

FONTS_XML = "/system/etc/fonts.xml"
LATIN_LOGICAL = "/system/fonts/Roboto-Regular.ttf"
CJK_LOGICAL = "/system/fonts/NotoSansCJK-Regular.ttf"


def _xml_node(declared: str, weight: int, axes: list[tuple[str, float]]) -> str:
    children = "".join(
        f'<axis tag="{tag}" stylevalue="{value:g}"/>' for tag, value in axes
    )
    return f'<font weight="{weight}" style="normal">{declared}{children}</font>'


def _ref(family: str, attrs: dict[str, str], declared: str, logical: str, weight: int) -> dict:
    return {
        "sourceXml": FONTS_XML,
        "sourcePartition": "system",
        "family": family,
        "familyNormalized": family.lower(),
        "familyAttributes": attrs,
        "declared": declared,
        "postScriptName": "",
        "weight": weight,
        "style": "normal",
        "index": 0,
        "axes": "",
        "resolvedPath": logical,
    }


def _slot(logical: str, stock: Path, families: list[str], refs: list[dict]) -> dict:
    fmt, metrics = font_inventory._read_metrics(stock, 0)
    return {
        "slotName": Path(logical).name,
        "path": logical,
        "partition": "system",
        "source": "benchmark",
        "families": families,
        "weight": 400,
        "style": "normal",
        "faceIndex": 0,
        "format": fmt,
        "metrics": metrics,
        "xmlRefs": refs,
        "legacyReplaceable": True,
        "runtimeEvidence": {"fontManager": True, "mount": False},
    }


def build_inputs(args: argparse.Namespace, work: Path) -> tuple[dict, dict, dict, Path]:
    weights = [int(item) for item in args.weights.split(",") if item.strip()]
    nodes: list[str] = []
    latin_refs: list[dict] = []
    nodes.append('<family name="sans-serif">')
    for weight in weights:
        nodes.append(_xml_node("Roboto-Regular.ttf", weight, [("wght", weight)]))
        latin_refs.append(_ref("sans-serif", {}, "Roboto-Regular.ttf", LATIN_LOGICAL, weight))
    nodes.append("</family>")
    if args.condensed:
        nodes.append('<family name="sans-serif-condensed">')
        for weight in weights:
            nodes.append(_xml_node(
                "Roboto-Regular.ttf", weight, [("wdth", 75), ("wght", weight)]
            ))
            latin_refs.append(_ref(
                "sans-serif-condensed", {}, "Roboto-Regular.ttf", LATIN_LOGICAL, weight
            ))
        nodes.append("</family>")
    cjk_refs: list[dict] = []
    nodes.append('<family lang="zh-Hans">')
    for weight in weights:
        nodes.append(_xml_node("NotoSansCJK-Regular.ttf", weight, [("wght", weight)]))
        cjk_refs.append(_ref("", {"lang": "zh-Hans"}, "NotoSansCJK-Regular.ttf", CJK_LOGICAL, weight))
    nodes.append("</family>")
    xml_path = work / "fonts.xml"
    xml_path.write_text("<familyset>" + "".join(nodes) + "</familyset>", encoding="utf-8")

    families = ["sans-serif"] + (["sans-serif-condensed"] if args.condensed else [])
    slots = {
        LATIN_LOGICAL: _slot(LATIN_LOGICAL, args.latin_stock, families, latin_refs),
        CJK_LOGICAL: _slot(CJK_LOGICAL, args.cjk_stock, [], cjk_refs),
    }
    topology = {
        "schema": "device-font-topology-v1",
        "topologyRevision": 2,
        "state": "ready",
        "buildKey": "benchmark",
        "romKind": "generic",
        "summary": {
            "slotCount": len(slots),
            "dataFontFileCount": 0,
            "dataFontConfigReferenceCount": 0,
            "unresolvedXmlRefCount": 0,
        },
        "slots": slots,
        "families": {},
        "xmlAliases": [],
        "unresolvedXmlRefs": [],
        "runtime": {},
    }
    roles, _shadow = font_role_shadow.build(topology)
    profile = font_source_profile.build([args.source])
    return topology, roles, profile, xml_path


def run_once(args: argparse.Namespace, work: Path, output_dir: Path) -> dict:
    timings: dict[str, float] = {}
    start = time.perf_counter()
    topology, roles, profile, xml_path = build_inputs(args, work)
    timings["inputs"] = time.perf_counter() - start

    start = time.perf_counter()
    plan = universal_font_plan.build_plan(topology, roles, profile)
    timings["plan"] = time.perf_counter() - start

    start = time.perf_counter()
    route = minimal_xml_router.build_route_plan(plan, {FONTS_XML: xml_path}, None, False)
    timings["route"] = time.perf_counter() - start

    stock_map = {LATIN_LOGICAL: args.latin_stock, CJK_LOGICAL: args.cjk_stock}
    start = time.perf_counter()
    if args.profile:
        profiler = cProfile.Profile()
        manifest = profiler.runcall(
            compiler.compile_all, plan, route, stock_map, output_dir, False
        )
        profiler.dump_stats(str(args.profile))
    else:
        manifest = compiler.compile_all(plan, route, stock_map, output_dir, False)
    timings["compile"] = time.perf_counter() - start

    modes: dict[str, int] = {}
    for item in manifest["artifacts"]:
        key = f"{item.get('mode') or 'none'}:{item['status']}"
        modes[key] = modes.get(key, 0) + 1
    return {
        "hostOnly": True,
        "roles": {
            path: roles["slots"][path]["role"] for path in sorted(roles["slots"])
        },
        "planActions": plan["summary"]["actionCounts"],
        "routeOperations": route["summary"]["operationCount"],
        "routingComplete": route["summary"]["routingComplete"],
        "artifactCount": manifest["summary"]["artifactCount"],
        "readyCount": manifest["summary"]["readyCount"],
        "blockedCount": manifest["summary"]["blockedCount"],
        "modes": modes,
        "blockedReasons": sorted({
            str(item.get("reason") or "")[:160]
            for item in manifest["artifacts"] if item["status"] != "ready"
        }),
        "timingsSeconds": {key: round(value, 3) for key, value in timings.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--latin-stock", type=Path, required=True)
    parser.add_argument("--cjk-stock", type=Path, required=True)
    parser.add_argument("--weights", default="100,200,300,400,500,600,700,800,900")
    parser.add_argument("--no-condensed", dest="condensed", action="store_false")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--keep-output", action="store_true",
                        help="reuse one output dir across runs (measures warm cache)")
    args = parser.parse_args()

    owned = args.work is None
    work = Path(tempfile.mkdtemp(prefix="luoshu-ufe-bench-")) if owned else args.work
    work.mkdir(parents=True, exist_ok=True)
    try:
        results = []
        for run in range(max(1, args.runs)):
            output_dir = work / ("out" if args.keep_output else f"out-{run}")
            results.append(run_once(args, work, output_dir))
        print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2))
        if args.profile:
            stats = pstats.Stats(str(args.profile))
            stats.sort_stats("cumulative").print_stats(35)
    finally:
        if owned:
            shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
