#!/usr/bin/env python3
"""HyperOS seed XML: discovery name parity, symlink-chain inventory, and the
default-on (``enabled=0`` disables) per-slot rewrite of /system_ext/etc seeds,
regular /system/etc XML and /product/etc/fonts_customization.xml, including
strict reference validation and zh-Hans/zh-Hant routing."""
from __future__ import annotations

import filecmp
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_payload_overlay as overlay  # noqa: E402
import font_inventory_scan as scan  # noqa: E402
import hyperos_source_xml as seedxml  # noqa: E402

SEED_PATTERNS = ("hyper_fonts*.xml", "hyper_font_fallback*.xml", "miui_fonts*.xml", "miui_font_fallback*.xml")

# Stock HyperOS-style seed: comments (one containing a <font>), family-list,
# axis children, odd spacing, an unmapped TTC node and CRLF in one line.
MIUI_FONTS = (
    "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
    "<!-- MIUI seed. Copied to /data/system/fonts/theme_webview/fonts.xml by init -->\n"
    "<familyset version=\"23\">\n"
    "    <!-- <font weight=\"400\" style=\"normal\">Roboto-Regular.ttf</font> -->\n"
    "    <family name=\"sans-serif\" supportedAxes=\"wght\">\n"
    "        <font weight=\"400\" style=\"normal\">Roboto-Regular.ttf\n"
    "            <axis tag=\"wght\" stylevalue=\"400\" />\n"
    "        </font>\n"
    "        <font weight=\"700\"  style='normal' >Roboto-Regular.ttf<axis tag=\"wght\" stylevalue=\"700\"/></font>\r\n"
    "    </family>\n"
    "    <family name=\"mipro\">\n"
    "        <font weight=\"400\" style=\"normal\">MiSansVF.ttf</font>\n"
    "    </family>\n"
    "    <alias name=\"arial\" to=\"sans-serif\" />\n"
    "    <family lang=\"zh-Hans\">\n"
    "        <font weight=\"400\" style=\"normal\" index=\"2\">NotoSansCJK-Regular.ttc</font>\n"
    "    </family>\n"
    "    <family-list name=\"serif-monospace\">\n"
    "        <family><font weight=\"400\" style=\"normal\">CutiveMono.ttf</font></family>\n"
    "    </family-list>\n"
    "</familyset>\n"
)
HYPER_FONTS = MIUI_FONTS.replace("MIUI seed", "Hyper seed")
MIUI_FALLBACK = (
    "<?xml version='1.0' encoding='utf-8'?>\n"
    "<familyset>\n"
    "  <family name='sans-serif'><font weight='400' style='normal'>Roboto-Regular.ttf</font></family>\n"
    "  <family name='emoji' lang='und-Zsye'><font weight='400' style='normal'>NotoColorEmoji.ttf</font></family>\n"
    "</familyset>\n"
)
SYSTEM_FONTS = (
    "<?xml version='1.0' encoding='utf-8'?>\n"
    "<familyset>\n"
    "  <family name='sans-serif'>\n"
    "    <font weight='400' style='normal'>Roboto-Regular.ttf</font>\n"
    "    <font weight='700' style='normal'>Roboto-Regular.ttf</font>\n"
    "  </family>\n"
    "  <family name='serif-monospace'><font weight='400' style='normal'>CutiveMono.ttf</font></family>\n"
    "</familyset>\n"
)
SYSTEM_FALLBACK = SYSTEM_FONTS.replace("CutiveMono.ttf", "CutiveMono.ttf")


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_bytes(content.encode("utf-8"))


def slot(source: Path, family: str, declared: str, generated: str, weight: int = 400,
         roles: tuple[str, ...] = ("global-ui",)) -> dict:
    return {
        "family": family,
        "familyNormalized": overlay.normalize(family),
        "familyAttributes": {},
        "sourceXml": str(source),
        "declared": declared,
        "postScriptName": "",
        "weight": weight,
        "style": "normal",
        "index": 0,
        "axes": "",
        "roles": list(roles),
        "replaceable": True,
        "stockPath": declared,
        "planStatus": "ready",
        "planReason": "",
        "generatedFile": generated,
        "generatedBytes": 4096,
        "signature": generated,
    }


