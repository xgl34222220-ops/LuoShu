"""Explicit fixed upright XML assets, independent of OEM physical containers.

Preparation verifies every source and OEM face before any outline compilation.
Only the intersection of selected roles, source coverage and original slot
coverage is exposed; unrelated scripts remain on retained original fallbacks.
This representation never grants permission to replace a physical/variable slot.
"""
from __future__ import annotations

import copy
import math
import unicodedata
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

import device_font_slot_build_base as slot_build
import device_font_slot_plan_base as slot_plan
import universal_font_plan

REPRESENTATION = "fixed-static-xml-v1"
RENDER_SCHEMA = "fixed-static-xml-render-v1"
REVISION = 1
VARIABLE_TABLES = {"fvar", "gvar", "avar", "cvar", "HVAR", "VVAR", "MVAR", "CFF2", "VARC"}
ROLES = {"ui-sans", "latin", "cjk"}
COMBINING = ((0x300, 0x36F), (0x1AB0, 0x1AFF), (0x1DC0, 0x1DFF))


def _api():
    # Import lazily: the universal entry point dispatches here only for this
    # explicit representation, while retaining its legacy validation helpers.
    import universal_font_compiler
    return universal_font_compiler


def _role(cp):
    if slot_build.is_cjk(cp):
        return "cjk"
    if slot_build.is_digit(cp):
        return "digit"
    if slot_build.is_latin(cp) or any(low <= cp <= high for low, high in COMBINING):
        return "latin"
    # Do not use punctuation_probe as a coverage allowlist: it accepts emoji
    # and arbitrary symbols. Only these text punctuation blocks are selected.
    if cp == 0x20 or (0x21 <= cp <= 0x7E and unicodedata.category(chr(cp))[0] in "PS"):
        return "latin"
    if 0x3000 <= cp <= 0x303F or 0xFF01 <= cp <= 0xFF0F or 0xFF1A <= cp <= 0xFF20 or 0xFF3B <= cp <= 0xFF40 or 0xFF5B <= cp <= 0xFF65:
        return "cjk"
    return None


def _allowed(role, cp):
    selected = _role(cp)
    return selected is not None and (role == "ui-sans" or selected in ({"latin", "digit"} if role == "latin" else {"cjk"}))


def _upright(font):
    selection = int(font["OS/2"].fsSelection)
    return (not selection & ((1 << 0) | (1 << 9))
            and not int(font["head"].macStyle) & (1 << 1)
            and float(font["post"].italicAngle) == 0)


def _strict_location(font, axes, weight):
    api = _api()
    if not isinstance(axes, list):
        raise api.CompilerError("fixed static original axes must be a list")
    requested = {}
    for entry in axes:
        if not isinstance(entry, dict):
            raise api.CompilerError("fixed static original axis is invalid")
        tag = str(entry.get("tag") or "")
        values = api._axis_values([entry])
        if not tag or tag in requested or tag not in values:
            raise api.CompilerError("fixed static original axis is duplicate or nonfinite")
        requested[tag] = values[tag]
    known = {str(axis.axisTag): axis for axis in font["fvar"].axes} if "fvar" in font else {}
    if set(requested) - set(known):
        raise api.CompilerError("fixed static original axis is absent from OEM face")
    location = {}
    for tag, axis in known.items():
        value = requested.get(tag, weight if tag == "wght" else float(axis.defaultValue))
        if not math.isfinite(value) or not float(axis.minValue) <= value <= float(axis.maxValue):
            raise api.CompilerError("fixed static original axis is outside OEM range: " + tag)
        location[tag] = float(value)
    if location.get("ital", 0) != 0 or location.get("slnt", 0) != 0:
        raise api.CompilerError("fixed static XML requires upright OEM location")
    return location


def _profile_contract(profile):
    return {key: copy.deepcopy(profile.get(key)) for key in
            ("metrics", "probeSchema", "probes", "sharedProbePoints")}


def _binding(contract):
    key = _api()._canonical_hash(contract)
    return {"renderContractId": "sha256:" + key, "postScriptName": "LuoShuFixed-" + key[:40],
            "faceIndex": 0, "axes": [], "fileName": "LuoShuFixed-" + key + ".ttf",
            "fontWeight": contract["staticMetadata"]["weightClass"], "fontItalic": False}


