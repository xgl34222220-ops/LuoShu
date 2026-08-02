#!/usr/bin/env python3
"""Identity-safe wrapper for the per-device payload builder."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import device_font_payload_build_base as _base
from device_font_payload_build_base import *  # noqa: F401,F403

_ORIGINAL_BUILD_SIGNATURE = _base.build_signature


def build_signature(slot: dict[str, Any], source_profile: dict[str, Any], source_weight: int) -> str:
    original = _ORIGINAL_BUILD_SIGNATURE(slot, source_profile, source_weight)
    identity = {
        "family": slot.get("family", ""),
        "familyNormalized": slot.get("familyNormalized", ""),
        "familyAttributes": slot.get("familyAttributes", {}),
        "declared": slot.get("declared", ""),
        "postScriptName": slot.get("postScriptName", ""),
        "sourceXml": slot.get("sourceXml", ""),
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{original}\0{encoded}".encode("utf-8")).hexdigest()


# The base builder resolves this global for every slot. Including family identity in
# the signature prevents two visually equivalent slots from sharing one generated
# file whose internal family name belongs to only the first slot.
_base.build_signature = build_signature


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
