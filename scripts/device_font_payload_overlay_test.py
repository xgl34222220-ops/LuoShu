#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_payload_overlay as overlay


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def slot(
    source_xml: Path,
    family: str,
    declared: str,
    generated: str | None,
    *,
    postscript: str = "",
    weight: int = 400,
    roles: list[str] | None = None,
    replaceable: bool = True,
    status: str = "ready",
) -> dict:
    result = {
        "family": family,
        "familyNormalized": overlay.normalize(family),
        "familyAttributes": {},
        "sourceXml": str(source_xml),
        "declared": declared,
        "postScriptName": postscript,
        "weight": weight,
        "style": "normal",
        "index": 0,
        "axes": "",
        "roles": roles or ["global-ui"],
        "replaceable": replaceable,
        "stockPath": declared,
        "planStatus": status,
        "planReason": "",
    }
    if generated:
        result["generatedFile"] = generated
        result["generatedBytes"] = 4096
        result["signature"] = generated
    return result


def family_names(path: Path) -> list[str]:
    tree = ET.parse(path)
    return [
        node.attrib.get("name", "")
        for node in tree.getroot().iter()
        if node.tag.rsplit("}", 1)[-1] == "family"
    ]


def font_texts(path: Path) -> list[str]:
    tree = ET.parse(path)
    return [
        (node.text or "").strip()
        for node in tree.getroot().iter()
        if node.tag.rsplit("}", 1)[-1] == "font"
    ]


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        system_primary = root / "system/etc/font_fallback.xml"
        system_legacy = root / "system/etc/fonts.xml"
        product_xml = root / "product/etc/fonts_customization.xml"
        dynamic_xml = root / "data/fonts/config/config.xml"
        write(
            system_primary,
            """<?xml version='1.0' encoding='utf-8'?>
<familyset>
  <family name='sans-serif'><font weight='400' style='normal'>Roboto-Regular.ttf</font></family>
  <family name='emoji-family' lang='und-Zsye'><font weight='400' style='normal'>NotoColorEmoji.ttf</font></family>
</familyset>
""",
        )
        write(
            system_legacy,
            """<?xml version='1.0' encoding='utf-8'?>
<familyset>
  <family name='sans-serif'><font weight='400' style='normal'>Roboto-Regular.ttf</font></family>
</familyset>
""",
        )
        write(
            product_xml,
            """<?xml version='1.0' encoding='utf-8'?>
<familyset>
  <family name='mi-sans'><font weight='400' style='normal'>MiSans-Regular.ttf</font></family>
</familyset>
""",
        )
        write(
            dynamic_xml,
            """<?xml version='1.0' encoding='utf-8'?>
<fontConfig>
  <lastModifiedDate value='123'/>
  <updatedFontDir value='hash-google'/>
  <family name='google-sans'><font name='GoogleSans-Regular' weight='400' style='normal'/></family>
  <family name='google-sans-text'><font name='GoogleSansText-Regular' weight='400' style='normal'/></family>
  <family name='emoji-dynamic'><font name='NotoColorEmoji' weight='400' style='normal'/></family>
</fontConfig>
""",
        )

        payload_root = root / "payload"
        fonts = payload_root / "fonts"
        fonts.mkdir(parents=True)
        generated = {
            "LuoShuSlot-ui-400.ttf",
            "LuoShuSlot-mi-400.ttf",
            "LuoShuSlot-google-400.ttf",
        }
        for name in generated:
            (fonts / name).write_bytes((name.encode("utf-8") + b"\0") * 256)

        slots = [
            slot(system_primary, "sans-serif", "Roboto-Regular.ttf", "LuoShuSlot-ui-400.ttf"),
            slot(system_legacy, "sans-serif", "Roboto-Regular.ttf", "LuoShuSlot-ui-400.ttf"),
            slot(product_xml, "mi-sans", "MiSans-Regular.ttf", "LuoShuSlot-mi-400.ttf"),
            slot(
                dynamic_xml,
                "google-sans",
                "",
                "LuoShuSlot-google-400.ttf",
                postscript="GoogleSans-Regular",
                roles=["dynamic", "global-ui"],
            ),
            slot(
                dynamic_xml,
                "google-sans-text",
                "",
                None,
                postscript="GoogleSansText-Regular",
                roles=["dynamic", "global-ui"],
                status="unsafe",
            ),
            slot(
                dynamic_xml,
                "emoji-dynamic",
                "",
                None,
                postscript="NotoColorEmoji",
                roles=["dynamic", "protected", "fallback"],
                replaceable=False,
                status="skipped",
            ),
        ]
        template = {
            "schema": "device-font-template-v1",
            "fingerprint": "overlay-fixture-rom",
            "xml": [str(system_primary), str(system_legacy), str(product_xml), str(dynamic_xml)],
            "slots": [],
        }
        payload = {
            "schema": "device-font-payload-v1",
            "deviceFingerprint": "overlay-fixture-rom",
            "slots": slots,
        }
        (payload_root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

        original_dynamic = overlay.is_dynamic_path
        original_partition = overlay.partition_for_xml
        original_primary = overlay.PRIMARY_SYSTEM_XMLS
        try:
            overlay.is_dynamic_path = lambda value: "/data/fonts/" in value.replace("\\", "/")
            overlay.partition_for_xml = lambda value: (
                "product" if "/product/" in value.replace("\\", "/") else "system"
            )
            overlay.PRIMARY_SYSTEM_XMLS = (str(system_primary), str(system_legacy))
            output = root / "overlay"
            report = overlay.render_overlay(template, payload, payload_root, output)
        finally:
            overlay.is_dynamic_path = original_dynamic
            overlay.partition_for_xml = original_partition
            overlay.PRIMARY_SYSTEM_XMLS = original_primary

        assert report["summary"] == {
            "mappedSlots": 4,
            "rewrittenSlots": 3,
            "dynamicSlots": 1,
            "dynamicInjectedFonts": 2,
            "uniqueCopiedFonts": 3,
            "xmlOutputs": 3,
            "incompleteDynamicFamilies": 1,
        }, report["summary"]
        assert report["incompleteDynamicFamilies"] == ["google-sans-text"]

        output_primary = output / str(system_primary).lstrip("/")
        output_legacy = output / str(system_legacy).lstrip("/")
        output_product = output / str(product_xml).lstrip("/")
        output_dynamic = output / "dynamic/data-fonts-config.xml"
        assert output_primary.is_file()
        assert output_legacy.is_file()
        assert output_product.is_file()
        assert output_dynamic.is_file()

        for path in (output_primary, output_legacy):
            names = family_names(path)
            texts = font_texts(path)
            assert "google-sans" in names
            assert "LuoShuSlot-ui-400.ttf" in texts
            assert "LuoShuSlot-google-400.ttf" in texts
        assert "NotoColorEmoji.ttf" in font_texts(output_primary)
        assert "LuoShuSlot-mi-400.ttf" in font_texts(output_product)

        dynamic_names = family_names(output_dynamic)
        assert "google-sans" not in dynamic_names
        assert "google-sans-text" in dynamic_names
        assert "emoji-dynamic" in dynamic_names
        dynamic_root = ET.parse(output_dynamic).getroot()
        assert any(node.tag.rsplit("}", 1)[-1] == "updatedFontDir" for node in dynamic_root.iter())

        assert (output / "system/fonts/LuoShuSlot-ui-400.ttf").is_file()
        assert (output / "system/fonts/LuoShuSlot-google-400.ttf").is_file()
        assert (output / "product/fonts/LuoShuSlot-mi-400.ttf").is_file()
        assert report["dynamicMounts"] == [
            {"source": "dynamic/data-fonts-config.xml", "target": str(dynamic_xml)}
        ]
        print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
