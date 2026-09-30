#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

import font_source_profile
import minimal_xml_router
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture
import universal_font_cutover_gate as gate
import universal_font_deployment as deployment
import universal_font_plan


def build_fixture(temp: Path):
    source = temp / "User-Regular.ttf"
    stock = temp / "Stock-Regular.ttf"
    fixture.make_font(source, family="User Font", y_min=-90, y_max=710)
    fixture.make_font(stock, family="Stock UI", y_min=-100, y_max=720)

    logical = "/system/fonts/Stock-Regular.ttf"
    slot = fixture.slot_from_stock(
        logical,
        stock,
        family="sans-serif",
        source_xml=None,
        declared="Stock-Regular.ttf",
    )
    profile = font_source_profile.build([source])
    topology = {
        "schema": "device-font-topology-v1",
        "topologyRevision": 3,
        "state": "ready",
        "buildKey": "phase9-test",
        "romKind": "generic",
        "summary": {},
        "slots": {logical: slot},
        "families": {},
        "xmlAliases": [],
        "unresolvedXmlRefs": [],
        "runtime": {},
    }
    roles = {
        "schema": "device-font-roles-v1",
        "roleRevision": 3,
        "state": "ready",
        "buildKey": "phase9-test",
        "romKind": "generic",
        "slots": {logical: fixture.role_map("latin")},
    }
    plan = universal_font_plan.build_plan(topology, roles, profile)
    route = minimal_xml_router.build_route_plan(plan, {}, None, False)
    artifacts = compiler.compile_all(
        plan,
        route,
        {logical: stock},
        temp / "compiled",
        False,
    )
    payload_root = temp / "payload"
    deployed = deployment.build_deployment(plan, route, artifacts, payload_root)
    return plan, route, artifacts, deployed, payload_root, logical


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-phase9-gate-") as raw:
        temp = Path(raw)
        plan, route, artifacts, deployed, payload_root, logical = build_fixture(temp)

        result = gate.evaluate(plan, route, artifacts, deployed, payload_root)
        assert result["eligible"] is True, result
        assert result["decision"] == "universal", result
        assert result["summary"]["replacementCount"] == 1, result

        missing = deepcopy(plan)
        missing["summary"]["missingRoleSlotCount"] = 1
        missing["missingRoleSlots"] = ["/system/fonts/Missing.ttf"]
        rejected = gate.evaluate(missing, route, artifacts, deployed, payload_root)
        assert rejected["eligible"] is False, rejected
        assert "missing-role-slots" in rejected["reasons"], rejected

        blocked = deepcopy(plan)
        blocked["targets"][logical]["action"] = "blocked"
        blocked["targets"][logical]["status"] = "blocked"
        rejected = gate.evaluate(blocked, route, artifacts, deployed, payload_root)
        assert rejected["eligible"] is False, rejected
        assert any(reason.startswith("blocked-target:") for reason in rejected["reasons"]), rejected

        protected = deepcopy(plan)
        protected["targets"][logical]["role"] = "emoji"
        protected["targets"][logical]["action"] = "compile"
        rejected = gate.evaluate(protected, route, artifacts, deployed, payload_root)
        assert rejected["eligible"] is False, rejected
        assert any("protected-role-not-preserved" in reason for reason in rejected["reasons"]), rejected

        tampered_payload = payload_root / "system/fonts/Stock-Regular.ttf"
        tampered_payload.write_bytes(tampered_payload.read_bytes() + b"x")
        rejected = gate.evaluate(plan, route, artifacts, deployed, payload_root)
        assert rejected["eligible"] is False, rejected
        assert any(reason.startswith("identity-or-integrity:") for reason in rejected["reasons"]), rejected

    print("universal_font_cutover_gate_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
