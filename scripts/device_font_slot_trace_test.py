#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_slot_trace as trace


def main() -> None:
    inventory = {
        "schema": "device-font-inventory-v1",
        "buildKey": "fixture-rom",
        "romKind": "generic",
        "slots": {
            "/system/fonts/A.ttf": {
                "slotName": "A.ttf", "partition": "system", "source": "xml",
                "format": "TTF", "weight": 400, "style": "normal", "families": ["sans-serif"],
            },
            "/system/fonts/B.ttf": {
                "slotName": "B.ttf", "partition": "system", "source": "verified-scan",
                "format": "TTF", "weight": 400, "style": "normal", "families": [],
            },
            "/product/fonts/C.ttc": {
                "slotName": "C.ttc", "partition": "product", "source": "verified-scan",
                "format": "TTC", "weight": 400, "style": "normal", "families": [],
            },
            "/product/fonts/D.ttf": {
                "slotName": "D.ttf", "partition": "product", "source": "heuristic",
                "format": "TTF", "weight": 700, "style": "normal", "families": [],
            },
            "/vendor/fonts/E.ttf": {
                "slotName": "E.ttf", "partition": "vendor", "source": "verified-scan",
                "format": "TTF", "weight": 400, "style": "normal", "families": [],
            },
        },
    }
    payload = {
        "schema": "device-font-payload-v1",
        "inventorySupplement": {
            "schema": "device-font-inventory-link-v1",
            "slots": [
                {"path": "/system/fonts/A.ttf", "disposition": "template"},
                {"path": "/system/fonts/B.ttf", "disposition": "direct"},
                {"path": "/product/fonts/C.ttc", "disposition": "preserved", "reason": "preserved-collection"},
                {"path": "/product/fonts/D.ttf", "disposition": "direct"},
                {"path": "/vendor/fonts/E.ttf", "disposition": "direct"},
            ],
        },
        "slots": [
            {
                "slotIndex": 0, "inventoryPath": "/system/fonts/A.ttf", "stockPath": "/system/fonts/A.ttf",
                "family": "sans-serif", "weight": 400, "style": "normal", "sourceXml": "/system/etc/fonts.xml",
                "planStatus": "ready", "planReason": "", "generatedFile": "LuoShuSlot-A.ttf",
            },
            {
                "slotIndex": 1, "inventoryPath": "/system/fonts/B.ttf", "stockPath": "/system/fonts/B.ttf",
                "family": "inventory-B", "weight": 400, "style": "normal", "sourceXml": "",
                "planStatus": "skipped", "planReason": "fixture-preserved",
            },
            {
                "slotIndex": 2, "inventoryPath": "/product/fonts/D.ttf", "stockPath": "/product/fonts/D.ttf",
                "family": "inventory-D", "weight": 700, "style": "normal", "sourceXml": "",
                "planStatus": "ready", "planReason": "", "generatedFile": "LuoShuSlot-D.ttf",
                "directPhysical": True,
            },
            {
                "slotIndex": 3, "inventoryPath": "/vendor/fonts/E.ttf", "stockPath": "/vendor/fonts/E.ttf",
                "family": "inventory-E", "weight": 400, "style": "normal", "sourceXml": "",
                "planStatus": "ready", "planReason": "", "generatedFile": "LuoShuSlot-E.ttf",
                "directPhysical": True,
            },
        ],
    }
    overlay = {
        "schema": "device-font-overlay-v1",
        "slotResults": [
            {
                "slotIndex": 0, "state": "mapped", "route": "xml",
                "targetPath": "system/fonts/LuoShuSlot-A.ttf", "generatedFile": "LuoShuSlot-A.ttf",
            },
            {
                "slotIndex": 1, "state": "preserved", "route": "stock", "targetPath": "",
            },
            {
                "slotIndex": 2, "state": "mapped", "route": "physical",
                "targetPath": "product/fonts/D.ttf", "generatedFile": "LuoShuSlot-D.ttf",
            },
        ],
    }
    verification = {
        "schema": "device-font-load-verification-v1",
        "state": "failed",
        "slotResults": [
            {
                "slotIndex": 0, "loadState": "loaded", "fontManagerConfirmed": True, "mountStatus": "ok",
            },
            {
                "slotIndex": 2, "loadState": "missing-mount", "fontManagerConfirmed": False,
            },
        ],
    }
    candidates = {
        "schema": "device-font-candidates-v1",
        "paths": [
            {"path": "/system/fonts/A.ttf", "partition": "system", "slotName": "A.ttf", "candidate": True, "reason": "visible-font-path"},
            {"path": "/system/fonts/NotoColorEmoji.ttf", "partition": "system", "slotName": "NotoColorEmoji.ttf", "candidate": False, "reason": "specialized-name"},
            {"path": "/product/assets/HiddenStandalone.ttf", "partition": "product", "slotName": "HiddenStandalone.ttf", "candidate": True, "reason": "visible-font-path"},
        ],
    }
    result = trace.build_trace(inventory, payload, overlay, verification, candidates)
    states = {item["path"]: item["state"] for item in result["slots"]}
    assert states["/system/fonts/A.ttf"] == "loaded", states
    assert states["/system/fonts/B.ttf"] == "preserved", states
    assert states["/product/fonts/C.ttc"] == "preserved", states
    assert states["/product/fonts/D.ttf"] == "missing-mount", states
    assert states["/vendor/fonts/E.ttf"] == "mapping-missing", states
    assert "/system/fonts/NotoColorEmoji.ttf" not in states, states
    assert "/product/assets/HiddenStandalone.ttf" not in states, states
    census_only = {item["path"]: item["reason"] for item in result["censusOnly"]}
    assert census_only["/system/fonts/NotoColorEmoji.ttf"] == "specialized-name", census_only
    assert census_only["/product/assets/HiddenStandalone.ttf"] == "not-promoted-to-ui-inventory", census_only
    c_slot = next(item for item in result["slots"] if item["path"] == "/product/fonts/C.ttc")
    assert c_slot["reason"] == "preserved-collection", c_slot
    summary = result["summary"]
    assert summary["inventorySlots"] == 5, summary
    assert summary["censusSlots"] == 7, summary
    assert summary["censusOnlySlots"] == 2, summary
    assert len(result["slots"]) == summary["inventorySlots"] == 5, (len(result["slots"]), summary)
    assert summary["replaceableSlots"] == 3, summary
    assert summary["replaced"] == 1, summary
    assert summary["protected"] == 2, summary
    assert summary["issues"] == 2, summary
    assert summary["remediable"] == 1, summary
    assert summary["loaded"] == 1, summary
    assert summary["preserved"] == 2, summary
    assert summary["missingMount"] == 1, summary
    assert summary["mappingMissing"] == 1, summary
    assert summary["notConsumed"] == 0, summary

    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as raw_tmp:
        plan = Path(raw_tmp) / "remediation.txt"
        trace.atomic_write_plan(result, plan)
        assert plan.read_text(encoding="utf-8").splitlines() == [
            "/vendor/fonts/E.ttf",
        ]

    no_boot = trace.build_trace(inventory, payload, overlay, None, candidates)
    no_boot_states = {item["path"]: item["state"] for item in no_boot["slots"]}
    assert no_boot_states["/system/fonts/A.ttf"] == "mapped-unverified"
    assert no_boot_states["/product/fonts/D.ttf"] == "mapped-unverified"
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
