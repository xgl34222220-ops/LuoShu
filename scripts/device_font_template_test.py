#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_template as mod


def find_fixture_font() -> Path | None:
    preferred = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    )
    for raw in preferred:
        path = Path(raw)
        if path.is_file():
            return path
    root = Path("/usr/share/fonts")
    if root.is_dir():
        for path in root.rglob("*.ttf"):
            if path.is_file():
                return path
    return None


def postscript_name(path: Path) -> str:
    font = TTFont(str(path), lazy=True, recalcTimestamp=False)
    try:
        for record in font["name"].names:
            if record.nameID != 6:
                continue
            value = record.toUnicode().strip()
            if value:
                return value
    finally:
        font.close()
    raise AssertionError(f"fixture font has no PostScript name: {path}")


def source_metrics(path: Path) -> tuple[int, int]:
    font = TTFont(str(path), lazy=True, recalcTimestamp=False)
    try:
        return int(font["hhea"].ascent), int(font["hhea"].descent)
    finally:
        font.close()


def main() -> None:
    fixture = find_fixture_font()
    if fixture is None:
        print(json.dumps({"status": "skipped", "reason": "no system TTF fixture"}))
        return
    ps_name = postscript_name(fixture)
    expected_ascent, expected_descent = source_metrics(fixture)

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        system_font = root / "system/fonts/Roboto-Regular.ttf"
        dynamic_font = root / "data/fonts/files/hash/GoogleSans-Regular.ttf"
        emoji_font = root / "system/fonts/NotoColorEmoji.ttf"
        for target in (system_font, dynamic_font, emoji_font):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fixture, target)

        system_xml = root / "system/etc/fonts.xml"
        system_xml.parent.mkdir(parents=True, exist_ok=True)
        system_xml.write_text(
            """<?xml version='1.0' encoding='utf-8'?>
<familyset>
  <family name='sans-serif'><font weight='400' style='normal'>Roboto-Regular.ttf</font></family>
  <family name='emoji-family'><font weight='400' style='normal'>NotoColorEmoji.ttf</font></family>
</familyset>
""",
            encoding="utf-8",
        )
        data_xml = root / "data/fonts/config/config.xml"
        data_xml.parent.mkdir(parents=True, exist_ok=True)
        data_xml.write_text(
            f"""<?xml version='1.0' encoding='utf-8'?>
<fontConfig>
  <lastModifiedDate value='1'/>
  <updatedFontDir value='hash'/>
  <family name='google-sans'><font name='{ps_name}' weight='400' style='normal'/></family>
</fontConfig>
""",
            encoding="utf-8",
        )

        payload = mod.build_template(
            [system_xml, data_xml],
            [root / "data/fonts/files", root / "system/fonts"],
            "fixture-build",
        )
        assert payload["schema"] == "device-font-template-v1"
        assert payload["summary"]["slots"] == 3, payload["summary"]
        assert payload["summary"]["resolved"] == 3, payload
        slots = {(slot["familyNormalized"], slot["weight"]): slot for slot in payload["slots"]}

        ui = slots[("sans-serif", 400)]
        assert ui["replaceable"] is True
        assert "global-ui" in ui["roles"]
        assert ui["font"]["metrics"]["hheaAscent"] == expected_ascent
        assert ui["font"]["metrics"]["hheaDescent"] == expected_descent
        assert ui["font"]["probes"]["digits"]["hits"] > 0

        dynamic = slots[("google-sans", 400)]
        assert "dynamic" in dynamic["roles"]
        assert dynamic["resolvedPath"].endswith("GoogleSans-Regular.ttf"), dynamic

        emoji = slots[("emoji-family", 400)]
        assert emoji["replaceable"] is False
        assert "protected" in emoji["roles"]
        print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
