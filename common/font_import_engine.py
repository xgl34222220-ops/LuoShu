#!/usr/bin/env python3
"""Content-based font import. Archives are data; their scripts are never extracted/run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
import zipfile

from fontTools.ttLib import TTFont, TTCollection
from font_metadata import axes, best_family, best_subfamily, coverage, italic, os2_weight, text_role_counts, protected_text_font

MAX_BYTES = 256 * 1024 * 1024
MAX_EXTRACT_BYTES = 512 * 1024 * 1024
MAX_FACES = 128
MAGIC = {b"\0\1\0\0": "TTF", b"true": "TTF", b"OTTO": "OTF", b"ttcf": "TTC",
         b"wOFF": "WOFF", b"wOF2": "WOFF2", b"PK\3\4": "ZIP", b"PK\5\6": "ZIP"}
STYLE = re.compile(r"[-_](?:(?:thin|extralight|ultralight|light|regular|book|normal|medium|semibold|demibold|bold|extrabold|ultrabold|black|heavy)(?:[-_]?(?:italic|oblique))?|(?:italic|oblique)(?:[-_]?(?:thin|extralight|light|regular|medium|semibold|bold|extrabold|black))?|w(?:[1-9]|[1-9]00)|[1-9]00)$", re.I)
FONT_SUFFIXES = {".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2", ".pfb", ".pfa", ".bdf", ".pcf", ".fon", ".fnt", ".eot"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def clean(value: str, fallback: str = "ImportedFont") -> str:
    value = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]+", "-", str(value))
    value = re.sub(r"[\s_]+", "-", value).strip(" .-")
    return value[:96] or fallback


def weight_label(weight: int) -> str:
    return ("Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Black")[max(0, min(8, (weight + 50) // 100 - 1))]


def format_of(path: Path) -> str:
    with path.open("rb") as handle:
        return MAGIC.get(handle.read(4), "UNKNOWN")


def unsupported(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in {".pfb", ".pfa", ".bdf", ".pcf", ".fon", ".fnt", ".eot"}:
        return "该 Type 1、位图或 EOT 格式尚无可靠转换器；请提供 TTF、OTF、TTC/OTC、WOFF/WOFF2"
    return "无法识别字体内容；支持 SFNT、TTC/OTC、WOFF/WOFF2 和字体模块 ZIP，扩展名不限"


class Importer:
    def __init__(self, work: Path):
        self.work = work
        self.rows: list[dict] = []
        self.issues: list[dict] = []
        self.props: dict[str, str] = {}
        self.expanded_bytes = 0
        self.members = 0
        self.seen_sources: set[str] = set()
        self.seen_fonts: set[str] = set()

    def issue(self, name: str, message: str):
        self.issues.append({"source": name, "reason": str(message)})

    def font(self, path: Path, name: str):
        kind = format_of(path)
        if kind not in {"TTF", "OTF", "TTC", "WOFF", "WOFF2"}:
            raise ValueError(unsupported(name))
        if kind in {"WOFF", "WOFF2"}:
            with path.open("rb") as handle:
                header = handle.read(20)
            if len(header) < 20 or struct.unpack(">I", header[16:20])[0] > MAX_BYTES:
                raise ValueError("网页字体解压尺寸异常或超过 256 MB")
        source_hash = digest(path)
        if source_hash in self.seen_sources:
            return
        self.seen_sources.add(source_hash)
        count = 1
        if kind == "TTC":
            collection = TTCollection(path, lazy=True)
            try:
                count = len(collection.fonts)
            finally:
                collection.close()
        if not 0 < count <= MAX_FACES or len(self.rows) + count > MAX_FACES:
            raise ValueError("导入字体面超过 128 个限制")
        for face_index in range(count):
            try:
                self.face(path, name, kind, source_hash, face_index)
            except Exception as error:
                self.issue(f"{name} [face {face_index}]", str(error))

    def face(self, path: Path, name: str, kind: str, source_hash: str, index: int):
        options = {"lazy": True, "recalcTimestamp": False}
        if kind == "TTC":
            options["fontNumber"] = index
        try:
            font = TTFont(path, **options)
        except ImportError as error:
            raise ValueError("WOFF2 解码组件不可用，未把压缩字体伪装为 TTF") from error
        try:
            if not all(tag in font for tag in ("head", "maxp", "cmap", "hhea", "hmtx")):
                raise ValueError("缺少必要的 SFNT 字符或度量表")
            if "glyf" in font:
                ext = "ttf"
            elif "CFF " in font or "CFF2" in font:
                ext = "otf"
            else:
                raise ValueError("仅有位图或无支持的 glyf/CFF/CFF2 轮廓")
            family = best_family(font)
            subfamily = best_subfamily(font)
            if protected_text_font(font):
                raise ValueError("Emoji、彩色或图标字体保留，不导入文字替换库")
            cmap = font.getBestCmap() or {}
            roles = text_role_counts(cmap)
            if not any(roles.values()):
                raise ValueError("没有可用于替换的中、英、数字形")
            gids = set(font.getGlyphOrder())
            if not gids or any(glyph not in gids for glyph in cmap.values()):
                raise ValueError("字符映射引用不存在的字形")
            metadata = coverage(font)
            face_axes = axes(font)
            weight = max(1, min(1000, os2_weight(font)))
            is_italic = italic(font)
            # Preserve real family/style/axes; the filename is only an App grouping key.
            base_stem = Path(name).stem
            matched = STYLE.search(base_stem)
            group = base_stem[:matched.start()] if matched and kind != "TTC" else family
            output = self.work / f"font-{len(self.rows):04d}.{ext}"
            if kind in {"TTF", "OTF"}:
                shutil.copyfile(path, output)
            else:
                font.flavor = None
                font.save(output, reorderTables=False)
            if output.stat().st_size > MAX_BYTES:
                raise ValueError("规范化后的字体超过 256 MB")
            # Re-open SFNT after decompression/extraction before publishing any file.
            with TTFont(output, lazy=True, recalcTimestamp=False) as verified:
                if verified.flavor is not None or (verified.getBestCmap() or {}) != cmap:
                    raise ValueError("字体规范化后字符映射不一致")
                if axes(verified) != face_axes or os2_weight(verified) != os2_weight(font):
                    raise ValueError("字体规范化后字重或变量轴不一致")
            font_hash = digest(output)
            if font_hash in self.seen_fonts:
                output.unlink()
                return
            self.seen_fonts.add(font_hash)
            self.rows.append({"path": str(output), "sha256": font_hash, "sourceUid": f"sha256:{source_hash}:face:{index}",
                              "source": name, "faceIndex": index, "family": family, "group": clean(group), "subfamily": subfamily,
                              "format": ext.upper(), "sourceFormat": kind, "weight": weight, "italic": is_italic,
                              "variable": bool(face_axes), "axes": face_axes, "roleCounts": roles,
                              "supportsCjk": bool(metadata["roles"]["cjk"])})
        finally:
            font.close()

    def archive(self, path: Path, prefix: str = "", depth: int = 0):
        if depth > 2:
            self.issue(prefix, "嵌套字体包超过三层，未展开")
            return
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                self.members += 1
                if self.members > 4096:
                    raise ValueError("字体包成员超过 4096 个限制")
                name = prefix + info.filename
                parts = PurePosixPath(info.filename.replace("\\", "/"))
                if info.is_dir():
                    continue
                if parts.is_absolute() or ".." in parts.parts or stat.S_ISLNK(info.external_attr >> 16):
                    self.issue(name, "跳过链接或越界路径")
                    continue
                if parts.name == "module.prop" and not self.props and info.file_size <= 65536:
                    for line in archive.read(info).decode("utf-8", "replace").splitlines():
                        key, sep, value = line.partition("=")
                        if sep and key in {"name", "version", "author"}:
                            self.props[key] = value.replace("\x00", "").strip()
                    continue
                target = None
                try:
                    with archive.open(info) as source:
                        magic = source.read(4)
                        kind = MAGIC.get(magic, "UNKNOWN")
                        if kind == "UNKNOWN":
                            if Path(info.filename).suffix.lower() in FONT_SUFFIXES:
                                self.issue(name, unsupported(info.filename))
                            continue
                        if info.file_size > MAX_BYTES or self.expanded_bytes + info.file_size > MAX_EXTRACT_BYTES:
                            raise ValueError("字体包解压超出单文件 256 MB / 总计 512 MB 限制")
                        self.expanded_bytes += info.file_size
                        target = self.work / f"member-{self.members:04d}"
                        with target.open("wb") as output:
                            output.write(magic)
                            remaining = min(MAX_BYTES, info.file_size) - 4
                            while True:
                                chunk = source.read(min(1024 * 1024, remaining + 1))
                                if not chunk:
                                    break
                                remaining -= len(chunk)
                                if remaining < 0:
                                    raise ValueError("字体包成员超过声明尺寸")
                                output.write(chunk)
                    if kind == "ZIP":
                        self.archive(target, name + "!", depth + 1)
                    else:
                        self.font(target, name)
                except Exception as error:
                    self.issue(name, str(error))
                finally:
                    if target is not None:
                        target.unlink(missing_ok=True)


def publish(importer: Importer, output_dir: Path, label: str, archive: bool) -> dict:
    rows = importer.rows
    if not rows:
        reasons = "; ".join(item["reason"] for item in importer.issues[:3])
        raise ValueError("没有可导入的文字字体" + ("：" + reasons if reasons else ""))
    output_dir.mkdir(parents=True, exist_ok=True)
    display = importer.props.get("name") or Path(label).stem or "ImportedFont"
    groups = list(dict.fromkeys(row["group"] for row in rows))
    # A one-family module keeps its existing user-facing family identity.
    names = {group: clean(display) if archive and len(groups) == 1 else clean((display + "-" if archive else "") + group) for group in groups}
    existing: dict[int, list[Path]] = {}
    for file in output_dir.iterdir():
        if file.is_file() and not file.is_symlink() and file.suffix.lower() in {".ttf", ".otf", ".ttc", ".otc"}:
            existing.setdefault(file.stat().st_size, []).append(file)
    hashes: dict[Path, str] = {}
    changes: list[tuple[Path, bytes | None]] = []
    imported = duplicates = 0
    results = []
    try:
        for row in rows:
            source = Path(row["path"])
            twin = None
            for file in existing.get(source.stat().st_size, []):
                if file not in hashes:
                    hashes[file] = digest(file)
                if hashes[file] == row["sha256"]:
                    twin = file
                    break
            stem = names[row["group"]]
            suffix = ("Italic-" if row["italic"] else "") + weight_label(row["weight"])
            # Variable and static faces with the same nominal weight stay distinct.
            variant = "-Variable" if row["variable"] else ""
            target = twin or output_dir / f"{stem}{variant}-{suffix}.{row['format'].lower()}"
            serial = 0
            while not twin and (target.exists() or target.is_symlink()):
                if target.is_file() and not target.is_symlink() and digest(target) == row["sha256"]:
                    break
                serial += 1
                collision = row["sha256"][:10] + (f"-{serial}" if serial > 1 else "")
                target = output_dir / f"{stem}-{collision}{variant}-{suffix}.{row['format'].lower()}"
            if twin or (target.is_file() and not target.is_symlink() and digest(target) == row["sha256"]):
                duplicates += 1
                duplicate = True
            else:
                changes.append((target, None))
                with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".import-", delete=False) as temp:
                    stage = Path(temp.name)
                try:
                    shutil.copyfile(source, stage)
                    stage.chmod(0o644)
                    os.replace(stage, target)
                finally:
                    stage.unlink(missing_ok=True)
                existing.setdefault(source.stat().st_size, []).append(target)
                hashes[target] = row["sha256"]
                imported += 1
                duplicate = False
            result = {key: value for key, value in row.items() if key not in {"path", "group"}}
            result.update(path=str(target), fileName=target.name, duplicate=duplicate, id=target.stem.removesuffix("-" + suffix))
            results.append(result)
        for stem in dict.fromkeys(row["id"] for row in results):
            members = [row for row in results if row["id"] == stem]
            group = members[0]["family"]
            conf = output_dir / f"{stem}.conf"
            # Keep unrelated existing metadata intact on a duplicate import.
            if conf.exists():
                continue
            values = {"name": display if len(groups) == 1 else f"{display} · {group}",
                      "description": "从字体模块导入" if archive else "导入字体文件",
                      "supports_cjk": str(any(row["supportsCjk"] for row in members)).lower(),
                      "is_variable": str(any(row["variable"] for row in members)).lower(),
                      "version": importer.props.get("version", ""), "author": importer.props.get("author", "")}
            changes.append((conf, None))
            conf.write_text("".join(f"{key}={value.replace(chr(10), ' ').replace(chr(13), ' ')}\n" for key, value in values.items()), encoding="utf-8")
    except Exception:
        for target, backup in reversed(changes):
            if backup is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(backup)
        raise
    best = max(results, key=lambda row: (row["supportsCjk"], row["roleCounts"]["cjk"], -abs(row["weight"] - 400), not row["italic"]))
    return {"status": "ok", "data": {"kind": "zip" if archive else "collection" if len(rows) > 1 else "font",
            "id": best["id"], "name": display, "displayName": display,
            "selected": best["fileName"], "source": best["source"], "family": best["family"], "format": best["format"],
            "supportsCjk": best["supportsCjk"], "mode": "family" if len(rows) > 1 else "variable" if best["variable"] else "single",
            "faceCount": len(rows), "familyFiles": len(rows), "familyCount": len(groups), "imported": imported,
            "importedText": imported, "duplicates": duplicates, "duplicate": imported == 0, "faces": results,
            "valid": len(rows), "invalid": len(importer.issues), "ignored": len(importer.issues), "issues": importer.issues,
            "message": f"已导入 {imported} 个字体面，{duplicates} 个已存在" + (f"；{len(importer.issues)} 项未导入，见详情" if importer.issues else "")}}


def import_file(source: Path, output_dir: Path, label: str) -> dict:
    if not source.is_file() or not 12 <= source.stat().st_size <= MAX_BYTES:
        raise ValueError("字体文件不存在、内容过小或超过 256 MB")
    with tempfile.TemporaryDirectory(prefix="luoshu-import-") as temporary:
        importer = Importer(Path(temporary))
        archive = format_of(source) == "ZIP"
        if archive:
            importer.archive(source)
        else:
            importer.font(source, label)
        return publish(importer, output_dir, label, archive)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--label", default="ImportedFont")
    args = parser.parse_args()
    try:
        result = import_file(Path(args.input), Path(args.output_dir), args.label)
        code = 0
    except Exception as error:
        result = {"status": "error", "message": str(error) or error.__class__.__name__}
        code = 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