def tree_bytes(case: Path) -> dict[str, bytes]:
    root = case / "overlay"
    result = {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    # The manifest records absolute stage paths; make them case-independent.
    if "overlay-manifest.json" in result:
        result["overlay-manifest.json"] = result["overlay-manifest.json"].replace(
            str(case).encode(), b"<case>")
    return result


def check_name_parity() -> None:
    inventory = set(p for p in scan.XML_PATTERNS if p.startswith(("hyper_", "miui_")))
    assert inventory == set(SEED_PATTERNS), inventory
    assert set(seedxml.SEED_PATTERNS) == set(SEED_PATTERNS)
    template = (ROOT / "common/device_font_template.sh").read_text(encoding="utf-8")
    for pattern in SEED_PATTERNS:
        assert f"-name '{pattern}'" in template, pattern
    partitions = (ROOT / "common/font_config_partitions.sh").read_text(encoding="utf-8")
    names = re.search(r"_luoshu_font_config_xml_names\(\) \{\n\s*printf '%s\\n' '([^']*)'", partitions)
    assert names, "font_config_partitions name list not found"
    listed = set(names.group(1).split())
    for pattern in SEED_PATTERNS:
        assert pattern.replace("*", "") in listed, pattern
    # Seeds must never become slot-template input; only the experiment reads them.
    collect = template.split("collect_xml() {", 1)[1].split("\n}\n", 1)[0]
    for pattern in SEED_PATTERNS:
        assert pattern not in collect.split("collect_hyperos_seed_xml", 1)[0], pattern


def shell_functions(names: list[str]) -> str:
    text = (ROOT / "common/device_font_template.sh").read_text(encoding="utf-8")
    chunks = []
    for name in names:
        match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.S | re.M)
        assert match, name
        chunks.append(match.group(0))
    return "\n".join(chunks)


def check_shell_discovery(base: Path) -> None:
    seed_etc = base / "sh/system_ext/etc"
    system_etc = base / "sh/system/etc"
    write(seed_etc / "miui_fonts.xml", MIUI_FONTS)
    write(seed_etc / "hyper_font_fallback.xml", MIUI_FALLBACK)
    write(seed_etc / "fonts_customization.xml", SYSTEM_FONTS)  # not a seed
    system_etc.mkdir(parents=True, exist_ok=True)
    os.symlink("/data/system/fonts/theme_webview/fonts.xml", system_etc / "fonts.xml")
    write(system_etc / "font_fallback.xml", SYSTEM_FALLBACK)
    script = shell_functions(["collect_hyperos_seed_xml", "record_xml_links"]) + (
        '\ncollect_hyperos_seed_xml "$OUT.seeds" || exit 3\n'
        'record_xml_links "$OUT" "$OUT.seeds" || exit 4\n'
    )
    out = base / "sh/links.conf"
    env = dict(os.environ, OUT=str(out), LUOSHU_HYPEROS_SEED_ETC_ROOT=str(seed_etc),
               LUOSHU_HYPEROS_SYSTEM_ETC_ROOT=str(system_etc))
    subprocess.run(["sh", "-c", script], check=True, env=env)
    seeds = sorted(Path(line).name for line in Path(str(out) + ".seeds").read_text().split())
    assert seeds == ["hyper_font_fallback.xml", "miui_fonts.xml"], seeds
    rows = {line.split("|")[0]: line.split("|") for line in out.read_text().splitlines()}
    fonts = rows[str(system_etc / "fonts.xml")]
    assert fonts[1] == "symlink" and fonts[2] == "/data/system/fonts/theme_webview/fonts.xml", fonts
    assert fonts[4] == "1", fonts
    assert rows[str(system_etc / "font_fallback.xml")][1:2] == ["file"]
    assert rows[str(seed_etc / "miui_fonts.xml")][4] == "0"


def check_inventory_links(base: Path) -> None:
    etc = base / "inv/system/etc"
    sx = base / "inv/system_ext/etc"
    etc.mkdir(parents=True)
    os.symlink("/data/system/fonts/theme_webview/fonts.xml", etc / "fonts.xml")
    os.symlink("/data/system/fonts/theme_webview/font_fallback.xml", etc / "font_fallback.xml")
    write(sx / "miui_fonts.xml", MIUI_FONTS)
    chains = scan._xml_link_chains([
        ("system", Path("/system/etc"), etc),
        ("system_ext", Path("/system_ext/etc"), sx),
    ])
    assert [c["path"] for c in chains] == ["/system/etc/font_fallback.xml", "/system/etc/fonts.xml"], chains
    assert all(c["dataSeeded"] for c in chains), chains


