#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_load_verify as verifier


def fixture() -> tuple[dict, dict, list[dict]]:
    payload = {
        "schema": "device-font-payload-v1",
        "slots": [
            {
                "family": "google-sans-text",
                "familyNormalized": "google-sans-text",
                "weight": 400,
                "generatedFile": "LuoShuSlot-abc.ttf",
            }
        ],
    }
    overlay = {
        "schema": "device-font-overlay-v1",
        "summary": {"mappedSlots": 1},
        "copiedFonts": [
            {
                "partition": "system",
                "filename": "LuoShuSlot-abc.ttf",
                "path": "system/fonts/LuoShuSlot-abc.ttf",
                "bytes": 4096,
            }
        ],
        "dynamic": [
            {
                "source": "/data/fonts/config/config.xml",
                "removedFamilies": ["google-sans-text"],
            }
        ],
    }
    mounts = [
        {
            "relative": "system/fonts/LuoShuSlot-abc.ttf",
            "visible": "/system/fonts/LuoShuSlot-abc.ttf",
            "status": "ok",
            "expectedSha256": "a" * 64,
            "actualSha256": "a" * 64,
            "bytes": 4096,
        }
    ]
    return payload, overlay, mounts


def main() -> None:
    payload, overlay, mounts = fixture()
    verified = verifier.verify(
        payload,
        overlay,
        "Family google-sans-text file=/system/fonts/LuoShuSlot-abc.ttf LuoShuSlot-google-sans-text-400",
        mounts,
        "DemoFont",
        {"state": "installed", "templateKey": "trusted"},
    )
    assert verified["state"] == "verified", verified
    assert verified["mode"] == "aligned"
    assert verified["summary"]["dynamicFamilyHits"] == 1

    missing_dynamic = verifier.verify(
        payload,
        overlay,
        "file=/system/fonts/LuoShuSlot-abc.ttf",
        mounts,
        "DemoFont",
        {"state": "installed"},
    )
    assert missing_dynamic["state"] == "failed", missing_dynamic
    assert "dynamic-family-not-loaded" in missing_dynamic["reasons"]

    unavailable_dump = verifier.verify(
        payload,
        overlay,
        "",
        mounts,
        "DemoFont",
        {"state": "installed"},
    )
    assert unavailable_dump["state"] == "verified", unavailable_dump
    assert unavailable_dump["mode"] == "mount-verified", unavailable_dump
    assert "font-manager-dump-unavailable" in unavailable_dump["reasons"]
    assert "dynamic-family-unconfirmed" in unavailable_dump["reasons"]
    assert "verified-by-visible-mounts" in unavailable_dump["reasons"]

    bad_mounts = [dict(mounts[0], status="mismatch")]
    mismatch = verifier.verify(
        payload,
        overlay,
        "Family google-sans-text file=/system/fonts/LuoShuSlot-abc.ttf",
        bad_mounts,
        "DemoFont",
        {"state": "installed"},
    )
    assert mismatch["state"] == "failed"
    assert "visible-font-hash-mismatch" in mismatch["reasons"]
    print(json.dumps(verified["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
