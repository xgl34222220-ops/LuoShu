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


def rendered(ratio: float = 1.0) -> dict:
    comparable = 12
    return {
        "status": "ok",
        "matched": round(comparable * ratio),
        "comparable": comparable,
        "ratio": ratio,
        "missingActual": [],
        "missingExpected": [],
        "path": "/system/fonts/LuoShuSlot-abc.ttf",
    }


def main() -> None:
    payload, overlay, mounts = fixture()
    verified = verifier.verify(
        payload,
        overlay,
        "Family google-sans-text file=/system/fonts/LuoShuSlot-abc.ttf LuoShuSlot-google-sans-text-400",
        mounts,
        rendered(),
        "DemoFont",
        {"state": "installed", "templateKey": "trusted"},
    )
    assert verified["state"] == "verified", verified
    assert verified["mode"] == "aligned"
    assert verified["summary"]["dynamicFamilyHits"] == 1
    assert "android-renderer-confirmed-generated-font" in verified["reasons"]

    # Some OEM FontManager dumps omit or rename dynamic families. A successful
    # renderer comparison is stronger evidence and must not trigger rollback.
    missing_dynamic = verifier.verify(
        payload,
        overlay,
        "file=/system/fonts/LuoShuSlot-abc.ttf",
        mounts,
        rendered(),
        "DemoFont",
        {"state": "installed"},
    )
    assert missing_dynamic["state"] == "verified", missing_dynamic
    assert "dynamic-family-unconfirmed" in missing_dynamic["reasons"]
    assert "android-renderer-confirmed-generated-font" in missing_dynamic["reasons"]

    unavailable_dump = verifier.verify(
        payload,
        overlay,
        "",
        mounts,
        {"status": "unavailable", "reason": "luoshu-app-not-installed"},
        "DemoFont",
        {"state": "installed"},
    )
    assert unavailable_dump["state"] == "unverified", unavailable_dump
    assert unavailable_dump["mode"] == "mount-only", unavailable_dump
    assert "font-manager-dump-unavailable" in unavailable_dump["reasons"]
    assert "dynamic-family-unconfirmed" in unavailable_dump["reasons"]
    assert "visible-mounts-do-not-prove-font-selection" in unavailable_dump["reasons"]

    renderer_mismatch = verifier.verify(
        payload,
        overlay,
        "Family google-sans-text file=/system/fonts/LuoShuSlot-abc.ttf",
        mounts,
        rendered(0.0),
        "DemoFont",
        {"state": "installed"},
    )
    assert renderer_mismatch["state"] == "failed", renderer_mismatch
    assert "android-renderer-does-not-match-generated-font" in renderer_mismatch["reasons"]

    bad_mounts = [dict(mounts[0], status="mismatch")]
    mismatch = verifier.verify(
        payload,
        overlay,
        "Family google-sans-text file=/system/fonts/LuoShuSlot-abc.ttf",
        bad_mounts,
        rendered(),
        "DemoFont",
        {"state": "installed"},
    )
    assert mismatch["state"] == "failed"
    assert "visible-font-hash-mismatch" in mismatch["reasons"]

    # Host-only CI does not ship the module's embedded fontTools. Coverage
    # inspection becomes unavailable rather than crashing the complete verifier.
    previous_ttfont = verifier._TTFont
    verifier._TTFont = None
    try:
        coverage_payload = dict(payload)
        coverage_payload["slots"] = [dict(payload["slots"][0], roles=["global-ui"])]
        host_result = verifier.verify(
            coverage_payload,
            overlay,
            "Family google-sans-text file=/system/fonts/LuoShuSlot-abc.ttf",
            mounts,
            rendered(),
            "DemoFont",
            {"state": "installed"},
        )
        assert host_result["state"] == "verified", host_result
        assert host_result["summary"]["coverageProbeUnavailable"] is True
        assert "runtime-coverage-probe-unavailable" in host_result["reasons"]
    finally:
        verifier._TTFont = previous_ttfont

    print(json.dumps(verified["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