def make_fixture(base: Path) -> dict:
    sys_fonts = base / "rom/system/etc/fonts.xml"
    sys_fallback = base / "rom/system/etc/font_fallback.xml"
    write(sys_fonts, SYSTEM_FONTS)
    write(sys_fallback, SYSTEM_FALLBACK)
    seed_etc = base / "rom/system_ext/etc"
    write(seed_etc / "miui_fonts.xml", MIUI_FONTS)
    write(seed_etc / "hyper_fonts.xml", HYPER_FONTS)
    write(seed_etc / "miui_font_fallback.xml", MIUI_FALLBACK)
    payload_root = base / "payload"
    for name in ("LuoShuSlot-ui-400.ttf", "LuoShuSlot-ui-700.ttf", "LuoShuSlot-mono-400.ttf"):
        write(payload_root / "fonts" / name, (name.encode() + b"\0") * 256)
    slots = [
        slot(sys_fonts, "sans-serif", "Roboto-Regular.ttf", "LuoShuSlot-ui-400.ttf"),
        slot(sys_fonts, "sans-serif", "Roboto-Regular.ttf", "LuoShuSlot-ui-700.ttf", 700),
        slot(sys_fonts, "serif-monospace", "CutiveMono.ttf", "LuoShuSlot-mono-400.ttf", roles=("mono",)),
        slot(sys_fallback, "sans-serif", "Roboto-Regular.ttf", "LuoShuSlot-ui-400.ttf"),
        slot(sys_fallback, "sans-serif", "Roboto-Regular.ttf", "LuoShuSlot-ui-700.ttf", 700),
        slot(sys_fallback, "serif-monospace", "CutiveMono.ttf", "LuoShuSlot-mono-400.ttf", roles=("mono",)),
    ]
    template = {
        "schema": "device-font-template-v1",
        "fingerprint": "hyperos-seed-fixture",
        "xml": [str(sys_fallback), str(sys_fonts)],
        "slots": [],
    }
    payload = {"schema": "device-font-payload-v1", "deviceFingerprint": "hyperos-seed-fixture", "slots": slots}
    return {"template": template, "payload": payload, "payload_root": payload_root, "seed_etc": seed_etc,
            "system_etc": base / "rom/system/etc"}


def render(fx: dict, case: Path, conf: str | None, env_extra: dict | None = None) -> dict:
    # Every case renders into <case>/overlay so manifest paths stay comparable.
    case.mkdir(parents=True, exist_ok=True)
    out = case / "overlay"
    conf_path = case / "hyperos_source_xml.conf"
    if conf is not None:
        conf_path.write_text(conf, encoding="utf-8")
    env = {
        "LUOSHU_HYPEROS_SOURCE_XML_CONF": str(conf_path),
        "LUOSHU_HYPEROS_SEED_ETC_ROOT": str(fx["seed_etc"]),
        "LUOSHU_HYPEROS_SYSTEM_ETC_ROOT": str(fx["system_etc"]),
        "LUOSHU_HYPEROS_SOURCE_XML_LOG": str(case / "hyperos-source-xml.log"),
        "LUOSHU_SELF_MOUNT_STATE_ROOT": str(case / "no-self-mount"),
        **(env_extra or {}),
    }
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    original_partition = overlay.partition_for_xml
    original_primary = overlay.PRIMARY_SYSTEM_XMLS
    try:
        overlay.partition_for_xml = lambda value: "system"
        overlay.PRIMARY_SYSTEM_XMLS = tuple(fx["template"]["xml"])
        return overlay.render_overlay(fx["template"], fx["payload"], fx["payload_root"], out)
    finally:
        overlay.partition_for_xml = original_partition
        overlay.PRIMARY_SYSTEM_XMLS = original_primary
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def staged_system_xml(tree: dict[str, bytes]) -> dict[str, bytes]:
    return {k: v for k, v in tree.items() if k.startswith("system_ext/")}


