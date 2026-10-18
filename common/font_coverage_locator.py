#!/usr/bin/env python3
"""Why is this screen not using my font?" - read-only per-package locator.

The App's 未覆盖界面定位 asks for one package (status bar -> SystemUI, lock
screen -> SystemUI/AOD, launcher, settings, any app). This helper runs the
existing per-process audit (device_font_process_audit) against that process,
using ``/proc/<pid>/root`` as the visible root so every path is judged in the
process's own mount namespace, then sorts what it finds into the causes users
actually hit, each with a concrete next step. The stock-file policy follows the
ROM: HyperOS uses hyperos_physical_policy, ColorOS/OxygenOS the ColorOS target
lists (coloros_global.sh) and coloros_latin_policy, other ROMs the module's
actual payload. Files kept stock by design are listed apart, never as misses:

* ``theme-takeover``   theme-store font owns the theme route
* ``outside-whitelist`` the process reads a stock file LuoShu does not replace
* ``namespace-hidden`` the module is invisible in that process (KernelSU
  "unmount modules" / App Profile, Magisk DenyList, mounted after start)
* ``app-embedded``     the app ships/downloads its own fonts or a WebView/X5/
  XWeb engine renders them (WeChat, QQ, Alipay, Chrome web fonts)
* ``link-switched``    the process loaded a font before LuoShu's mount or the
  framework re-pointed a link after boot
* ``weight-loss``      a static font sits on a variable MiSansVF slot, so
  medium/bold render as regular
* ``collection-kept``  the stock NotoSans/SerifCJK collection could not be
  rebuilt this time; the reason comes from .luoshu-metrics-report.json
* ``flip-font``        ColorOS Settings/Theme font owns the OPlus flip font
* ``covered``          every mapped font is LuoShu's

Nothing is modified: maps, stat and (optionally) a font table read.
``--scan``: locate() over every running app process, with fixable settings.
``--export``: one sanitized full coverage report file (scan + payload/mount/
metrics/theme/WebView evidence + recent log), see export().
Output: one JSON object on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import device_font_process_audit as audit  # noqa: E402

try:
    import hyperos_physical_policy as policy  # noqa: E402
except ImportError:  # pragma: no cover
    policy = None
try:
    import coloros_latin_policy as coloros_policy  # noqa: E402
except ImportError:  # pragma: no cover
    coloros_policy = None

SCHEMA = "luoshu-coverage-locator-v1"
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+(:[A-Za-z0-9_.]+)?$")
# Apps that render most text with bundled fonts or their own web engine.
EMBEDDED_FONT_APPS = {
    "com.tencent.mm": "微信（XWeb 内核与内置字体）",
    "com.tencent.mobileqq": "QQ（X5 内核与内置字体）",
    "com.tencent.tim": "TIM（X5 内核与内置字体）",
    "com.eg.android.AlipayGphone": "支付宝（内置数字/金额字体）",
    "com.ss.android.ugc.aweme": "抖音（内置字体）",
}
WEB_ENGINES = {
    "com.android.chrome": "Chrome（网页字体由网站提供）",
    "com.google.android.webview": "Android System WebView",
    "com.android.webview": "Android WebView",
}
THEME_PLACEHOLDER_MAX_BYTES = 65536
MAX_FILES = 48  # findings list every file (the App shows the first few)

GUIDE = {
    "theme-takeover": (
        "主题商店字体接管了系统字体",
        "在主题商店把字体切回“默认/MiSans”后重启；或在洛书 HyperOS 覆盖设置里开启“接管主题商店字体”（默认关，重启生效）。"),
    "outside-whitelist": (
        "该界面读取了洛书没有替换的原厂字体文件",
        "若文件属于锁屏/小部件样式组，可在 HyperOS 覆盖设置里开启该组后重新应用字体；MiSansL3 生僻字库/其他文字语种字体按设计保留原厂；其他文件名请导出诊断反馈。"),
    "namespace-hidden": (
        "该应用的挂载命名空间里看不到洛书模块",
        "KernelSU：在管理器 App Profile 里关闭该应用的“卸载模块”，并检查“默认卸载模块”；Magisk：把该应用移出 DenyList。然后强行停止该应用再打开。"),
    "app-embedded": (
        "该应用使用自带字体或独立网页内核",
        "微信、QQ、支付宝等内嵌字体与 Chrome 网页字体不在系统字体覆盖范围内，洛书无法替换（主模块不做 Hook）。"),
    "link-switched": (
        "进程在洛书挂载前加载了字体，或开机后系统切换了字体链接",
        "强行停止该应用（系统界面可重启）后再看；若每次开机都出现，请导出诊断反馈。"),
    "weight-loss": (
        "静态字体压在可变字体槽上，粗细变化丢失",
        "改用带字重轴的可变字体，或在字体组合里补齐中粗/粗体后重新应用。"),
    "covered": (
        "该进程读取的字体都来自洛书",
        "如仍觉得没变，可能是应用自绘图片文字；可截图并导出诊断反馈。"),
    "not-running": (
        "该应用当前没有运行",
        "先打开那个界面，保持在后台，再回到洛书重新检测。"),
    "no-payload": (
        "洛书当前没有生效的字体负载",
        "先在字体库应用一款字体并重启。"),
    "unreadable": (
        "无法读取该进程的字体映射",
        "请确认已授予洛书 Root 权限后重试。"),
    "collection-kept": (
        "本机 CJK 字体集合本次未能替换，已保留原厂",
        "原因见详情；重新应用字体会再次尝试。若反复出现，请导出完整诊断反馈。"),
    "flip-font": (
        "ColorOS 系统字体设置/主题字体接管了 flip 字体",
        "在 设置→字体 改回系统自带字体（不使用主题商店字体）后重启，再重新应用洛书。"),
}
# The same causes worded for the ROM in use (HyperOS keeps the texts above).
ROM_GUIDE = {
    "coloros": {
        "theme-takeover": ("主题/系统字体设置接管了系统字体",
                           "在 设置→字体 或主题商店改回系统默认字体后重启，再重新应用洛书。"),
        "outside-whitelist": ("该界面读取了洛书没有替换的原厂字体文件",
                              "SysSans/OPlusSans/时钟等替换目标之外的文件名请导出完整诊断反馈；"
                              "OSans-RC 生僻字库与其他语种字体按设计保留原厂。"),
    },
    "other": {
        "theme-takeover": ("主题字体接管了系统字体",
                           "在系统主题/字体设置中改回默认字体后重启，再重新应用洛书。"),
        "outside-whitelist": ("该界面读取了洛书没有替换的原厂字体文件",
                              "这些文件不在洛书本次实际替换的清单里；请导出完整诊断反馈文件名。"),
    },
}
ROMS = ("hyperos", "coloros", "other")
ROM_LABELS = {"hyperos": "HyperOS", "coloros": "ColorOS / OxygenOS", "other": "当前系统"}


def finding(category: str, files: list[str] | None = None, detail: str = "",
            rom: str = "hyperos") -> dict[str, Any]:
    title, action = ROM_GUIDE.get(rom, {}).get(category) or GUIDE[category]
    return {"category": category, "title": title, "action": action,
            "detail": detail, "files": (files or [])[:MAX_FILES]}


def _split(value: str) -> list[str]:
    return [] if not value or value == "none" else [item for item in value.split(";") if item]


THEME_ROBOTO_MAX_BYTES = 4 * 1024 * 1024


def _journal_ids(path: Path, field: int) -> set[tuple[int, int]]:
    ids = set()
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return ids
    for line in lines:
        parts = line.split("|")
        bits = parts[field].split(":") if len(parts) > field else []
        if len(bits) >= 2 and bits[0].isdigit() and bits[1].isdigit():
            ids.add((int(bits[0]), int(bits[1])))
    return ids


def _same_bytes(path: Path, candidates: list[Path]) -> bool:
    try:
        size, data = path.stat().st_size, None
        for candidate in candidates:
            if candidate.is_file() and candidate.stat().st_size == size:
                data = data or path.read_bytes()
                if candidate.read_bytes() == data:
                    return True
    except OSError:
        pass
    return False


def theme_state(theme_dir: Path, module: Path | None = None,
                stock_dir: Path = Path("/system/fonts")) -> dict[str, Any]:
    """Same rules as hyperos_theme_takeover.sh _lht_classify: LuoShu's own files
    (webview-route clone, provider theme views, payload copies), ROM copies and the
    theme engine's Roboto are not theme-store fonts; takeover-owned files are."""
    files, user, own = [], [], []
    try:
        entries = sorted(theme_dir.iterdir())
    except OSError:
        entries = []
    config = (module / "config") if module else Path("/nonexistent")
    luoshu = _journal_ids(config / "hyperos-webview-route.conf", 3) | \
        _journal_ids(config / "hyperos-theme-font-namespaces.conf", 1)
    for folder in ("hyperos-webview-route", "hyperos-theme-font"):
        luoshu |= {i for i in map(_stat_id, config.glob(f"{folder}/*.ttf")) if i}
    takeover = _journal_ids(config / "hyperos-theme-takeover.journal", 3)
    fonts = (module / ".luoshu-payload/system/fonts") if module else Path("/nonexistent")
    for entry in entries:
        if not entry.is_file() or entry.is_symlink() or \
                not entry.name.lower().endswith((".ttf", ".otf", ".ttc")):
            continue
        files.append(entry.name)
        identity = _stat_id(entry)
        try:
            size = entry.stat().st_size
        except OSError:
            size = 0
        if identity in takeover:
            kind = "user"
        elif identity in luoshu or _same_bytes(entry, [*fonts.glob(".luoshu-font-store/*.font"), *fonts.glob("*.ttf")]):
            kind = "luoshu"
        elif size <= THEME_PLACEHOLDER_MAX_BYTES or _same_bytes(
                entry, [stock_dir / "Roboto-Regular.ttf", stock_dir / entry.name, stock_dir / "MiSansVF.ttf"]):
            kind = "stock"
        elif size <= THEME_ROBOTO_MAX_BYTES and re.search(rb"(?<![A-Za-z])Roboto", entry.read_bytes().replace(b"\0", b"")):
            kind = "stock"
        else:
            kind = "user"
        (user if kind == "user" else own if kind == "luoshu" else []).append(entry.name)
    state = "user-theme" if user else ("placeholder" if files else "none")
    return {"state": state, "files": files[:MAX_FILES], "userFiles": user[:MAX_FILES],
            "luoshuFiles": own[:MAX_FILES]}


