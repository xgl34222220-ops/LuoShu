#!/usr/bin/env python3

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("device_validation_gate.py")
SPEC = importlib.util.spec_from_file_location("device_validation_gate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def device(device_id: str, status: str = "passed") -> dict:
    return {
        "id": device_id,
        "status": status,
        "testedAt": "2026-07-30",
        "evidence": ["acceptance-report.json"],
    }


valid = {"devices": [device(device_id) for device_id in MODULE.REQUIRED_DEVICE_IDS]}
assert MODULE.validate_matrix(valid) == []

pending = {"devices": [device(device_id) for device_id in MODULE.REQUIRED_DEVICE_IDS]}
pending["devices"][-1]["status"] = "pending"
failures = MODULE.validate_matrix(pending)
assert failures == ["generic-apatch: status=pending"], failures

missing_evidence = {"devices": [device(device_id) for device_id in MODULE.REQUIRED_DEVICE_IDS]}
missing_evidence["devices"][0]["evidence"] = []
assert MODULE.validate_matrix(missing_evidence) == ["coloros16-kernelsu: evidence missing"]

print("device validation gate tests passed")