def check_flag_off_identical(base: Path, fx: dict) -> dict[str, bytes]:
    # Proof that with an explicit enabled=0 the rewrite never runs at all.
    real_apply = seedxml.apply

    def forbidden(*_args, **_kwargs):
        raise AssertionError("hyperos_source_xml.apply must not run when disabled")

    seedxml.apply = forbidden
    try:
        render(fx, base / "off-zero", "enabled=0\n")
        render(fx, base / "off-zero-comment", "# user turned it off\nenabled=0\n")
    finally:
        seedxml.apply = real_apply
    reference = tree_bytes(base / "off-zero")
    assert tree_bytes(base / "off-zero-comment") == reference
    assert not staged_system_xml(reference), reference.keys()
    manifest = json.loads(reference["overlay-manifest.json"])
    assert "hyperosSourceXml" not in manifest
    assert not (base / "off-zero/hyperos-source-xml.log").exists()
    return reference


def check_default_on(base: Path, fx: dict) -> None:
    # Missing conf, enabled=1 and anything that is not an exact enabled=0 all run it.
    trees = []
    for name, conf in (("default-missing", None), ("default-one", "enabled=1\n"),
                       ("default-garbage", "enabled=false\n enabled=0\nenabled=0 \n")):
        report = render(fx, base / name, conf)
        assert report["hyperosSourceXml"]["status"] == "applied", (name, report["hyperosSourceXml"])
        trees.append(tree_bytes(base / name))
    assert trees[0] == trees[1] == trees[2]


def check_flag_on(base: Path, fx: dict, reference: dict[str, bytes]) -> None:
    out = base / "on"
    report = render(fx, out, "enabled=1\n")
    hx = report["hyperosSourceXml"]
    assert hx["status"] == "applied", hx
    assert hx["schema"] == "hyperos-source-xml-v2"
    links = {item["path"]: item for item in hx["links"]}
    assert links["/system/etc/fonts.xml"]["kind"] == "file"
    tree = tree_bytes(out)
    staged = staged_system_xml(tree)
    assert sorted(staged) == [
        "system_ext/etc/hyper_fonts.xml",
        "system_ext/etc/miui_font_fallback.xml",
        "system_ext/etc/miui_fonts.xml",
    ], sorted(staged)
    for name, original in (("miui_fonts.xml", MIUI_FONTS), ("hyper_fonts.xml", HYPER_FONTS)):
        expected = (
            original
            .replace(">Roboto-Regular.ttf\n            <axis", ">LuoShuSlot-ui-400.ttf\n            <axis", 1)
            .replace(">Roboto-Regular.ttf<axis tag=\"wght\" stylevalue=\"700\"/>",
                     ">LuoShuSlot-ui-700.ttf<axis tag=\"wght\" stylevalue=\"700\"/>", 1)
            .replace(">CutiveMono.ttf<", ">LuoShuSlot-mono-400.ttf<", 1)
        ).encode("utf-8")
        assert staged[f"system_ext/etc/{name}"] == expected, staged[f"system_ext/etc/{name}"].decode()
        # The commented-out Roboto node, MiSansVF, the TTC index node and CRLF stay stock.
        assert b"<!-- <font weight=\"400\" style=\"normal\">Roboto-Regular.ttf</font> -->" in expected
        assert b"index=\"2\">NotoSansCJK-Regular.ttc<" in expected and b"\r\n" in expected
    fallback = staged["system_ext/etc/miui_font_fallback.xml"].decode()
    assert fallback == MIUI_FALLBACK.replace(">Roboto-Regular.ttf<", ">LuoShuSlot-ui-400.ttf<"), fallback
    for name in ("LuoShuSlot-ui-400.ttf", "LuoShuSlot-ui-700.ttf", "LuoShuSlot-mono-400.ttf"):
        assert f"system/fonts/{name}" in tree, name
    # Regular (non-seeded) /system/etc XML the main renderer did not stage is
    # rewritten by the same per-slot mapping.
    expected_system = (SYSTEM_FONTS.replace("'400' style='normal'>Roboto-Regular.ttf", "'400' style='normal'>LuoShuSlot-ui-400.ttf")
                       .replace("'700' style='normal'>Roboto-Regular.ttf", "'700' style='normal'>LuoShuSlot-ui-700.ttf")
                       .replace(">CutiveMono.ttf<", ">LuoShuSlot-mono-400.ttf<"))
    assert tree["system/etc/fonts.xml"].decode() == expected_system, tree["system/etc/fonts.xml"].decode()
    assert {e["source"] for e in hx["extra"]} == {"/system/etc/fonts.xml", "/system/etc/font_fallback.xml"}
    # Everything the main renderer produced is unchanged apart from the manifest.
    for key, value in reference.items():
        if key != "overlay-manifest.json":
            assert tree.get(key) == value, key
    assert (base / "on/hyperos-source-xml.log").read_text(encoding="utf-8").count('"status":"applied"') == 1


