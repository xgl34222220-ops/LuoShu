#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_slot_build as builder
import device_font_slot_plan as planner
import device_font_template as template_engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", required=True, type=Path)
    return parser.parse_args()


def shifted_probe(probe: dict, *, shift_y: float = 0.0, advance_delta: float = 0.0) -> dict:
    result = copy.deepcopy(probe)
    for key in ("yMin", "yMax", "centerY", "yMinP25", "yMaxP75"):
        if result.get(key) is not None:
            result[key] = float(result[key]) + shift_y
    if result.get("advance") is not None:
        result["advance"] = float(result["advance"]) + advance_delta
    return result


def main() -> None:
    args = parse_args()
    source = template_engine.inspect_font(args.font, -1, hash_fonts=True)
    assert source["probes"]["digits"]["hits"] >= 10
    target = copy.deepcopy(source)
    target["path"] = "/system/fonts/Clockopia.ttf"
    target["probes"]["digits"] = shifted_probe(
        source["probes"]["digits"],
        shift_y=48.0,
        advance_delta=24.0,
    )

    template = {
        "schema": "device-font-template-v1",
        "captureRevision": 2,
        "fingerprint": "clock-builder-fixture",
        "slots": [
            {
                "family": "clock-family",
                "familyNormalized": "clock-family",
                "weight": 400,
                "style": "normal",
                "index": 0,
                "axes": "",
                "roles": ["clock"],
                "sourceXml": "/system/etc/fonts.xml",
                "resolvedPath": "/system/fonts/Clockopia.ttf",
                "replaceable": True,
                "font": target,
            }
        ],
    }
    plan = planner.build_plan(template, source)
    assert plan["schema"] == "device-font-slot-plan-v2"
    assert plan["summary"]["ready"] == 1, plan["summary"]
    slot = plan["slots"][0]
    assert slot["status"] == "ready", slot

    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "Clockopia.ttf"
        report = builder.build_slot(args.font, -1, slot, output)
        assert report["schema"] == "device-font-slot-build-v2"
        assert report["status"] == "ok", report
        assert report["transformed"]["probes"]["digits"] >= 10, report
        assert output.is_file() and output.stat().st_size > 1024

        generated = template_engine.inspect_font(output, -1, hash_fonts=False)
        for key in ("hheaAscent", "hheaDescent", "hheaLineGap"):
            assert generated["metrics"][key] == target["metrics"][key], (key, generated["metrics"], target["metrics"])

        source_digits = source["probes"]["digits"]
        target_digits = target["probes"]["digits"]
        generated_digits = generated["probes"]["digits"]
        assert abs(generated_digits["yMin"] - target_digits["yMin"]) <= 1.0, (source_digits, target_digits, generated_digits)
        assert abs(generated_digits["yMax"] - target_digits["yMax"]) <= 1.0, (source_digits, target_digits, generated_digits)
        assert abs(generated_digits["advance"] - target_digits["advance"]) <= 1.0, (source_digits, target_digits, generated_digits)

        generated_caps = generated["probes"]["latinCap"]
        source_caps = source["probes"]["latinCap"]
        assert abs(generated_caps["yMin"] - source_caps["yMin"]) <= 1.0
        assert abs(generated_caps["yMax"] - source_caps["yMax"]) <= 1.0
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()