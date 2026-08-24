#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
import font_config_overlay as overlay
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

        assert child_text(families["monospace"]) == ["LuoShuMono-400.ttf"]
        assert child_text(families["serif"]) == ["NotoSerif-Regular.ttf"]
        assert child_text(families["material-icons"]) == ["MaterialIcons.ttf"]
        assert child_text(families["mitype-clock"]) == ["Mitype2019.ttf"]

        anonymous = next(family for family in root if family.tag == "family" and "name" not in family.attrib)
        assert child_text(anonymous) == ["NotoNaskhArabic-Regular.ttf"]
        alias = next(element for element in root if element.tag == "alias")
        assert alias.attrib == {"name": "sans", "to": "sans-serif", "weight": "400"}

    # UI text families should not depend exclusively on a vendor allow-list. `ui-sans-serif` is
    # explicitly included because a naive serif guard would otherwise regress this standard UI name.
    for name in (
        "sans-serif", "sans-serif-condensed", "ui-sans-serif", "google-sans-text", "misans",
        "mipro", "sysfont", "op-sans-en", "oplus-os-ui", "harmonyos-sans", "honor-sans",
        "hihonor-sans", "magic-sans", "vivo-sans", "iqoo-sans", "flyme-sans", "meizu-sans",
        "nubia-sans", "zte-sans", "redmagic-sans", "lenovo-sans", "motorola-sans", "asus-sans",
        "sharp-sans", "sony-sans", "tcl-sans", "transsion-sans", "itel-sans", "oneui-sans",
        "samsung-sans", "nothing-sans", "noto-sans", "noto-sans-cjk", "opposans", "vivosans",
        "flymesans", "roboto", "system-ui",
    ):
        assert overlay.is_safe_family(name), f"UI family not recognised: {name}"

    for name in (
        "monospace", "roboto-mono", "noto-sans-mono", "droid-sans-mono",
        "sans-serif-monospace", "ui-monospace",
    ):
        assert overlay.is_safe_mono_family(name), f"monospace family not recognised: {name}"

    for name in (
        "serif", "noto-serif", "source-serif", "serif-condensed", "noto-color-emoji",
        "material-icons", "material-symbols-outlined", "mitype-clock", "miui-clock", "ndot",
        "android-clock", "noto-sans-symbols", "noto-sans-math", "noto-emoji", "fallback",
        "legacy-sans", "misans-serif", "oplus-sans-serif", "honor-serif-display",
    ):
        assert not overlay.is_safe_family(name), f"protected family was rewritten: {name}"
        assert not overlay.is_safe_mono_family(name), f"protected family was rewritten as mono: {name}"

    # TTC-backed UI families can be redirected safely by XML and must lose the collection index;
    # serif TTC faces remain untouched.
    with tempfile.TemporaryDirectory() as tmp:
        ttc_doc = Path(tmp) / "ttc.xml"
        ttc_doc.write_text(
            '<familyset>'
            '<family name="ui-sans-serif">'
            '<font weight="400" style="normal" index="1">NotoSansCJK-Regular.ttc</font>'
            '</family>'
            '<family name="monospace">'
            '<font weight="400" style="normal">DroidSansMono.ttf</font>'
            '</family>'
            '<family name="serif">'
            '<font weight="400" style="normal" index="0">NotoSerifCJK-Regular.ttc</font>'
            '</family>'
            '</familyset>',
            encoding="utf-8",
        )
        tree = parse_xml(ttc_doc)
        rewrite_tree(tree, "LuoShu", "LuoShuMono")
        families = {f.attrib.get("name"): f for f in tree.getroot() if f.tag == "family"}
        sans_font = list(families["ui-sans-serif"])[0]
        assert sans_font.text == "LuoShu-400.ttf"
        assert "index" not in sans_font.attrib
        assert child_text(families["monospace"]) == ["LuoShuMono-400.ttf"]
        serif_font = list(families["serif"])[0]
        assert serif_font.text == "NotoSerifCJK-Regular.ttc"
        assert serif_font.attrib.get("index") == "0"

    print("Font configuration overlay tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
