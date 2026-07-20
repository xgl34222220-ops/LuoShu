#!/usr/bin/env python3
"""Collect cross-device Android font configuration and mount diagnostics."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

MODDIR = Path(os.environ.get("MODDIR", "/data/adb/modules/LuoShu"))
REPORT = Path(os.environ.get("LUOSHU_FONT_PROBE_REPORT", str(MODDIR / "logs/font-runtime-probe.txt")))
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
CONFIG_PATHS = [
    Path("/system/etc/fonts.xml"),
    Path("/system/etc/font_fallback.xml"),
    Path("/product/etc/fonts_customization.xml"),
    Path("/product/etc/fonts.xml"),
    Path("/system_ext/etc/fonts_customization.xml"),
    Path("/system_ext/etc/fonts.xml"),
    Path("/vendor/etc/fonts_customization.xml"),
    Path("/vendor/etc/fonts.xml"),
    Path("/my_product/etc/fonts_customization.xml"),
    Path("/my_product/etc/fonts.xml"),
]
FONT_DIRS = [
    Path("/system/fonts"),
    Path("/product/fonts"),
    Path("/system_ext/fonts"),
    Path("/vendor/fonts"),
    Path("/my_product/fonts"),
    Path("/data/fonts/files"),
    Path("/data/system/theme/fonts"),
    MODDIR / "system/fonts",
    MODDIR / "product/fonts",
    MODDIR / "system_ext/fonts",
    MODDIR / "vendor/fonts",
    MODDIR / "my_product/fonts",
]
TARGET_PACKAGES = ["com.android.vending", "com.android.deskclock", "com.miui.clock"]


def run(*args: str, timeout: int = 20) -> str:
    try:
        proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (proc.stdout or proc.stderr or "").strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return "unreadable"
    return digest.hexdigest()


def list_users() -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"UserInfo\{(\d+):", run("cmd", "user", "list")):
        values.append(match.group(1))
    user_root = Path("/data/user")
    if user_root.is_dir():
        for item in user_root.iterdir():
            if item.is_dir() and item.name.isdigit():
                values.append(item.name)
    values.append("0")
    return sorted(set(values), key=int)


def dump_xml(path: Path, out: list[str]) -> None:
    if not path.is_file():
        return
    out.append(f"\n[{path}]")
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        out.append(f"parseError={exc}")
        return

    count = 0
    for family in root.iter():
        if local_name(family.tag) != "family":
            continue
        name = family.attrib.get("name", "(fallback)")
        lang = family.attrib.get("lang", "")
        variant = family.attrib.get("variant", "")
        out.append(f"family={name} lang={lang} variant={variant}".rstrip())
        for child in family:
            if local_name(child.tag) != "font":
                continue
            filename = (child.text or "").strip().splitlines()[0] if (child.text or "").strip() else ""
            axes = []
            for axis in child:
                if local_name(axis.tag) == "axis":
                    axes.append(f"{axis.attrib.get('tag', '')}={axis.attrib.get('stylevalue', '')}")
            out.append(
                "  font={} weight={} style={} index={} axes={}".format(
                    filename,
                    child.attrib.get("weight", "400"),
                    child.attrib.get("style", "normal"),
                    child.attrib.get("index", "0"),
                    ",".join(axes),
                )
            )
            count += 1
            if count >= 1200:
                out.append("  ...truncated...")
                return
    for alias in root.iter():
        if local_name(alias.tag) == "alias":
            out.append(
                f"alias={alias.attrib.get('name', '')} to={alias.attrib.get('to', '')} "
                f"weight={alias.attrib.get('weight', '')}".rstrip()
            )


def dump_font_dir(path: Path, out: list[str]) -> None:
    if not path.exists():
        return
    out.append(f"\n[{path}]")
    entries: list[Path] = []
    try:
        for root, dirs, files in os.walk(path):
            rel_depth = len(Path(root).relative_to(path).parts)
            if rel_depth >= 2:
                dirs[:] = []
            for name in files:
                item = Path(root) / name
                if item.suffix.lower() in FONT_EXTENSIONS:
                    entries.append(item)
    except OSError as exc:
        out.append(f"walkError={exc}")
        return

    for item in sorted(entries)[:1500]:
        try:
            stat = item.stat()
            rel = item.relative_to(path)
            link = os.readlink(item) if item.is_symlink() else ""
            out.append(
                f"{rel}|size={stat.st_size}|dev={stat.st_dev}|ino={stat.st_ino}|link={link}"
            )
        except OSError as exc:
            out.append(f"{item.name}|error={exc}")
    if len(entries) > 1500:
        out.append(f"...truncated total={len(entries)}...")


def package_paths(package: str) -> list[Path]:
    paths: list[Path] = []
    for line in run("pm", "path", package).splitlines():
        if line.startswith("package:"):
            paths.append(Path(line[8:]))
    return paths


def dump_apk_fonts(package: str, out: list[str]) -> None:
    out.append(f"\n[{package} APK fonts]")
    paths = package_paths(package)
    if not paths:
        out.append("notInstalled=true")
        return
    matched = 0
    for apk in paths:
        out.append(f"apk={apk}")
        try:
            with zipfile.ZipFile(apk) as archive:
                for name in archive.namelist():
                    lower = name.lower()
                    if (
                        lower.startswith("res/font/")
                        or "/res/font/" in lower
                        or "assets/font" in lower
                        or lower.endswith((".ttf", ".otf", ".ttc"))
                    ):
                        out.append(f"  {name}")
                        matched += 1
                        if matched >= 500:
                            out.append("  ...truncated...")
                            return
        except (OSError, zipfile.BadZipFile) as exc:
            out.append(f"  zipError={exc}")
    if matched == 0:
        out.append("bundledFonts=none")


def dump_mountinfo(out: list[str]) -> None:
    for source in (Path("/proc/self/mountinfo"), Path("/proc/1/mountinfo")):
        if not source.is_file():
            continue
        out.append(f"\n[{source} font mounts]")
        try:
            lines = source.read_text(errors="replace").splitlines()
        except OSError as exc:
            out.append(f"readError={exc}")
            continue
        hits = [line for line in lines if "font" in line.lower() or "luoshu" in line.lower()]
        out.extend(hits[:500] or ["none"])


def dump_overlay_comparison(out: list[str]) -> None:
    out.append("\n# Overlay comparison")
    state = MODDIR / "config/hyperos_dynamic_targets.conf"
    names = {
        "MiSansVF.ttf",
        "MiSansVF_Overlay.ttf",
        "MiSansLatinVF.ttf",
        "Roboto-Regular.ttf",
        "RobotoFlex-Regular.ttf",
        "GoogleSans-Regular.ttf",
        "SourceSansPro-Regular.ttf",
    }
    if state.is_file():
        try:
            names.update(line.strip() for line in state.read_text(errors="replace").splitlines() if line.strip())
        except OSError:
            pass
    roots = [Path("/system/fonts"), Path("/product/fonts"), Path("/system_ext/fonts")]
    module_roots = [MODDIR / "system/fonts", MODDIR / "product/fonts", MODDIR / "system_ext/fonts"]
    for name in sorted(names):
        visible = next((root / name for root in roots if (root / name).exists()), None)
        module = next((root / name for root in module_roots if (root / name).exists()), None)
        if not visible and not module:
            continue
        visible_info = "missing"
        module_info = "missing"
        if visible:
            visible_info = f"{visible}|size={visible.stat().st_size}|sha256={file_sha256(visible)}"
        if module:
            module_info = f"{module}|size={module.stat().st_size}|sha256={file_sha256(module)}"
        out.append(f"target={name}")
        out.append(f"  visible={visible_info}")
        out.append(f"  module={module_info}")


def main() -> int:
    out: list[str] = ["# LuoShu font runtime probe v2"]
    out.append(f"time={run('date', '+%Y-%m-%d %H:%M:%S')}")
    for key in (
        "ro.product.manufacturer",
        "ro.product.brand",
        "ro.product.model",
        "ro.product.device",
        "ro.build.version.release",
        "ro.build.version.sdk",
        "ro.build.display.id",
        "ro.mi.os.version.name",
        "ro.miui.ui.version.code",
    ):
        out.append(f"{key}={run('getprop', key)}")

    out.append("\n# GMS downloadable font provider")
    out.append(f"gmsPath={','.join(str(path) for path in package_paths('com.google.android.gms'))}")
    bridge = MODDIR / "common/play_font_bridge"
    if bridge.is_file():
        status = run("sh", str(bridge), "status")
        out.extend(status.splitlines() or ["bridgeStatus=empty"])
    dump_lines = [line for line in run("dumpsys", "package", "com.google.android.gms", timeout=30).splitlines() if "font" in line.lower()]
    out.append("dumpsysFontEntries:")
    out.extend(f"  {line}" for line in dump_lines[:200])

    out.append("\n# Font configuration")
    for path in CONFIG_PATHS:
        dump_xml(path, out)

    out.append("\n# Physical and module font files")
    for path in FONT_DIRS:
        dump_font_dir(path, out)

    dump_overlay_comparison(out)
    dump_mountinfo(out)
    for package in TARGET_PACKAGES:
        dump_apk_fonts(package, out)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(REPORT, 0o644)
    print(REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
