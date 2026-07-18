#!/usr/bin/env python3
"""Read variable-axis capability for the LuoShu native App without modifying a font."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont


def main() -> int:
    path = Path(sys.argv[1])
    if not path.is_file():
        raise FileNotFoundError(path)
    kwargs: dict[str, object] = {"lazy": True, "recalcTimestamp": False}
    if path.read_bytes()[:4] == b"ttcf":
        kwargs["fontNumber"] = 0
    font = TTFont(str(path), **kwargs)
    try:
        axes = []
        if "fvar" in font:
            for axis in font["fvar"].axes:
                axes.append(
                    {
                        "tag": str(axis.axisTag),
                        "min": float(axis.minValue),
                        "default": float(axis.defaultValue),
                        "max": float(axis.maxValue),
                    }
                )
        weight = next((axis for axis in axes if axis["tag"] == "wght"), None)
        result = {
            "status": "ok",
            "variable": bool(axes),
            "hasWeight": weight is not None,
            "weight": weight,
            "axes": axes,
        }
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    finally:
        font.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False, separators=(",", ":")))
        raise SystemExit(1)