def _subset(font, points):
    opts = subset.Options()
    opts.recalc_timestamp = False
    opts.hinting = False
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    worker = subset.Subsetter(options=opts)
    worker.populate(unicodes=points)
    worker.subset(font)
    # A shaping closure may retain glyphs, never additional character claims.
    for table in font["cmap"].tables:
        if hasattr(table, "cmap"):
            table.cmap = {cp: name for cp, name in table.cmap.items() if cp in points}
        if getattr(table, "format", None) == 14:
            table.uvsDict = {selector: [(cp, name) for cp, name in entries if cp in points]
                             for selector, entries in table.uvsDict.items()}


def _validate_unit(unit):
    api = _api()
    artifact, target = unit["artifact"], unit["target"]
    source = target.get("source") or {}
    if artifact.get("representation") != REPRESENTATION:
        raise api.CompilerError("fixed static XML representation missing")
    if unit.get("deploymentKinds") != ["xml-route"] or not unit.get("routeNodes"):
        raise api.CompilerError("fixed static representation is XML-only")
    if (artifact.get("requiredFaceIndex") != 0 or artifact.get("requiredAxes") != []
            or artifact.get("requiredPostScriptName") != "" or artifact.get("container") != "sfnt"):
        raise api.CompilerError("fixed static output contract must be a standalone axis-free face")
    if type(artifact.get("originalStockFaceIndex")) is not int or artifact["originalStockFaceIndex"] < 0:
        raise api.CompilerError("fixed static original face contract missing")
    if target.get("role") not in ROLES or str(target.get("path") or "").startswith("/data/"):
        raise api.CompilerError("fixed static target role or path unsupported")
    if not universal_font_plan.is_fixed_composite_selection(source):
        raise api.CompilerError("fixed static XML requires a hash-bound fixed composite selection")
    if source.get("italic") or target.get("targetContract", {}).get("italic") or artifact.get("requiredStyle") != "normal":
        raise api.CompilerError("fixed static XML requires an upright source and route")
    if target.get("status") == "blocked" or set(target.get("risks") or []) & {
        "static-weight-fallback", "italic-style-mismatch", "source-weight-axis-out-of-range",
        "source-style-axis-missing", "source-style-axis-out-of-range",
    }:
        raise api.CompilerError("fixed static XML cannot bypass blocked source/style gates")


def verify_original_face(target, stock, face_index):
    """Verify another sealed XML face inside an unchanged original collection.

    The capture face hint remains unchanged. Its whole-file digest seals every
    collection face; selecting another face requires an exact frozen XML index
    and actual TTC bounds. Generic physical/variable contracts stay unchanged.
    """
    api = _api()
    identity = (target.get("targetContract") or {}).get("stockIdentity") or {}
    captured = identity.get("faceIndex")
    if type(captured) is not int or type(face_index) is not int or face_index < 0:
        raise api.CompilerError("original face identity missing")
    if captured == face_index:
        return api._validate_stock_contract(target, stock, face_index)["verifiedStockIdentity"]
    if api._magic(stock) != api.COLLECTION_MAGIC:
        raise api.CompilerError("another original face requires a sealed collection")
    if (target.get("targetContract", {}).get("faceIndex") != face_index or
            not any(ref.get("index") == face_index and ref.get("fingerprint")
                    for ref in target.get("xmlRefs") or [])):
        raise api.CompilerError("original collection face is not bound to a frozen XML node")
    evidence = api._validate_stock_contract(target, stock, captured)["verifiedStockIdentity"]
    selected = api._open_face(stock, face_index, lazy=True)
    selected.close()
    return {**evidence, "scope":"sealed-container-xml-face-v1", "captureFaceIndex":captured,
            "faceIndex":face_index}


