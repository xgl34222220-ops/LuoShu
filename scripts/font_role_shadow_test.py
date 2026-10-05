#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def slot(
    name: str,
    families: list[str],
    *,
    han: bool = False,
    latin: bool = False,
    digits: bool = False,
    replaceable: bool | None = None,
    runtime: bool = False,
    xml_lang: str = "",
) -> dict:
    coverage = {
        "hasHan": han,
        "hanCount": 64 if han else 0,
        "hasLatin": latin,
        "latinCount": 52 if latin else 0,
        "hasDigits": digits,
        "digitCount": 10 if digits else 0,
    }
    value = {
        "slotName": name,
        "families": families,
        "partition": "system",
        "source": "xml" if families else "verified-scan",
        "sourceXmls": ["/system/etc/fonts.xml"] if families else [],
        "metrics": {"coverage": coverage},
        "runtimeEvidence": {"fontManager": runtime, "mount": False},
    }
    if xml_lang:
        value["xmlRefs"] = [{
            "sourceXml": "/system/etc/fonts.xml",
            "family": families[0] if families else "",
            "familyAttributes": {"lang": xml_lang},
            "resolvedPath": "/system/fonts/" + name,
        }]
    if replaceable is not None:
        value["legacyReplaceable"] = replaceable
    return value


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    script = root / "common/font_role_shadow.py"

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        topology = temp / "device_font_topology.json"
        roles = temp / "device_font_roles.json"
        plan = temp / "device_font_shadow_plan.json"

        slots = {
            "/system/fonts/Roboto-Regular.ttf": slot(
                "Roboto-Regular.ttf", ["sans-serif"], latin=True, digits=True,
                replaceable=True, runtime=True,
            ),
            "/product/fonts/CjkFallback.otf": slot(
                "CjkFallback.otf", ["fallback"], han=True, latin=True, digits=True,
                replaceable=False, xml_lang="zh-Hans",
            ),
            "/product/fonts/LatinFallback.ttf": slot(
                "LatinFallback.ttf", ["fallback"], latin=True, digits=True,
                replaceable=False, xml_lang="en",
            ),
            "/system_ext/fonts/OemNumeric.ttf": slot(
                "OemNumeric.ttf", [], digits=True, replaceable=False,
            ),
            "/system/fonts/AndroidClock.ttf": slot(
                "AndroidClock.ttf", ["clock-ui"], latin=True, digits=True,
                replaceable=True,
            ),
            # Explicit monospace family must beat the Mitype filename clock hint.
            "/system/fonts/MitypeMono.ttf": slot(
                "MitypeMono.ttf", ["monospace"], latin=True, digits=True,
                replaceable=True,
            ),
            "/system/fonts/RobotoMono-Regular.ttf": slot(
                "RobotoMono-Regular.ttf", [], latin=True, digits=True,
                replaceable=False,
            ),
            "/system/fonts/NotoSerif-Regular.ttf": slot(
                "NotoSerif-Regular.ttf", ["serif"], latin=True, digits=True,
                replaceable=False,
            ),
            "/system/fonts/NotoColorEmoji.ttf": slot(
                "NotoColorEmoji.ttf", ["emoji"], replaceable=True,
            ),
            "/system/fonts/MaterialSymbols.ttf": slot(
                "MaterialSymbols.ttf", ["material-symbols"], replaceable=True,
            ),
            "/system/fonts/MysteryFallback.otf": slot(
                "MysteryFallback.otf", ["fallback"], latin=True, digits=True,
                replaceable=False, xml_lang="ja",
            ),
            "/vendor/fonts/MysteryBroad.ttf": slot(
                "MysteryBroad.ttf", [], han=True, latin=True, digits=True,
                replaceable=True,
            ),
            # OEM global UI families carry Han + Latin without a sans-serif name.
            "/system/fonts/MiSansVF.ttf": slot(
                "MiSansVF.ttf", ["mipro"], han=True, latin=True, digits=True,
                replaceable=True,
            ),
            "/system/fonts/SysFont-Regular.ttf": slot(
                "SysFont-Regular.ttf", ["sysfont"], han=True, latin=True, digits=True,
                replaceable=True,
            ),
            "/my_product/fonts/OPlusSans3.0.ttf": slot(
                "OPlusSans3.0.ttf", ["oplus-sans"], han=True, latin=True, digits=True,
                replaceable=True,
            ),
            "/system/fonts/MitypeVF.ttf": slot(
                "MitypeVF.ttf", ["mitype"], latin=True, digits=True,
                replaceable=False,
            ),
            # Generic design families and script-only fallbacks stay stock.
            "/system/fonts/ComingSoon.ttf": slot(
                "ComingSoon.ttf", ["casual"], latin=True, digits=True, replaceable=False,
            ),
            "/system/fonts/DancingScript-Regular.ttf": slot(
                "DancingScript-Regular.ttf", ["cursive"], latin=True, digits=True, replaceable=False,
            ),
            "/system/fonts/NotoSansMiao-Regular.otf": slot(
                "NotoSansMiao-Regular.otf", [], latin=True, digits=True,
                replaceable=False, xml_lang="und-Plrd",
            ),
            "/system/fonts/NotoSansOldItalic-Regular.ttf": slot(
                "NotoSansOldItalic-Regular.ttf", [], latin=True, replaceable=False,
                xml_lang="und-Ital",
            ),
            # HyperOS 3 (device bundle): clock faces named *Mono, the zh-Hant UI
            # font tagged "zh-Hant,zh-Bopo", and the ja/ko/zh CJK collection.
            "/product/fonts/MiClockMono.otf": slot(
                "MiClockMono.otf", [], latin=True, digits=True, replaceable=False,
            ),
            "/product/fonts/MitypeClockMono.otf": slot(
                "MitypeClockMono.otf", [], digits=True, replaceable=False,
            ),
            "/system/fonts/MiSansTCVF.ttf": slot(
                "MiSansTCVF.ttf", [], han=True, latin=True, digits=True,
                replaceable=False, xml_lang="zh-Hant,zh-Bopo",
            ),
            "/system/fonts/NotoSansCJK-Regular.ttc": slot(
                "NotoSansCJK-Regular.ttc", [], han=True, latin=True, digits=True,
                replaceable=False, xml_lang="ja ko zh-Hans",
            ),
            "/system/fonts/LatinUnd.ttf": slot(
                "LatinUnd.ttf", ["fallback"], latin=True, digits=True,
                replaceable=False, xml_lang="und-Latn",
            ),
        }

        font_fallback = slot("FontLevelFallback.ttf", ["fallback"], latin=True, digits=True)
        font_fallback["xmlRefs"] = [{"family": "fallback", "fallbackFor": "serif"}]
        slots["/system/fonts/FontLevelFallback.ttf"] = font_fallback

        # Gothi(cOn)e crosses two unrelated name components. Neither an icon
        # substring nor ara(b) in Parabolic is semantic evidence of a symbol or
        # unsupported-script font. Actual cmap evidence can still identify text.
        for name in ("DelaGothicOne.otf", "DelaGothicOne-HZ.otf", "Lexicon-Regular.ttf", "Parabolic-Regular.ttf"):
            slots["/product/fonts/" + name] = slot(name, [], latin=True, digits=True)
        unknown_dela = {"slotName": "DelaGothicOne-Unmeasured.otf", "families": [], "source": "physical-scan"}
        slots["/product/fonts/DelaGothicOne-Unmeasured.otf"] = unknown_dela
        slots["/product/fonts/DelaGothicOne-Clock.otf"] = slot(
            "DelaGothicOne-Clock.otf", ["miclock-dela-gothic-one"], latin=True, digits=True,
        )
        # Genuine dedicated font identities remain protected, whether the ROM
        # spells them in CamelCase, lowercase compounds or with separators.
        icons = (
            "NotoSansSymbols2-Regular.ttf", "NotoSansSymbols-Regular.ttf",
            "MaterialIcons-Regular.ttf", "MaterialSymbols.ttf", "FontAwesome.ttf",
            "fontawesome-webfont.ttf", "materialicons-regular.ttf", "Glyphicons-Halflings.ttf",
            "AppIcons.ttf", "App-Icons_Regular.ttf", "NotoSansMath-Regular.ttf",
        )
        for name in icons:
            slots["/system/fonts/" + name] = slot(name, [], latin=True, digits=True)
        for name in ("myemojiMono.ttf", "brandemojibold.ttf", "NotoColorEmojiFlags.ttf"):
            slots["/system/fonts/" + name] = slot(name, [], latin=True, digits=True)
        cjk_names = ("SourceHanSansSC-Regular.otf", "SourceHanSansTC-Regular.otf", "SourceHanSansCN.otf",
                     "sourcehansanssc-Regular.otf", "NotoSansSC-Regular.otf", "NotoSansTC-Regular.otf")
        for name in cjk_names:
            slots["/system/fonts/" + name] = slot(name, [], han=True, latin=True, digits=True)

        topology.write_text(
            json.dumps(
                {
                    "schema": "device-font-topology-v1",
                    "topologyRevision": 2,
                    "state": "ready",
                    "buildKey": "role-shadow-test",
                    "romKind": "generic",
                    "slots": slots,
                    "families": {},
                    "summary": {"slotCount": len(slots)},
                    "runtime": {},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        built = run(
            [
                sys.executable,
                str(script),
                "--topology", str(topology),
                "--roles-output", str(roles),
                "--plan-output", str(plan),
            ]
        )
        assert built.returncode == 0, built.stderr or built.stdout
        result = json.loads(built.stdout)
        role_map = json.loads(roles.read_text(encoding="utf-8"))
        shadow = json.loads(plan.read_text(encoding="utf-8"))

        assert result["status"] == "ok"
        assert role_map["schema"] == "device-font-roles-v1"
        assert shadow["schema"] == "device-font-shadow-plan-v1"
        assert shadow["state"] == "shadow"
        assert shadow["mutatesSystem"] is False

        def role(path: str) -> str:
            return role_map["slots"][path]["role"]

        def action(path: str) -> str:
            return shadow["slots"][path]["action"]

        assert role("/system/fonts/Roboto-Regular.ttf") == "ui-sans"
        assert action("/system/fonts/Roboto-Regular.ttf") == "replace"

        assert role("/product/fonts/CjkFallback.otf") == "cjk"
        assert action("/product/fonts/CjkFallback.otf") == "conditional"
        assert role_map["slots"]["/product/fonts/CjkFallback.otf"]["evidence"]["xmlSemantics"]["lang"] == ["zh-Hans"]
        assert shadow["slots"]["/product/fonts/CjkFallback.otf"]["comparison"] == "current-gap"

        assert role("/product/fonts/LatinFallback.ttf") == "latin"
        assert action("/product/fonts/LatinFallback.ttf") == "conditional"

        assert role("/system_ext/fonts/OemNumeric.ttf") == "numeric"
        assert action("/system_ext/fonts/OemNumeric.ttf") == "specialized"

        assert role("/system/fonts/AndroidClock.ttf") == "clock"
        assert action("/system/fonts/AndroidClock.ttf") == "specialized"

        assert role("/system/fonts/MitypeMono.ttf") == "monospace"
        assert action("/system/fonts/MitypeMono.ttf") == "preserve"
        assert shadow["slots"]["/system/fonts/MitypeMono.ttf"]["comparison"] == "current-overreach"

        assert role("/system/fonts/RobotoMono-Regular.ttf") == "monospace"
        assert action("/system/fonts/RobotoMono-Regular.ttf") == "preserve"
        assert "monospace-file-identity" in role_map["slots"]["/system/fonts/RobotoMono-Regular.ttf"]["reasons"]

        assert role("/system/fonts/NotoSerif-Regular.ttf") == "serif"
        assert action("/system/fonts/NotoSerif-Regular.ttf") == "preserve"

        assert role("/system/fonts/NotoColorEmoji.ttf") == "emoji"
        assert action("/system/fonts/NotoColorEmoji.ttf") == "preserve"
        assert shadow["slots"]["/system/fonts/NotoColorEmoji.ttf"]["comparison"] == "current-overreach"

        assert role("/system/fonts/MaterialSymbols.ttf") == "symbol-icon"
        assert action("/system/fonts/MaterialSymbols.ttf") == "preserve"
        for name in icons:
            path = "/system/fonts/" + name
            assert role(path) == "symbol-icon", (path, role_map["slots"][path])
            assert action(path) == "preserve"
        for name in ("DelaGothicOne.otf", "DelaGothicOne-HZ.otf", "Lexicon-Regular.ttf", "Parabolic-Regular.ttf"):
            path = "/product/fonts/" + name
            assert role(path) == "latin", (path, role_map["slots"][path])
            assert action(path) == "conditional"
            assert role_map["slots"][path]["evidence"]["coverage"]["latinCount"] == 52
        assert role("/product/fonts/DelaGothicOne-Unmeasured.otf") == "unknown-protected"
        assert action("/product/fonts/DelaGothicOne-Unmeasured.otf") == "review"
        assert role("/product/fonts/DelaGothicOne-Clock.otf") == "clock"
        for name in ("myemojiMono.ttf", "brandemojibold.ttf", "NotoColorEmojiFlags.ttf"):
            path = "/system/fonts/" + name
            assert role(path) == "emoji", (path, role_map["slots"][path])
            assert action(path) == "preserve"
        for name in cjk_names:
            path = "/system/fonts/" + name
            assert role(path) == "cjk", (path, role_map["slots"][path])
            assert action(path) == "conditional"

        assert role("/system/fonts/MysteryFallback.otf") == "special-fallback"
        assert action("/system/fonts/MysteryFallback.otf") == "preserve"
        assert "xml-language-special-fallback" in role_map["slots"]["/system/fonts/MysteryFallback.otf"]["reasons"]
        assert role("/system/fonts/FontLevelFallback.ttf") == "special-fallback"
        assert action("/system/fonts/FontLevelFallback.ttf") == "preserve"
        assert role_map["slots"]["/system/fonts/FontLevelFallback.ttf"]["evidence"]["xmlSemantics"]["fallbackFor"] == ["serif"]

        assert role("/vendor/fonts/MysteryBroad.ttf") == "unknown-protected"
        assert action("/vendor/fonts/MysteryBroad.ttf") == "review"

        for oem_ui in (
            "/system/fonts/MiSansVF.ttf",
            "/system/fonts/SysFont-Regular.ttf",
            "/my_product/fonts/OPlusSans3.0.ttf",
        ):
            assert role(oem_ui) == "ui-sans", (oem_ui, role_map["slots"][oem_ui])
            assert action(oem_ui) == "replace", oem_ui

        for protected in (
            "/system/fonts/ComingSoon.ttf",
            "/system/fonts/DancingScript-Regular.ttf",
            "/system/fonts/NotoSansMiao-Regular.otf",
            "/system/fonts/NotoSansOldItalic-Regular.ttf",
        ):
            assert role(protected) == "special-fallback", (protected, role_map["slots"][protected])
            assert action(protected) == "preserve", protected
        assert role("/system/fonts/LatinUnd.ttf") == "latin"
        assert role("/product/fonts/MiClockMono.otf") == "clock"
        assert role("/product/fonts/MitypeClockMono.otf") == "clock"
        assert role("/system/fonts/MiSansTCVF.ttf") == "cjk"
        # Covers kana/Hangul too: replacing it would drop Japanese and Korean.
        assert role("/system/fonts/NotoSansCJK-Regular.ttc") == "special-fallback"

        # HyperOS Mitype drives lock-screen/status-bar digits: exact-width path.
        assert role("/system/fonts/MitypeVF.ttf") == "clock"
        assert action("/system/fonts/MitypeVF.ttf") == "specialized"

        # Phase 2 safety invariants.
        for item in shadow["slots"].values():
            if item["role"] in {"emoji", "symbol-icon", "serif", "monospace", "special-fallback"}:
                assert item["action"] == "preserve"
            if item["role"] in {"clock", "numeric"}:
                assert item["action"] == "specialized"
            if item["role"] == "unknown-protected":
                assert item["action"] == "review"

        assert shadow["summary"]["actionCounts"]["preserve"] == 25
        assert shadow["summary"]["actionCounts"]["specialized"] == 6
        assert shadow["summary"]["actionCounts"]["conditional"] == 14
        assert shadow["summary"]["actionCounts"]["replace"] == 4
        assert shadow["summary"]["actionCounts"]["review"] == 2

        validated = run(
            [
                sys.executable,
                str(script),
                "--validate",
                "--topology", str(topology),
                "--roles-output", str(roles),
                "--plan-output", str(plan),
            ]
        )
        assert validated.returncode == 0, validated.stderr or validated.stdout

    print("font_role_shadow_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
