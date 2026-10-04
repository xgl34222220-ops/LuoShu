#!/usr/bin/env python3
"""Core slots must be replaced; a non-core slot that cannot be keeps its stock font."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

import font_role_shadow
import font_source_profile
import minimal_xml_router
import universal_composite_test as composite
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture
import universal_font_cutover_gate as gate
import universal_font_deployment as deployment
import universal_font_plan as planner

ROBOTO = "/system/fonts/Roboto-Regular.ttf"
CJK = "/system/fonts/NotoSansCJK-Regular.ttf"
CLOCK = "/system/fonts/AndroidClock.ttf"


def ref(style: str = "normal", lang: str = "") -> dict:
    return {"style": style, "familyAttributes": {"lang": lang} if lang else {}}


def test_core_definition() -> None:
    core = planner.is_core_target
    assert core({"role": "ui-sans", "xmlRefs": [ref(), ref("italic")]})
    assert not core({"role": "ui-sans", "xmlRefs": [ref("italic")]})
    assert not core({"role": "ui-sans", "slotName": "Roboto-Italic.ttf", "xmlRefs": []})
    assert core({"role": "ui-sans", "slotName": "MiSansVF.ttf", "xmlRefs": []})
    assert core({"role": "cjk", "xmlRefs": [ref(lang="zh-Hans")]})
    assert core({"role": "cjk", "xmlRefs": [ref(lang="und-Hant")]})
    assert not core({"role": "cjk", "xmlRefs": [ref(lang="ja")]})
    assert not core({"role": "cjk", "xmlRefs": []})
    assert core({"role": "clock"}) and core({"role": "numeric"})
    assert not core({"role": "latin", "xmlRefs": [ref(lang="en")]})


def test_record_exclusions(temp: Path) -> None:
    plan = {"targets": {
        "/system/fonts/Core.ttf": {"role": "ui-sans", "xmlRefs": [ref()]},
        "/system/fonts/Extra.ttf": {"role": "latin", "xmlRefs": [ref(lang="en")]},
    }}

    def manifest(*paths: str) -> dict:
        return {"artifacts": [
            {"targetPath": path, "status": "blocked", "reason": "no-shared-probes"} for path in paths
        ] + [{"targetPath": "/system/fonts/Core.ttf", "status": "ready"}]}

    out = temp / "exclusions.json"
    assert compiler._record_exclusions(manifest(), plan, out) == []
    assert not out.exists()
    assert compiler._record_exclusions(manifest("/system/fonts/Extra.ttf"), plan, out) == ["/system/fonts/Extra.ttf"]
    assert planner.load_exclusions(out) == {"/system/fonts/Extra.ttf": "no-shared-probes"}
    # Excluding the same slot again cannot make progress: fail instead of looping.
    try:
        compiler._record_exclusions(manifest("/system/fonts/Extra.ttf"), plan, out)
    except compiler.CompilerError as error:
        assert "保留原厂后仍有字体无法替换" in str(error)
    else:
        raise AssertionError("repeated exclusion must fail")
    try:
        compiler._record_exclusions(manifest("/system/fonts/Core.ttf"), plan, temp / "core.json")
    except compiler.CompilerError as error:
        assert "核心字体无法安全替换" in str(error) and "Core.ttf" in str(error)
    else:
        raise AssertionError("blocked core slot must fail")
    assert not (temp / "core.json").exists()


def test_chain(temp: Path) -> None:
    topology, _roles, stocks, xml_map = composite.build_device(temp / "device")
    # Make the stock Roboto italic-only: a non-core UI slot.
    topology = copy.deepcopy(topology)
    for item in topology["slots"][ROBOTO]["xmlRefs"]:
        item["style"] = "italic"
    roles, _shadow = font_role_shadow.build(topology)
    fonts = temp / "fonts"
    fonts.mkdir()
    cjk, latin = fonts / "UserCJK.ttf", fonts / "UserLatin.ttf"
    composite.make_cjk_font(cjk, family="User CJK", variable=True, pentagon=True)
    fixture.make_font(latin, family="User Latin", variable=True, triangle=True)
    profile = font_source_profile.build(
        [], {"cjk": [cjk], "latin": [latin], "digit": [latin]},
        {"cjk": "auto", "latin": "auto", "digit": "auto"}, {},
    )

    plain = planner.build_plan(topology, roles, profile)
    assert plain["targets"][ROBOTO]["action"] in {"compile", "replace"}

    # A core exclusion is ignored; a non-core one keeps the slot stock.
    plan = planner.build_plan(topology, roles, profile, {ROBOTO: "no-shared-probes", CJK: "x", CLOCK: "x"})
    roboto = plan["targets"][ROBOTO]
    assert roboto["action"] == planner.KEEP_STOCK and roboto["keptStockReason"] == "no-shared-probes", roboto
    assert plan["targets"][CJK]["action"] in {"compile", "replace"}
    assert plan["targets"][CLOCK]["action"] == "compile-specialized"
    assert plan["planId"] != plain["planId"]
    planner.validate_plan(plan)

    forged = copy.deepcopy(plan)
    forged["targets"][CJK].update(action=planner.KEEP_STOCK)
    try:
        planner.validate_plan(forged)
    except planner.UniversalPlanError as error:
        assert "核心字体不得保留原厂" in str(error)
    else:
        raise AssertionError("core keep-stock must be rejected")

    # The rest still routes, compiles, deploys and passes the gate.
    route = minimal_xml_router.build_route_plan(plan, xml_map, None, False)
    assert route["summary"]["routingComplete"] is True
    manifest = compiler.compile_all(plan, route, stocks, temp / "out", False)
    assert manifest["summary"]["blockedCount"] == 0
    assert ROBOTO not in {item["targetPath"] for item in manifest["artifacts"]}
    payload = temp / "payload"
    deployed = deployment.build_deployment(plan, route, manifest, payload)
    verdict = gate.evaluate(plan, route, manifest, deployed, payload)
    assert verdict["eligible"] is True, verdict
    rendered = json.dumps(deployed, ensure_ascii=False)
    assert "Roboto-Regular.ttf" not in json.dumps(deployed.get("physicalTargets") or {}), rendered[:400]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-keep-stock-") as raw:
        temp = Path(raw)
        test_core_definition()
        test_record_exclusions(temp)
        test_chain(temp)
    print("universal_keep_stock_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
