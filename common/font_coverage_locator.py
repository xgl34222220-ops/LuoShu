#!/usr/bin/env python3
"""Why is this screen not using my font?" - read-only per-package locator.

The App's 未覆盖界面定位 asks for one package (status bar -> SystemUI, lock
screen -> SystemUI/AOD, launcher, settings, any app). This helper runs the
existing per-process audit (device_font_process_audit) against that process,
using ``/proc/<pid>/root`` as the visible root so every path is judged in the
process's own mount namespace, then sorts what it finds into the causes users
actually hit on HyperOS, each with a concrete next step:

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
* ``covered``          every mapped font is LuoShu's

Nothing is modified: maps, stat and (optionally) a font table read.
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
MAX_FILES = 12

GUIDE = {
    "theme-takeover": (
        "主题商店字体接管了系统字体",
        "在主题商店把字体切回“默认/MiSans”后重启；或在洛书 HyperOS 覆盖设置里开启“接管主题商店字体”（默认关，重启生效）。"),
    "outside-whitelist": (
        "该界面读取了洛书没有替换的原厂字体文件",
        "若文件属于锁屏/小部件样式组，可在 HyperOS 覆盖设置里开启该组后重新应用字体；等宽/MiSansL3/语种字体按设计保留原厂；其他文件名请导出诊断反馈。"),
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
}


def finding(category: str, files: list[str] | None = None, detail: str = "") -> dict[str, Any]:
    title, action = GUIDE[category]
    return {"category": category, "title": title, "action": action,
            "detail": detail, "files": (files or [])[:MAX_FILES]}


def _split(value: str) -> list[str]:
    return [] if not value or value == "none" else [item for item in value.split(";") if item]


def theme_state(theme_dir: Path) -> dict[str, Any]:
    files, user = [], []
    try:
        entries = sorted(theme_dir.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if not entry.is_file() or entry.is_symlink():
            continue
        if not entry.name.lower().endswith((".ttf", ".otf", ".ttc")):
            continue
        files.append(entry.name)
        try:
            if entry.stat().st_size > THEME_PLACEHOLDER_MAX_BYTES:
                user.append(entry.name)
        except OSError:
            pass
    state = "user-theme" if user else ("placeholder" if files else "none")
    return {"state": state, "files": files[:MAX_FILES], "userFiles": user[:MAX_FILES]}


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
    name = path.split("@", 1)[0].rsplit("/", 1)[-1]
    if policy is None:
        return "unlisted"
    kind = policy.classify(name)
    if kind in policy.GROUP_DEFAULTS:
        active = policy.enabled_groups() if groups is None else groups
        return "group-on" if kind in active else f"group-off:{kind}"
    return kind


def locate(package: str, pid: str, *, module: Path | None, proc_root: Path = Path("/proc"),
           host_root: Path = Path("/"), theme_dir: Path = Path("/data/system/theme/fonts"),
           groups: frozenset[str] | None = None,
           weight_probe: Callable[[Path], bool] = static_on_variable_slot) -> dict[str, Any]:
    result: dict[str, Any] = {"schema": SCHEMA, "package": package, "pid": pid or "",
                              "findings": []}
    findings: list[dict[str, Any]] = result["findings"]
    theme = theme_state(theme_dir)
    result["theme"] = theme
    if package in EMBEDDED_FONT_APPS or package in WEB_ENGINES:
        label = EMBEDDED_FONT_APPS.get(package) or WEB_ENGINES[package]
        findings.append(finding("app-embedded", [], label))
    if not pid or not pid.isdigit():
        findings.insert(0, finding("not-running"))
        result["verdict"] = "not-running"
        return result
    visible = str(proc_root / pid / "root")
    args = SimpleNamespace(target=[f"app={pid}@{package}"], proc_root=str(proc_root),
                           module=module, visible_root=visible)
    report = audit.build_report(args)
    result["audit"] = {key: value for key, value in report.items() if key.startswith(("app.", "font"))}
    state = report.get("app.state", "")
    if report.get("fontAudit") == "inactive:no-payload":
        findings.insert(0, finding("no-payload"))
        result["verdict"] = "no-payload"
        return result
    if state != "ok":
        findings.insert(0, finding("unreadable", [], state))
        result["verdict"] = "unreadable"
        return result

    payload = audit.PayloadIndex(module)
    theme_paths = _split(report.get("app.themePaths", ""))
    stock_paths = _split(report.get("app.stockPaths", ""))
    replaced = _split(report.get("app.replacedSlotStockPaths", ""))
    others = _split(report.get("app.otherFiles", ""))
    luoshu_hits = int(report.get("app.luoshuHits", "0") or 0)

    if theme["state"] == "user-theme" and (theme_paths or not luoshu_hits):
        findings.append(finding("theme-takeover", theme_paths or theme["userFiles"],
                                "检测到 /data/system/theme/fonts 中有主题商店字体"))
    elif theme_paths and theme["state"] == "user-theme":
        findings.append(finding("theme-takeover", theme_paths))

    hidden = namespace_hidden(payload, proc_root, pid, host_root, default_probes(payload))
    if hidden:
        findings.append(finding("namespace-hidden", hidden))

    switched = [item for item in replaced if item.endswith(":loaded-before-mount")]
    if switched:
        findings.append(finding("link-switched", switched))

    outside, kept = [], []
    replaced_paths = {item.split("@", 1)[0] for item in replaced}
    for item in stock_paths:
        path = item.split("@", 1)[0]
        if path in replaced_paths:
            continue
        kind = classify_stock(item, groups)
        if kind in ("mono", "rare-han", "excluded"):
            kept.append(f"{path}（按设计保留：{kind}）")
        elif kind != "core" and kind != "group-on":
            outside.append(path if not kind.startswith("group-off:")
                           else f"{path}（{kind.split(':', 1)[1]} 组未开启）")
    if outside:
        findings.append(finding("outside-whitelist", outside))
    if kept:
        result["keptByDesign"] = kept[:MAX_FILES]
    if others and not any(f["category"] == "app-embedded" for f in findings):
        findings.append(finding("app-embedded", others, "进程自行打开了应用内或下载的字体文件"))
    stock_on_slot = [item for item in replaced if not item.endswith(":loaded-before-mount")]
    if stock_on_slot and not hidden and not switched:
        findings.append(finding("link-switched", stock_on_slot, "已替换槽位仍映射原厂 inode"))

    payload_fonts = (module / ".luoshu-payload/system/fonts") if module else Path("/nonexistent")
    if any("MiSansVF" in item for item in report.get("app.luoshuPaths", "").split(";")) \
            and weight_probe(payload_fonts):
        findings.append(finding("weight-loss", ["MiSansVF.ttf"]))

    if not findings:
        findings.append(finding("covered"))
    result["verdict"] = findings[0]["category"]
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--pid", default="")
    parser.add_argument("--module", type=Path)
    parser.add_argument("--proc-root", type=Path, default=Path("/proc"))
    parser.add_argument("--host-root", type=Path, default=Path("/"))
    parser.add_argument("--theme-dir", type=Path, default=Path("/data/system/theme/fonts"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not PACKAGE_RE.match(args.package or ""):
        print(json.dumps({"status": "error", "message": "包名格式不正确"}, ensure_ascii=False))
        return 0
    try:
        data = locate(args.package, args.pid.strip(), module=args.module, proc_root=args.proc_root,
                      host_root=args.host_root, theme_dir=args.theme_dir)
        print(json.dumps({"status": "ok", "data": data}, ensure_ascii=False))
    except Exception as exc:  # diagnostics never break the caller
        print(json.dumps({"status": "error",
                          "message": f"定位失败：{exc.__class__.__name__}"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
