#!/usr/bin/env python3
"""Read variable-axis capability for the LuoShu native App without modifying a font."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from font_metadata import axes as font_axes, is_collection


def read_axis_info(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    kwargs: dict[str, object] = {"lazy": True, "recalcTimestamp": False}
    # Keep TTFont lazy: collection detection needs four bytes, not a full CJK
    # font allocation before the actual axis/name tables can be read.
    if is_collection(path):
        kwargs["fontNumber"] = 0
    font = TTFont(str(path), **kwargs)
    try:
        axes = font_axes(font)
        tags = set()
        for index, axis in enumerate(axes):
            tag = axis["tag"]
            minimum, default, maximum = (axis[key] for key in ("min", "default", "max"))
            if (len(tag) != 4 or any(not 32 <= ord(char) <= 126 for char in tag)
                    or tag in tags or not all(math.isfinite(value) for value in (minimum, default, maximum))
                    or not minimum <= default <= maximum):
                raise ValueError(f"字体轴 {tag} 的定义无效")
            tags.add(tag)
            axis["hidden"] = bool(font["fvar"].axes[index].flags & 1)
        weight = next((axis for axis in axes if axis["tag"] == "wght"), None)
        result = {
            "status": "ok",
            "variable": bool(axes),
            "hasWeight": weight is not None,
            "weight": weight,
            "axes": axes,
        }
        return result
    finally:
        font.close()


def main() -> int:
    result = read_axis_info(Path(sys.argv[1]))
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False, separators=(",", ":")))
        raise SystemExit(1)
