#!/usr/bin/env python3
"""Validate coverage JSON and emit the five integer fields used by shell policy."""

from __future__ import annotations

import json
import sys

MAX_INPUT_BYTES = 64 * 1024
COVERAGE_FIELDS = ("cjk", "latin", "digits", "punctuation")


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def integer(value: object, maximum: int) -> int:
    # bool is an int subclass; accepting true as 1 would silently alter coverage.
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid coverage integer")
    return value


def parse_fields(raw: bytes) -> tuple[int, int, int, int, int]:
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("coverage JSON exceeds limit")
    root = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant)
    if not isinstance(root, dict) or not isinstance(root.get("coverage"), dict):
        raise ValueError("coverage object missing")
    # Read only the actual top-level field and coverage object. Message strings,
    # similarly named nested fields and extra diagnostic fields cannot substitute.
    han = integer(root.get("coreHan"), 0x110000)
    coverage = root["coverage"]
    values = [integer(coverage.get(key), 100) for key in COVERAGE_FIELDS]
    return han, values[0], values[1], values[2], values[3]


def main() -> int:
    try:
        values = parse_fields(sys.stdin.buffer.read(MAX_INPUT_BYTES + 1))
    except (ValueError, UnicodeError, RecursionError):
        print("Invalid font coverage response", file=sys.stderr)
        return 2
    print(" ".join(map(str, values)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
