#!/usr/bin/env python3
"""Read-only three-way font configuration parity and updatable-font diagnostics.

Different renderers read different configuration files:

* normal Apps go through FontManagerService (`cmd font dump`);
* Chromium/WebView reads the mounted legacy `/system/etc/fonts.xml` directly;
* Android 15+ SystemFonts reads `/system/etc/font_fallback.xml`, plus the OEM
  `/product/etc/fonts_customization.xml`.

This helper compares the first font chosen for `sans-serif` and `zh-Hans` in each
view and reports `xmlParity=ok|mismatch:<detail>|unknown:<reason>`.  It also lists
FontManagerService updatable fonts under `/data/fonts/files` (PostScript name and
fontRevision when FontTools is available) and marks
`shadowedByUpdatableFont=<names>` when one carries the same PostScript name as a slot
LuoShu replaced.  Nothing is modified, cleared or deleted: output only.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "luoshu-xml-parity-v1"
TARGETS = ("sans-serif", "zh-Hans")
FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")
SAFE_TOKEN = re.compile(r"[^A-Za-z0-9._@#+-]")
MAX_UPDATABLE_FONTS = 64


def safe_token(value: str, limit: int = 96) -> str:
    return SAFE_TOKEN.sub("_", str(value or ""))[:limit]


def _font_key(path: str, index: int = 0) -> str:
    name = os.path.basename(str(path or "").strip())
    if not name:
        return ""
    return f"{name}#{index}" if index else name


def _pick(fonts: list[dict[str, Any]]) -> str:
    """Prefer the regular upright face; otherwise the first listed font."""
    if not fonts:
        return ""
    for font in fonts:
        if font.get("weight") == 400 and not font.get("italic"):
            return _font_key(font["path"], font.get("index", 0))
    first = fonts[0]
    return _font_key(first["path"], first.get("index", 0))


# ---------------------------------------------------------------- cmd font dump
_PATH_RE = re.compile(r"path = ([^,\s]+)")
_INDEX_RE = re.compile(r"index = (\d+)")
_WEIGHT_RE = re.compile(r"weight\s*=\s*(\d+)")
_SLANT_RE = re.compile(r"slant\s*=\s*(\w+)")
_NAMED_RE = re.compile(r"^\s*Named Family \(([^)]*)\)")
_FALLBACK_RE = re.compile(r'^\s*Fallback Family \[\d+\]: lang="([^"]*)"')
_UPDATED_RE = re.compile(r"Font is updated from (\S+)")


def _dump_font(line: str) -> dict[str, Any] | None:
    match = _PATH_RE.search(line)
    if not match:
        return None
    weight = _WEIGHT_RE.search(line)
    slant = _SLANT_RE.search(line)
    index = _INDEX_RE.search(line)
    slant_value = (slant.group(1) if slant else "0").lower()
    return {
        "path": match.group(1),
        "index": int(index.group(1)) if index else 0,
        "weight": int(weight.group(1)) if weight else 400,
        "italic": slant_value not in ("0", "upright", "normal"),
    }


def parse_font_dump(text: str) -> dict[str, Any]:
    """Parse `cmd font dump` (Android 12-16 FontManagerShellCommand format)."""
    named = _first_family_per_named(text)
    zh_hans: list[dict[str, Any]] = []
    updated_from: list[str] = []
    section = ""
    lang_hit = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("Dump Fallback Families"):
            section = "fallback"
            continue
        if stripped.startswith("Dump Family Aliases"):
            section = "alias"
            continue
        updated = _UPDATED_RE.search(line)
        if updated:
            updated_from.append(updated.group(1))
            continue
        if section != "fallback":
            continue
        match = _FALLBACK_RE.match(line)
        if match:
            # Only the first zh-Hans fallback family is the primary CJK choice.
            lang_hit = not zh_hans and "zh-Hans" in re.split(r"[\s,]+", match.group(1))
            continue
        font = _dump_font(line)
        if font and lang_hit:
            zh_hans.append(font)
    return {
        "sans-serif": _pick(named.get("sans-serif", [])),
        "zh-Hans": _pick(zh_hans),
        "updatedFrom": updated_from,
        "available": bool(named or zh_hans),
    }


def _first_family_per_named(text: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    current = ""
    family_blocks = 0
    in_named = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("Named Family List") or stripped.startswith("Named Font Families"):
            in_named = True
            continue
        if stripped.startswith("Dump Fallback Families"):
            break
        if not in_named:
            continue
        match = _NAMED_RE.match(line)
        if match:
            current = match.group(1).strip()
            result.setdefault(current, [])
            family_blocks = 0
            continue
        if stripped == "Family":
            family_blocks += 1
            continue
        font = _dump_font(line)
        if font and current and family_blocks <= 1:
            result[current].append(font)
    return result


# ---------------------------------------------------------------- XML views
def _local(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _xml_fonts(family: ET.Element, font_dir: str) -> list[dict[str, Any]]:
    fonts: list[dict[str, Any]] = []
    for element in family.iter():
        if _local(element.tag) != "font":
            continue
        name = (element.text or "").strip()
        if not name:
            continue
        path = name if name.startswith("/") else f"{font_dir.rstrip('/')}/{name}"
        try:
            weight = int(element.get("weight") or 400)
        except ValueError:
            weight = 400
        try:
            index = int(element.get("index") or 0)
        except ValueError:
            index = 0
        fonts.append({
            "path": path,
            "index": index,
            "weight": weight,
            "italic": (element.get("style") or "normal").lower() == "italic",
        })
    return fonts


def _read_xml(path: Path | None) -> ET.Element | None:
    if not path or not path.is_file():
        return None
    try:
        return ET.fromstring(path.read_bytes())
    except (ET.ParseError, OSError):
        return None


def _lang_tags(family: ET.Element) -> list[str]:
    return [tag for tag in re.split(r"[\s,]+", family.get("lang") or "") if tag]


def parse_font_xml(root: ET.Element | None, font_dir: str = "/system/fonts") -> dict[str, Any]:
    """Parse fonts.xml (<familyset>) or font_fallback.xml (<family-list>)."""
    if root is None:
        return {"sans-serif": "", "zh-Hans": "", "available": False}
    named: dict[str, list[dict[str, Any]]] = {}
    zh_hans: list[dict[str, Any]] = []
    for element in list(root):
        tag = _local(element.tag)
        if tag == "family-list":
            name = element.get("name") or ""
            first = next((child for child in element if _local(child.tag) == "family"), None)
            if name and name not in named and first is not None:
                named[name] = _xml_fonts(first, font_dir)
        elif tag == "family":
            name = element.get("name") or ""
            if name:
                named.setdefault(name, _xml_fonts(element, font_dir))
            elif not zh_hans and "zh-Hans" in _lang_tags(element):
                zh_hans = _xml_fonts(element, font_dir)
    return {
        "sans-serif": _pick(named.get("sans-serif", [])),
        "zh-Hans": _pick(zh_hans),
        "available": True,
    }


def apply_customization(view: dict[str, Any], root: ET.Element | None,
                        font_dir: str = "/product/fonts") -> dict[str, Any]:
    """Apply OEM fonts_customization.xml new-named-family / new-locale-family hooks."""
    if root is None or not view.get("available"):
        return view
    result = dict(view)
    for element in root.iter():
        if _local(element.tag) != "family":
            continue
        kind = element.get("customizationType") or ""
        fonts = _xml_fonts(element, font_dir)
        if not fonts:
            continue
        if kind == "new-named-family" and element.get("name") == "sans-serif":
            result["sans-serif"] = _pick(fonts)
        elif kind == "new-locale-family" and "zh-Hans" in _lang_tags(element):
            operation = (element.get("operation") or "").lower()
            if operation in ("prepend", "replace") or not result.get("zh-Hans"):
                result["zh-Hans"] = _pick(fonts)
    return result


def compare(font_manager: dict[str, Any], fonts_xml: dict[str, Any],
            fallback_xml: dict[str, Any]) -> str:
    if not font_manager.get("available"):
        return "unknown:font-manager-dump-unavailable"
    if not fonts_xml.get("available"):
        return "unknown:fonts-xml-unavailable"
    details: list[str] = []
    for target in TARGETS:
        views = [("fm", font_manager.get(target, "")), ("fontsXml", fonts_xml.get(target, ""))]
        if fallback_xml.get("available"):
            views.append(("fallbackXml", fallback_xml.get(target, "")))
        values = {value for _, value in views}
        if len(values) > 1:
            body = ",".join(f"{key}={safe_token(value) or 'none'}" for key, value in views)
            details.append(f"{target}({body})")
    return "ok" if not details else "mismatch:" + ";".join(details)


# ---------------------------------------------------------------- /data/fonts
def _fonttools() -> Any:
    try:
        from fontTools.ttLib import TTCollection, TTFont  # type: ignore
        return TTFont, TTCollection
    except Exception:
        return None


def font_identity(path: Path, tools: Any) -> list[tuple[str, str]]:
    """Return [(postScriptName, fontRevision)] for every face; [] when unreadable."""
    if tools is None:
        return []
    TTFont, TTCollection = tools
    faces: list[Any] = []
    holder: Any = None
    try:
        if path.suffix.lower() in (".ttc", ".otc"):
            holder = TTCollection(str(path), lazy=True)
            faces = list(holder.fonts)
        else:
            holder = TTFont(str(path), lazy=True, fontNumber=0)
            faces = [holder]
    except Exception:
        return []
    try:
        return _face_identities(faces)
    finally:
        try:
            holder.close()
        except Exception:
            pass


def _face_identities(faces: list[Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for face in faces:
        try:
            ps = face["name"].getDebugName(6) or ""
        except Exception:
            ps = ""
        try:
            revision = f"{float(face['head'].fontRevision):.3f}"
        except Exception:
            revision = "unknown"
        if ps:
            result.append((ps, revision))
    return result


def _iter_font_files(root: Path, limit: int = MAX_UPDATABLE_FONTS) -> Iterable[Path]:
    count = 0
    if not root.is_dir():
        return
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.lower().endswith(FONT_SUFFIXES):
                yield Path(dirpath) / name
                count += 1
                if count >= limit:
                    return


def scan_updatable_fonts(root: Path, tools: Any) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for path in _iter_font_files(root):
        identity = font_identity(path, tools)
        if identity:
            for ps, revision in identity:
                entries.append({"file": path.name, "postScriptName": ps, "fontRevision": revision, "source": "fonttools"})
        else:
            entries.append({"file": path.name, "postScriptName": path.stem, "fontRevision": "unknown", "source": "filename"})
    return entries


def replaced_slots(module: Path) -> list[str]:
    """Visible slot paths LuoShu replaced, from the payload / installed manifests."""
    result: list[str] = []
    config = module / "config"
    for name, field in (("font-payload-manifest.conf", 0), ("device-font-installed.conf", 1)):
        path = config / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = raw.strip().split("|")
            if len(parts) <= field:
                continue
            rel = parts[field].strip().lstrip("/")
            if "/fonts/" in f"/{rel}" and rel.lower().endswith(FONT_SUFFIXES) and rel not in result:
                result.append(rel)
    return result


def slot_postscript_names(module: Path, slots: list[str], tools: Any,
                          visible_root: str = "/") -> set[str]:
    names: set[str] = set()
    for rel in slots:
        names.add(Path(rel).stem)
        candidates = [module / ".luoshu-payload" / rel, module / rel, Path(visible_root) / rel]
        for candidate in candidates:
            if candidate.is_file():
                names.update(ps for ps, _ in font_identity(candidate, tools))
                break
    return {name for name in names if name}


def shadowed(entries: list[dict[str, str]], slot_names: set[str], slots: list[str],
             updated_from: list[str]) -> list[str]:
    lowered = {name.lower() for name in slot_names}
    slot_files = {os.path.basename(rel).lower() for rel in slots}
    result: list[str] = []
    for entry in entries:
        name = entry.get("postScriptName", "")
        if name and name.lower() in lowered and name not in result:
            result.append(name)
    for original in updated_from:
        base = os.path.basename(original)
        if base.lower() in slot_files:
            stem = Path(base).stem
            if stem not in result:
                result.append(stem)
    return sorted(result)


# ---------------------------------------------------------------- report
def _read_text(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def build_report(args: argparse.Namespace) -> dict[str, str]:
    dump = parse_font_dump(_read_text(args.font_dump))
    fonts_xml = parse_font_xml(_read_xml(args.fonts_xml))
    fallback = parse_font_xml(_read_xml(args.fallback_xml))
    customization_root = _read_xml(args.customization_xml)
    fallback = apply_customization(fallback, customization_root)
    parity = compare(dump, fonts_xml, fallback)

    tools = _fonttools()
    entries = scan_updatable_fonts(args.data_fonts, tools)
    slots = replaced_slots(args.module) if args.module else []
    slot_names = slot_postscript_names(args.module, slots, tools, args.visible_root) if args.module else set()
    shadow = shadowed(entries, slot_names, slots, dump.get("updatedFrom", []))
    status_text = _read_text(args.font_status)

    report = {
        "schema": SCHEMA,
        "time": str(int(time.time())),
        "xmlParity": parity,
        "sansSerifFontManager": safe_token(dump["sans-serif"]) or "none",
        "sansSerifFontsXml": safe_token(fonts_xml["sans-serif"]) or "none",
        "sansSerifFallbackXml": safe_token(fallback["sans-serif"]) or ("none" if fallback["available"] else "absent"),
        "zhHansFontManager": safe_token(dump["zh-Hans"]) or "none",
        "zhHansFontsXml": safe_token(fonts_xml["zh-Hans"]) or "none",
        "zhHansFallbackXml": safe_token(fallback["zh-Hans"]) or ("none" if fallback["available"] else "absent"),
        "fallbackXml": "present" if fallback["available"] else "absent",
        "customizationXml": "present" if customization_root is not None else "absent",
        "fontStatus": "available" if status_text.strip() else "unavailable",
        "updatableFontNameSource": "fonttools" if tools is not None else "filename",
        "updatableFonts": str(len(entries)),
        "updatableFontList": ";".join(
            f"{safe_token(e['postScriptName'])}@{safe_token(e['fontRevision'])}" for e in entries
        ) or "none",
        "replacedSlots": str(len(slots)),
        "shadowedByUpdatableFont": ",".join(safe_token(name) for name in shadow) or "none",
    }
    for line in status_text.splitlines()[:8]:
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = re.sub(r"[^A-Za-z0-9]", "", key.title())
        if key in ("CurrentVersion", "LastModifiedDate", "NumberOfUpdatedFontFiles"):
            report["fontStatus" + key] = safe_token(value.strip())
    return report


def render(report: dict[str, str]) -> str:
    return "".join(f"{key}={value}\n" for key, value in report.items())


def atomic_write(text: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    try:
        temporary.chmod(0o644)
    except OSError:
        pass
    temporary.replace(output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dump", type=Path)
    parser.add_argument("--font-status", type=Path)
    parser.add_argument("--fonts-xml", type=Path, default=Path("/system/etc/fonts.xml"))
    parser.add_argument("--fallback-xml", type=Path, default=Path("/system/etc/font_fallback.xml"))
    parser.add_argument("--customization-xml", type=Path, default=Path("/product/etc/fonts_customization.xml"))
    parser.add_argument("--data-fonts", type=Path, default=Path("/data/fonts/files"))
    parser.add_argument("--module", type=Path)
    parser.add_argument("--visible-root", default="/")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args)
    except Exception as exc:  # diagnostics must never break the caller
        report = {"schema": SCHEMA, "time": str(int(time.time())),
                  "xmlParity": "unknown:helper-error-" + safe_token(exc.__class__.__name__),
                  "shadowedByUpdatableFont": "unknown"}
    text = render(report)
    if args.output:
        try:
            atomic_write(text, args.output)
        except OSError:
            pass
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