def prepare_unit(unit, stock_paths, allow_live_stock):
    """Verify and measure one route. No output font or source mutation occurs."""
    api = _api()
    _validate_unit(unit)
    target, artifact = unit["target"], unit["artifact"]
    source = target["source"]
    path = Path(str(source.get("sourcePath") or ""))
    api._file_uid_matches(source, path)
    if api._font_container(path) != "TTF":
        raise api.CompilerError("fixed static XML currently requires a standalone TrueType source")
    face = int(source.get("faceIndex", 0))
    original = api._open_face(path, face)
    stock_font = stock_geometry = None
    try:
        if (VARIABLE_TABLES & set(original.keys()) or "glyf" not in original
                or any(tag not in original for tag in ("head", "hhea", "OS/2", "post", "name"))):
            raise api.CompilerError("fixed static XML source must be a complete static glyf face")
        if not _upright(original):
            raise api.CompilerError("fixed static XML source metadata is not upright")
        stock = api._resolve_stock(str(target["path"]), stock_paths, allow_live_stock)
        stock_face = artifact["originalStockFaceIndex"]
        verified = verify_original_face(target, stock, stock_face)
        stock_font = api._open_face(stock, stock_face, lazy=True)
        original_ps = str(artifact.get("originalStockPostScriptName") or "")
        # AOSP FontListParser uses XML postScriptName as a font-update file
        # lookup key, independently from the TTC index. Its CJK configuration
        # intentionally repeats the JP key for SC/TC/KR collection faces.
        # Bind the key to the frozen XML, while bytes and actual face remain
        # protected by verify_original_face. This representation excludes an
        # active update layer and rechecks that generation before activation.
        if original_ps and not any(str(ref.get("postScriptName") or "") == original_ps
                                   for ref in target.get("xmlRefs") or []):
            raise api.CompilerError("fixed static XML PostScript update key differs from sealed XML")
        xml_identity = {"kind": "aosp-font-update-lookup-key", "declaredPostScriptName": original_ps,
                        "actualFacePostScriptNames": sorted({record.toUnicode() for record in stock_font["name"].names
                                                             if record.nameID == 6}), "faceIndex": stock_face}
        if "VARC" in stock_font:
            raise api.CompilerError("fixed static XML OEM VARC geometry is unsupported")
        weight = api._int(artifact.get("requiredWeight"), 400)
        location = _strict_location(stock_font, artifact["originalStockAxes"], weight)
        source_points = set(original.getBestCmap() or {})
        stock_points = set(stock_font.getBestCmap() or {})
        role = str(target["role"])
        allowed_stock = {cp for cp in stock_points if _allowed(role, cp)}
        points = sorted(allowed_stock & source_points)
        if not points:
            raise api.CompilerError("fixed static XML has no selected shared coverage")
        exposed = sorted({_role(cp) for cp in points})
        has_han = any(slot_build.is_cjk(cp) for cp in points)
        # Measure actual bytes at the exact original location, never trust a
        # caller-supplied geometryVerified flag or archived profile alone.
        stock_geometry, actual_location = api._stock_geometry_font(
            stock, stock_face, weight, location, source_font=original,
            role="cjk" if has_han else role,
        )
        if actual_location != location:
            raise api.CompilerError("fixed static XML OEM measurement location changed")
        stock_profile, source_profile = api._paired_geometry_profiles(
            stock_geometry, original, "cjk" if has_han else role)
        if has_han:
            # The old shared-probe fallback can accept different canonical
            # subsets on each side. This asset exposes only their intersection,
            # so measure the same actual Han codepoints on both sides always.
            shared = [cp for cp in points if slot_build.is_cjk(cp)]
            if len(shared) > 64:
                shared = [shared[i * (len(shared) - 1) // 63] for i in range(64)]
            for font, profile in ((stock_geometry, stock_profile), (original, source_profile)):
                profile["probes"]["cjk"] = api.template_engine.glyph_group(font, shared)
                profile["sharedProbePoints"] = {"cjk": shared}
        needed = set()
        for cp in points:
            if cp == 0x20:
                continue
            probe = slot_build.probe_for_codepoint(cp)
            if probe is None and any(a <= cp <= b for a, b in COMBINING):
                probe = "latinX"
            if probe is not None:
                needed.add(probe)
        # Measure only codepoints this asset will actually expose. Full source
        # Latin probes must not veto a CJK-only asset (or vice versa), and probe
        # fallbacks must not borrow characters outside the sealed intersection.
        selected_points = set(points)
        for font, profile in ((stock_geometry, stock_profile), (original, source_profile)):
            previous_cjk = profile["probes"].get("cjk") if has_han else None
            filtered = {}
            for probe, canonical in api.template_engine.PROBE_GROUPS.items():
                selected = [cp for cp in canonical if cp in selected_points]
                if selected:
                    filtered[probe] = api.template_engine.glyph_group(font, selected)
            if previous_cjk is not None:
                filtered["cjk"] = previous_cjk
            profile["probes"] = filtered
        geometry = api._geometry_plan(target, stock_profile, source_profile, weight)
        for probe in sorted(needed):
            transform = slot_build.transform_for_probe(geometry, probe)
            if not transform or transform.get("status") != "ready":
                raise api.CompilerError("fixed static XML missing verified role geometry: " + probe)
            for profile in (stock_profile, source_profile):
                sample = slot_plan.select_probe(profile["probes"], probe)
                if int(sample.get("boundsHits") or 0) < slot_plan.minimum_hits(probe):
                    raise api.CompilerError("fixed static XML insufficient outlined role probes: " + probe)
        line = geometry["lineContract"]
        required_line = ("unitsPerEm", "hheaAscent", "hheaDescent", "hheaLineGap",
                         "typoAscender", "typoDescender", "typoLineGap", "winAscent", "winDescent")
        if any(type(line.get(key)) is not int for key in required_line):
            raise api.CompilerError("fixed static XML incomplete OEM line contract")
        coverage = {
            "policy": "source-stock-role-intersection-v1", "exposedRoles": exposed,
            "codepointCount": len(points), "codepointSha256": api._canonical_hash(points),
            "roleCounts": {r: sum(_role(cp) == r for cp in points) for r in exposed},
            "preservedMissingSourceCount": len(allowed_stock - source_points),
            "preservedMissingSourceSha256": api._canonical_hash(sorted(allowed_stock - source_points)),
        }
        # Provenance/route addresses are separately retained by each artifact.
        # The render key contains only complete immutable source and geometry
        # contracts, including the stock content/face/location that established it.
        contract = {
            "schema": RENDER_SCHEMA, "revision": REVISION, "compilerRevision": api.COMPILER_REVISION,
            "source": {"sha256": api._sha256(path), "faceIndex": face,
                       "fixedSelection": copy.deepcopy(source["mixedSelection"]),
                       "profile": _profile_contract(source_profile)},
            "stock": {"sha256": verified["sha256"], "faceIndex": stock_face,
                      "location": location, "profile": _profile_contract(stock_profile)},
            "role": role, "coverage": coverage,
            "geometry": {key: copy.deepcopy(geometry.get(key)) for key in
                         ("roles", "lineContract", "transforms", "upemScale", "sharedProbePoints",
                          "targetAdvancePolicy", "targetOutlinePolicy")},
            "staticMetadata": {"weightClass": int(original["OS/2"].usWeightClass),
                               "widthClass": int(original["OS/2"].usWidthClass),
                               "fsSelection": int(original["OS/2"].fsSelection),
                               "macStyle": int(original["head"].macStyle)},
        }
        contract["geometry"]["requiredProbes"] = sorted(needed)
        binding = _binding(contract)
        # Guard concurrent edits between source validation and measurement.
        api._file_uid_matches(source, path)
        if api._sha256(stock) != verified["sha256"]:
            raise api.CompilerError("fixed static XML OEM bytes changed during preparation")
        return {"contract": contract, "binding": binding, "points": points,
                "sourcePath": str(path), "stockPath": str(stock), "stockProfile": stock_profile,
                "geometry": geometry, "stockXmlIdentity": xml_identity, "unit": copy.deepcopy(unit)}
    finally:
        original.close()
        if stock_font is not None:
            stock_font.close()
        if stock_geometry is not None:
            stock_geometry.close()


def _validate_saved(path, prepared):
    api = _api()
    with TTFont(path, lazy=False, recalcTimestamp=False) as font:
        if VARIABLE_TABLES & set(font.keys()) or "glyf" not in font or not _upright(font):
            raise api.CompilerError("fixed static XML output retained variable or italic metadata")
        actual_points = set()
        for table in font["cmap"].tables:
            if hasattr(table, "cmap"):
                actual_points.update(table.cmap)
            if getattr(table, "format", None) == 14:
                actual_points.update(cp for entries in table.uvsDict.values() for cp, _ in entries)
        if actual_points != set(prepared["points"]):
            raise api.CompilerError("fixed static XML output coverage differs from the sealed intersection")
        if {record.toUnicode() for record in font["name"].names if record.nameID == 6} != {prepared["binding"]["postScriptName"]}:
            raise api.CompilerError("fixed static XML output PostScript identity differs")
        profile = api._profile_from_font(font)
        for key, expected in prepared["geometry"]["lineContract"].items():
            if key in {"headYMin", "headYMax", "weightClass", "widthClass", "fsSelection", "capHeight", "xHeight"}:
                continue
            if expected is not None and profile["metrics"].get(key) != expected:
                raise api.CompilerError("fixed static XML output line contract differs: " + key)
        metadata = prepared["contract"]["staticMetadata"]
        if (int(font["OS/2"].usWeightClass) != metadata["weightClass"]
                or int(font["OS/2"].usWidthClass) != metadata["widthClass"]):
            raise api.CompilerError("fixed static XML output mislabels source weight/width")
        line = prepared["geometry"]["lineContract"]
        ceiling = min(line["hheaAscent"], line["typoAscender"], line["winAscent"])
        floor = max(line["hheaDescent"], line["typoDescender"], -line["winDescent"])
        glyph_set = font.getGlyphSet()
        low = high = None
        for name in font.getGlyphOrder():
            bounds = api._bounds(glyph_set, name)
            if bounds is None:
                # Distinguish empty outlines from failed bounds measurements.
                if font["glyf"][name].numberOfContours != 0:
                    raise api.CompilerError("fixed static XML cannot measure glyph bounds: " + name)
                continue
            low = bounds[1] if low is None else min(low, bounds[1])
            high = bounds[3] if high is None else max(high, bounds[3])
        if low is None or high is None or low < floor or high > ceiling:
            raise api.FontGeometryError("fixed static XML outlines exceed the exact OEM line budget", "fixed-static-line-budget",
                                       {"yMin": low, "yMax": high, "minDescent": floor, "maxAscent": ceiling})
        for name, points in (prepared["stockProfile"].get("sharedProbePoints") or {}).items():
            profile["probes"][name] = api.template_engine.glyph_group(font, points)
        for name in prepared["contract"]["geometry"]["requiredProbes"]:
            sample = slot_plan.select_probe(profile["probes"], name)
            if int(sample.get("boundsHits") or 0) < slot_plan.minimum_hits(name):
                raise api.CompilerError("fixed static XML output lost required probes: " + name)
        alignment = api._probe_alignment(prepared["stockProfile"], profile, prepared["contract"]["role"])
        if alignment["status"] != "ready":
            raise api.CompilerError("fixed static XML output alignment failed: " + ",".join(alignment["issues"]))
        return {"lineBudget": {"yMin": low, "yMax": high, "minDescent": floor, "maxAscent": ceiling},
                "alignment": alignment, "coverage": prepared["contract"]["coverage"]}


def compile_prepared(prepared, output_dir, cache):
    """Compile one canonical render contract once; verify every reused binding."""
    api = _api()
    binding = prepared["binding"]
    contract = prepared["contract"]
    if binding != _binding(contract):
        raise api.CompilerError("fixed static XML prepared render contract changed")
    if (api._sha256(Path(prepared["sourcePath"])) != contract["source"]["sha256"]
            or api._sha256(Path(prepared["stockPath"])) != contract["stock"]["sha256"]):
        raise api.CompilerError("fixed static XML input changed after preparation")
    key = binding["renderContractId"]
    output = Path(output_dir) / binding["fileName"]
    hit = cache.get(key)
    if hit:
        if not output.is_file() or api._sha256(output) != hit["sha256"]:
            raise api.CompilerError("fixed static XML grouped asset integrity mismatch")
        validation = _validate_saved(output, prepared)
        return {"output": str(output), "staticXmlContract": copy.deepcopy(binding),
                "report": {"mode": REPRESENTATION, "renderContract": contract, "validation": validation,
                           "stockXmlIdentity": copy.deepcopy(prepared["stockXmlIdentity"]),
                           "renderReuse": {"hit": True}}}
    font = api._open_face(Path(prepared["sourcePath"]), contract["source"]["faceIndex"])
    try:
        _subset(font, set(prepared["points"]))
        slot_build.apply_line_contract(font, prepared["geometry"])
        transformed = slot_build.apply_outline_transforms(font, prepared["geometry"])
        if transformed["glyphs"] <= 0:
            raise api.CompilerError("fixed static XML transformed no selected outlines")
        metadata = contract["staticMetadata"]
        font["OS/2"].usWeightClass = metadata["weightClass"]
        font["OS/2"].usWidthClass = metadata["widthClass"]
        # Preserve source style identity while carrying the OEM line-selection bit.
        font["OS/2"].fsSelection = ((metadata["fsSelection"] & ~(1 << 7))
                                   | (int(prepared["geometry"]["lineContract"].get("fsSelection") or 0) & (1 << 7)))
        font["head"].macStyle = metadata["macStyle"]
        if "STAT" in font:
            del font["STAT"]
        name = binding["postScriptName"]
        for record in font["name"].names:
            if record.nameID in {1, 3, 4, 6, 16}:
                record.string = name.encode(record.getEncoding())
        for name_id in (1, 3, 4, 6, 16):
            font["name"].setName(name, name_id, 3, 1, 0x409)
        api._drop_stale_tables(font)
        api._save_font(font, output)
        validation = _validate_saved(output, prepared)
        cache[key] = {"sha256": api._sha256(output)}
        return {"output": str(output), "staticXmlContract": copy.deepcopy(binding),
                "report": {"mode": REPRESENTATION, "renderContract": contract, "validation": validation,
                           "stockXmlIdentity": copy.deepcopy(prepared["stockXmlIdentity"]),
                           "transformed": transformed, "renderReuse": {"hit": False}}}
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        font.close()


def validate_artifact(artifact, unit):
    """Check saved representation, geometry/coverage seals and honest metadata."""
    api = _api()
    _validate_unit(unit)
    contract = (artifact.get("report") or {}).get("renderContract")
    if not isinstance(contract, dict) or contract.get("schema") != RENDER_SCHEMA or contract.get("revision") != REVISION:
        raise api.CompilerError("fixed static artifact missing versioned render contract")
    if contract.get("compilerRevision") != api.COMPILER_REVISION:
        raise api.CompilerError("fixed static artifact compiler revision differs")
    binding = artifact.get("staticXmlContract")
    if binding != _binding(contract) or Path(str(artifact.get("output") or "")).name != binding["fileName"]:
        raise api.CompilerError("fixed static artifact binding differs from its render contract")
    source = unit["target"]["source"]
    stock_identity = unit["target"]["targetContract"].get("stockIdentity") or {}
    if (contract["source"].get("sha256") != str(source.get("fileUid") or "").removeprefix("sha256:")
            or contract["source"].get("faceIndex") != int(source.get("faceIndex", 0))
            or contract["source"].get("fixedSelection") != source.get("mixedSelection")
            or contract["stock"].get("sha256") != stock_identity.get("sha256")
            or contract["stock"].get("faceIndex") != unit["artifact"]["originalStockFaceIndex"]
            or contract.get("role") != unit["target"].get("role")):
        raise api.CompilerError("fixed static artifact source/OEM identity differs from its route")
    output = Path(artifact["output"])
    with TTFont(output, lazy=True, recalcTimestamp=False) as font:
        points = sorted(font.getBestCmap() or {})
    coverage = contract["coverage"]
    if (coverage.get("codepointCount") != len(points) or coverage.get("codepointSha256") != api._canonical_hash(points)
            or any(not _allowed(contract["role"], cp) for cp in points)):
        raise api.CompilerError("fixed static artifact coverage seal differs")
    prepared = {"binding": binding, "contract": contract, "points": points,
                "geometry": contract["geometry"], "stockProfile": contract["stock"]["profile"]}
    _validate_saved(output, prepared)
