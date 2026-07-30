#!/usr/bin/env python3
"""Validate the minimum real-device evidence required for a stable LuoShu release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_DEVICE_IDS = (
    "coloros16-kernelsu",
    "hyperos3-kernelsu",
    "generic-magisk",
    "generic-apatch",
)


def validate_matrix(payload: dict) -> list[str]:
    devices = {
        str(device.get("id", "")): device
        for device in payload.get("devices", [])
        if isinstance(device, dict)
    }
    failures: list[str] = []
    for device_id in REQUIRED_DEVICE_IDS:
        device = devices.get(device_id)
        if device is None:
            failures.append(f"{device_id}: missing")
            continue
        if device.get("status") != "passed":
            failures.append(f"{device_id}: status={device.get('status', 'missing')}")
            continue
        evidence = device.get("evidence")
        if not isinstance(evidence, list) or not any(str(item).strip() for item in evidence):
            failures.append(f"{device_id}: evidence missing")
        if not str(device.get("testedAt", "")).strip():
            failures.append(f"{device_id}: testedAt missing")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--matrix",
        default="docs/device_validation.json",
        help="Path to the machine-readable device validation matrix",
    )
    args = parser.parse_args()
    matrix_path = Path(args.matrix)
    try:
        payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"device matrix unreadable: {error}")
        return 1

    failures = validate_matrix(payload)
    if failures:
        print("minimum stable device matrix is incomplete:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("minimum stable device matrix passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
