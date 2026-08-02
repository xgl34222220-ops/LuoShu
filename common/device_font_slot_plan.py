#!/usr/bin/env python3
# Packaging contract marker: device-font-slot-plan-v2
"""Coverage-aware policy for Android fallback font slots."""
from __future__ import annotations

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


def slot_plan(slot: dict[str, Any], source_profile: dict[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_SLOT_PLAN(slot, source_profile)
    roles = set(slot.get("roles") or [])
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
