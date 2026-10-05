#!/usr/bin/env python3
"""Engine diagnostic bundle: device-side export and host-side replay round trip."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

import dataclasses
import errno
from unittest import mock

import font_role_shadow
import luoshu_engine
import font_fixtures as composite
import font_fixtures as fixture


def process_font_evidence(temp: Path) -> None:
    """Maps evidence must retain unknown sources without calling them rendered fonts."""
    import luoshu_diagnostics

    proc = temp / "proc"
    maps = "\n".join((
        "1000-2000 r--p 00000000 fd:00 11 /system/fonts/Roboto-Regular.ttf",
        "2000-3000 r--p 00001000 fd:00 12 /data/user/0/com.example.fontconsumer/cache/Latin.ttf (deleted)",
        "3000-4000 r--p 00002000 fd:00 13 /data/app/com.example.fontconsumer/base.apk",
        "4000-5000 r--p 00000000 fd:00 14 /data/user/0/com.example.fontconsumer/files/fonts/opaque-cache",
        "5000-6000 r--p 00000000 00:01 15 /memfd:font-buffer (deleted)",
        "6000-7000 r--p 00000000 00:00 0 [anon:font-cache]",
        "7000-8000 r--p 00000000 00:01 16 /memfd:jit-cache (deleted)",
        "8000-9000 rw-p 00000000 00:00 0",
        "9000-a000 r--p 00000000 fd:00 17 /data/user/0/com.example.fontconsumer/files/chat.db",
        "a000-b000 r--p 00000000 fd:00 18 /data/user/0/com.example.fontconsumer/cache/web.woff2",
        "b000-c000 r--p 00000000 fd:00 11 /system/fonts/Roboto-Regular.ttf",
        "c000-d000 r--p 00000000 invalid-device 99 /system/fonts/Invalid.ttf",
        "d000-e000 r--p 00000000 fd:01 11 /system/fonts/Roboto-Regular.ttf",
        "e000-f000 r--p 00000000 fd:00 19 /data/user/0/com.example.fontconsumer/cache/opaque-font-cache",
    )) + "\n"
    for pid, name in ((101, "com.example.fontconsumer"), (102, "com.example.denied"),
                      (103, "com.example.exited"), (104, "com.example.hidden"),
                      (105, ""), (106, "com.example.noobservedfont")):
        entry = proc / str(pid)
        entry.mkdir(parents=True)
        (entry / "cmdline").write_bytes(name.encode() + b"\0private-argument-not-exported\0")
        if pid != 103:
            (entry / "maps").write_text(maps if pid == 101 else "1000-2000 rw-p 00000000 00:00 0\n")
    real_open, real_read = Path.open, Path.read_bytes

    def maps_open(path: Path, *args, **kwargs):
        if path == proc / "102/maps":
            raise PermissionError(errno.EACCES, "permission denied")
        return real_open(path, *args, **kwargs)

    def cmdline_read(path: Path):
        if path == proc / "104/cmdline":
            raise PermissionError(errno.EACCES, "permission denied")
        return real_read(path)

    with mock.patch.object(Path, "open", maps_open), mock.patch.object(Path, "read_bytes", cmdline_read):
        observed = luoshu_diagnostics._process_fonts(proc)
    rows = {row["pid"]: row for row in observed["processes"]}
    fonts = rows[101]["fonts"]
    assert any(row.get("deleted") and row["inode"] == "12" for row in fonts), "deleted font mapping was dropped"
    assert observed["capturedAt"] <= observed["finishedAt"]
    assert observed["renderingVerified"] is False
    assert rows[101]["mapsStatus"] == "read"
    assert rows[101]["fontSourceStatus"] == "unconfirmed"
    assert rows[101]["apkMaps"] == [{"path": "/data/app/com.example.fontconsumer/base.apk", "device": "fd:00", "inode": "13", "offset": "00002000"}]
    assert {row["inode"] for row in rows[101]["fontCandidates"]} == {"14", "15", "0", "19"}
    assert {row["kind"] for row in rows[101]["fontCandidates"]} == {"font-cache-path", "font-named-memory"}
    assert "apk-font-use-unconfirmed" in rows[101]["unknownSources"]
    assert "opaque-or-memory-font-use-unconfirmed" in rows[101]["unknownSources"]
    assert any(row["path"].endswith("web.woff2") for row in fonts)
    roboto_maps = [row for row in fonts if row["inode"] == "11"]
    assert len(roboto_maps) == 2 and {row["device"] for row in roboto_maps} == {"fd:00", "fd:01"}, "maps identity lost the device or retained duplicates"
    serialized = json.dumps(observed)
    assert "chat.db" not in serialized and "jit-cache" not in serialized
    assert "invalid-device" not in serialized
    assert "private-argument" not in serialized
    assert rows[102]["mapsStatus"] == "unavailable" and rows[102]["mapsError"] == "EACCES"
    assert rows[103]["mapsStatus"] == "unavailable" and rows[103]["mapsError"] == "ENOENT"
    assert "maps-unavailable" in rows[102]["unknownSources"]
    assert observed["processReadErrors"] == [{"pid": 104, "reason": "cmdline-unavailable", "error": "EACCES"}]
    assert 105 not in rows, "empty kernel cmdline became an inferred app"
    assert rows[106]["mapsStatus"] == "read" and rows[106]["fonts"] == []
    assert "no-font-source-observed" in rows[106]["unknownSources"]
    assert {row["process"] for row in observed["processes"]} == {
        "com.example.fontconsumer", "com.example.denied", "com.example.exited", "com.example.noobservedfont"}
    assert observed["observedProcessNames"] == sorted(row["process"] for row in observed["processes"])
    assert observed["namedProcessCount"] == 4 and observed["cmdlineUnreadableCount"] == 1
    with mock.patch.object(Path, "open", maps_open), mock.patch.object(Path, "read_bytes", cmdline_read), \
            mock.patch.object(luoshu_diagnostics, "PROCESS_MAP_LIMIT", 1), \
            mock.patch.object(luoshu_diagnostics, "PROCESS_EVIDENCE_LIMIT", 3), \
            mock.patch.object(luoshu_diagnostics, "PROCESS_READ_ERROR_LIMIT", 0):
        limited = luoshu_diagnostics._process_fonts(proc)
    assert limited["truncated"] and len(limited["processes"]) == 3
    assert limited["namedProcessCount"] == 4 and limited["processReadErrorsTruncated"]
    assert limited["processes"][0]["mapsTruncated"] == {"fonts": True, "apkMaps": False, "fontCandidates": True}
    assert "map-evidence-truncated" in limited["processes"][0]["unknownSources"]
    missing_proc = luoshu_diagnostics._process_fonts(temp / "absent-proc")
    assert missing_proc["procStatus"] == "unavailable" and missing_proc["procError"] == "ENOENT"

    class InterruptedMaps:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            yield maps.splitlines()[0]
            raise OSError(errno.EIO, "maps read interrupted")

    def interrupted_open(path: Path, *args, **kwargs):
        return InterruptedMaps() if path == proc / "101/maps" else maps_open(path, *args, **kwargs)

    with mock.patch.object(Path, "open", interrupted_open), mock.patch.object(Path, "read_bytes", cmdline_read):
        interrupted = luoshu_diagnostics._process_fonts(proc)
    partial = next(row for row in interrupted["processes"] if row["pid"] == 101)
    assert partial["mapsStatus"] == "partial" and partial["mapsError"] == "EIO"
    assert len(partial["fonts"]) == 1 and "maps-partially-read" in partial["unknownSources"]


def latin_ligature_evidence(temp: Path) -> None:
    import luoshu_diagnostics
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont

    source = temp / "Ligature.ttf"
    fixture.make_font(source, family="Ligature Source")
    with TTFont(source) as font:
        for name in ("f_i", "unused_nontext"):
            pen = TTGlyphPen(None)
            # Keep these inside every ASCII glyph's bounds, so the extrema
            # safeguard cannot accidentally retain the unencoded ligature.
            pen.moveTo((80, 0))
            pen.lineTo((400, 0))
            pen.lineTo((400, 400))
            pen.lineTo((80, 400))
            pen.closePath()
            font["glyf"].glyphs[name] = pen.glyph()
            font["hmtx"].metrics[name] = (560, 80)
        font.setGlyphOrder([*font.getGlyphOrder(), "f_i", "unused_nontext"])
        addOpenTypeFeaturesFromString(font, "feature liga { sub u0066 u0069 by f_i; } liga;")
        font.save(source)
    hollow = temp / "LigatureHollow.ttf"
    luoshu_diagnostics._hollow(source, hollow, luoshu_diagnostics._keep_codepoints())
    with TTFont(source) as original, TTFont(hollow) as result:
        assert result.getTableData("LSDG") == luoshu_diagnostics.HOLLOW_MARKER_DATA
        assert result["glyf"]["f_i"].numberOfContours > 0, "Latin GSUB ligature was hollowed"
        assert result["glyf"]["f_i"].getCoordinates(result["glyf"]) == original["glyf"]["f_i"].getCoordinates(original["glyf"])
        assert result["glyf"]["unused_nontext"].numberOfContours == 0, "unreferenced glyph was unnecessarily retained"


def partial_stock_evidence(temp: Path) -> None:
    import luoshu_diagnostics

    directory = temp / "partial"
    directory.mkdir()
    moddir = directory / "module"
    config = moddir / "config"
    (config / "luoshu-engine-build").mkdir(parents=True)
    (moddir / "module.prop").write_text("id=LuoShu\nversion=test\nversionCode=1\n")
    (config / "active_font.conf").write_text("mix\n")
    slots = {}
    stock_files = {}
    for name, family in (("Roboto-Regular.ttf", "sans-serif"), ("NotoSerif-Regular.ttf", "serif"),
                         ("NotoSerif-Bold.ttf", "serif"), ("DroidSansMono.ttf", "monospace")):
        stock = directory / name
        fixture.make_font(stock, family="Stock " + family)
        logical = "/system/fonts/" + name
        slots[logical] = fixture.slot_from_stock(logical, stock, family=family,
            source_xml="/system/etc/fonts.xml", declared=name)
        stock_files[logical] = stock
    large = stock_files["/system/fonts/NotoSerif-Bold.ttf"]
    with large.open("ab") as handle:
        handle.write(b"\0" * (luoshu_diagnostics.SMALL_PRESERVED_LIMIT + 1))
    topology = {"schema": "device-font-topology-v1", "state": "ready", "slots": slots}
    (config / "device_font_topology.json").write_text(json.dumps(topology))
    roles, _shadow = font_role_shadow.build(topology)
    (config / "device_font_roles.json").write_text(json.dumps(roles))
    # This is a real old-report shape: only the UI file was replaced. The
    # eligible protected text bases must still be available to the new replay.
    report = {"replaced": [{"path": "/system/fonts/Roboto-Regular.ttf", "role": "ui-sans"}],
              "keptStock": [], "sources": {}}
    (config / "luoshu-engine-build/report.json").write_text(json.dumps(report))
    wanted = {path: action for path, _role, action in luoshu_diagnostics._wanted_slots(config)}
    assert wanted.get("/system/fonts/NotoSerif-Regular.ttf") == "partial-stock", "old build report lost the eligible serif stock base"
    assert wanted.get("/system/fonts/DroidSansMono.ttf") == "partial-stock"
    lower = directory / "lower-root"
    (lower / "lower/system-fonts").mkdir(parents=True)
    for logical, stock in stock_files.items():
        shutil.copy(stock, lower / "lower/system-fonts" / Path(logical).name)
    output = directory / "lite.zip"
    luoshu_diagnostics.export(moddir, output, lower)
    with zipfile.ZipFile(output) as archive:
        index = json.loads(archive.read("index.json"))
        for logical in ("/system/fonts/NotoSerif-Regular.ttf", "/system/fonts/DroidSansMono.ttf"):
            record = index["stock"][logical]
            assert record["action"] == "partial-stock" and record["hollow"] is False
            assert archive.read(record["file"]) == stock_files[logical].read_bytes(), "partial stock was not kept byte for byte"
        bold = index["stock"]["/system/fonts/NotoSerif-Bold.ttf"]
        assert bold["hollow"] is False and archive.read(bold["file"]) == large.read_bytes()
        assert index["stock"]["/system/fonts/Roboto-Regular.ttf"]["hollow"] is True
    luoshu_diagnostics.export(moddir, directory / "full.zip", lower, full=True)
    with zipfile.ZipFile(directory / "full.zip") as archive:
        index = json.loads(archive.read("index.json"))
        record = index["stock"]["/system/fonts/NotoSerif-Bold.ttf"]
        assert record["hollow"] is False and archive.read(record["file"]) == large.read_bytes()


def global_stock_audit_evidence(temp: Path) -> None:
    """Old reports must not hide unknown, fallback, collection or missing routes."""
    import luoshu_diagnostics
    from fontTools.ttLib import TTCollection, TTFont
    import struct
    import time

    directory = temp / "global-audit"
    directory.mkdir()
    moddir = directory / "module"
    config = moddir / "config"
    (config / "luoshu-engine-build").mkdir(parents=True)
    (moddir / "module.prop").write_text("id=LuoShu\nversion=test\nversionCode=1\n")
    (config / "active_font.conf").write_text("mix\n")
    stocks = {}
    slots = {}
    roles = {}
    for logical, family, role in (
        ("/system/fonts/Roboto-Regular.ttf", "sans-serif", "ui-sans"),
        ("/vendor/fonts/nested/OrdinaryMystery.ttf", "", "unknown-protected"),
        ("/product/fonts/UnknownText.ttf", "", "unknown-protected"),
        ("/product/fonts/LargeUnknown.ttf", "", "unknown-protected"),
        ("/system/fonts/LargeSerif.ttf", "serif", "serif"),
        ("/system/fonts/EmojiMono.ttf", "monospace", "monospace"),
        ("/system/fonts/Symbol.ttf", "", "symbol-icon"),
        ("/system/fonts/Missing.ttf", "", "unknown-protected"),
        ("/system/fonts/Unreadable.ttf", "", "unknown-protected"),
        ("/data/user/0/private/Hidden.ttf", "", "unknown-protected"),
    ):
        source = directory / Path(logical).name
        fixture.make_font(source, family="Stock " + (family or "Mystery"))
        if logical.endswith("/LargeUnknown.ttf"):
            with source.open("r+b") as handle:
                handle.truncate(luoshu_diagnostics.SMALL_PRESERVED_LIMIT + 1)
        if logical.endswith("/LargeSerif.ttf"):
            # A valid small sfnt plus a sparse trailing region exercises the
            # actual 64 MiB boundary without building huge glyph fixtures.
            with source.open("r+b") as handle:
                handle.truncate(luoshu_diagnostics.ORIGINAL_TEXT_FILE_LIMIT + 1)
        stocks[logical] = source
        slots[logical] = fixture.slot_from_stock(logical, source, family=family,
            source_xml=None, declared=source.name)
        roles[logical] = {"role": role}
    cjk_source = directory / "CJK.ttf"
    composite.make_cjk_font(cjk_source, family="Multiscript CJK", variable=True)
    logical_cjk = "/system/fonts/NotoSansCJK-Variable.ttc"
    cjk_collection = directory / "NotoSansCJK-Variable.ttc"
    collection = TTCollection()
    collection.fonts = [TTFont(cjk_source), TTFont(cjk_source)]
    collection.save(cjk_collection)
    collection.close()
    with cjk_collection.open("ab") as handle:
        handle.write(b"\0" * (luoshu_diagnostics.SMALL_PRESERVED_LIMIT + 1))
    stocks[logical_cjk] = cjk_collection
    slots[logical_cjk] = fixture.slot_from_stock(logical_cjk, cjk_collection, family="",
        source_xml="/system/etc/fonts.xml", declared=cjk_collection.name)
    slots[logical_cjk]["xmlRefs"][0]["familyAttributes"] = {"lang": "und-Zsye,zh-Hans"}
    roles[logical_cjk] = {"role": "special-fallback"}
    (config / "device_font_topology.json").write_text(json.dumps({"slots": slots}))
    (config / "device_font_roles.json").write_text(json.dumps({"slots": roles}))
    (config / "luoshu-engine-build/report.json").write_text(json.dumps({
        "replaced": [{"path": "/system/fonts/Roboto-Regular.ttf", "role": "ui-sans"},
                     {"path": "/system/fonts/Symbol.ttf", "role": "symbol-icon"}],
        # Even a stale report targeting a symbol never authorizes its export.
        "keptStock": [{"path": "/system/fonts/Symbol.ttf"}], "sources": {},
    }))
    lower = directory / "lower-root"
    for logical, source in stocks.items():
        if logical.startswith("/data/") or logical.endswith("/Missing.ttf"):
            continue
        parts = Path(logical).parts
        target = lower / "lower" / (parts[1] + "-fonts") / Path(*parts[3:])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)
    real_open = Path.open
    denied = lower / "lower/system-fonts/Unreadable.ttf"

    def guarded_open(path: Path, *args, **kwargs):
        assert "/data/user/" not in str(path), "diagnostic read App private content"
        if path == denied:
            raise PermissionError(errno.EACCES, "test snapshot permission denied")
        return real_open(path, *args, **kwargs)

    output = directory / "lite.zip"
    with mock.patch.object(Path, "open", guarded_open):
        luoshu_diagnostics.export(moddir, output, lower)
    with zipfile.ZipFile(output) as archive:
        index = json.loads(archive.read("index.json"))
        audit = index["stockCoverageAudit"]
        assert set(audit) == set(slots), "audit lost an unselected topology path"
        assert index["stockCoverageAuditSummary"]["pathCount"] == len(slots)
        for logical in ("/vendor/fonts/nested/OrdinaryMystery.ttf", "/product/fonts/UnknownText.ttf"):
            row = audit[logical]
            assert row["selected"] and row["probeStatus"] == "probed", row
            assert row["faces"][0]["asciiLetters"] == 52 and row["faces"][0]["asciiDigits"] == 10
            assert row["action"] == "audit-stock" and row["hollow"] is False
            assert archive.read(row["file"]) == stocks[logical].read_bytes()
        cjk_audit = audit[logical_cjk]
        assert cjk_audit["selected"] and cjk_audit["hollow"] is False
        assert archive.read(cjk_audit["file"]) == cjk_collection.read_bytes()
        assert cjk_audit["probeStatus"] == "probed" and cjk_audit["faceCount"] == 2
        for face in cjk_audit["faces"]:
            assert face["asciiLetters"] == 52 and face["asciiDigits"] == 10, face
            assert face["format"] == "TrueType" and face["variable"]
            assert face["axes"] == [{"tag": "wght", "min": 100.0, "default": 400.0, "max": 900.0}]
        huge = audit["/system/fonts/LargeSerif.ttf"]
        assert huge["probeStatus"] == "probed" and huge["faces"][0]["asciiLetters"] == 52
        assert not huge["selected"] and huge["skippedReason"] == "original-text-file-limit"
        unknown = audit["/product/fonts/LargeUnknown.ttf"]
        assert unknown["probeStatus"] == "probed" and unknown["faces"][0]["asciiDigits"] == 10
        assert not unknown["selected"] and unknown["skippedReason"] == "audit-stock-too-large"
        capture_summary = index["stockCoverageAuditSummary"]
        assert capture_summary["originalTextBytes"] == cjk_collection.stat().st_size
        assert capture_summary["originalTextFileLimit"] == 64 * 1024 * 1024
        assert capture_summary["originalTextTotalLimit"] == 160 * 1024 * 1024
        assert capture_summary["originalTextLimitApplied"] is True
        for logical in ("/system/fonts/EmojiMono.ttf", "/system/fonts/Symbol.ttf"):
            row = audit[logical]
            assert row["probeStatus"] == "excluded" and row["skippedReason"] == "excluded-emoji-or-symbol"
            assert row["faceCount"] is None and row["faces"] == [] and not row["selected"]
            assert logical not in index["stock"]
        assert audit["/data/user/0/private/Hidden.ttf"]["skippedReason"] == "unsupported-system-font-path"
        missing = audit["/system/fonts/Missing.ttf"]
        assert missing["probeStatus"] == "unavailable" and missing["faceCount"] is None and missing["faces"] == []
        denied_audit = audit["/system/fonts/Unreadable.ttf"]
        assert denied_audit["probeStatus"] == "unavailable" and not denied_audit["selected"]
        assert "PermissionError" in denied_audit["probeReason"]
        assert len(index["stockSkipped"]) == len(slots) - len(index["stock"])
    luoshu_diagnostics.export(moddir, directory / "full.zip", lower, full=True)
    with zipfile.ZipFile(directory / "full.zip") as archive:
        index = json.loads(archive.read("index.json"))
        row = index["stock"][logical_cjk]
        assert row["hollow"] is False and archive.read(row["file"]) == cjk_collection.read_bytes()
        huge = index["stock"]["/system/fonts/LargeSerif.ttf"]
        assert huge["hollow"] is False and archive.getinfo(huge["file"]).file_size == luoshu_diagnostics.ORIGINAL_TEXT_FILE_LIMIT + 1
        with archive.open(huge["file"]) as font, stocks["/system/fonts/LargeSerif.ttf"].open("rb") as original:
            assert font.read(256) == original.read(256)
        assert index["stockCoverageAuditSummary"]["originalTextLimitApplied"] is False

    # Lower the dedicated total only to keep this integration fixture small;
    # it exercises selection after a successful metadata probe, not a mock
    # selection result. File and archive budgets remain independently active.
    with mock.patch.object(luoshu_diagnostics, "ORIGINAL_TEXT_TOTAL_LIMIT", luoshu_diagnostics.SMALL_PRESERVED_LIMIT):
        luoshu_diagnostics.export(moddir, directory / "total-limited.zip", lower)
    with zipfile.ZipFile(directory / "total-limited.zip") as archive:
        index = json.loads(archive.read("index.json"))
        row = index["stockCoverageAudit"][logical_cjk]
        assert row["probeStatus"] == "probed" and row["faces"][0]["asciiLetters"] == 52
        assert not row["selected"] and row["skippedReason"] == "original-text-total-limit"
        assert index["stockCoverageAuditSummary"]["originalTextBytes"] == 0
        assert "/vendor/fonts/nested/OrdinaryMystery.ttf" in index["stock"]
    with mock.patch.object(luoshu_diagnostics, "STOCK_PROBE_FACE_LIMIT", 1):
        luoshu_diagnostics.export(moddir, directory / "faces-limited.zip", lower)
    with zipfile.ZipFile(directory / "faces-limited.zip") as archive:
        index = json.loads(archive.read("index.json"))
        row = index["stockCoverageAudit"][logical_cjk]
        assert row["probeStatus"] == "partial" and row["faces"][0]["asciiLetters"] == 52
        assert not row["selected"] and row["skippedReason"] == "original-stock-metadata-unproved"
    with mock.patch.object(luoshu_diagnostics, "STOCK_TOTAL_LIMIT", luoshu_diagnostics.SMALL_PRESERVED_LIMIT):
        luoshu_diagnostics.export(moddir, directory / "stock-limited.zip", lower, full=True)
    with zipfile.ZipFile(directory / "stock-limited.zip") as archive:
        index = json.loads(archive.read("index.json"))
        row = index["stockCoverageAudit"][logical_cjk]
        assert row["probeStatus"] == "probed" and not row["selected"] and row["skippedReason"] == "size-limit"
        assert index["stockCoverageAuditSummary"]["stockBytes"] <= luoshu_diagnostics.SMALL_PRESERVED_LIMIT

    def budget():
        return {"bytes": 0, "deadline": time.monotonic() + 60}

    # Probing metadata must not read any post/glyf/CFF/gvar outline table.
    original_getitem = TTFont.__getitem__

    def metadata_getitem(font, tag):
        assert tag not in {"post", "glyf", "gvar", "CFF ", "CFF2"}, tag
        return original_getitem(font, tag)

    with mock.patch.object(TTFont, "__getitem__", metadata_getitem):
        metadata = luoshu_diagnostics._probe_stock_coverage(cjk_collection, budget())
        assert metadata["probeStatus"] == "probed", metadata
    with mock.patch.object(luoshu_diagnostics, "STOCK_PROBE_FACE_LIMIT", 1):
        metadata = luoshu_diagnostics._probe_stock_coverage(cjk_collection, budget())
        assert metadata["faceCount"] == 2 and metadata["probeStatus"] == "partial"
        assert metadata["facesTruncated"] and metadata["probeReason"] == "metadata-face-count-limit"
        assert len(metadata["faces"]) == 1 and metadata["faces"][0]["asciiLetters"] == 52
    with mock.patch.object(luoshu_diagnostics, "STOCK_PROBE_BYTE_LIMIT", 0):
        metadata = luoshu_diagnostics._probe_stock_coverage(cjk_collection, budget())
        assert metadata["probeStatus"] == "unavailable"
        assert all(face["reason"] == "metadata-byte-limit" and face["asciiLetters"] is None for face in metadata["faces"])
    metadata = luoshu_diagnostics._probe_stock_coverage(cjk_collection, {"bytes": 0, "deadline": 0})
    assert metadata["probeStatus"] == "unavailable" and metadata["probeReason"] == "metadata-time-limit"
    malformed = directory / "UnboundedCollection.ttc"
    malformed.write_bytes(b"ttcf\0\x01\0\0" + struct.pack(">I", luoshu_diagnostics.STOCK_PROBE_COLLECTION_LIMIT + 1))
    metadata = luoshu_diagnostics._probe_stock_coverage(malformed, budget())
    assert metadata["probeReason"] == "collection-directory-limit" and metadata["faces"] == []
    # A huge declared cmap range must be refused before dictionary expansion.
    cmap = struct.pack(">HHHHI", 0, 1, 3, 10, 12) + struct.pack(">HHIII", 12, 0, 28, 0, 1) + struct.pack(">III", 0, 0xFFFFFFFF, 0)
    assert not luoshu_diagnostics._bounded_cmap(cmap)
    hollow_collection = directory / "HollowCollection.ttc"
    luoshu_diagnostics._hollow(cjk_collection, hollow_collection, luoshu_diagnostics._keep_codepoints())
    with TTCollection(hollow_collection) as fonts:
        assert len(fonts.fonts) == 2
        assert all(font.getTableData("LSDG") == luoshu_diagnostics.HOLLOW_MARKER_DATA for font in fonts.fonts)
    metadata = luoshu_diagnostics._probe_stock_coverage(hollow_collection, budget())
    assert all(face["hollowMarker"] for face in metadata["faces"])
    assert luoshu_diagnostics._original_stock_skip_reason(metadata, "special-fallback",
        hollow_collection.stat().st_size, 0) == "original-stock-metadata-unproved"
    no_ascii = {"probeStatus": "probed", "faces": [{"status": "probed", "asciiLetters": 0,
        "asciiDigits": 0, "hollowMarker": False}]}
    assert luoshu_diagnostics._original_stock_skip_reason(no_ascii, "special-fallback",
        luoshu_diagnostics.SMALL_PRESERVED_LIMIT + 1, 0) == "original-stock-ascii-text-unproved"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-diag-") as raw:
        temp = Path(raw)
        process_font_evidence(temp)
        latin_ligature_evidence(temp)
        partial_stock_evidence(temp)
        global_stock_audit_evidence(temp)
        topology, _roles, stocks, xml_map = composite.build_device(temp / "device")
        moddir = temp / "module"
        config = moddir / "config"
        (config / "font-config-source" / "system").mkdir(parents=True)
        (moddir / "logs").mkdir()
        (moddir / "module.prop").write_text("id=LuoShu\nversion=test\nversionCode=1\n", encoding="utf-8")
        (moddir / "logs" / "fontswitch.log").write_text("universal prepare start font=mix\n", encoding="utf-8")
        (config / "active_font.conf").write_text("mix\n", encoding="utf-8")
        shutil.copy(xml_map["/system/etc/fonts.xml"], config / "font-config-source" / "system" / "fonts.xml")
        roles, shadow = font_role_shadow.build(topology)
        for name, value in (("device_font_topology.json", topology), ("device_font_roles.json", roles),
                            ("device_font_shadow_plan.json", shadow)):
            (config / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

        # Stock bytes live in the pre-mount lower snapshot, as on a device with a font active.
        lower = temp / "self-mount"
        for logical, stock in stocks.items():
            target = lower / "lower" / "system-fonts" / Path(logical).name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(stock, target)

        public = temp / "sdcard" / "fonts"
        public.mkdir(parents=True)
        cjk, latin, digit = public / "UserCJK.ttf", public / "UserLatin.ttf", public / "UserDigit.ttf"
        composite.make_cjk_font(cjk, family="User CJK", variable=True, pentagon=True)
        fixture.make_font(latin, family="User Latin", variable=True, triangle=True)
        fixture.make_font(digit, family="User Digit", advance=560)
        # The last switch on the device: its report records the source fonts.
        spec = {"mode": "composite", "roles": {
            "cjk": {"files": [str(cjk)], "mode": "auto"},
            "latin": {"files": [str(latin)], "mode": "auto"},
            "digit": {"files": [str(digit)], "mode": "fixed", "axes": {"wght": 500}},
        }}
        build_dir = config / "luoshu-engine-build"
        _manifest, device_report = luoshu_engine.build(
            topology, spec, build_dir / "payload", temp / "device-cache", xml_root=config / "font-config-source")
        (build_dir / "report.json").write_text(json.dumps(device_report), encoding="utf-8")

        # Hollowing keeps everything the engine inspects: style, axes, coverage.
        import luoshu_diagnostics
        keep_points = luoshu_diagnostics._keep_codepoints()
        fullwidth_points = set(range(0xFF21, 0xFF3B)) | set(range(0xFF41, 0xFF5B))
        assert fullwidth_points <= keep_points
        # Give fullwidth English independent cmap entries, with no ASCII alias
        # that could accidentally retain their outlines in a lite bundle.
        from fontTools.ttLib import TTFont
        fullwidth_source = temp / "Fullwidth.ttf"
        fixture.make_font(fullwidth_source, family="Fullwidth English")
        with TTFont(fullwidth_source) as font:
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap = dict(table.cmap)
                    for point in fullwidth_points:
                        table.cmap[point] = table.cmap.pop(point - 0xFEE0)
            font.save(fullwidth_source)
        fullwidth_hollow = temp / "FullwidthHollow.ttf"
        luoshu_diagnostics._hollow(fullwidth_source, fullwidth_hollow, keep_points)
        with TTFont(fullwidth_source) as original, TTFont(fullwidth_hollow) as hollow_font:
            for point in fullwidth_points:
                original_glyph = original["glyf"][original.getBestCmap()[point]]
                hollow_glyph = hollow_font["glyf"][hollow_font.getBestCmap()[point]]
                assert hollow_glyph.numberOfContours > 0, hex(point)
                assert original_glyph.getCoordinates(original["glyf"]) == hollow_glyph.getCoordinates(hollow_font["glyf"]), hex(point)
        # Real pre-mount snapshots retain ROM symlinks. Reading such a link
        # through pathlib can escape into the active overlay; resolve all hops
        # inside lower/mirror instead, or record a missing stock snapshot.
        aliases = temp / "aliases" / "lower"
        (aliases / "system-fonts").mkdir(parents=True)
        (aliases / "product-fonts").mkdir()
        stock_bytes = b"original-stock"
        (aliases / "system-fonts" / "MiSansVF.ttf").write_bytes(stock_bytes)
        absolute = aliases / "system-fonts" / "MiSans-Regular.ttf"
        absolute.symlink_to("/system/fonts/MiSansVF.ttf")
        relative = aliases / "system-fonts" / "MiSans-Medium.ttf"
        relative.symlink_to("MiSans-Regular.ttf")
        (aliases / "product-fonts" / "Cross.ttf").write_bytes(b"cross-partition-stock")
        (aliases / "system-fonts" / "Cross.ttf").symlink_to("../../product/fonts/Cross.ttf")
        (aliases / "system-fonts" / "Physical.ttf").symlink_to("../product-fonts/Cross.ttf")
        for name in ("MiSans-Regular.ttf", "MiSans-Medium.ttf"):
            found = luoshu_diagnostics._resolve_stock(f"/system/fonts/{name}", aliases.parent, False)
            assert found is not None and found[0] == "lower", name
            assert found[1].read_bytes() == stock_bytes, found
        for name in ("Cross.ttf", "Physical.ttf"):
            found = luoshu_diagnostics._resolve_stock(f"/system/fonts/{name}", aliases.parent, False)
            assert found is not None and found[1].read_bytes() == b"cross-partition-stock", name
        overlay = temp / "live-overlay.ttf"
        overlay.write_bytes(b"current-custom-payload")
        unsafe = aliases / "system-fonts" / "Unsafe.ttf"
        unsafe.symlink_to(overlay)
        assert unsafe.is_file() and unsafe.read_bytes() == b"current-custom-payload"
        assert luoshu_diagnostics._resolve_stock("/system/fonts/Unsafe.ttf", aliases.parent, False) is None
        (aliases / "system-fonts" / "Theme.ttf").symlink_to("/data/system/theme/fonts/Roboto-Regular.ttf")
        assert luoshu_diagnostics._resolve_stock("/system/fonts/Theme.ttf", aliases.parent, False) is None
        (aliases / "system-fonts" / "Cycle.ttf").symlink_to("Cycle.ttf")
        assert luoshu_diagnostics._resolve_stock("/system/fonts/Cycle.ttf", aliases.parent, False) is None
        (aliases / "system-fonts" / "Nested").symlink_to(temp)
        assert luoshu_diagnostics._resolve_stock("/system/fonts/Nested/live-overlay.ttf", aliases.parent, False) is None
        # Mirrors rebase absolute ROM links just like lower does.
        mirror = temp / "mirror"
        (mirror / "system/fonts").mkdir(parents=True)
        (mirror / "system/fonts/Original.ttf").write_bytes(stock_bytes)
        (mirror / "system/fonts/Alias.ttf").symlink_to("/system/fonts/Original.ttf")
        found = luoshu_diagnostics._snapshot_file("/system/fonts/Alias.ttf", mirror, lower_layout=False)
        assert found is not None and found.read_bytes() == stock_bytes
        (mirror / "data/system/theme/fonts").mkdir(parents=True)
        (mirror / "data/system/theme/fonts/Theme.ttf").write_bytes(b"current-theme-font")
        (mirror / "system/fonts/Theme.ttf").symlink_to("/data/system/theme/fonts/Theme.ttf")
        assert luoshu_diagnostics._snapshot_file("/system/fonts/Theme.ttf", mirror, lower_layout=False) is None
        hollow = temp / "hollow.ttf"
        luoshu_diagnostics._hollow(cjk, hollow, luoshu_diagnostics._keep_codepoints())

        def profiled(path: Path) -> list[dict]:
            return [{key: value for key, value in dataclasses.asdict(face).items()
                     if key not in {"path", "identity"}} for face in luoshu_engine._inspect(path)]

        assert profiled(hollow) == profiled(cjk)
        assert hollow.stat().st_size < cjk.stat().st_size

        bundle = temp / "out" / "bundle.zip"
        exported = subprocess.run(
            [sys.executable, str(ROOT / "common" / "luoshu_diagnostics.py"),
             "--moddir", str(moddir), "--output", str(bundle), "--lower-root", str(lower)],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert exported.returncode == 0, exported.stdout + exported.stderr
        result = json.loads(exported.stdout)
        assert result["status"] == "ok", result
        assert result["data"]["stockCount"] == len(stocks), result
        assert result["data"]["sourceCount"] == 3, result

        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
            index = json.loads(archive.read("index.json"))
        assert "config/font-config-source/system/fonts.xml" in names
        assert "logs/fontswitch.log" in names
        assert index["activeFont"] == "mix"
        assert index["mode"] == "lite"
        assert all(entry["hollow"] for entry in [*index["stock"].values(), *index["sources"].values()]), index
        assert {entry["origin"] for entry in index["stock"].values()} == {"lower"}, index["stock"]
        assert all(entry["file"] in names for entry in index["stock"].values())

        # The full bundle ships the fonts byte for byte, including ROM files with
        # 1970 mtimes (ColorOS), which zip rejects unless timestamps are clamped.
        for path in (lower / "lower" / "system-fonts").iterdir():
            os.utime(path, (0, 0))
        full = subprocess.run(
            [sys.executable, str(ROOT / "common" / "luoshu_diagnostics.py"), "--full",
             "--moddir", str(moddir), "--output", str(temp / "out" / "full.zip"), "--lower-root", str(lower)],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert full.returncode == 0, full.stdout + full.stderr
        with zipfile.ZipFile(temp / "out" / "full.zip") as archive:
            full_index = json.loads(archive.read("index.json"))
            roboto = full_index["stock"]["/system/fonts/Roboto-Regular.ttf"]
            assert full_index["mode"] == "full" and roboto["hollow"] is False
            assert archive.read(roboto["file"]) == stocks["/system/fonts/Roboto-Regular.ttf"].read_bytes()

        # A font is active, so the live /system/fonts view (LuoShu's overlay) is never read.
        missing_lower = subprocess.run(
            [sys.executable, str(ROOT / "common" / "luoshu_diagnostics.py"),
             "--moddir", str(moddir), "--output", str(temp / "out" / "nolower.zip"),
             "--lower-root", str(temp / "absent")],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert missing_lower.returncode == 0, missing_lower.stdout + missing_lower.stderr
        assert json.loads(missing_lower.stdout)["data"]["stockCount"] == 0
        with zipfile.ZipFile(temp / "out" / "nolower.zip") as archive:
            missing_index = json.loads(archive.read("index.json"))
            assert len(missing_index["stockSkipped"]) == len(stocks), missing_index
            assert {item["reason"] for item in missing_index["stockSkipped"]} == {"no-stock-snapshot"}

        # A live payload reachable through a lower symlink must not be shipped
        # under the stock label, even if the source is otherwise a valid font.
        broken_slot = lower / "lower" / "system-fonts" / "Roboto-Regular.ttf"
        broken_slot.unlink()
        broken_slot.symlink_to(latin)
        unsafe_export = subprocess.run(
            [sys.executable, str(ROOT / "common" / "luoshu_diagnostics.py"), "--full",
             "--moddir", str(moddir), "--output", str(temp / "out" / "unsafe.zip"), "--lower-root", str(lower)],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert unsafe_export.returncode == 0, unsafe_export.stdout + unsafe_export.stderr
        with zipfile.ZipFile(temp / "out" / "unsafe.zip") as archive:
            unsafe_index = json.loads(archive.read("index.json"))
            assert "/system/fonts/Roboto-Regular.ttf" not in unsafe_index["stock"], unsafe_index
            assert {"path": "/system/fonts/Roboto-Regular.ttf", "reason": "no-stock-snapshot"} in unsafe_index["stockSkipped"]
            assert "stock/system/fonts/Roboto-Regular.ttf" not in archive.namelist()

        replay = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "replay_diagnostics.py"), str(bundle),
             "--work", str(temp / "replay")],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert replay.returncode == 0, replay.stdout + replay.stderr
        assert "RESULT: PASS" in replay.stdout, replay.stdout
        assert f"replaced: {len(device_report['replaced'])}" in replay.stdout, replay.stdout

    print("luoshu_diagnostics_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