def check_fail_closed(base: Path, fx: dict, reference: dict[str, bytes]) -> None:
    def assert_noop(name: str, report: dict, reason_part: str) -> None:
        hx = report["hyperosSourceXml"]
        assert hx["status"] == "error" and reason_part in hx["reason"], hx
        tree = tree_bytes(base / name)
        assert not staged_system_xml(tree), name
        for key, value in reference.items():
            if key != "overlay-manifest.json":
                assert tree.get(key) == value, (name, key)
        assert set(tree) == set(reference), (name, set(tree) ^ set(reference))

    # Seed is not stock (already a LuoShu view): do nothing.
    dirty = base / "dirty-etc"
    for item in fx["seed_etc"].iterdir():
        write(dirty / item.name, item.read_bytes())
    write(dirty / "miui_fonts.xml", MIUI_FONTS.replace("MiSansVF.ttf", "LuoShuSlot-old-400.ttf"))
    assert_noop("dirty", render(fx, base / "dirty", "enabled=1\n",
                                {"LUOSHU_HYPEROS_SEED_ETC_ROOT": str(dirty)}), "not a stock view")

    # One broken seed aborts every seed, including ones that would have rewritten fine.
    broken = base / "broken-etc"
    for item in fx["seed_etc"].iterdir():
        write(broken / item.name, item.read_bytes())
    write(broken / "miui_fonts.xml", MIUI_FONTS.replace("</familyset>", ""))
    assert_noop("broken", render(fx, base / "broken", "enabled=1\n",
                                 {"LUOSHU_HYPEROS_SEED_ETC_ROOT": str(broken)}), "parse")

    # A mapped node that carries a collection index is refused by the text rewriter.
    raw = MIUI_FALLBACK.replace("style='normal'>Roboto", "style='normal' index='1'>Roboto").encode()
    root = seedxml._parse_bytes(raw)
    try:
        seedxml.rewrite_text(raw, root, {0: "LuoShuSlot-ui-400.ttf"})
    except seedxml.SourceXmlError as error:
        assert "collection index" in str(error), error
    else:
        raise AssertionError("collection index must be refused")
    # An unsafe replacement name is refused too.
    root = seedxml._parse_bytes(MIUI_FALLBACK.encode())
    try:
        seedxml.rewrite_text(MIUI_FALLBACK.encode(), root, {0: "../evil.ttf"})
    except seedxml.SourceXmlError:
        pass
    else:
        raise AssertionError("unsafe generated name must be refused")

    # No seeds on this ROM: nothing staged, report says why.
    report = render(fx, base / "noseed", "enabled=1\n", {"LUOSHU_HYPEROS_SEED_ETC_ROOT": str(base / "absent")})
    assert report["hyperosSourceXml"]["status"] == "skipped"
    assert report["hyperosSourceXml"]["reason"] == "no-seed-xml"
    assert not staged_system_xml(tree_bytes(base / "noseed"))


def check_snapshot_preferred(base: Path, fx: dict) -> None:
    # A frozen stock snapshot wins over a live view that already carries LuoShu names.
    snap = base / "snap"
    write(snap / "system_ext/etc/miui_fonts.xml", MIUI_FONTS)
    live = base / "live-etc"
    write(live / "miui_fonts.xml", MIUI_FONTS.replace("Roboto-Regular.ttf", "LuoShuSlot-ui-400.ttf"))
    fx_snap = dict(fx)
    fx_snap["template"] = {**fx["template"], "xmlSourceRoot": str(snap)}
    report = render(fx_snap, base / "snapout", "enabled=1\n", {"LUOSHU_HYPEROS_SEED_ETC_ROOT": str(live)})
    hx = report["hyperosSourceXml"]
    assert hx["status"] == "applied" and hx["seeds"][0]["input"] == "template-snapshot", hx


