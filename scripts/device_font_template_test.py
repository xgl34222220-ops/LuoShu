#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_template as mod


def by_family(refs: list[mod.FontRef]) -> dict[str, mod.FontRef]:
    return {mod.normalize(ref.family): ref for ref in refs}


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        system_xml = root / "system/etc/fonts.xml"
        system_xml.parent.mkdir(parents=True, exist_ok=True)
        system_xml.write_text(
            """<?xml version='1.0' encoding='utf-8'?>
<familyset>
  <family name='sans-serif'>
    <font weight='401' style='normal'>Roboto-Regular.ttf</font>
  </family>
  <family name='clock-family'>
    <font weight='500' style='normal'>Clockopia.ttf</font>
  </family>
  <family name='emoji-family' lang='und-Zsye'>
    <font weight='400' style='normal'>NotoColorEmoji.ttf</font>
  </family>
  <family name='language-fallback' lang='ar'>
    <font weight='400' style='normal'>NotoNaskhArabic-Regular.ttf</font>
  </family>
</familyset>
""",
            encoding="utf-8",
        )
        data_xml = root / "data/fonts/config/config.xml"
        data_xml.parent.mkdir(parents=True, exist_ok=True)
        data_xml.write_text(
            """<?xml version='1.0' encoding='utf-8'?>
<fontConfig>
  <lastModifiedDate value='1'/>
  <updatedFontDir value='hash'/>
  <family name='google_sans_text'>
    <font name='GoogleSansText-Regular' weight='400' style='normal'/>
  </family>
</fontConfig>
""",
            encoding="utf-8",
        )

        system = by_family(mod.parse_xml(system_xml))
        dynamic = by_family(mod.parse_xml(data_xml))
        assert set(system) == {
            "sans-serif",
            "clock-family",
            "emoji-family",
            "language-fallback",
        }
        assert set(dynamic) == {"google-sans-text"}
        assert mod.partition_root_for_xml(system_xml) == root / "system"
        assert mod.nearest_weight("401") == 400
        assert mod.nearest_weight("749") == 700
        assert mod.nearest_weight("invalid") == 400

        ui_roles = mod.classify_roles(system["sans-serif"], Path("/system/fonts/Roboto-Regular.ttf"))
        assert "global-ui" in ui_roles
        assert "protected" not in ui_roles

        clock_roles = mod.classify_roles(system["clock-family"], Path("/system/fonts/Clockopia.ttf"))
        assert "clock" in clock_roles
        assert "protected" not in clock_roles

        emoji_roles = mod.classify_roles(system["emoji-family"], Path("/system/fonts/NotoColorEmoji.ttf"))
        assert "protected" in emoji_roles
        assert "fallback" in emoji_roles

        fallback_roles = mod.classify_roles(
            system["language-fallback"],
            Path("/system/fonts/NotoNaskhArabic-Regular.ttf"),
        )
        assert "fallback" in fallback_roles

        dynamic_ref = dynamic["google-sans-text"]
        assert dynamic_ref.dynamic is True
        assert dynamic_ref.postscript_name == "GoogleSansText-Regular"
        dynamic_roles = mod.classify_roles(dynamic_ref, Path("/data/fonts/files/hash/GoogleSansText-Regular.ttf"))
        assert "dynamic" in dynamic_roles
        assert "global-ui" in dynamic_roles
        assert "protected" not in dynamic_roles

        print(
            json.dumps(
                {
                    "status": "ok",
                    "systemFamilies": len(system),
                    "dynamicFamilies": len(dynamic),
                    "protected": ["emoji-family", "language-fallback"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
