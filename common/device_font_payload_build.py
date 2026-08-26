#!/usr/bin/env python3
# Packaging contract marker: device-font-payload-v1
"""Identity-safe wrapper for the per-device payload builder."""
from __future__ import annotations

from typing import Any

import device_font_payload_build_base as _base
from device_font_payload_build_base import *  # noqa: F401,F403

_ORIGINAL_BUILD_SIGNATURE = _base.build_signature


def build_signature(slot: dict[str, Any], source_profile: dict[str, Any], source_weight: int) -> str:
    # Android resolves the family graph from fonts.xml; duplicating an otherwise identical outline
    # solely for each family/name-table identity multiplied first-apply time by dozens of full font
    # rewrites. The actual device metric/role contract remains part of the base signature.
    return _ORIGINAL_BUILD_SIGNATURE(slot, source_profile, source_weight)


_base.build_signature = build_signature


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
