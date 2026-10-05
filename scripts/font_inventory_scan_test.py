#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)


def check_oem_xml_graph(scanner, temp: Path, font: Path) -> None:
    """The observed seven-config topology, using original small fixtures."""
    import font_topology_snapshot as topology
    import font_role_shadow as role_policy

    fixture = temp / "oem-xml"
    etc = {part: fixture / part / "etc" for part in ("system", "system_ext", "product")}
    fonts = {part: fixture / part / "fonts" for part in etc}
    for path in (*etc.values(), *fonts.values()):
        path.mkdir(parents=True)
    for part in ("system", "product"):
        shutil.copy2(font, fonts[part] / "Shared.ttf")
    for name in ("BebasNeue-Mono.otf", "DelaGothicOne.otf", "MiSerifSCVF.ttf"):
        shutil.copy2(font, fonts["product"] / name)
    main_xml = (
        '<familyset><family name="sans-serif">'
        '<font weight="350" postScriptName="SharedText">Shared.ttf'
        '<axis tag="wght" stylevalue="350"/></font>'
        '<font weight="950" postScriptName="SharedText">Shared.ttf'
        '<axis tag="wght" stylevalue="950"/></font>'
        '</family></familyset>'
    )
    fallback_xml = (
        '<familyset><family lang="ja"><font weight="400" fallbackFor="serif">Shared.ttf</font></family>'
        '<family lang="zh-Hans"><font weight="400">Shared.ttf</font></family></familyset>'
    )
    customization = (
        '<fonts-modification>'
        '<family customizationType="new-named-family" name="miclock-bebas-neue-mono">'
        '<font weight="400" postScriptName="BebasNeue-Mono">BebasNeue-Mono.otf</font></family>'
        '<family customizationType="new-named-family" name="miclock-dela-gothic-one">'
        '<font weight="400" postScriptName="LogoSCUnboundedSans-Regular">DelaGothicOne.otf</font></family>'
        '<family customizationType="new-named-family" name="miclock-serif-sc-regular">'
        '<font weight="400" postScriptName="MiSerifSCVF">MiSerifSCVF.ttf'
        '<axis tag="wght" stylevalue="330"/></font>'
        '<font weight="400" postScriptName="MiSerifSCVF">MiSerifSCVF.ttf'
        '<axis tag="wght" stylevalue="330"/></font>'
        '<font weight="700" postScriptName="MiSerifSCVF">MiSerifSCVF.ttf'
        '<axis tag="wght" stylevalue="430"/></font></family>'
        '<family customizationType="new-locale-family" operation="prepend" lang="ja">'
        '<font weight="400">Shared.ttf</font></family>'
        '<family customizationType="new-locale-family" operation="prepend" lang="zh-Hans">'
        '<font weight="400">Shared.ttf</font></family></fonts-modification>'
    )
    documents = {
        ("system", "fonts.xml"): main_xml,
        ("system", "font_fallback.xml"): fallback_xml,
        ("system_ext", "hyper_fonts.xml"): main_xml,
        ("system_ext", "hyper_font_fallback.xml"): fallback_xml,
        ("system_ext", "miui_fonts.xml"): main_xml,
        ("system_ext", "miui_font_fallback.xml"): fallback_xml,
        ("product", "mi_fonts_customization.xml"): customization,
    }
    for (part, name), xml in documents.items():
        (etc[part] / name).write_text(xml, encoding="utf-8")
    # A normal HyperOS alias points at another partition by logical path. The
    # scanner must remap it to captured stock rather than follow the live view.
    (etc["system"] / "fonts.xml").unlink()
    (etc["system"] / "fonts.xml").symlink_to("/system_ext/etc/hyper_fonts.xml")
    (etc["system"] / "font_settings.xml").write_text('<settings><family name="sans-serif"/></settings>')
    (etc["system"] / "font_broken.xml").write_text('<familyset>')
    (etc["system"] / "nested").mkdir()
    (etc["system"] / "nested/fonts.xml").write_text(main_xml)
    outside = fixture / "untrusted.xml"
    outside.write_text(main_xml)
    (etc["system"] / "font_escape.xml").symlink_to(outside)
    source_roots = [(part, Path(f"/{part}/etc"), path) for part, path in etc.items()]
    discovered = scanner._discover_xml_sources(source_roots)
    assert len(discovered) == 7, discovered
    assert {str(logical) for _part, logical, _actual in discovered} == {
        f"/{part}/etc/{name}" for part, name in documents
    }
    font_roots = [scanner.base.FontRoot(part, Path(f"/{part}/fonts"), path) for part, path in fonts.items()]
    graph = scanner._parse_full_xml_graph(discovered, font_roots)
    assert graph["refCount"] == 18, graph
    source = "/product/etc/mi_fonts_customization.xml"
    product_refs = [ref for ref in graph["refs"] if ref["sourceXml"] == source]
    assert len(product_refs) == 6
    assert all(ref["resolvedPath"].startswith("/product/fonts/") for ref in product_refs)
    assert all(ref["resolvedPath"] == "/system/fonts/Shared.ttf" for ref in graph["refs"]
               if ref["sourceXml"] != source)
    variable_refs = [ref for ref in product_refs if ref["declared"] == "MiSerifSCVF.ttf"]
    assert [ref["weight"] for ref in variable_refs] == [400, 700]
    assert [ref["axisSettings"] for ref in variable_refs] == [
        [{"tag": "wght", "stylevalue": "330"}], [{"tag": "wght", "stylevalue": "430"}],
    ]
    assert all(ref["postScriptName"] == "MiSerifSCVF" for ref in variable_refs)
    assert {ref["weight"] for ref in graph["refs"] if ref["family"] == "sans-serif"} == {350, 950}
    fallback = [ref for ref in graph["refs"] if ref["fallbackFor"]]
    assert len(fallback) == 3 and all(ref["fallbackFor"] == "serif" for ref in fallback)
    locales = [ref for ref in product_refs if ref["declared"] == "Shared.ttf"]
    assert {ref["familyAttributes"]["lang"] for ref in locales} == {"ja", "zh-Hans"}
    assert all(ref["familyAttributes"]["operation"] == "prepend" for ref in locales)

    # XML semantics attach to each existing physical path, with no duplicate
    # slots and without silently promoting protected mono/serif/icon roles.
    inventory = {
        "schema": "device-font-inventory-v1", "state": "ready", "buildKey": "oem-xml",
        "scannerRevision": scanner.SCANNER_REVISION, "inventoryRevision": 1,
        "slots": {"/system/fonts/Shared.ttf": {"partition": "system", "source": "xml", "families": ["sans-serif"]}},
        "xmlSources": [str(logical) for _part, logical, _actual in discovered], "xmlGraph": graph,
        "families": {}, "romKind": "hyperos",
    }
    candidates = {"paths": [{"path": f"/{part}/fonts/{path.name}", "partition": part, "slotName": path.name}
                             for part, directory in fonts.items() for path in sorted(directory.iterdir())]}
    snapshot = topology.build_topology(inventory, candidates, "", None, None, "")
    assert snapshot["summary"]["slotCount"] == 5
    serif = snapshot["slots"]["/product/fonts/MiSerifSCVF.ttf"]
    assert serif["families"] == ["miclock-serif-sc-regular"]
    assert len(serif["xmlRefs"]) == 2 and not serif["legacyReplaceable"]
    roles, _shadow = role_policy.build(snapshot)
    assert roles["slots"]["/product/fonts/BebasNeue-Mono.otf"]["role"] == "monospace"
    assert roles["slots"]["/product/fonts/MiSerifSCVF.ttf"]["role"] == "serif"
    assert roles["slots"]["/product/fonts/DelaGothicOne.otf"]["role"] == "clock"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, required=True)
    args = parser.parse_args()
    if not args.font.is_file():
        raise SystemExit("test font missing")

    root = Path(__file__).resolve().parents[1]
    common = root / "common"
    sys.path.insert(0, str(common))
    embedded_fonttools = common / "python/lib/python3.14/site-packages"
    if embedded_fonttools.is_dir():
        previous = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = str(embedded_fonttools) + (os.pathsep + previous if previous else "")
    script = common / "font_inventory_scan.py"

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        primary = ("system", "system_ext", "product", "my_product", "vendor")
        auxiliary = ("odm", "oem", "my_region", "hw_product")
        font_dirs = {name: temp / name / "fonts" for name in (*primary, *auxiliary)}
        etc_dirs = {name: temp / name / "etc" for name in (*primary, *auxiliary)}
        for path in (*font_dirs.values(), *etc_dirs.values()):
            path.mkdir(parents=True)

        shutil.copy2(args.font, font_dirs["system"] / "Roboto-Regular.ttf")
        # Absent from XML and every OEM filename heuristic: revision 4 must
        # discover this slot from real font structure/coverage alone.
        shutil.copy2(args.font, font_dirs["system_ext"] / "MysteryUiFace-Regular.ttf")
        shutil.copy2(args.font, font_dirs["product"] / "ProductUi-Regular.ttf")
        shutil.copy2(args.font, font_dirs["my_product"] / "SysFont-Hans-Regular.ttf")
        os.link(font_dirs["product"] / "ProductUi-Regular.ttf", font_dirs["odm"] / "DuplicateProduct.ttf")
        shutil.copy2(args.font, font_dirs["oem"] / "OPlusSans3.0.ttf")
        shutil.copy2(args.font, font_dirs["hw_product"] / "HwUi-Regular.ttf")

        dynamic_root = temp / "dynamic-root"
        future_fonts = dynamic_root / "future_oem/fonts"
        future_etc = dynamic_root / "future_oem/etc"
        future_fonts.mkdir(parents=True)
        future_etc.mkdir(parents=True)
        shutil.copy2(args.font, future_fonts / "FutureUi-Regular.ttf")

        (etc_dirs["system"] / "fonts.xml").write_text(
            '<familyset><family name="sans-serif"><font weight="400">Roboto-Regular.ttf</font></family>'
            '<alias name="sans" to="sans-serif"/></familyset>\n',
            encoding="utf-8",
        )
        (etc_dirs["product"] / "fonts_customization.xml").write_text(
            '<fonts-modification>'
            '<family name="system-ui"><font weight="400">ProductUi-Regular.ttf</font></family>'
            '<family name="fallback-japanese" lang="ja" variant="compact">'
            '<font weight="400">ProductUi-Regular.ttf</font></family>'
            '</fonts-modification>\n',
            encoding="utf-8",
        )
        (etc_dirs["my_product"] / "fonts.xml").write_text(
            '<familyset><family name="sysfont"><font weight="400">SysFont-Hans-Regular.ttf</font></family></familyset>\n',
            encoding="utf-8",
        )
        (etc_dirs["oem"] / "fonts.xml").write_text(
            '<familyset><family name="system-ui"><font weight="400">ProductUi-Regular.ttf</font></family></familyset>\n',
            encoding="utf-8",
        )
        (etc_dirs["hw_product"] / "fonts.xml").write_text(
            '<familyset><family name="system-ui"><font weight="400">HwUi-Regular.ttf</font></family></familyset>\n',
            encoding="utf-8",
        )

        (future_etc / "fonts.xml").write_text(
            '<familyset><family name="system-ui"><font weight="400">FutureUi-Regular.ttf</font></family></familyset>\n',
            encoding="utf-8",
        )

        font_check = temp / "font_check.sh"
        font_check.write_text(
            '#!/bin/sh\nprintf \'%s\\n\' \'{"valid":true,"format":"TTF","bytes":4096,"variable":false,"color":false}\'\n',
            encoding="utf-8",
        )
        font_check.chmod(0o755)
        output = temp / "device_font_inventory.json"
        command = [
            sys.executable,
            str(script),
            "--scan",
            "--output", str(output),
            "--font-check", str(font_check),
            "--build-key", "inventory-v4-rom",
        ]
        for name in primary:
            command.extend(["--" + name.replace("_", "-") + "-fonts", str(font_dirs[name])])
            command.extend(["--" + name.replace("_", "-") + "-etc", str(etc_dirs[name])])
        for name in auxiliary:
            command.extend(["--" + name.replace("_", "-") + "-fonts", str(font_dirs[name])])
            command.extend(["--" + name.replace("_", "-") + "-etc", str(etc_dirs[name])])

        scan_env = {**os.environ, "LUOSHU_DYNAMIC_PARTITION_SCAN_ROOTS": str(dynamic_root)}
        first = run(command, scan_env)
        assert first.returncode == 0, first.stderr
        result = json.loads(first.stdout)
        payload = json.loads(output.read_text(encoding="utf-8"))
        candidates = json.loads((temp / "device_font_candidates.json").read_text(encoding="utf-8"))
        summary = payload["scanSummary"]

        assert payload["scannerRevision"] == 6
        assert payload["romKind"] == "coloros"
        assert result["stockFontFileCount"] == 8
        assert result["stockFontUniqueFileCount"] == 7
        assert result["genericSlotCount"] >= 2
        assert result["candidatePathCount"] == 8
        assert candidates["schema"] == "device-font-candidates-v1"
        assert candidates["fontFileCount"] == 8
        assert candidates["candidateCount"] == 8
        assert summary["installCandidatePathCount"] == 8
        assert summary["stockFontFileCount"] == 8
        assert summary["stockFontUniqueFileCount"] == 7
        assert summary["verifiedScanUiFileCount"] >= 2
        assert summary["partitionFontFileCounts"]["odm"] == 1
        assert summary["partitionUniqueFontFileCounts"]["odm"] == 0
        assert summary["xmlSourceCount"] == 6
        assert payload["xmlGraph"]["schema"] == "device-font-xml-graph-v1"
        assert payload["xmlGraph"]["refCount"] >= 7
        assert payload["xmlGraph"]["aliasCount"] == 1
        fallback_refs = [
            ref for ref in payload["xmlGraph"]["refs"]
            if ref["family"] == "fallback-japanese"
        ]
        assert len(fallback_refs) == 1
        assert fallback_refs[0]["familyAttributes"]["lang"] == "ja"
        assert fallback_refs[0]["familyAttributes"]["variant"] == "compact"
        assert fallback_refs[0]["resolvedPath"] == "/product/fonts/ProductUi-Regular.ttf"
        assert payload["xmlGraph"]["aliases"] == [{
            "sourceXml": "/system/etc/fonts.xml",
            "name": "sans",
            "to": "sans-serif",
        }]
        assert payload["slotCount"] == 8
        assert "/system/fonts/Roboto-Regular.ttf" in payload["slots"]
        mystery = payload["slots"]["/system_ext/fonts/MysteryUiFace-Regular.ttf"]
        assert mystery["source"] == "verified-scan"
        assert mystery["validatedBy"] == "fontTools-generic-stock-scan"
        assert "/product/fonts/ProductUi-Regular.ttf" in payload["slots"]
        assert "/my_product/fonts/SysFont-Hans-Regular.ttf" in payload["slots"]
        assert "/oem/fonts/OPlusSans3.0.ttf" in payload["slots"]
        assert "/hw_product/fonts/HwUi-Regular.ttf" in payload["slots"]
        assert "/future_oem/fonts/FutureUi-Regular.ttf" in payload["slots"]
        assert payload["discoveredPartitions"] == ["future_oem"]
        assert summary["partitionFontFileCounts"]["future_oem"] == 1
        assert (temp / "device_font_partitions.conf").read_text(encoding="utf-8") == "future_oem\n"
        assert summary["fontSignatures"]["coloros"] == ["SysFont-Hans-Regular.ttf", "OPlusSans3.0.ttf"]
        assert "Roboto-Regular.ttf" in summary["fontSignatures"]["aosp"]
        assert all(not path.startswith("/data/") for path in payload["slots"])

        reused = run(command, scan_env)
        assert reused.returncode == 0, reused.stderr
        reused_result = json.loads(reused.stdout)
        assert reused_result["status"] == "reused"
        assert reused_result["stockFontUniqueFileCount"] == 7
        assert reused_result["genericSlotCount"] >= 2
        assert reused_result["candidatePathCount"] == 8

        scanner = importlib.import_module("font_inventory_scan")
        assert not scanner._can_reuse(dict(payload, scannerRevision=5), "inventory-v4-rom")
        # The previous valid graph is upgraded through a verified stock view.
        old = dict(payload, scannerRevision=5)
        output.write_text(json.dumps(old), encoding="utf-8")
        upgraded = run(command, {**scan_env, "LUOSHU_STOCK_VIEW_VERIFIED": "1"})
        assert upgraded.returncode == 0, upgraded.stderr
        assert json.loads(upgraded.stdout)["status"] == "ok"
        assert json.loads(output.read_text())["scannerRevision"] == 6
        # A failed upgrade retains the old readable inventory byte-for-byte.
        output.write_text(json.dumps(old), encoding="utf-8")
        before = output.read_bytes()
        failed_upgrade = run(command, {**scan_env, "LUOSHU_STOCK_VIEW_VERIFIED": "0"})
        assert failed_upgrade.returncode != 0
        assert output.read_bytes() == before
        assert json.loads(failed_upgrade.stderr)["retainedInventory"] is True
        check_oem_xml_graph(scanner, temp, args.font)
        theme = temp / "theme/fonts"
        theme.mkdir(parents=True)
        shutil.copy2(args.font, theme / "Theme.ttf")
        scanner.THEME_FONT_ROOTS = (theme,)
        assert scanner._theme_override_roots() == [str(theme)]

    print("font_inventory_scan_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
