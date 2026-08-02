#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import device_font_payload_build as payload_build
import device_font_slot_build as slot_build
import device_font_slot_plan as slot_plan
import device_font_template as template


def ref(*, family: str = "", attrs: dict[str, str] | None = None, declared: str = ""):
    return template.FontRef(
        family=family,
        family_attrs=attrs or {},
        declared=declared,
        postscript_name="",
        weight=400,
        style="normal",
        index=0,
        axes="",
        source_xml=Path("/system/etc/fonts.xml"),
        dynamic=False,
    )


zh_roles = template.classify_roles(
    ref(attrs={"lang": "zh-Hans"}, declared="NotoSansCJK-Regular.ttc"), None
)
assert "fallback-cjk" in zh_roles, zh_roles
assert "global-ui" in zh_roles, zh_roles
assert "fallback" not in zh_roles, zh_roles

ja_roles = template.classify_roles(
    ref(attrs={"lang": "ja"}, declared="NotoSansCJK-Regular.ttc"), None
)
assert "fallback" in ja_roles and "fallback-other" in ja_roles, ja_roles
assert "global-ui" not in ja_roles, ja_roles

variant_roles = template.classify_roles(
    ref(family="sans-serif", attrs={"variant": "elegant"}, declared="Roboto-Regular.ttf"), None
)
assert "global-ui" in variant_roles, variant_roles
assert "fallback" not in variant_roles, variant_roles

cjk_slot = {
    "family": "",
    "familyNormalized": "",
    "familyAttributes": {"lang": "zh-Hans"},
    "declared": "NotoSansCJK-Regular.ttc",
    "postScriptName": "NotoSansCJKsc-Regular",
    "sourceXml": "/system/etc/fonts.xml",
    "weight": 400,
    "style": "normal",
    "roles": ["fallback-cjk", "global-ui"],
    "replaceable": True,
    "font": {
        "metrics": {"unitsPerEm": 1000, "hheaAscent": 800, "hheaDescent": -200},
        "probes": {"cjk": {"hits": 20, "height": 900, "yMin": -100, "yMax": 800}},
    },
}
latin_profile = {
    "metrics": {"unitsPerEm": 1000},
    "probes": {
        "latinCap": {"hits": 20},
        "latinX": {"hits": 12},
        "digits": {"hits": 10},
        "cjk": {"hits": 0},
    },
}
cjk_profile = {
    "metrics": {"unitsPerEm": 1000},
    "probes": {
        "cjk": {"hits": 20, "height": 900, "yMin": -100, "yMax": 800},
        "punctuationFullwidth": {"hits": 8, "height": 800, "yMin": -50, "yMax": 750},
    },
}
assert not slot_plan.source_supports_slot(cjk_slot, latin_profile)
assert slot_plan.source_supports_slot(cjk_slot, cjk_profile)
result = slot_plan.slot_plan(cjk_slot, latin_profile)
assert result["status"] == "skipped", result
assert result["reason"] == "source-cjk-coverage-missing", result

identity = slot_build.target_family_identity({
    "family": "sans-serif",
    "weight": 400,
    "style": "normal",
    "postScriptName": "Roboto-Regular",
})
assert identity[0] == "sans-serif", identity
assert identity[3] == "Roboto-Regular", identity

source_profile = {"sha256": "abc", "faceIndex": -1}
slot_a = {
    "family": "sans-serif",
    "familyNormalized": "sans-serif",
    "familyAttributes": {},
    "sourceXml": "/system/etc/fonts.xml",
    "weight": 400,
    "style": "normal",
    "roles": ["global-ui"],
    "lineContract": {},
    "transforms": {},
}
slot_b = dict(slot_a, family="google-sans", familyNormalized="google-sans")
assert payload_build.build_signature(slot_a, source_profile, 400) != payload_build.build_signature(slot_b, source_profile, 400)

print("fallback_coverage_policy_test: PASS")
