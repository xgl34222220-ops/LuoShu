#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_payload_build as payload_builder
import device_font_template as template_engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", required=True, type=Path)
    return parser.parse_args()


def slot(
    family: str,
    source_xml: str,
    profile: dict,
    *,
    weight: int = 400,
    roles: list[str] | None = None,
    replaceable: bool = True,
) -> dict:
    return {
        "family": family,
        "familyNormalized": family,
        "familyAttributes": {},
        "sourceXml": source_xml,
        "declared": f"{family}.ttf",
        "postScriptName": "",
        "weight": weight,
        "style": "normal",
        "index": 0,
        "axes": "",
        "roles": roles or ["global-ui"],
        "replaceable": replaceable,
        "resolvedPath": f"/system/fonts/{family}.ttf",
        "font": profile,
    }


def main() -> None:
    args = parse_args()
    source_profile = template_engine.inspect_font(args.font, -1, hash_fonts=True)
    assert source_profile["probes"]["digits"]["hits"] >= 10

    ui_profile = copy.deepcopy(source_profile)
    ui_profile["path"] = "/system/fonts/Roboto-Regular.ttf"
    clock_profile = copy.deepcopy(source_profile)
    clock_profile["path"] = "/system/fonts/Clockopia.ttf"
    for key in ("yMin", "yMax", "centerY", "yMinP25", "yMaxP75"):
        if clock_profile["probes"]["digits"].get(key) is not None:
            clock_profile["probes"]["digits"][key] += 36.0
    clock_profile["probes"]["digits"]["advance"] += 20.0

    template = {
        "schema": "device-font-template-v1",
        "captureRevision": 2,
        "fingerprint": "payload-fixture-rom",
        "slots": [
            slot("sans-serif", "/system/etc/fonts.xml", ui_profile),
            # Different semantic family roles with the same effective outline
            # contract must share one generated file.
            slot(
                "sans-serif",
                "/product/etc/fonts.xml",
                copy.deepcopy(ui_profile),
                roles=["named-ui"],
            ),
            slot("clock-family", "/system/etc/fonts.xml", clock_profile, weight=700, roles=["clock"]),
            slot(
                "emoji-family",
                "/system/etc/fonts.xml",
                copy.deepcopy(ui_profile),
                roles=["protected", "fallback"],
                replaceable=False,
            ),
        ],
    }

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source_dir = root / "sources"
        output_dir = root / "payload"
        source_dir.mkdir()
        shutil.copyfile(args.font, source_dir / "LuoShu-400.ttf")
        shutil.copyfile(args.font, source_dir / "LuoShu-700.ttf")

        payload = payload_builder.build_payload(
            template,
            source_dir,
            "LuoShu",
            output_dir,
            output_dir / "manifest.json",
        )
        assert payload["summary"] == {
            "slots": 4,
            "mapped": 3,
            "uniqueFonts": 2,
            "deduplicatedReferences": 1,
            "unsafe": 0,
            "unresolved": 0,
            "skipped": 1,
            "failures": 0,
        }, payload["summary"]
        font_files = sorted((output_dir / "fonts").glob("*.ttf"))
        assert len(font_files) == 2, font_files
        manifest_before = (output_dir / "manifest.json").read_bytes()
        files_before = {path.name: path.read_bytes() for path in font_files}

        original_build_slot = payload_builder.slot_builder.build_slot
        try:
            def fail_build(*_args, **_kwargs):
                raise RuntimeError("fixture failure")

            payload_builder.slot_builder.build_slot = fail_build
            changed = copy.deepcopy(template)
            changed["slots"][0]["font"]["metrics"]["hheaAscent"] += 1
            changed["slots"][1]["font"]["metrics"]["hheaAscent"] += 1
            try:
                payload_builder.build_payload(
                    changed,
                    source_dir,
                    "LuoShu",
                    output_dir,
                    output_dir / "manifest.json",
                )
            except payload_builder.PayloadError as exc:
                assert "fixture failure" in str(exc)
            else:
                raise AssertionError("failed batch unexpectedly replaced the payload")
        finally:
            payload_builder.slot_builder.build_slot = original_build_slot

        assert (output_dir / "manifest.json").read_bytes() == manifest_before
        for name, content in files_before.items():
            assert (output_dir / "fonts" / name).read_bytes() == content

        # Canonical install inventory may contain a verified UI slot that is not
        # represented in the XML template. It must be consumed by the final
        # aligned builder, while TTC containers remain stock with an explicit reason.
        stock_root = root / "stock"
        hidden_stock = stock_root / "system_ext/fonts/HiddenUi-Regular.ttf"
        hidden_stock.parent.mkdir(parents=True)
        shutil.copyfile(args.font, hidden_stock)
        inventory = {
            "buildKey": "inventory-fixture",
            "romKind": "generic",
            "slots": {
                "/system/fonts/sans-serif.ttf": {
                    "slotName": "sans-serif.ttf", "partition": "system",
                    "source": "xml", "format": "TTF", "weight": 400,
                    "style": "normal", "families": ["sans-serif"],
                },
                "/system_ext/fonts/HiddenUi-Regular.ttf": {
                    "slotName": "HiddenUi-Regular.ttf", "partition": "system_ext",
                    "source": "verified-scan", "format": "TTF", "weight": 400,
                    "style": "normal", "families": [],
                },
                "/product/fonts/OemCollection.ttc": {
                    "slotName": "OemCollection.ttc", "partition": "product",
                    "source": "verified-scan", "format": "TTC", "weight": 400,
                    "style": "normal", "families": [],
                },
            },
        }
        original_inventory_loader = payload_builder._load_inventory
        old_stock_root = os.environ.get("LUOSHU_DEVICE_FONT_STOCK_ROOT")
        try:
            payload_builder._load_inventory = lambda _module: inventory
            os.environ["LUOSHU_DEVICE_FONT_STOCK_ROOT"] = str(stock_root)
            inventory_output = root / "inventory-payload"
            inventory_payload = payload_builder.build_payload(
                copy.deepcopy(template),
                source_dir,
                "LuoShu",
                inventory_output,
                inventory_output / "manifest.json",
            )
        finally:
            payload_builder._load_inventory = original_inventory_loader
            if old_stock_root is None:
                os.environ.pop("LUOSHU_DEVICE_FONT_STOCK_ROOT", None)
            else:
                os.environ["LUOSHU_DEVICE_FONT_STOCK_ROOT"] = old_stock_root

        supplement = inventory_payload["inventorySupplement"]
        assert supplement["inventorySlotCount"] == 3, supplement
        assert supplement["templateMatched"] == 1, supplement
        assert supplement["directAdded"] == 1, supplement
        assert supplement["preserved"] == 1, supplement
        dispositions = {item["path"]: item for item in supplement["slots"]}
        assert dispositions["/system_ext/fonts/HiddenUi-Regular.ttf"]["disposition"] == "direct"
        assert dispositions["/product/fonts/OemCollection.ttc"]["disposition"] == "preserved"
        assert dispositions["/product/fonts/OemCollection.ttc"]["reason"] == "preserved-collection"
        hidden_slots = [
            item for item in inventory_payload["slots"]
            if item.get("inventoryPath") == "/system_ext/fonts/HiddenUi-Regular.ttf"
        ]
        assert len(hidden_slots) == 1 and hidden_slots[0].get("generatedFile"), hidden_slots
        assert hidden_slots[0]["directPhysical"] is True
        assert inventory_payload["summary"]["mapped"] == 4
        print(json.dumps({
            "baseline": payload["summary"],
            "inventory": inventory_payload["summary"],
            "supplement": {
                "matched": supplement["templateMatched"],
                "direct": supplement["directAdded"],
                "preserved": supplement["preserved"],
            },
        }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
