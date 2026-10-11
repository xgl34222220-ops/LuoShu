#!/usr/bin/env python3
# Packaging contract marker: device-font-slot-plan-v2
"""Coverage-aware policy for Android fallback font slots."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import device_font_slot_plan_base as _base
from device_font_slot_plan_base import *  # noqa: F401,F403

_ORIGINAL_SLOT_PLAN = _base.slot_plan


def _probe_hits(profile: dict[str, Any], name: str) -> int:
    probes = profile.get("probes") if isinstance(profile.get("probes"), dict) else {}
    value = probes.get(name) if isinstance(probes.get(name), dict) else {}
    try:
        return max(0, int(value.get("hits") or 0))
    except (TypeError, ValueError):
        return 0


def source_supports_slot(slot: dict[str, Any], source_profile: dict[str, Any]) -> bool:
    roles = set(slot.get("roles") or [])
    if "fallback-cjk" in roles:
        return _probe_hits(source_profile, "cjk") >= 8
    if "fallback-latin" in roles:
        return (
            _probe_hits(source_profile, "latinCap") >= 8
            and _probe_hits(source_profile, "latinX") >= 8
            and _probe_hits(source_profile, "digits") >= 10
        )
    if "fallback-other" in roles or "fallback" in roles:
        return False
    return True


_CLOCK_REPORTS: dict[tuple[str, int, str], dict[str, Any] | None] = {}


def _clock_log(message: str) -> None:
    print(f"[clock-glyph-gate] {message}", file=sys.stderr)


def source_clock_report(source_profile: dict[str, Any]) -> dict[str, Any] | None:
    """Clock glyph gate for the selected source; None when it cannot be read."""
    path = str(source_profile.get("path") or "")
    try:
        face = int(source_profile.get("faceIndex", -1))
    except (TypeError, ValueError):
        face = -1
    key = (path, face, str(source_profile.get("sha256") or ""))
    if key in _CLOCK_REPORTS:
        return _CLOCK_REPORTS[key]
    report: dict[str, Any] | None = None
    if path and Path(path).is_file():
        try:
            import font_role_check

            report = font_role_check.inspect_clock(Path(path), face)
        except Exception as exc:  # unreadable source: keep the existing plan
            _clock_log(f"无法读取源字体，跳过时钟字符检查：{Path(path).name}：{exc.__class__.__name__}")
    _CLOCK_REPORTS[key] = report
    if report is not None:
        name = Path(path).name
        if not report.get("tabularDigits"):
            _clock_log(f"{report.get('warning')}：{name} 数字前进宽度 {report.get('digitAdvances')}")
        if report.get("missing"):
            _clock_log(f"源字体缺少时钟字符 {' '.join(report['missing'])}，时钟槽位保留原厂字形：{name}")
    return report


def slot_plan(slot: dict[str, Any], source_profile: dict[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_SLOT_PLAN(slot, source_profile)
    roles = set(slot.get("roles") or [])
    if "clock" in roles and result.get("status") == "ready":
        report = source_clock_report(source_profile)
        if report is not None and report.get("missing"):
            # Keep the stock clock face: the payload builder skips this slot and
            # leaves the ROM file in place. Fonts that pass keep the plan unchanged.
            result["status"] = "skipped"
            result["reason"] = "source-clock-glyphs-missing"
            result["clockGlyphsMissing"] = list(report["missing"])
            result["transforms"] = {}
        return result
    if "protected" in roles or not roles.intersection(("fallback-cjk", "fallback-latin")):
        return result

    if not source_supports_slot(slot, source_profile):
        result["status"] = "skipped"
        if "fallback-cjk" in roles:
            result["reason"] = "source-cjk-coverage-missing"
        else:
            result["reason"] = "source-latin-coverage-missing"
        result["transforms"] = {}
        return result

    if "fallback-cjk" in roles:
        transform = (result.get("transforms") or {}).get("cjk", {})
        if not isinstance(transform, dict) or transform.get("status") != "ready":
            result["status"] = "unresolved"
            result["reason"] = "cjk-anchor-unresolved"
    return result


_base.slot_plan = slot_plan


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
