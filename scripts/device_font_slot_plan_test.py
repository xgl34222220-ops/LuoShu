#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_slot_plan as planner


def profile(
    *,
    upem: int,
    cap_height: float,
    cap_min: float,
    cap_advance: float,
    digit_height: float,
    digit_min: float,
    digit_advance: float,
) -> dict:
    scale = upem / 1000.0
    return {
        "path": "/fixture/source.ttf",
        "faceIndex": -1,
        "sha256": "0" * 64,
        "names": ["Fixture"],
        "metrics": {
            "unitsPerEm": upem,
            "headYMin": round(-250 * scale),
            "headYMax": round(950 * scale),
            "hheaAscent": round(930 * scale),
            "hheaDescent": round(-250 * scale),
            "hheaLineGap": 0,
            "typoAscender": round(930 * scale),
            "typoDescender": round(-250 * scale),
            "typoLineGap": 0,
            "winAscent": round(980 * scale),
            "winDescent": round(350 * scale),
            "capHeight": int(cap_height),
            "xHeight": round(500 * scale),
            "weightClass": 400,
            "widthClass": 5,
            "fsSelection": 128,
        },
        "probes": {
            "latinCap": {
                "hits": 5,
                "yMin": cap_min,
                "yMax": cap_min + cap_height,
                "height": cap_height,
                "inkWidth": 540 * scale,
                "advance": cap_advance,
            },
            "digits": {
                "hits": 10,
                "yMin": digit_min,
                "yMax": digit_min + digit_height,
                "height": digit_height,
                "inkWidth": 510 * scale,
                "advance": digit_advance,
            },
            "latinX": {
                "hits": 4,
                "yMin": 0,
                "yMax": 500 * scale,
                "height": 500 * scale,
                "inkWidth": 430 * scale,
                "advance": 520 * scale,
            },
            "latinDescender": {
                "hits": 5,
                "yMin": -210 * scale,
                "yMax": 510 * scale,
                "height": 720 * scale,
                "inkWidth": 450 * scale,
                "advance": 530 * scale,
            },
            "cjk": {
                "hits": 8,
                "yMin": -80 * scale,
                "yMax": 880 * scale,
                "height": 960 * scale,
                "inkWidth": 920 * scale,
                "advance": 1000 * scale,
            },
            "punctuation": {
                "hits": 8,
                "yMin": -120 * scale,
                "yMax": 760 * scale,
                "height": 880 * scale,
                "inkWidth": 300 * scale,
                "advance": 420 * scale,
            },
        },
    }


def slot(family: str, roles: list[str], target: dict, replaceable: bool = True) -> dict:
    return {
        "family": family,
        "familyNormalized": family,
        "weight": 400,
        "style": "normal",
        "index": 0,
        "axes": "",
        "roles": roles,
        "sourceXml": "/system/etc/fonts.xml",
        "resolvedPath": f"/system/fonts/{family}.ttf",
        "replaceable": replaceable,
        "font": target,
    }


def main() -> None:
    source = profile(
        upem=1000,
        cap_height=700,
        cap_min=0,
        cap_advance=600,
        digit_height=700,
        digit_min=-10,
        digit_advance=560,
    )
    stock_ui = profile(
        upem=2000,
        cap_height=1400,
        cap_min=20,
        cap_advance=1200,
        digit_height=1400,
        digit_min=0,
        digit_advance=1120,
    )
    stock_ui["path"] = "/system/fonts/Roboto-Regular.ttf"
    stock_ui["metrics"].update(
        {
            "hheaAscent": 1900,
            "hheaDescent": -500,
            "hheaLineGap": 0,
            "typoAscender": 1900,
            "typoDescender": -500,
            "typoLineGap": 0,
            "winAscent": 2000,
            "winDescent": 700,
        }
    )
    stock_clock = profile(
        upem=1000,
        cap_height=680,
        cap_min=5,
        cap_advance=580,
        digit_height=620,
        digit_min=60,
        digit_advance=600,
    )
    stock_clock["path"] = "/system/fonts/Clockopia.ttf"

    template = {
        "schema": "device-font-template-v1",
        "fingerprint": "fixture-rom",
        "slots": [
            slot("sans-serif", ["global-ui"], stock_ui),
            slot("clock-family", ["clock"], stock_clock),
            slot("emoji-family", ["protected", "fallback"], stock_ui, replaceable=False),
        ],
    }
    result = planner.build_plan(template, source)
    assert result["schema"] == "device-font-slot-plan-v1"
    assert result["summary"] == {
        "slots": 3,
        "ready": 2,
        "unsafe": 0,
        "unresolved": 0,
        "skipped": 1,
    }, result["summary"]

    plans = {item["familyNormalized"]: item for item in result["slots"]}
    ui = plans["sans-serif"]
    assert ui["status"] == "ready"
    assert ui["lineContract"]["hheaAscent"] == 1900
    assert ui["lineContract"]["hheaDescent"] == -500
    assert ui["upemScale"] == 2.0
    assert ui["transforms"]["latinCap"]["outlineScaleY"] == 2.0
    assert ui["transforms"]["latinCap"]["relativeScaleY"] == 1.0
    assert ui["transforms"]["latinCap"]["shiftY"] == 20.0
    assert ui["transforms"]["digits"]["advanceScale"] == 2.0

    clock = plans["clock-family"]
    assert clock["status"] == "ready"
    assert set(clock["transforms"]) == {"digits", "punctuation", "latinCap"}
    assert clock["transforms"]["digits"]["outlineScaleY"] == round(620 / 700, 8)
    assert clock["transforms"]["digits"]["shiftY"] == 68.8571
    assert clock["transforms"]["digits"]["targetAdvance"] == 600.0

    emoji = plans["emoji-family"]
    assert emoji["status"] == "skipped"
    assert emoji["reason"] == "protected-or-fallback"

    extreme = profile(
        upem=1000,
        cap_height=1200,
        cap_min=400,
        cap_advance=1000,
        digit_height=1200,
        digit_min=400,
        digit_advance=1000,
    )
    unsafe = planner.slot_plan(slot("sans-serif", ["global-ui"], extreme), source)
    assert unsafe["status"] == "unsafe"
    assert "latinCap" in unsafe["unsafeProbes"]

    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