def _stat_id(path: Path) -> tuple[int, int] | None:
    try:
        st = os.stat(path)
        return (st.st_dev, st.st_ino)
    except OSError:
        return None


def _shows_payload(payload: audit.PayloadIndex, logical: str, visible: Path) -> bool | None:
    """True/False when ``visible`` is/is not LuoShu's file; None when unreadable."""
    identity = _stat_id(visible)
    if identity is None:
        return None
    if identity in payload.ids:
        return True
    # OverlayFS reports its own device; fall back to size + sha256.
    return payload.same_content(logical, visible)


def namespace_hidden(payload: audit.PayloadIndex, proc_root: Path, pid: str,
                     host_root: Path, probes: list[str]) -> list[str]:
    """Slots that show LuoShu's file in the host namespace but stock in the app's."""
    hidden = []
    app_root = proc_root / pid / "root"
    for logical in probes:
        host = _shows_payload(payload, logical, host_root / logical.lstrip("/"))
        app = _shows_payload(payload, logical, app_root / logical.lstrip("/"))
        if host is True and app is False:
            hidden.append(logical)
    return hidden


def default_probes(payload: audit.PayloadIndex) -> list[str]:
    preferred = ("/system/fonts/MiSansVF.ttf", "/system/fonts/Roboto-Regular.ttf",
                 "/system/fonts/MiSansLatinVF.ttf", "/product/fonts/MiSansVF.ttf")
    picks = [path for path in preferred if payload.slot_for(path) is not None]
    if picks:
        return picks
    return ["/" + rel for rel in sorted(payload.by_rel)
            if rel.count("/") == 2 and "/fonts/" in "/" + rel][:4]


