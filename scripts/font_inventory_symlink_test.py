#!/usr/bin/env python3
"""Regression tests for stock font links escaping lower/mirror mounts."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

import font_inventory as inventory
import font_inventory_scan as scanner
from hyperos_metrics_batch import _cjk_routing


def make_font(path: Path, *, han: bool = False) -> None:
    names = [".notdef", "A"] + (["uni4E2D"] if han else [])
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({65: "A", **({0x4E2D: "uni4E2D"} if han else {})})
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        if name != ".notdef":
            pen.moveTo((0, 0))
            pen.lineTo((500, 0))
            pen.lineTo((500, 700))
            pen.lineTo((0, 700))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 0) for name in names})
    builder.setupHorizontalHeader(ascent=1044, descent=-282)
    builder.setupOS2(sTypoAscender=890, sTypoDescender=-110, sTypoLineGap=326,
                     usWinAscent=1044, usWinDescent=282)
    builder.setupNameTable({"familyName": "Stock Link Test", "styleName": "Regular"})
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)


class StockFontLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.live = self.base / "live"
        self.lower = self.base / "lower"
        self.roots = []
        for part in ("system", "product", "vendor"):
            logical = self.live / part / "fonts"
            actual = self.lower / f"{part}-fonts"
            logical.mkdir(parents=True)
            actual.mkdir(parents=True)
            self.roots.append(inventory.FontRoot(part, logical, actual))
        self.system, self.product, self.vendor = self.roots

    def resolve(self, root: inventory.FontRoot, name: str) -> Path:
        return inventory._stock_font_path(root, root.actual / name, self.roots)

    def test_absolute_product_link_never_reads_live_donor(self) -> None:
        name = "MiSansLatinVF.ttf"
        stock = self.product.actual / name
        live = self.product.logical / name
        make_font(stock)
        make_font(live, han=True)
        alias = self.system.actual / name
        alias.symlink_to(live)
        # This was the old scanner's behavior despite a verified system root.
        self.assertTrue(inventory._read_metrics(alias, 0)[1]["coverage"]["hasHan"])
        self.assertEqual(self.resolve(self.system, name), stock)

        checked = []
        def check(path: Path, _script: Path) -> str:
            checked.append(path)
            self.assertFalse(inventory._read_metrics(path, 0)[1]["coverage"]["hasHan"])
            return "TTF"
        slots = {}
        with patch.object(inventory, "_font_check", check):
            inventory._add_heuristic_slots(slots, self.roots, self.base / "font_check.sh")
        self.assertEqual(checked, [stock, stock])
        inventory._populate_metrics(slots)
        system_key, product_key = str(self.system.logical / name), str(self.product.logical / name)
        self.assertEqual(slots[system_key]["metrics"], slots[product_key]["metrics"])
        self.assertFalse(slots[system_key]["metrics"]["coverage"]["hasHan"])
        data = {"slots": {system_key: slots[system_key]}}
        # The inventory must still describe the true stock Latin seed, but
        # HyperOS can open MiSansLatinVF directly from launcher/SystemUI paths.
        # Generated OEM aliases therefore keep full CJK coverage rather than
        # relying on the Android family fallback graph.
        self.assertEqual(_cjk_routing(data, system_key, frozenset({0x4E2D}))[2],
                         "oem-direct-full-coverage")

    def test_xml_keeps_alias_identity_but_reads_stock_entity(self) -> None:
        name = "MiSansLatinVF.ttf"
        stock = self.product.actual / name
        make_font(stock)
        make_font(self.product.logical / name, han=True)
        alias = self.system.actual / name
        alias.symlink_to(self.product.logical / name)
        xml = self.base / "fonts.xml"
        xml.write_text(f'<familyset><family name="sans-serif"><font>{name}</font></family></familyset>')
        with patch.object(inventory, "_is_ui_family", scanner._is_ui_family):
            families, slots = inventory._parse_xml_mappings([xml], self.roots)
        key = str(self.system.logical / name)
        self.assertEqual(families["sans-serif"], [key])
        self.assertEqual(slots[key]["actualPath"], str(stock))
        self.assertEqual(inventory._resolve_file(name, iter(self.roots)), (self.system, alias))
        inventory._populate_metrics(slots)
        self.assertFalse(slots[key]["metrics"]["coverage"]["hasHan"])

    def test_real_android_absolute_and_relative_namespaces(self) -> None:
        roots = [inventory.FontRoot(root.partition, Path(f"/{root.partition}/fonts"), root.actual)
                 for root in self.roots]
        stock = self.product.actual / "MiSansLatinVF.ttf"
        make_font(stock)
        absolute = self.system.actual / "Absolute.ttf"
        relative = self.system.actual / "Relative.ttf"
        absolute.symlink_to("/product/fonts/MiSansLatinVF.ttf")
        relative.symlink_to("../../product/fonts/MiSansLatinVF.ttf")
        partition_alias = self.system.actual / "PartitionAlias.ttf"
        partition_alias.symlink_to("/system/product/fonts/MiSansLatinVF.ttf")
        for alias in (absolute, relative, partition_alias):
            self.assertEqual(inventory._stock_font_path(roots[0], alias, roots), stock)
        self.assertEqual(inventory._resolve_file("/system/product/fonts/MiSansLatinVF.ttf", roots),
                         (roots[1], stock))

    def test_transitive_links_and_directory_links_remap_every_hop(self) -> None:
        stock = self.vendor.actual / "Final.ttf"
        make_font(stock)
        (self.system.actual / "MiSansLatinVF.ttf").symlink_to(self.product.logical / "Next.ttf")
        (self.product.actual / "Next.ttf").symlink_to("Bridge/Final.ttf")
        (self.product.actual / "Bridge").symlink_to(self.vendor.logical)
        self.assertEqual(self.resolve(self.system, "MiSansLatinVF.ttf"), stock)

    def test_mutable_and_unselected_targets_are_rejected(self) -> None:
        targets = ["/data/system/fonts/theme/Roboto-Regular.ttf", "/odm/fonts/Foo.ttf",
                   str(self.base / "outside.ttf"), "../../../../data/system/fonts/theme/Foo.ttf"]
        for index, target in enumerate(targets):
            name = f"MiSans{index}.ttf"
            (self.system.actual / name).symlink_to(target)
            with self.assertRaises(inventory.InventoryError):
                self.resolve(self.system, name)

    def test_cycle_missing_and_non_file_are_rejected(self) -> None:
        (self.system.actual / "A.ttf").symlink_to("B.ttf")
        (self.system.actual / "B.ttf").symlink_to("A.ttf")
        (self.system.actual / "Dir.ttf").mkdir()
        for name in ("A.ttf", "Missing.ttf", "Dir.ttf"):
            with self.assertRaises(inventory.InventoryError):
                self.resolve(self.system, name)

    def test_absolute_xml_escape_does_not_fall_back_to_same_basename(self) -> None:
        make_font(self.system.actual / "Roboto-Regular.ttf")
        self.assertIsNone(inventory._resolve_file("/data/system/fonts/Roboto-Regular.ttf", self.roots))

    def test_unmounted_coloros_root_and_relative_alias_still_work(self) -> None:
        root = inventory.FontRoot("product", self.product.logical, self.product.logical)
        stock = root.actual / "SysSans-Hans-Regular.ttf"
        make_font(stock, han=True)
        alias = root.actual / "SysFont-Hans-Regular.ttf"
        alias.symlink_to(stock.name)
        self.assertEqual(inventory._stock_font_path(root, alias, [root]), stock)
        self.assertEqual(inventory._resolve_file(stock.name, [root]), (root, stock))


if __name__ == "__main__":
    unittest.main()
