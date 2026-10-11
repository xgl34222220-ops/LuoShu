#!/usr/bin/env python3
"""Clock glyph gate (P1-7): tabular digits and required clock separators.

Synthetic fonts are built with fontTools so the test does not depend on any
system font that may or may not carry U+2236 / U+FF1A / U+2007 / U+202F.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))

from fontTools.fontBuilder import FontBuilder  # noqa: E402
from fontTools.pens.ttGlyphPen import TTGlyphPen  # noqa: E402

import device_font_payload_build as payload_builder  # noqa: E402
import device_font_slot_plan as planner  # noqa: E402
import device_font_template as template_engine  # noqa: E402
import font_coverage_info  # noqa: E402
import font_role_check  # noqa: E402

LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
PUNCT = ".,;!?-()[]·/"
CLOCK = (0x003A, 0x2236, 0xFF1A, 0x2007, 0x202F)


def box(width: int, top: int, bottom: int = 0):
    pen = TTGlyphPen(None)
    pen.moveTo((60, bottom))
    pen.lineTo((60, top))
    pen.lineTo((max(80, width - 60), top))
    pen.lineTo((max(80, width - 60), bottom))
    pen.closePath()
    return pen.glyph()


def build_font(path: Path, *, family: str, digit_widths: list[int] | None = None, drop: tuple[int, ...] = ()) -> Path:
    widths = digit_widths or [560] * 10
    order = [".notdef"]
    glyphs = {".notdef": box(500, 700)}
    metrics = {".notdef": (500, 60)}
    cmap: dict[int, str] = {}

    def add(codepoint: int, width: int, top: int, bottom: int = 0) -> None:
        if codepoint in drop:
            return
        name = f"uni{codepoint:04X}"
        order.append(name)
        glyphs[name] = box(width, top, bottom)
        metrics[name] = (width, 60)
        cmap[codepoint] = name

    for index, char in enumerate("0123456789"):
        add(ord(char), widths[index], 700)
    for char in LATIN:
        add(ord(char), 600, 700 if char.isupper() else 500, -200 if char in "gjpqy" else 0)
    for char in PUNCT:
        add(ord(char), 300, 120)
    add(0x0020, 260, 0)
    for codepoint in CLOCK:
        add(codepoint, 560 if codepoint == 0x2007 else 300, 500 if codepoint != 0x2007 and codepoint != 0x202F else 0, 100 if codepoint not in (0x2007, 0x202F) else 0)

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=930, descent=-250)
    # font_role_check.check() rejects files under 4 KiB; pad the name table.
    builder.setupNameTable({"familyName": family, "styleName": "Regular", "copyright": "LuoShu clock gate fixture. " * 160})
    builder.setupOS2(sTypoAscender=930, sTypoDescender=-250, usWinAscent=980, usWinDescent=350, sCapHeight=700, sxHeight=500)
    builder.setupPost()
    builder.save(str(path))
    return path


def slot(profile: dict, roles: list[str], family: str) -> dict:
    return {
        "family": family, "familyNormalized": family, "familyAttributes": {}, "sourceXml": "/system/etc/fonts.xml",
        "declared": f"{family}.ttf", "postScriptName": "", "weight": 400, "style": "normal", "index": 0,
        "axes": "", "roles": roles, "replaceable": True, "resolvedPath": f"/system/fonts/{family}.ttf", "font": profile,
    }


def plan_with_log(slot_record: dict, source: dict) -> tuple[dict, str]:
    planner._CLOCK_REPORTS.clear()
    stream = io.StringIO()
    with contextlib.redirect_stderr(stream):
        result = planner.slot_plan(slot_record, source)
    return result, stream.getvalue()


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        good = build_font(root / "good.ttf", family="ClockGood")
        uneven = build_font(root / "uneven.ttf", family="ClockUneven", digit_widths=[560, 420, 560, 560, 560, 560, 560, 560, 560, 560])
        no_colon = build_font(root / "nocolon.ttf", family="ClockNoColon", drop=(0x003A,))
        stock = build_font(root / "stock.ttf", family="StockClock", digit_widths=[600] * 10)

        # 1. Report contract.
        report = font_role_check.inspect_clock(good)
        assert report["clockSafe"] and report["tabularDigits"] and report["missing"] == [] and report["warning"] == "", report
        report = font_role_check.inspect_clock(uneven)
        assert report["clockSafe"] and not report["tabularDigits"], report
        assert report["warning"] == "数字非等宽，状态栏秒数可能抖动", report
        assert report["digitAdvances"] == [420, 560], report
        report = font_role_check.inspect_clock(no_colon)
        assert not report["clockSafe"] and report["missing"] == ["U+003A"] and report["missingText"] == ":", report
        assert report["tabularDigits"], report

        # 2. Existing roles are untouched; the CLI understands the new clock role.
        assert font_role_check.check(good, "digit")["valid"] is True
        assert font_role_check.check(no_colon, "digit")["valid"] is True
        assert font_role_check.check(no_colon, "clock")["status"] == "error"
        assert font_role_check.check(good, "clock")["status"] == "ok"

        # 3. Slot plan gate.
        stock_profile = template_engine.inspect_font(stock, -1, hash_fonts=False)
        stock_profile["path"] = "/system/fonts/Clockopia.ttf"
        clock_slot = slot(stock_profile, ["clock"], "clock-family")
        ui_slot = slot(stock_profile, ["global-ui"], "sans-serif")

        good_profile = template_engine.inspect_font(good, -1, hash_fonts=True)
        baseline = planner._ORIGINAL_SLOT_PLAN(clock_slot, good_profile)
        gated, log = plan_with_log(clock_slot, good_profile)
        assert baseline["status"] == "ready", baseline
        # Passing fonts keep a byte-identical plan (and therefore identical signatures/outputs).
        assert json.dumps(gated, sort_keys=True) == json.dumps(baseline, sort_keys=True)
        assert log == "", log

        uneven_profile = template_engine.inspect_font(uneven, -1, hash_fonts=True)
        baseline = planner._ORIGINAL_SLOT_PLAN(clock_slot, uneven_profile)
        gated, log = plan_with_log(clock_slot, uneven_profile)
        assert json.dumps(gated, sort_keys=True) == json.dumps(baseline, sort_keys=True), "non-tabular must only warn"
        assert "数字非等宽，状态栏秒数可能抖动" in log, log

        missing_profile = template_engine.inspect_font(no_colon, -1, hash_fonts=True)
        gated, log = plan_with_log(clock_slot, missing_profile)
        assert gated["status"] == "skipped", gated
        assert gated["reason"] == "source-clock-glyphs-missing", gated
        assert gated["clockGlyphsMissing"] == ["U+003A"], gated
        assert gated["transforms"] == {}, gated
        assert "U+003A" in log and "保留原厂字形" in log, log
        ui_plan, _ = plan_with_log(ui_slot, missing_profile)
        assert ui_plan == planner._ORIGINAL_SLOT_PLAN(ui_slot, missing_profile), "non-clock slots are not gated"

        # Unreadable source keeps the existing behaviour.
        ghost = dict(missing_profile, path=str(root / "missing.ttf"))
        gated, _ = plan_with_log(clock_slot, ghost)
        assert gated == planner._ORIGINAL_SLOT_PLAN(clock_slot, ghost)

        # 4. Payload: the clock slot is not generated (stock file stays) and the
        # manifest records why; the UI slot is still generated.
        template = {"schema": "device-font-template-v1", "captureRevision": 2, "fingerprint": "clock-gate",
                    "slots": [ui_slot, clock_slot]}
        for name, source, mapped in (("missing", no_colon, 1), ("good", good, 2)):
            source_dir = root / f"src-{name}"
            source_dir.mkdir()
            (source_dir / "LuoShu-400.ttf").write_bytes(source.read_bytes())
            planner._CLOCK_REPORTS.clear()
            with contextlib.redirect_stderr(io.StringIO()):
                payload = payload_builder.build_payload(template, source_dir, "LuoShu", root / f"out-{name}", root / f"out-{name}" / "manifest.json")
            assert payload["summary"]["mapped"] == mapped, payload["summary"]
            clock_record = [item for item in payload["slots"] if item["family"] == "clock-family"][0]
            if name == "missing":
                assert clock_record["planStatus"] == "skipped" and clock_record["planReason"] == "source-clock-glyphs-missing"
                assert "generatedFile" not in clock_record
            else:
                assert clock_record.get("generatedFile"), clock_record

        # 5. Coverage panel data.
        data = font_coverage_info.inspect(no_colon)["data"]
        assert data["clock"]["missing"] == ["U+003A"] and data["clock"]["tabularDigits"] is True, data["clock"]
        data = font_coverage_info.inspect(uneven)["data"]
        assert data["clock"]["missing"] == [] and data["clock"]["tabularDigits"] is False, data["clock"]
    print("clock glyph gate ok")


if __name__ == "__main__":
    main()