def static_on_variable_slot(payload_fonts: Path) -> bool:
    """True when the payload's MiSansVF.ttf has no fvar (static user font)."""
    target = payload_fonts / "MiSansVF.ttf"
    if not target.is_file():
        return False
    try:
        from fontTools.ttLib import TTFont  # type: ignore
        with TTFont(target, lazy=True, fontNumber=0) as font:
            return "fvar" not in font
    except Exception:
        return False


def classify_stock(path: str, groups: frozenset[str] | None) -> str:
    """HyperOS physical policy kind of a stock file (kept for callers/tests)."""
    name = path.split("@", 1)[0].rsplit("/", 1)[-1]
    if policy is None:
        return "unlisted"
    kind = policy.classify(name)
    if kind in policy.GROUP_DEFAULTS:
        active = policy.enabled_groups() if groups is None else groups
        return "group-on" if kind in active else f"group-off:{kind}"
    return kind


def _getprop(name: str) -> str:
    import subprocess
    try:
        return subprocess.run(["getprop", name], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def detect_rom(getprop: Callable[[str], str] = _getprop) -> str:
    """hyperos | coloros | other; LUOSHU_COVERAGE_ROM wins (bridge/tests)."""
    forced = os.environ.get("LUOSHU_COVERAGE_ROM", "").strip()
    if forced in ROMS:
        return forced
    if getprop("ro.mi.os.version.name") or getprop("ro.miui.ui.version.name"):
        return "hyperos"
    if (getprop("ro.build.version.oplusrom") or getprop("ro.build.version.opporom")
            or getprop("ro.oxygen.version") or Path("/data/oplus/os").is_dir()
            or Path("/system_ext/oplus").is_dir()):
        return "coloros"
    return "other"


METRICS_REPORT = ".luoshu-payload/.luoshu-metrics-report.json"
# HyperOS NotoSans/SerifCJK collections are rebuilt per face (hyperos_metrics_batch).
COLLECTION_TARGETS = ("NotoSansCJK-Regular.ttc", "NotoSerifCJK-Regular.ttc")
# AOSP named families apps request explicitly (casual, cursive, serif-monospace...).
DECORATIVE_PREFIXES = ("CarroisGothic", "ComingSoon", "DancingScript", "CutiveMono")
COLOROS_FLIP_PREFIXES = ("OplusOSUI-", "ColorOSUI-")


def load_metrics(module: Path | None) -> dict[str, Any]:
    try:
        data = json.loads((module / METRICS_REPORT).read_text(encoding="utf-8")) if module else {}
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def coloros_targets(module: Path | None) -> frozenset[str]:
    """Names the ColorOS mapper replaces (core/Google/vendor/OEM lists, digits and
    discovery), read from common/coloros_global.sh so both never drift."""
    script = (module / "common/coloros_global.sh") if module else None
    if script is None or not script.is_file():
        script = Path(__file__).resolve().parent / "coloros_global.sh"
    import subprocess
    env = dict(os.environ, MODULE_DIR=str(module or ""), MODDIR=str(module or ""))
    try:
        out = subprocess.run(["sh", "-c", '. "$1" >/dev/null 2>&1; get_all_coloros_files', "coverage", str(script)],
                             capture_output=True, text=True, timeout=10, env=env).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    return frozenset(line.strip() for line in out.splitlines() if line.strip())


class StockPolicy:
    """Why a stock file a process maps is (not) LuoShu's, for one ROM.

    ``judge(path)`` -> (kind, note): ``kept`` (by design, never a miss),
    ``outside`` (not on the ROM's target list: a real miss), ``group-off`` (an
    optional group the user can switch on), ``target`` (a listed target the
    current payload lacks: reapply, reported apart) or ``collection`` (rebuild
    failed; note = reason).
    """

    def __init__(self, rom: str, module: Path | None, payload: "audit.PayloadIndex | None" = None,
                 groups: frozenset[str] | None = None, metrics: dict[str, Any] | None = None,
                 coloros_names: frozenset[str] | None = None,
                 coloros_groups: frozenset[str] | None = None) -> None:
        self.rom = rom if rom in ROMS else "other"
        self.groups = groups
        self.metrics = load_metrics(module) if metrics is None else metrics
        self.payload_names = {Path(rel).name for rel in (payload.by_rel if payload else {})}
        self._coloros_names = coloros_names
        self._module = module
        self.coloros_groups = coloros_groups
        preserved = set(self.metrics.get("preservedDynamicAliases") or [])
        preserved |= set(self.metrics.get("preservedStockAliases") or [])
        fallback = self.metrics.get("preservedFallbackSlots") or {}
        preserved |= set(fallback if isinstance(fallback, (dict, list)) else [])
        self.preserved = preserved
        kept = self.metrics.get("preservedCollections") or {}
        self.collections_kept = kept if isinstance(kept, dict) else {}

    @property
    def coloros_names(self) -> frozenset[str]:
        if self._coloros_names is None:
            self._coloros_names = coloros_targets(self._module)
        return self._coloros_names

    def judge(self, path: str) -> tuple[str, str]:
        path = path.split("@", 1)[0]
        name = path.rsplit("/", 1)[-1]
        lower = name.lower()
        if path in self.collections_kept:
            return "collection", str(self.collections_kept[path])
        if path in self.preserved:
            return "kept", "ROM 动态别名/回退槽位"
        if lower.endswith((".ttc", ".otc")):
            if name in COLLECTION_TARGETS and (self.rom == "hyperos" or (
                    self.rom == "coloros" and coloros_policy is not None
                    and coloros_policy.cjk_collections_enabled(self._module))):
                return "outside", "CJK 集合在替换范围，但本次负载没有生成（未记录原因，请重新应用）"
            return "kept", "多语言字体集合"
        if policy is not None:
            kind = policy.classify(name)
            if kind == "excluded":
                return "kept", "斜体/衬线/表情/符号/其他语种字体"
            if kind == "rare-han":
                return "kept", "生僻字库"
        if coloros_policy is not None and coloros_policy.classify(name) == "keep":
            return "kept", "生僻字库/占位字体"
        if name.startswith(DECORATIVE_PREFIXES):
            return "kept", "应用显式指定的风格化字体族"
        if name.startswith("Noto") and (policy is None or policy.classify(name) == "unlisted"):
            return "kept", "其他文字语种字体"
        if self.rom == "hyperos" and policy is not None:
            kind = policy.classify(name)
            if kind in policy.GROUP_DEFAULTS:
                active = policy.enabled_groups() if self.groups is None else self.groups
                if kind not in active:
                    return "group-off", kind
                return "target", "所属可选组已开启，重新应用字体后替换"
            if kind in ("core", "clock"):
                return "target", "洛书替换目标，但本次负载没有该文件"
            return "outside", ""
        if self.rom == "coloros":
            if coloros_policy is not None and coloros_policy.classify(name) == "digits" \
                    and coloros_policy.keeps_stock(name, self.coloros_groups):
                return "group-off", "osans_digits"
            if name in self.coloros_names or name in self.payload_names:
                return "target", "ColorOS 替换目标，但本次负载没有该文件"
            return "outside", ""
        if name in self.payload_names:
            return "target", "同名文件已替换，但该分区路径未覆盖"
        return "outside", ""


def locate(package: str, pid: str, *, module: Path | None, proc_root: Path = Path("/proc"),
           host_root: Path = Path("/"), theme_dir: Path = Path("/data/system/theme/fonts"),
           groups: frozenset[str] | None = None, stock_dir: Path = Path("/system/fonts"),
           weight_probe: Callable[[Path], bool] = static_on_variable_slot,
           theme: dict[str, Any] | None = None, rom: str | None = None,
           stock_policy: StockPolicy | None = None) -> dict[str, Any]:
    rom = rom if rom in ROMS else detect_rom()
    result: dict[str, Any] = {"schema": SCHEMA, "package": package, "pid": pid or "",
                              "rom": rom, "findings": []}
    findings: list[dict[str, Any]] = result["findings"]

    def add(category: str, files: list[str] | None = None, detail: str = "") -> dict[str, Any]:
        item = finding(category, files, detail, rom)
        findings.append(item)
        return item

    if theme is None:
        theme = theme_state(theme_dir, module, stock_dir) if rom == "hyperos" else \
            {"state": "none", "files": [], "userFiles": [], "luoshuFiles": []}
    result["theme"] = theme
    if package in EMBEDDED_FONT_APPS or package in WEB_ENGINES:
        label = EMBEDDED_FONT_APPS.get(package) or WEB_ENGINES[package]
        add("app-embedded", [], label)
    if not pid or not pid.isdigit():
        findings.insert(0, finding("not-running", rom=rom))
        result["verdict"] = "not-running"
        return result
    visible = str(proc_root / pid / "root")
    args = SimpleNamespace(target=[f"app={pid}@{package}"], proc_root=str(proc_root),
                           module=module, visible_root=visible)
    # The audit's 24-path cap suits its summary file; the locator must see
    # every mapped stock file (zygote preloads all system fonts).
    listed, audit.MAX_LISTED = audit.MAX_LISTED, max(audit.MAX_LISTED, 512)
    try:
        report = audit.build_report(args)
    finally:
        audit.MAX_LISTED = listed
    result["audit"] = {key: value for key, value in report.items() if key.startswith(("app.", "font"))}
    state = report.get("app.state", "")
    if report.get("fontAudit") == "inactive:no-payload":
        findings.insert(0, finding("no-payload", rom=rom))
        result["verdict"] = "no-payload"
        return result
    if state != "ok":
        findings.insert(0, finding("unreadable", [], state, rom))
        result["verdict"] = "unreadable"
        return result

    payload = audit.PayloadIndex(module)
    theme_paths = _split(report.get("app.themePaths", ""))
    stock_paths = _split(report.get("app.stockPaths", ""))
    replaced = _split(report.get("app.replacedSlotStockPaths", ""))
    others = _split(report.get("app.otherFiles", ""))
    luoshu_hits = int(report.get("app.luoshuHits", "0") or 0)

    if theme["state"] == "user-theme" and (theme_paths or not luoshu_hits):
        add("theme-takeover", theme_paths or theme["userFiles"], "检测到 /data/system/theme/fonts 中有主题商店字体")
    elif theme_paths and theme["state"] == "user-theme":
        add("theme-takeover", theme_paths)

    flip = [name for name in others if rom == "coloros" and name.startswith(COLOROS_FLIP_PREFIXES)]
    if flip:
        add("flip-font", flip, "/data/format_unclear/font 中的英文数字 flip 字体不在 /system/fonts")
        others = [name for name in others if name not in flip]

    hidden = namespace_hidden(payload, proc_root, pid, host_root, default_probes(payload))
    if hidden:
        add("namespace-hidden", hidden)

    switched = [item for item in replaced if item.endswith(":loaded-before-mount")]
    if switched:
        add("link-switched", switched)

    judge = stock_policy or StockPolicy(rom, module, payload, groups)
    outside, kept, collections, pending = [], [], [], []
    replaced_paths = {item.split("@", 1)[0] for item in replaced}
    for item in stock_paths:
        path = item.split("@", 1)[0]
        if path in replaced_paths:
            continue
        kind, note = judge.judge(path)
        if kind == "kept":
            kept.append(f"{path}（按设计保留：{note}）")
        elif kind == "group-off":
            outside.append(f"{path}（{note} 组未开启）")
        elif kind == "collection":
            collections.append((path, note))
        elif kind == "target":
            pending.append(f"{path}（{note}）")
        else:
            outside.append(f"{path}（{note}）" if note else path)
    if collections:
        add("collection-kept", [path for path, _ in collections],
            "；".join(f"{path.rsplit('/', 1)[-1]}：{reason}" for path, reason in collections))
    if outside:
        add("outside-whitelist", outside)
    if kept:
        result["keptByDesign"] = kept[:MAX_FILES]
    if pending:
        result["targetsNotInPayload"] = pending[:MAX_FILES]
    if others and not any(f["category"] == "app-embedded" for f in findings):
        add("app-embedded", others, "进程自行打开了应用内或下载的字体文件")
    stock_on_slot = [item for item in replaced if not item.endswith(":loaded-before-mount")]
    if stock_on_slot and not hidden and not switched:
        add("link-switched", stock_on_slot, "已替换槽位仍映射原厂 inode")

    payload_fonts = (module / ".luoshu-payload/system/fonts") if module else Path("/nonexistent")
    if any("MiSansVF" in item for item in report.get("app.luoshuPaths", "").split(";")) \
            and weight_probe(payload_fonts):
        add("weight-loss", ["MiSansVF.ttf"])

    if not findings:
        add("covered")
    result["verdict"] = findings[0]["category"]
    return result


SCAN_SCHEMA = "luoshu-coverage-scan-v1"
GROUP_OFF_RE = re.compile(r"（(lockscreen_styles|miui_ex|misans_ext) 组未开启）$")


def running_app_processes(proc_root=Path("/proc"), limit=96):
    found = {}
    try:
        pids = sorted((e.name for e in proc_root.iterdir() if e.name.isdigit()), key=int)
    except OSError:
        return []
    for pid in pids:
        try:
            name = (proc_root / pid / "cmdline").read_bytes().split(b"\0", 1)[0].decode("utf-8", "replace")
        except OSError:
            continue
        if PACKAGE_RE.match(name) and name not in found.values() and len(found) < limit:
            found[pid] = name
    return list(found.items())


def suggested_fixes(result):
    fixes, reasons = [], []
    hyperos = result.get("rom", "hyperos") == "hyperos"
    for item in result.get("findings", []):
        category, files = item["category"], item.get("files", [])
        if category == "theme-takeover" and hyperos:
            fixes.append("theme_takeover")
        elif category == "outside-whitelist":
            keys = ["group:" + m.group(1) for f in files if hyperos and (m := GROUP_OFF_RE.search(f))]
            fixes += keys
            if len(keys) < len(files):
                rest = [f for f in files if not (hyperos and GROUP_OFF_RE.search(f))]
                reasons.append("白名单外文件：" + "、".join(f.rsplit("/", 1)[-1] for f in rest[:6])
                               + ("等" if len(rest) > 6 else "") + "。" + item["action"])
        elif category == "collection-kept":
            reasons.append(f"{item['title']}：{item['detail']}")
        elif category != "covered":
            reasons.append(f"{item['title']}：{item['action']}")
    return list(dict.fromkeys(fixes)), list(dict.fromkeys(reasons))


def scan(*, module, proc_root=Path("/proc"), host_root=Path("/"), theme_dir=Path("/data/system/theme/fonts"),
         groups=None, weight_probe=static_on_variable_slot, budget_s=45.0, clock=None, rom=None,
         coloros_names=None):
    import time
    now = clock or time.monotonic
    started = now()
    rom = rom if rom in ROMS else detect_rom()
    theme = theme_state(theme_dir, module) if rom == "hyperos" else \
        {"state": "none", "files": [], "userFiles": [], "luoshuFiles": []}
    weight = weight_probe((module / ".luoshu-payload/system/fonts") if module else Path("/nonexistent"))
    judge = StockPolicy(rom, module, audit.PayloadIndex(module), groups, coloros_names=coloros_names)
    items, covered, truncated = [], 0, False
    for pid, name in running_app_processes(proc_root):
        if now() - started > budget_s:
            truncated = True
            break
        try:
            result = locate(name, pid, module=module, proc_root=proc_root, host_root=host_root, theme_dir=theme_dir,
                            groups=groups, weight_probe=lambda _p: weight, theme=theme, rom=rom,
                            stock_policy=judge)
        except Exception:  # one process never breaks the scan
            continue
        if result["verdict"] == "no-payload":
            return {"schema": SCAN_SCHEMA, "verdict": "no-payload", "rom": rom, "scanned": 0, "covered": 0,
                    "items": [], "fixes": []}
        # weight-loss is payload-wide (reported once), not a miss in this process.
        found = [f for f in result["findings"] if f["category"] not in ("weight-loss", "covered")]
        if not found:
            covered += 1
            continue
        result["findings"] = found
        fixes, reasons = suggested_fixes(result)
        items.append({"package": name.split(":", 1)[0], "process": name, "verdict": found[0]["category"],
                      "title": found[0]["title"], "fixes": fixes, "reasons": reasons,
                      "findings": [{"category": f["category"], "title": f["title"], "detail": f["detail"],
                                    "files": f["files"]} for f in found],
                      "files": list(dict.fromkeys(file for f in found for file in f["files"])),
                      "keptByDesign": result.get("keptByDesign", []),
                      "targetsNotInPayload": result.get("targetsNotInPayload", [])})
    return {"schema": SCAN_SCHEMA, "verdict": "ok", "rom": rom, "romLabel": ROM_LABELS[rom],
            "scanned": covered + len(items), "covered": covered,
            "items": items, "fixes": list(dict.fromkeys(k for i in items for k in i["fixes"])),
            "truncated": truncated, "weightLoss": bool(weight)}


# ----------------------------------------------------------------- export
EXPORT_SCHEMA = "luoshu-coverage-full-v1"
LOG_KEYWORDS = re.compile(r"MIX|CJK|集合|collection|preserved|保留|失败|错误|error|fail|warn|警告|⚠|"
                          r"挂载|mount|webview|WebView|主题|theme|flip|weight|字重|覆盖|coverage|"
                          r"切换|switch|应用字体|reboot|重启", re.IGNORECASE)
_USER_PATH = re.compile(r"(/sdcard|/storage|/data/media|/mnt/user|content:)/?[^\s'\"|;,]*")
_FONT_TOKEN = re.compile(r"[^\s/'\"|;,=:：()（）、，。\[\]【】<>《》]+\.(?:ttf|otf|ttc|otc|font)\b", re.IGNORECASE)
_DIGEST = re.compile(r"\b[0-9a-f]{40,64}\b")


class Sanitizer:
    """Existing diagnostic rule: no device identifiers, accounts, chat content or
    source font names; system slot names and APK font resource names may stay."""

    def __init__(self, allowed_names: set[str]) -> None:
        self.allowed = {name.lower() for name in allowed_names}

    def font(self, match: re.Match[str]) -> str:
        token = match.group(0)
        return token if token.lower() in self.allowed else "<字体名已隐藏>"

    def __call__(self, text: str) -> str:
        text = _USER_PATH.sub("<用户路径已隐藏>", text)
        text = _FONT_TOKEN.sub(self.font, text)
        return _DIGEST.sub("<hash>", text)


def _stat_dict(path: Path) -> dict[str, Any] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return {"size": st.st_size, "dev": f"{os.major(st.st_dev)}:{os.minor(st.st_dev)}", "ino": st.st_ino}


def slot_mounts(module: Path | None, payload: "audit.PayloadIndex", host_root: Path = Path("/"),
                limit: int = 400) -> list[dict[str, Any]]:
    """Every payload slot: what the host namespace shows at that path vs the module file."""
    rows = []
    for rel in sorted(payload.by_rel)[:limit]:
        if not rel.lower().endswith(audit.FONT_SUFFIXES) or any(part.startswith(".") for part in rel.split("/")):
            continue
        logical = "/" + rel
        slot = payload.by_rel[rel]
        visible = host_root / rel
        shown = _stat_dict(visible)
        mine = _stat_dict(slot["path"])
        if shown is None:
            state = "missing"
        elif (shown["dev"], shown["ino"]) == ((mine or {}).get("dev"), (mine or {}).get("ino")):
            state = "luoshu"
        elif payload.same_content(logical, visible):
            state = "luoshu-content"
        else:
            state = "stock"
        rows.append({"slot": logical, "state": state, "visible": shown, "payload": mine})
    return rows


def mountinfo_fonts(proc_root: Path = Path("/proc"), pid: str = "self", limit: int = 80) -> list[str]:
    try:
        lines = (proc_root / pid / "mountinfo").read_text(errors="replace").splitlines()
    except OSError:
        return []
    keep = [" ".join(line.split()[3:6] + line.split(" - ", 1)[-1].split()[:1])
            for line in lines if "fonts" in line or "LuoShu" in line or "theme" in line]
    return keep[:limit]


def metric_slots(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`slots` in .luoshu-metrics-report.json is a list of {"slot": ...} rows
    (older/fixture reports used a {logical: info} dict); accept both."""
    raw = metrics.get("slots")
    if isinstance(raw, dict):
        return {str(key): value if isinstance(value, dict) else {} for key, value in raw.items()}
    rows: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict) and isinstance(row.get("slot"), str):
                rows[row["slot"]] = row
    return rows


def weight_loss_slots(module: Path | None, metrics: dict[str, Any]) -> list[str]:
    """Variable slots (MiSansVF-style or recorded variableSlotSource) given a static file."""
    root = (module / ".luoshu-payload") if module else None
    if root is None or not root.is_dir():
        return []
    slots = metric_slots(metrics)
    wanted = {logical for logical, info in slots.items()
              if isinstance(info, dict) and info.get("variableSlotSource")}
    for path in root.glob("*/fonts/*.ttf"):
        if "VF" in path.name:
            wanted.add("/" + path.relative_to(root).as_posix())
    lost = []
    try:
        from fontTools.ttLib import TTFont  # type: ignore
    except Exception:  # pragma: no cover
        return []
    for logical in sorted(wanted):
        target = root / logical.lstrip("/")
        try:
            with TTFont(target, lazy=True, fontNumber=0) as font:
                if "fvar" not in font:
                    lost.append(logical)
        except Exception:
            continue
    return lost


def webview_visibility(module: Path | None, payload: "audit.PayloadIndex", proc_root: Path,
                       host_root: Path) -> list[dict[str, Any]]:
    """Is the module visible in webview_zygote / WebView sandboxed renderers?"""
    rows = []
    probes = default_probes(payload)
    try:
        pids = sorted((e.name for e in proc_root.iterdir() if e.name.isdigit()), key=int)
    except OSError:
        pids = []
    for pid in pids:
        try:
            name = (proc_root / pid / "cmdline").read_bytes().split(b"\0", 1)[0].decode("utf-8", "replace")
        except OSError:
            continue
        if "webview" not in name.lower():
            continue
        hidden = namespace_hidden(payload, proc_root, pid, host_root, probes)
        visible = [probe for probe in probes if _shows_payload(
            payload, probe, proc_root / pid / "root" / probe.lstrip("/")) is True]
        rows.append({"process": name.rsplit("/", 1)[-1], "probes": probes, "luoshuVisible": visible,
                     "hidden": hidden, "state": "hidden" if hidden else ("visible" if visible else "unknown")})
        if len(rows) >= 16:
            break
    return rows


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same finding categories + file sets are listed once, with every affected process."""
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        key = json.dumps([[f["category"], f["files"]] for f in item.get("findings", [])], ensure_ascii=False)
        group = groups.setdefault(key, {"findings": item.get("findings", []), "reasons": item.get("reasons", []),
                                        "fixes": item.get("fixes", []), "keptByDesign": item.get("keptByDesign", []),
                                        "processes": []})
        group["processes"].append(item["process"])
    return sorted(groups.values(), key=lambda group: -len(group["processes"]))


def recent_log(module: Path | None, sanitize: Callable[[str], str], lines: int = 240) -> list[str]:
    try:
        raw = (module / "logs/fontswitch.log").read_text(errors="replace").splitlines()[-3000:] if module else []
    except OSError:
        raw = []
    picked = [line for line in raw if LOG_KEYWORDS.search(line)]
    return [sanitize(line)[:400] for line in picked[-lines:]]


def read_module_prop(module: Path | None) -> dict[str, str]:
    values = {}
    try:
        for line in (module / "module.prop").read_text(errors="replace").splitlines() if module else []:
            key, sep, value = line.partition("=")
            if sep and key in ("id", "version", "versionCode"):
                values[key] = value.strip()
    except OSError:
        pass
    return values


def _where(exc: BaseException) -> str:
    """ExcType@file:line of the innermost LuoShu frame (no message: may hold paths)."""
    import traceback
    frames = [frame for frame in traceback.extract_tb(exc.__traceback__)]
    frame = frames[-1] if frames else None
    if frame is None:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}@{Path(frame.filename).name}:{frame.lineno}"


def export(*, module: Path | None, out_dir: Path, rom: str | None = None, device: dict[str, str] | None = None,
           proc_root: Path = Path("/proc"), host_root: Path = Path("/"),
           theme_dir: Path = Path("/data/system/theme/fonts"), groups=None,
           weight_probe=static_on_variable_slot, budget_s: float = 60.0, clock=None,
           summary_name: str = "LuoShu-diagnostic-summary.txt", now: str | None = None,
           coloros_names=None) -> dict[str, Any]:
    """Write one sanitized LuoShu-coverage-full-<time>.json; return its path/size."""
    import time
    rom = rom if rom in ROMS else detect_rom()
    payload = audit.PayloadIndex(module)
    metrics = load_metrics(module)
    stamp = now or time.strftime("%Y%m%d-%H%M%S")
    allowed = set(payload.names) | {Path(path).name for path in metric_slots(metrics)}
    for root in ("system", "system_ext", "product"):
        try:
            allowed |= {entry.name for entry in (host_root / root / "fonts").iterdir()}
        except OSError:
            pass
    sanitize = Sanitizer(allowed)
    errors: dict[str, str] = {}

    def safe(name: str, build, default):
        # One broken section never costs the whole report.
        try:
            return build()
        except Exception as exc:  # noqa: BLE001 - diagnostics never break the caller
            errors[name] = _where(exc)
            return default

    scanned = safe("scan", lambda: scan(module=module, proc_root=proc_root, host_root=host_root, theme_dir=theme_dir, groups=groups,
                   weight_probe=weight_probe, budget_s=budget_s, clock=clock, rom=rom, coloros_names=coloros_names),
                   {"verdict": "error", "items": []})
    theme = safe("theme", lambda: theme_state(theme_dir, module), {"state": "error"}) \
        if rom == "hyperos" else {"state": "n/a"}
    flip = None
    if rom == "coloros" and module is not None:
        try:
            flip = json.loads((module / "logs/coloros_flipfont.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            flip = None
    summary_text = ""
    try:
        summary_text = (out_dir / summary_name).read_text(errors="replace")[:200_000]
    except OSError:
        pass
    collections_kept = metrics.get("preservedCollections") or {}
    report = {
        "schema": EXPORT_SCHEMA,
        "generatedAt": stamp,
        "module": read_module_prop(module),
        "device": {"rom": rom, "romLabel": ROM_LABELS[rom], **(device or {})},
        "scan": {key: value for key, value in scanned.items() if key != "items"},
        "issues": safe("issues", lambda: dedupe_items(scanned.get("items", [])), []),
        "metrics": {
            "available": bool(metrics),
            "collections": metrics.get("collections") or [],
            "preservedCollections": collections_kept,
            "preservedFallbackSlots": metrics.get("preservedFallbackSlots") or {},
            "preservedDynamicAliases": metrics.get("preservedDynamicAliases") or [],
            "preservedStockAliases": metrics.get("preservedStockAliases") or [],
            "weightLossSlots": safe("weightLossSlots", lambda: weight_loss_slots(module, metrics), []),
        },
        "slots": safe("slots", lambda: slot_mounts(module, payload, host_root), []),
        "mountinfo": safe("mountinfo", lambda: [sanitize(line) for line in mountinfo_fonts(proc_root)], []),
        "theme": theme,
        **({"colorosFlipFont": flip} if flip is not None else {}),
        "webview": safe("webview", lambda: webview_visibility(module, payload, proc_root, host_root), []),
        "fontswitchLog": safe("fontswitchLog", lambda: recent_log(module, sanitize), []),
        "sanitizedDiagnostic": sanitize(summary_text) if summary_text else "not-generated",
        "privacy": "设备标识、账号、聊天内容、用户路径与来源字体名已省略；系统字体槽位与应用内字体资源名可能保留",
    }
    report["sectionErrors"] = errors
    report["counts"] = {"issues": len(report["issues"]),
                        "processesWithIssues": sum(len(group["processes"]) for group in report["issues"]),
                        "slots": len(report["slots"]),
                        "slotsNotLuoShu": sum(row["state"] in ("stock", "missing") for row in report["slots"])}
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"LuoShu-coverage-full-{stamp}.json"
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(temporary, 0o644)
    os.replace(temporary, target)
    return {"path": str(target), "bytes": target.stat().st_size, "issues": report["counts"]["issues"],
            "processesWithIssues": report["counts"]["processesWithIssues"], "rom": rom}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="")
    parser.add_argument("--scan", action="store_true", help="scan every running app process")
    parser.add_argument("--export", type=Path, metavar="DIR", help="write the full coverage report into DIR")
    parser.add_argument("--rom", choices=ROMS)
    parser.add_argument("--device", action="append", default=[], metavar="KEY=VALUE",
                        help="device facts for --export (romVersion, androidSdk, rootManager...)")
    parser.add_argument("--pid", default="")
    parser.add_argument("--module", type=Path)
    parser.add_argument("--proc-root", type=Path, default=Path("/proc"))
    parser.add_argument("--host-root", type=Path, default=Path("/"))
    parser.add_argument("--theme-dir", type=Path, default=Path("/data/system/theme/fonts"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.export:
        try:
            device = dict(item.split("=", 1) for item in args.device if "=" in item)
            device = {key: re.sub(r"[^A-Za-z0-9._ +()/-]", "", value)[:80]
                      for key, value in device.items() if re.fullmatch(r"[A-Za-z]{2,32}", key)}
            data = export(module=args.module, out_dir=args.export, rom=args.rom, device=device,
                          proc_root=args.proc_root, host_root=args.host_root, theme_dir=args.theme_dir)
            print(json.dumps({"status": "ok", "data": data}, ensure_ascii=False))
        except Exception as exc:  # diagnostics never break the caller
            print(json.dumps({"status": "error",
                              "message": f"导出失败：{_where(exc)}"}, ensure_ascii=False))
        return 0
    if args.scan:
        try:
            data = scan(module=args.module, proc_root=args.proc_root, host_root=args.host_root,
                        theme_dir=args.theme_dir, rom=args.rom)
            print(json.dumps({"status": "ok", "data": data}, ensure_ascii=False))
        except Exception as exc:  # diagnostics never break the caller
            print(json.dumps({"status": "error",
                              "message": f"扫描失败：{exc.__class__.__name__}"}, ensure_ascii=False))
        return 0
    if not PACKAGE_RE.match(args.package or ""):
        print(json.dumps({"status": "error", "message": "包名格式不正确"}, ensure_ascii=False))
        return 0
    try:
        data = locate(args.package, args.pid.strip(), module=args.module, proc_root=args.proc_root,
                      host_root=args.host_root, theme_dir=args.theme_dir, rom=args.rom)
        print(json.dumps({"status": "ok", "data": data}, ensure_ascii=False))
    except Exception as exc:  # diagnostics never break the caller
        print(json.dumps({"status": "error",
                          "message": f"定位失败：{exc.__class__.__name__}"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
