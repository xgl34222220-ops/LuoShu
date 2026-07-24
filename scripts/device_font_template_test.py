#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_template as mod


def ref(
    family: str,
    declared: str,
    *,
    attrs: dict[str, str] | None = None,
    dynamic: bool = False,
) -> mod.FontRef:
    return mod.FontRef(
        family=family,
        family_attrs=attrs or {},
        declared=declared,
        postscript_name="GoogleSansText-Regular" if dynamic else "",
        weight=400,
        style="normal",
        index=0,
        axes="",
        source_xml=Path("/data/fonts/config/config.xml" if dynamic else "/system/etc/fonts.xml"),
        dynamic=dynamic,
    )


def main() -> None:
    assert mod.normalize("Google_Sans Text") == "google-sans-text"
    assert mod.nearest_weight("401") == 400
    assert mod.nearest_weight("749") == 700
    assert mod.nearest_weight("invalid") == 400

    ui = ref("sans-serif", "Roboto-Regular.ttf")
    ui_roles = mod.classify_roles(ui, Path("/system/fonts/Roboto-Regular.ttf"))
    assert ui_roles == ["global-ui"], ui_roles

    clock = ref("clock-family", "Clockopia.ttf")
    clock_roles = mod.classify_roles(clock, Path("/system/fonts/Clockopia.ttf"))
    assert "clock" in clock_roles
    assert "protected" not in clock_roles

    emoji = ref("emoji-family", "NotoColorEmoji.ttf", attrs={"lang": "und-Zsye"})
    emoji_roles = mod.classify_roles(emoji, Path("/system/fonts/NotoColorEmoji.ttf"))
    assert "fallback" in emoji_roles
    assert "protected" in emoji_roles

    dynamic = ref("google_sans_text", "", dynamic=True)
    dynamic_roles = mod.classify_roles(
        dynamic,
        Path("/data/fonts/files/hash/GoogleSansText-Regular.ttf"),
    )
    assert "dynamic" in dynamic_roles
    assert "global-ui" in dynamic_roles
    assert "protected" not in dynamic_roles

    assert mod.partition_root_for_xml(Path("/system/etc/fonts.xml")) == Path("/system")
    print(
        json.dumps(
            {
                "status": "ok",
                "ui": ui_roles,
                "clock": clock_roles,
                "emoji": emoji_roles,
                "dynamic": dynamic_roles,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