def check_cache_key_flag(base: Path) -> None:
    """Cache sourceKey: no seed XML or enabled=0 == legacy key; HyperOS default changes it."""
    module = base / "cache-module"
    store = module / "system/fonts/.luoshu-font-store"
    store.mkdir(parents=True)
    (module / "config").mkdir()
    (store / "regular.font").write_bytes(b"font-data\n")
    conf = module / "config/hyperos_source_xml.conf"
    seeds = base / "cache-seeds"
    seeds.mkdir()
    script = '. "$ROOT/common/device_font_cache.sh"; _dfcache_source_key'
    env = dict(os.environ, ROOT=str(ROOT), MODULE_DIR=str(module), MODDIR=str(module),
               LUOSHU_CACHE_AUTOSTART="0", LUOSHU_HYPEROS_SEED_ETC_ROOT=str(seeds))

    def key() -> str:
        return subprocess.run(["sh", "-c", script], check=True, env=env,
                              capture_output=True, text=True).stdout.strip()

    digest = hashlib.sha256(b"font-data\n").hexdigest()
    legacy = hashlib.sha256(f"source-contract-v5-content\nregular.font|{digest}\n".encode()).hexdigest()
    expected_on = hashlib.sha256(
        f"source-contract-v5-content\nhyperos-source-xml-v2\nregular.font|{digest}\n".encode()).hexdigest()
    # Non-HyperOS (no seeds): unchanged identity whatever the flag says.
    assert key() == legacy
    conf.write_text("enabled=1\n")
    assert key() == legacy
    conf.unlink()
    write(seeds / "miui_fonts.xml", MIUI_FONTS)
    assert key() == expected_on and expected_on != legacy
    for text in ("enabled=1\n", "enabled=true\n", " enabled=0\n", "enabled=0 \n"):
        conf.write_text(text)
        assert key() == expected_on, text
    conf.write_text("# off\nenabled=0\n")
    assert key() == legacy


