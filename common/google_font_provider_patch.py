#!/usr/bin/env python3
"""Build a Google/GMS provider font clone from the active LuoShu weight source.

The provider cache is never modified. The generated clone is stored inside the module
and later bind-mounted over the provider file in the consumer mount namespaces.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

NAME_IDS = {1, 2, 3, 4, 6, 16, 17, 21, 22}
PROVIDER_FAMILIES = {
    "googlesans", "googlesanstext", "googlesansdisplay", "googlesansflex", "productsans",
}


class ProviderPatchError(RuntimeError):
    pass


def open_font(path: Path, *, lazy: bool = False) -> TTFont:
    with path.open("rb") as stream:
        collection = stream.read(4) == b"ttcf"
    kwargs: dict[str, Any] = {
        "lazy": lazy,
        "recalcTimestamp": False,
        "recalcBBoxes": False,
    }
    if collection:
        kwargs["fontNumber"] = 0
    return TTFont(str(path), **kwargs)


def inspect_target(path: Path) -> int | None:
    """Recognize a provider font by its family, including opaque cache filenames.

    The shell only submits files inside known font-cache directories. Do not infer
    identity from a filename: Google Sans Code, emoji and unrelated app fonts must
    remain untouched. TTC caches need per-face replacement, which this bridge does
    not yet implement, so leave collections alone instead of breaking TTC indexes.
    """
    if any(char in str(path) for char in "\r\n\t|"):
        return None
    with path.open("rb") as stream:
        if stream.read(4) not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            return None
    with open_font(path, lazy=True) as font:
        if "name" not in font:
            return None
        families = {
            re.sub(r"[\s_-]+", "", record.toUnicode()).lower()
            for record in font["name"].names if record.nameID in (1, 16)
        }
        if not families.intersection(PROVIDER_FAMILIES):
            return None
        # Named GMS instances encode the requested weight before width/italic.
        match = re.search(r"(?:^|[._-])([1-9]00)(?=[._-]|$)", path.name)
        if match:
            return int(match.group(1))
        weight = int(font["OS/2"].usWeightClass) if "OS/2" in font else 400
        return min(range(100, 1000, 100), key=lambda value: abs(value - weight))


def copy_target_names(source: TTFont, target: TTFont) -> None:
    if "name" not in source or "name" not in target:
        raise ProviderPatchError("source-or-target-name-table-missing")
    source_table = source["name"]
    target_records = [copy.deepcopy(record) for record in target["name"].names if record.nameID in NAME_IDS]
    if not target_records:
        raise ProviderPatchError("target-name-records-missing")
    source_table.names = [record for record in source_table.names if record.nameID not in NAME_IDS]
    source_table.names.extend(target_records)


def normalize_weight(font: TTFont, weight: int) -> None:
    weight = max(1, min(1000, int(weight)))
    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.usWeightClass = weight
        selection = int(getattr(os2, "fsSelection", 0))
        selection &= ~(1 << 5)
        selection &= ~(1 << 6)
        if weight >= 700:
            selection |= 1 << 5
        elif weight == 400:
            selection |= 1 << 6
        os2.fsSelection = selection
    if "head" in font:
        style = int(getattr(font["head"], "macStyle", 0))
        style &= ~1
        if weight >= 700:
            style |= 1
        font["head"].macStyle = style


def instantiate_for_target(source: TTFont, target: TTFont, weight: int) -> TTFont:
    target_variable = "fvar" in target
    source_variable = "fvar" in source
    # Skia ignores variation coordinates for axes absent from a font. A real
    # static donor is therefore valid even if the provider originally returned a
    # variable font. Keep it static; copying the target's fvar without matching
    # variation outlines would create a malformed font.
    # https://api.skia.org/structSkFontArguments.html#setVariationDesignPosition
    if source_variable and not target_variable:
        axes = {axis.axisTag: float(axis.defaultValue) for axis in source["fvar"].axes}
        if "wght" in axes:
            axis = next(axis for axis in source["fvar"].axes if axis.axisTag == "wght")
            axes["wght"] = max(float(axis.minValue), min(float(axis.maxValue), float(weight)))
        source = instantiateVariableFont(source, axes, inplace=False, optimize=True)
    return source


def atomic_save(font: TTFont, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_raw = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temporary = Path(temporary_raw)
    try:
        font.save(str(temporary), reorderTables=False)
        if temporary.stat().st_size < 1024:
            raise ProviderPatchError("generated-font-too-small")
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def patch(source_path: Path, target_path: Path, output_path: Path, weight: int) -> dict[str, Any]:
    source = open_font(source_path)
    target = open_font(target_path)
    try:
        source = instantiate_for_target(source, target, weight)
        copy_target_names(source, target)
        normalize_weight(source, weight)
        atomic_save(source, output_path)
        return {
            "status": "ok",
            "source": str(source_path),
            "target": str(target_path),
            "output": str(output_path),
            "weight": int(weight),
            "targetVariable": "fvar" in target,
            "outputVariable": "fvar" in source,
            "variationMode": "native" if "fvar" in source else "static-instance",
            "outputBytes": output_path.stat().st_size,
        }
    finally:
        try:
            source.close()
        except Exception:
            pass
        target.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect-targets", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--weight", type=int)
    args = parser.parse_args()
    if args.inspect_targets is not None:
        seen: set[str] = set()
        for raw in args.inspect_targets.read_text(encoding="utf-8").splitlines():
            if not raw or raw in seen:
                continue
            seen.add(raw)
            try:
                weight = inspect_target(Path(raw))
            except Exception:
                # A provider can rotate files while scanning; a corrupt/cache
                # metadata file is not a reason to abort other valid targets.
                continue
            if weight is not None:
                print(f"{raw}\t{weight}")
        return 0
    if any(value is None for value in (args.source, args.target, args.output, args.weight)):
        parser.error("--source, --target, --output and --weight are required for patching")
    try:
        result = patch(args.source, args.target, args.output, args.weight)
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False, separators=(",", ":")))
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
