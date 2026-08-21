#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import composite_font  # noqa: E402


class Value:
    def __init__(self, **values):
        self.__dict__.update(values)


class NameRecord:
    def __init__(self, name_id: int, value: str):
        self.nameID = name_id
        self.value = value

    def toUnicode(self) -> str:
        return self.value


def fake_font(*, os2=None, names=(), mac_style=0):
    font = {
        "name": Value(names=[NameRecord(name_id, value) for name_id, value in names]),
        "head": Value(macStyle=mac_style),
    }
    if os2 is not None:
        font["OS/2"] = Value(usWeightClass=os2)
    return font


assert composite_font._font_weight(fake_font(os2=615, names=[(17, "Bold")])) == 615
assert composite_font._font_weight(fake_font(os2=0, names=[(17, "Extra Bold")])) == 800
assert composite_font._font_weight(fake_font(os2=400, names=[(17, "Extra Bold")])) == 800
assert composite_font._font_weight(fake_font(names=[(2, "DemiBold Italic")])) == 600
assert composite_font._font_weight(fake_font(mac_style=1)) == 700
assert composite_font._font_weight(fake_font()) == 400

assert composite_font._safe_baseline_shift([0, 2, 4], 1.0, 1000) == -2.0
assert composite_font._safe_baseline_shift([0, -200, 0], 1.0, 1000) == 0.0
assert composite_font._safe_baseline_shift([-1000, -1001], 1.0, 1000) == 250.0
assert composite_font._safe_baseline_shift([10], 1.0, 1000) == 0.0

print("Composite weight and baseline safeguard tests passed.")
