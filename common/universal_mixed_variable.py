#!/usr/bin/env python3
"""Assemble a real wght VF from the nine generated static composite masters.

This is deliberately a fail-closed bridge, not an outline compatibility repair
or a way of relabelling one static font as a variable family.  Masters already
contain the selected CJK/Latin/digit geometry; their OS/2 weight can still be the
static CJK base's weight.  Only the *in-memory* master metadata is assigned the
requested composite coordinate.  No source files are modified.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.ttLib import TTFont
from fontTools.varLib import build as build_variable
from fontTools.varLib.instancer import instantiateVariableFont

WEIGHTS = tuple(range(100, 901, 100))
STYLES = ("Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Black")
# The only tables permitted to differ between complete masters.  Every other
# table, including all Unicode/UVS cmaps, shaping, hinting and color data, must
# agree byte-for-byte.  Table repertoire itself must also agree (except DSIG).
MASTER_TABLES = frozenset({"head", "hhea", "OS/2", "glyf", "loca", "hmtx", "vhea", "vmtx", "maxp", "name", "post", "DSIG", "STAT"})
VARIATION_TABLES = frozenset({"fvar", "gvar", "avar", "HVAR", "VVAR", "MVAR", "cvar", "CFF2", "VARC"})
REQUIRED_TABLES = frozenset({"head", "hhea", "OS/2", "glyf", "loca", "hmtx", "maxp", "name", "post", "cmap"})
# Prevent varLib from rewriting invariant layout or dropping incompatible
# hint programs. They have already passed stricter equality checks below.
EXCLUDE_TABLES = ("GDEF", "GPOS", "GSUB", "BASE", "JSTF", "COLR", "cvar")
ROUNDING_TOLERANCE = 1.01
MAX_MASTER_BYTES = 128 * 1024 * 1024
MAX_BUILD_MEMORY_BYTES = 4 * 1024 * 1024 * 1024
UNKNOWN_MEMORY_BUDGET_BYTES = 1024 * 1024 * 1024


def _available_memory() -> int | None:
    """Best-effort Linux/Android and container headroom, never a reservation."""
    limits = []
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                limits.append(int(line.split()[1]) * 1024)
                break
    except (OSError, ValueError, IndexError):
        pass
    for limit_path, used_path in (
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
    ):
        try:
            maximum = int(Path(limit_path).read_text().strip())
            used = int(Path(used_path).read_text().strip())
            limits.append(max(0, maximum - used))
        except (OSError, ValueError):
            pass
    return min(limits) if limits else None


def _resource_budget(fonts: list[tuple[int, Path]]) -> dict[str, int]:
    total = sum(Path(path).stat().st_size for _, path in fonts)
    if total > MAX_MASTER_BYTES:
        raise VariableFamilyError("resource-budget-exceeded", f"masters total {total} bytes; limit {MAX_MASTER_BYTES}")
    # Real CJK decompilation retains many Python point/glyph objects. Account
    # for nine expanded masters, a VF, one instantiated copy, and working data.
    # This guard is deliberately conservative, not a claim of phone RAM safety.
    estimate = 128 * 1024 * 1024 + total * 64
    available = _available_memory()
    budget = min(MAX_BUILD_MEMORY_BYTES, available // 2 if available is not None else UNKNOWN_MEMORY_BUDGET_BYTES)
    if estimate > budget:
        raise VariableFamilyError("resource-budget-exceeded", f"estimated {estimate} bytes exceeds safe headroom {budget}; use static output")
    return {"masterBytes": total, "estimatedMemoryBytes": estimate}


class VariableFamilyError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


def _table_bytes(font: TTFont, tag: str) -> bytes:
    return font.getTableData(tag)


def _topology(font: TTFont, name: str) -> tuple[Any, ...]:
    glyph = font["glyf"][name]
    program = getattr(glyph, "program", None)
    hints = bytes(program.getBytecode()) if program else b""
    if glyph.isComposite():
        components = []
        for component in glyph.components:
            transform = tuple(tuple(row) for row in getattr(component, "transform", ((1, 0), (0, 1))))
            # gvar represents XY component offsets, not transforms or a change
            # between point-attached and XY components. Keep these immutable.
            components.append((component.glyphName, transform, component.flags,
                               hasattr(component, "firstPt"),
                               getattr(component, "firstPt", None),
                               getattr(component, "secondPt", None)))
        return (glyph.numberOfContours, tuple(components), hints)
    coords, ends, flags = glyph.getCoordinates(font["glyf"])
    return (glyph.numberOfContours, len(coords), tuple(ends), bytes(flags), hints)


def _outline(font: TTFont, name: str):
    return font["glyf"][name].getCoordinates(font["glyf"])[0]


def _preflight(masters: list[tuple[int, TTFont]]) -> tuple[set[str], dict[str, bytes]]:
    base = next(font for weight, font in masters if weight == 400)
    order = base.getGlyphOrder()
    tags = set(base.keys()) - {"GlyphOrder", "DSIG"}
    protected = {tag: _table_bytes(base, tag) for tag in tags - MASTER_TABLES}
    varying: set[str] = set()
    for weight, font in masters:
        if not REQUIRED_TABLES.issubset(font.keys()) or "CFF " in font or "CFF2" in font:
            raise VariableFamilyError("non-glyf-master", str(weight))
        unexpected = VARIATION_TABLES.intersection(font.keys())
        if unexpected:
            raise VariableFamilyError("non-static-master", f"{weight}: {sorted(unexpected)}")
        if font.flavor is not None:
            raise VariableFamilyError("unsupported-container", str(weight))
        if set(font.keys()) - {"GlyphOrder", "DSIG"} != tags:
            raise VariableFamilyError("incompatible-tables", str(weight))
        if font["head"].unitsPerEm != base["head"].unitsPerEm:
            raise VariableFamilyError("incompatible-upem", str(weight))
        if font.getGlyphOrder() != order:
            raise VariableFamilyError("incompatible-glyph-order", str(weight))
        if set(font["glyf"].glyphs) != set(order) or set(font["hmtx"].metrics) != set(order):
            raise VariableFamilyError("incompatible-glyph-set", str(weight))
        for tag, expected in protected.items():
            if _table_bytes(font, tag) != expected:
                code = "incompatible-cmap" if tag == "cmap" else "incompatible-layout-or-data"
                raise VariableFamilyError(code, f"{weight}: {tag}")
        for name in order:
            if _topology(font, name) != _topology(base, name):
                raise VariableFamilyError("incompatible-glyph-topology", f"{weight}: {name}")
            if name not in varying and _outline(font, name) != _outline(base, name):
                varying.add(name)
    if not varying:
        raise VariableFamilyError("no-variable-geometry", "all nine masters have identical outlines")
    return varying, protected


def _assign_weight(font: TTFont, weight: int) -> None:
    # Composite geometry, not the original CJK base's OS/2, determines this
    # coordinate. Do not change any geometry to manufacture weight diversity.
    font["OS/2"].usWeightClass = weight
    font["OS/2"].fsSelection &= ~((1 << 5) | (1 << 6))
    if weight >= 700:
        font["OS/2"].fsSelection |= 1 << 5
    elif weight == 400 and not font["OS/2"].fsSelection & 1:
        font["OS/2"].fsSelection |= 1 << 6
    font["head"].macStyle = (font["head"].macStyle & ~1) | int(weight >= 700)
    style = STYLES[WEIGHTS.index(weight)]
    for name_id in (2, 17):
        for record in list(font["name"].names):
            if record.nameID == name_id:
                font["name"].setName(style, name_id, record.platformID, record.platEncID, record.langID)
        font["name"].setName(style, name_id, 3, 1, 0x409)
    # Instanced source fonts may retain STAT axes/ranges for their old source.
    # varLib otherwise leaves that stale table intact. Rebuild it for this VF.
    if "STAT" in font:
        del font["STAT"]


def _check_points(actual, left, right, factor: float, label: str) -> None:
    if len(actual) != len(left) or len(actual) != len(right):
        raise VariableFamilyError("roundtrip-topology-mismatch", label)
    for point, a, b in zip(actual, left, right):
        for value, start, end in zip(point, a, b):
            expected = start + (end - start) * factor
            if abs(value - expected) > ROUNDING_TOLERANCE:
                raise VariableFamilyError("roundtrip-geometry-mismatch", f"{label}: {value} != {expected}")


def _validate_roundtrips(font: TTFont, masters: list[tuple[int, TTFont]], protected: dict[str, bytes]) -> list[int]:
    axes = font["fvar"].axes if "fvar" in font else []
    if len(axes) != 1 or (axes[0].axisTag, axes[0].minValue, axes[0].defaultValue, axes[0].maxValue) != ("wght", 100, 400, 900):
        raise VariableFamilyError("invalid-variable-axis")
    if "gvar" not in font or not any(
        point is not None and any(point)
        for variations in font["gvar"].variations.values()
        for variation in variations
        for point in variation.coordinates[:-4]
    ):
        raise VariableFamilyError("no-variable-geometry", "no actual outline deltas in serialized gvar")
    order = masters[0][1].getGlyphOrder()
    if font.getGlyphOrder() != order:
        raise VariableFamilyError("roundtrip-glyph-order-mismatch")
    for tag, expected in protected.items():
        if tag not in font or _table_bytes(font, tag) != expected:
            raise VariableFamilyError("roundtrip-protected-table-mismatch", tag)
    samples = list(range(100, 901, 50))
    master_map = dict(masters)
    for weight in samples:
        lower = weight // 100 * 100
        upper = min(900, lower + 100) if weight % 100 else lower
        left, right = master_map[lower], master_map[upper]
        factor = (weight - lower) / (upper - lower) if upper != lower else 0.0
        instance = instantiateVariableFont(font, {"wght": weight}, inplace=False, optimize=False)
        try:
            for tag, expected in protected.items():
                if tag not in instance or _table_bytes(instance, tag) != expected:
                    raise VariableFamilyError("roundtrip-protected-table-mismatch", f"{weight}: {tag}")
            for name in order:
                _check_points(_outline(instance, name), _outline(left, name), _outline(right, name), factor, f"wght={weight} glyph={name}")
                for tag in ("hmtx", "vmtx"):
                    if tag not in left:
                        continue
                    actual = instance[tag].metrics[name]
                    a, b = left[tag].metrics[name], right[tag].metrics[name]
                    # Between masters the advance interpolates; sidebearing can
                    # change nonlinearly if a different point becomes an extreme.
                    count = 2 if upper == lower else 1
                    for index in range(count):
                        expected = a[index] + (b[index] - a[index]) * factor
                        if abs(actual[index] - expected) > ROUNDING_TOLERANCE:
                            raise VariableFamilyError("roundtrip-metrics-mismatch", f"{weight}: {name}: {tag}")
        finally:
            instance.close()
    return samples


def build_variable_family(fonts: list[tuple[int, Path]], output: Path) -> dict:
    """Build, serialize and verify a real mixed VF, then atomically publish it.

    Exactly one static glyf composite is required at each weight 100..900.
    Failures leave any previous output untouched. Fixed components are valid;
    some real outline geometry must vary. Layout/cmap mismatches, unsupported
    outlines and incompatible topology are errors, never silently repaired.
    """
    if any(type(weight) is not int for weight, _ in fonts) or sorted(weight for weight, _ in fonts) != list(WEIGHTS):
        raise VariableFamilyError("invalid-master-weights", "expected exactly 100,200,...,900")
    output = Path(output)
    if output.resolve() in {Path(path).resolve() for _, path in fonts}:
        raise VariableFamilyError("output-is-master")
    masters: list[tuple[int, TTFont]] = []
    variable = None
    temporary: Path | None = None
    try:
        budget = _resource_budget(fonts)
        for weight, path in sorted(fonts):
            master = TTFont(Path(path), lazy=False, recalcTimestamp=False)
            masters.append((weight, master))
            if not REQUIRED_TABLES.issubset(master.keys()) or "CFF " in master or "CFF2" in master:
                raise VariableFamilyError("non-glyf-master", f"{weight}: {path}")
        varying, protected = _preflight(masters)
        base = dict(masters)[400]
        designspace = DesignSpaceDocument()
        axis = AxisDescriptor()
        axis.name, axis.tag = "Weight", "wght"
        axis.minimum, axis.default, axis.maximum = 100, 400, 900
        designspace.addAxis(axis)
        family = base["name"].getDebugName(16) or base["name"].getDebugName(1) or "LuoShu Composite"
        for (weight, master), style in zip(masters, STYLES):
            _assign_weight(master, weight)
            source = SourceDescriptor()
            source.name, source.font, source.location = f"master-{weight}", master, {"Weight": weight}
            source.familyName, source.styleName = family, style
            designspace.addSource(source)
            instance = InstanceDescriptor()
            instance.familyName, instance.styleName = family, style
            instance.location = {"Weight": weight}
            designspace.addInstance(instance)
        variable, _, _ = build_variable(designspace, exclude=list(EXCLUDE_TABLES), optimize=False)
        for tag in EXCLUDE_TABLES:
            if tag in base:
                variable[tag] = copy.deepcopy(base[tag])
        # Outlines changed, so old cached device metrics/signatures are invalid.
        for tag in ("DSIG", "LTSH", "VDMX", "hdmx"):
            if tag in variable:
                del variable[tag]
            protected.pop(tag, None)
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".ttf", dir=output.parent)
        os.close(descriptor)
        temporary = Path(filename)
        variable.save(temporary)
        with TTFont(temporary, lazy=False, recalcTimestamp=False) as saved:
            samples = _validate_roundtrips(saved, masters, protected)
            glyph_count = len(saved.getGlyphOrder())
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        os.replace(temporary, output)
        temporary = None
        return {
            "schema": "universal-mixed-variable-v1", "state": "ready",
            "path": str(output), "sha256": digest,
            "weights": list(WEIGHTS),
            "axes": [{"tag": "wght", "min": 100, "default": 400, "max": 900}],
            "glyphCount": glyph_count, "variableGlyphCount": len(varying),
            "fixedGlyphCount": glyph_count - len(varying),
            "validatedWeights": samples, "protectedTables": sorted(protected),
            "resourceBudget": budget,
            "weightCoordinates": "requested-composite-masters; source axis provenance must be checked by caller",
        }
    except VariableFamilyError:
        raise
    except Exception as error:
        raise VariableFamilyError("variable-family-build-failed", str(error)) from error
    finally:
        if variable is not None:
            variable.close()
        for _, master in masters:
            master.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def discover_masters(directory: Path, family: str = "LuoShuMix") -> list[tuple[int, Path]]:
    directory = Path(directory)
    if not family or Path(family).name != family or "/" in family or "\\" in family:
        raise VariableFamilyError("invalid-family-prefix")
    masters = []
    for weight, style in zip(WEIGHTS, STYLES):
        matches = [path for suffix in (".ttf", ".otf") if (path := directory / f"{family}-{style}{suffix}").is_file()]
        if len(matches) != 1:
            raise VariableFamilyError("missing-or-ambiguous-master", f"{weight}: {style}")
        masters.append((weight, matches[0]))
    return masters


def find_masters(directory: Path) -> list[tuple[int, Path]]:
    return discover_masters(directory, family="LuoShuAutoMix")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonts-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_variable_family(find_masters(args.fonts_dir), args.output)
    except VariableFamilyError as error:
        print(json.dumps({"schema": "universal-mixed-variable-v1", "state": "blocked", "error": error.code, "detail": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