def check_policy_and_lang_routing(base: Path, fx: dict) -> None:
    """Mono files only take mono builds; zh families follow a CJK-capable user font."""
    raw = (
        "<?xml version='1.0' encoding='utf-8'?>\n"
        "<familyset>\n"
        "  <family name='sans-serif'><font weight='400' style='normal'>Roboto-Regular.ttf</font></family>\n"
        "  <family name='monospace'><font weight='400' style='normal'>DroidSansMono.ttf</font></family>\n"
        "  <family lang='zh-Hans'><font weight='400' style='normal'>NotoSansSC-Regular.otf</font>\n"
        "    <font weight='700' style='normal'>NotoSansSC-Bold.otf</font></family>\n"
        "  <family lang='zh-Hant zh-Bopo'><font weight='400' style='normal'>NotoSansTC-Regular.otf</font></family>\n"
        "  <family lang='zh-Hans ja'><font weight='400' style='normal'>NotoSansSC-Regular.otf</font></family>\n"
        "  <family lang='zh-HK'><font weight='400' style='normal' index='1'>NotoSansCJK-Regular.ttc</font></family>\n"
        "  <family lang='zh-Hant'><font weight='400' style='normal'>NotoSerifTC-Regular.otf</font></family>\n"
        "  <family lang='zh-Hans' variant='compact'><font weight='400' style='normal'>NotoSansSC-Regular.otf</font></family>\n"
        "</familyset>\n").encode()
    root = seedxml._parse_bytes(raw)
    source = base / "routing.xml"
    slots = [slot(source, "sans-serif", "Roboto-Regular.ttf", "LuoShuSlot-ui-400.ttf"),
             slot(source, "sans-serif", "Roboto-Regular.ttf", "LuoShuSlot-ui-700.ttf", 700),
             slot(source, "monospace", "DroidSansMono.ttf", "LuoShuSlot-prop-400.ttf")]
    # Proportional build for a Mono file: kept stock.
    mapping, notes = seedxml.plan_mapping(root, slots, "fonts.xml", None)
    assert mapping == {0: "LuoShuSlot-ui-400.ttf"}, mapping
    assert "policy-kept:DroidSansMono.ttf" in notes, notes
    # Mono-role build (stock-exact advances): allowed.
    mono_slots = slots[:2] + [slot(source, "monospace", "DroidSansMono.ttf", "LuoShuSlot-mono-400.ttf", roles=("mono",))]
    mapping, _notes = seedxml.plan_mapping(root, mono_slots, "fonts.xml", None)
    assert mapping[1] == "LuoShuSlot-mono-400.ttf", mapping
    # zh routing: simplified-only coverage routes zh-Hans, not zh-Hant.
    counts = {"LuoShuSlot-ui-400.ttf": 7000, "LuoShuSlot-ui-700.ttf": 7000}
    targets = seedxml.cjk_route_targets(slots, lambda name: counts.get(name, 0))
    assert targets == {400: ("LuoShuSlot-ui-400.ttf", 7000), 700: ("LuoShuSlot-ui-700.ttf", 7000)}, targets
    mapping, notes = seedxml.plan_mapping(root, slots, "fonts.xml", targets)
    assert mapping == {0: "LuoShuSlot-ui-400.ttf", 2: "LuoShuSlot-ui-400.ttf", 3: "LuoShuSlot-ui-700.ttf"}, mapping
    assert any(note.startswith("cjk-coverage-low:NotoSansTC-Regular.otf") for note in notes), notes
    assert any(note.startswith("cjk-coverage-low:NotoSerifTC-Regular.otf") for note in notes), notes
    # Full Big5 coverage routes zh-Hant (incl. AOSP "zh-Hant zh-Bopo") sans files;
    # a zh+ja family, a TTC index, serif and variant families stay stock.
    counts = {"LuoShuSlot-ui-400.ttf": 20000, "LuoShuSlot-ui-700.ttf": 20000}
    targets = seedxml.cjk_route_targets(slots, lambda name: counts.get(name, 0))
    mapping, notes = seedxml.plan_mapping(root, slots, "fonts.xml", targets)
    assert mapping.get(4) == "LuoShuSlot-ui-400.ttf", mapping
    assert 5 not in mapping and 6 not in mapping and 7 not in mapping and 8 not in mapping, mapping
    assert "cjk-kept:NotoSansCJK-Regular.ttc" in notes and "policy-kept:NotoSerifTC-Regular.otf" in notes, notes
    assert seedxml.cjk_lang_min({"lang": "zh-Hant zh-Bopo"}) == 13000
    assert seedxml.cjk_lang_min({"lang": "zh-Hans ja"}) == 0
    assert seedxml.cjk_lang_min({"lang": "zh-HK"}) == 13000

    # End-to-end apply: routed zh family in a seed is staged and validated.
    seed_etc = base / "route-rom/system_ext/etc"
    write(seed_etc / "miui_fonts.xml", raw.decode())
    payload_root = base / "route-payload"
    for name in ("LuoShuSlot-ui-400.ttf", "LuoShuSlot-ui-700.ttf", "LuoShuSlot-prop-400.ttf"):
        write(payload_root / "fonts" / name, (name.encode() + b"\0") * 256)
    stage = base / "route-stage"
    stage.mkdir()
    copied: dict = {}
    env = {"LUOSHU_HYPEROS_SEED_ETC_ROOT": str(seed_etc),
           "LUOSHU_HYPEROS_SYSTEM_ETC_ROOT": str(base / "route-rom/system/etc"),
           "LUOSHU_HYPEROS_PRODUCT_ETC_ROOT": str(base / "route-rom/product/etc"),
           "LUOSHU_HYPEROS_SOURCE_XML_LOG": str(base / "route.log"),
           "LUOSHU_SELF_MOUNT_STATE_ROOT": str(base / "no-self-mount")}
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        report = seedxml.apply({}, slots, payload_root, stage, copied, overlay.copy_generated,
                               han_count=lambda name: 7000)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    assert report["status"] == "applied", report
    staged = (stage / "system_ext/etc/miui_fonts.xml").read_text()
    assert ">LuoShuSlot-ui-400.ttf</font>\n    <font weight='700' style='normal'>LuoShuSlot-ui-700.ttf<" in staged, staged
    assert ">DroidSansMono.ttf<" in staged and ">NotoSansTC-Regular.otf<" in staged
    assert report["cjkRouting"]["400"]["file"] == "LuoShuSlot-ui-400.ttf"


