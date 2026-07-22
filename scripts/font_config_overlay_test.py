#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from font_config_overlay import parse_xml, rewrite_tree

SAMPLE = """<?xml version='1.0' encoding='utf-8'?>
<familyset version="23">
  <family name="sans-serif" supportedAxes="wght,ital">
    <font weight="100" style="normal" index="0">SysFont-Regular.ttf<axis tag="wght" stylevalue="100"/></font>
    <font weight="450" style="normal">SysFont-Regular.ttf</font>
  </family>
  <alias name="sans" to="sans-serif" weight="400"/>
  <family name="sys-sans-en"><font weight="400">SysSans-En-Regular.ttf</font></family>
  <family name="monospace"><font weight="400">DroidSansMono.ttf</font></family>
  <family name="serif"><font weight="400">NotoSerif-Regular.ttf</font></family>
  <family name="material-icons"><font weight="400">MaterialIcons.ttf</font></family>
  <family lang="und-Arab"><font weight="400">NotoNaskhArabic-Regular.ttf</font></family>
  <family name="mitype-clock"><font weight="400">Mitype2019.ttf</font></family>
</familyset>
"""


def child_text(family: ET.Element) -> list[str]:
    return [(font.text or "").strip() for font in family if font.tag == "font"]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-font-config-") as directory:
        source = Path(directory) / "fonts.xml"
        source.write_text(SAMPLE, encoding="utf-8")
        tree = parse_xml(source)
        report = rewrite_tree(tree, "LuoShu", "LuoShuMono")
        assert report["changed_fonts"] == 4, report
        assert report["changed_mono_families"] == ["monospace"], report

        root = tree.getroot()
        families = {family.attrib.get("name", ""): family for family in root if family.tag == "family"}
        sans = families["sans-serif"]
        assert "supportedAxes" not in sans.attrib
        assert child_text(sans) == ["LuoShu-100.ttf", "LuoShu-400.ttf"]
        assert "index" not in list(sans)[0].attrib
        assert not list(list(sans)[0])
        assert child_text(families["sys-sans-en"]) == ["LuoShu-400.ttf"]

        # Named monospace families use the fixed-width derivative so terminal/install
        # pages no longer mix LuoShu Chinese with ROM English and digits.
        assert child_text(families["monospace"]) == ["LuoShuMono-400.ttf"]
        assert child_text(families["serif"]) == ["NotoSerif-Regular.ttf"]
        assert child_text(families["material-icons"]) == ["MaterialIcons.ttf"]
        assert child_text(families["mitype-clock"]) == ["Mitype2019.ttf"]

        anonymous = next(family for family in root if family.tag == "family" and "name" not in family.attrib)
        assert child_text(anonymous) == ["NotoNaskhArabic-Regular.ttf"]
        alias = next(element for element in root if element.tag == "alias")
        assert alias.attrib == {"name": "sans", "to": "sans-serif", "weight": "400"}

    print("Font configuration overlay tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