def check_product_customization_and_strict_validation(base: Path) -> None:
    rom = base / "cust-rom"
    seed_etc = rom / "system_ext/etc"
    write(seed_etc / "miui_font_fallback.xml", MIUI_FALLBACK)
    product = rom / "product/etc/fonts_customization.xml"
    write(product, "<?xml version='1.0' encoding='utf-8'?>\n<fonts-modification version='1'>\n"
                   "  <family customizationType='new-named-family' name='sans-serif'>\n"
                   "    <font weight='400' style='normal'>Roboto-Regular.ttf</font>\n"
                   "  </family>\n</fonts-modification>\n")
    system_etc = rom / "system/etc"
    system_etc.mkdir(parents=True)
    # HyperOS 2+: data-seeded symlinks are reported, never replaced.
    os.symlink("/data/system/fonts/theme_webview/fonts.xml", system_etc / "fonts.xml")
    os.symlink("/data/system/fonts/theme_webview/font_fallback.xml", system_etc / "font_fallback.xml")
    payload_root = base / "cust-payload"
    write(payload_root / "fonts/LuoShuSlot-ui-400.ttf", b"x" * 4096)
    slots = [slot(product, "sans-serif", "Roboto-Regular.ttf", "LuoShuSlot-ui-400.ttf")]
    env = {"LUOSHU_HYPEROS_SEED_ETC_ROOT": str(seed_etc),
           "LUOSHU_HYPEROS_SYSTEM_ETC_ROOT": str(system_etc),
           "LUOSHU_HYPEROS_PRODUCT_ETC_ROOT": str(rom / "product/etc"),
           "LUOSHU_HYPEROS_SOURCE_XML_LOG": str(base / "cust.log"),
           "LUOSHU_SELF_MOUNT_STATE_ROOT": str(base / "no-self-mount")}

    def run(stage: Path, copy=overlay.copy_generated) -> dict:
        stage.mkdir()
        saved = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        try:
            return seedxml.apply({}, slots, payload_root, stage, {}, copy, han_count=lambda name: 0)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    stage = base / "cust-stage"
    report = run(stage)
    assert report["status"] == "applied", report
    assert sorted(report["stagedXml"]) == ["product/etc/fonts_customization.xml",
                                           "system_ext/etc/miui_font_fallback.xml"], report
    # Customization fonts resolve against /product/fonts: the build is staged there.
    assert (stage / "product/fonts/LuoShuSlot-ui-400.ttf").is_file()
    assert not (stage / "system/etc/fonts.xml").exists()
    assert all(item["dataSeeded"] for item in report["links"]), report["links"]
    # The main renderer already staged the customization file: skipped, not an error.
    stage2 = base / "cust-stage2"
    write(stage2 / "product/etc/fonts_customization.xml", b"<main/>")
    stage2_report = None
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        stage2_report = seedxml.apply({}, slots, payload_root, stage2, {}, overlay.copy_generated,
                                      han_count=lambda name: 0)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    assert stage2_report["status"] == "applied", stage2_report
    assert stage2_report["extra"][0]["skipped"] == "staged-by-main-renderer"
    assert (stage2 / "product/etc/fonts_customization.xml").read_bytes() == b"<main/>"

    # A rewritten reference that is not in the staged tree fails the whole step.
    def fake_copy(payload, stage_dir, partition, name, copied):
        path = stage_dir / partition / "fonts" / name
        copied[(partition, name)] = path
        return path  # never actually written

    stage3 = base / "cust-stage3"
    report = run(stage3, fake_copy)
    assert report["status"] == "error" and "missing from staged" in report["reason"], report
    assert not any(stage3.rglob("*.xml")), list(stage3.rglob("*"))

    # Direct validator: names unresolved on this ROM before are tolerated; a
    # rewritten name outside the staged tree, or a family losing a font, fails.
    original = MIUI_FALLBACK.encode()
    seedxml.validate_references(original, original, stage, "system", rom / "fonts-absent")
    for broken, reason in (
        (original.replace(b"NotoColorEmoji.ttf", b"Missing.ttf"), "missing from staged"),
        (original.replace(b"<font weight='400' style='normal'>NotoColorEmoji.ttf</font>", b""), "lost fonts"),
    ):
        try:
            seedxml.validate_references(original, broken, stage, "system", rom / "fonts-absent")
        except seedxml.SourceXmlError as error:
            assert reason in str(error), (reason, error)
        else:
            raise AssertionError(reason)


def main() -> None:
    check_name_parity()
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        check_shell_discovery(base)
        check_inventory_links(base)
        check_cache_key_flag(base)
        fx = make_fixture(base)
        reference = check_flag_off_identical(base, fx)
        check_default_on(base, fx)
        check_flag_on(base, fx, reference)
        check_fail_closed(base, fx, reference)
        check_snapshot_preferred(base, fx)
        check_policy_and_lang_routing(base, fx)
        check_product_customization_and_strict_validation(base)
    print("hyperos_source_xml_test: ok")


if __name__ == "__main__":
    main()
