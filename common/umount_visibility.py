#!/usr/bin/env python3
"""Read-only umount visibility diagnosis: who can still see LuoShu's mounts.

Root managers and Zygisk implementations can detach module mounts from App
processes ("umount modules"); when that happens the process loads stock fonts
no matter what LuoShu staged.  This helper answers *where* the unmount happens:

* facts from ``common/umount_visibility.sh facts`` (root manager + version,
  KernelSU ``kernel_umount`` / ``webview_zygote_umount``, Magisk Zygisk and
  DenyList switches, installed ZygiskNext / ReZygisk / NeoZygisk, dmesg umount
  counters, the optional preload companion);
* ``/proc/<pid>/mountinfo`` of init (PID 1 route), system_server, zygote,
  webview_zygote, WebView sandboxed renderers and running App processes:
  font mounts, LuoShu-owned font mounts, their overlay ``source`` names;
* optionally a ``probe(pid)`` callback (the coverage locator passes its
  dev:ino/content probe of ``/proc/<pid>/root``) for metamodule setups whose
  mounts do not carry LuoShu's paths.

Nothing is modified.  The result is the ``umountVisibility`` section of the
coverage export plus a one-line Chinese conclusion for the App's coverage card.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

SCHEMA = "luoshu-umount-visibility-v1"
FACTS_SCHEMA = "luoshu-umount-facts-v1"
MAX_APPS = 48
MAX_RENDERERS = 4
MAX_SAMPLES = 6
FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")
# Sources NeoZygisk unmounts from zygote / DenyList processes (unmount.cpp):
# the root implementation's name, or anything rooted at /adb/modules.
ROOT_TRACE_SOURCES = ("KSU", "APatch", "magisk")
LUOSHU_MARKERS = (".luoshu-payload", "/luoshu/self-mount", ".luoshu-runtime")
_FACT_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,40}$")
_SAFE_VALUE = re.compile(r"[^A-Za-z0-9 ._+()/:|-]")
_PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+(:[A-Za-z0-9_.]+)?$")
_OCTAL = re.compile(r"\\([0-7]{3})")
SANDBOX_TOKEN = ":sandboxed_process"
APP_UID_MIN, APP_UID_MAX = 10000, 19999
Probe = Callable[[str], "str | None"]


# ---------------------------------------------------------------- facts
def parse_facts(text: str) -> dict[str, Any]:
    """key=value lines from umount_visibility.sh; repeated module keys become lists."""
    facts: dict[str, Any] = {"zygiskModule": [], "hiderModule": []}
    for raw in (text or "").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not _FACT_KEY.match(key):
            continue
        value = _SAFE_VALUE.sub("", value.strip())[:120]
        if key in ("zygiskModule", "hiderModule"):
            parts = (value.split("|") + ["", "", "", ""])[:4]
            facts[key].append({"id": parts[0], "name": parts[1], "version": parts[2],
                               "state": parts[3] or "unknown"})
        else:
            facts[key] = value
    return facts


def collect_facts(module: Path | None, timeout: float = 30.0) -> tuple[str, str]:
    """Run <module>/common/umount_visibility.sh facts; ('', reason) when unavailable."""
    if module is None:
        return "", "no-module"
    script = module / "common" / "umount_visibility.sh"
    if not script.is_file():
        return "", "script-missing"
    shell = "/system/bin/sh" if os.path.exists("/system/bin/sh") else "sh"
    try:
        done = subprocess.run([shell, str(script), "facts"], capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return "", exc.__class__.__name__
    return done.stdout, ""


def _int_or(value: Any) -> int | None:
    return int(value) if isinstance(value, str) and value.isdigit() else None


def zygisk_impl(facts: dict[str, Any]) -> dict[str, Any]:
    """Which Zygisk is live: an enabled standalone implementation wins over Magisk's."""
    found = []
    for module in facts.get("zygiskModule", []):
        name = (module.get("name") or "").lower().replace(" ", "")
        ident = (module.get("id") or "").lower()
        if "neozygisk" in name or "neozygisk" in ident:
            impl = "NeoZygisk"
        elif "rezygisk" in name or ident == "rezygisk":
            impl = "ReZygisk"
        elif "zygisknext" in name or "zygisk-next" in name or ident in ("zygisksu", "zygisk_next", "zygisknext"):
            impl = "ZygiskNext"
        else:
            impl = module.get("id") or "unknown"
        found.append({"impl": impl, "version": module.get("version", ""), "state": module.get("state", "")})
    live = [row for row in found if row["state"] == "enabled"]
    if live:
        return {**live[0], "installed": found}
    if facts.get("magiskZygisk") == "1":
        return {"impl": "MagiskBuiltin", "version": facts.get("magiskVersion", ""), "state": "enabled",
                "installed": found}
    return {"impl": "none", "version": "", "state": "", "installed": found}


# ---------------------------------------------------------------- mountinfo
def _unescape(value: str) -> str:
    return _OCTAL.sub(lambda m: chr(int(m.group(1), 8)), value)


def parse_mountinfo(text: str) -> list[dict[str, str]]:
    rows = []
    for line in (text or "").splitlines():
        if " - " not in line:
            continue
        head, tail = line.split(" - ", 1)
        left, right = head.split(), tail.split()
        if len(left) < 5 or len(right) < 2:
            continue
        rows.append({"root": _unescape(left[3]), "target": _unescape(left[4]), "fstype": right[0],
                     "source": _unescape(right[1]), "super": right[2] if len(right) > 2 else ""})
    return rows


def _is_font_target(target: str) -> bool:
    parts = target.rstrip("/").split("/")
    return "fonts" in parts or "font" in parts or target.lower().endswith(FONT_SUFFIXES)


def _is_luoshu(row: dict[str, str], markers: tuple[str, ...]) -> bool:
    text = row["root"] + " " + row["super"]
    return any(marker in text for marker in markers)


def _is_root_trace(row: dict[str, str]) -> bool:
    return row["source"] in ROOT_TRACE_SOURCES or row["root"].startswith("/adb/modules") \
        or row["target"].startswith("/data/adb/modules")


def mount_summary(rows: list[dict[str, str]], markers: tuple[str, ...]) -> dict[str, Any]:
    fonts = [row for row in rows if _is_font_target(row["target"])]
    mine = [row for row in fonts if _is_luoshu(row, markers)]
    return {
        "fontMounts": len(fonts),
        "luoshuMounts": len(mine),
        "moduleFontMounts": sum(_is_root_trace(row) for row in fonts),
        "luoshuSources": sorted({row["source"] for row in mine})[:8],
        "luoshuTypes": sorted({row["fstype"] for row in mine})[:4],
    }


def module_markers(module: Path | None) -> tuple[str, ...]:
    markers = list(LUOSHU_MARKERS)
    if module is not None and module.name:
        markers.append(f"/modules/{module.name}/")
        markers.append(f"/modules/{module.name} ")
    return tuple(markers)


# ---------------------------------------------------------------- processes
def _read(path: Path, limit: int = 1 << 20) -> str | None:
    try:
        with path.open("rb") as handle:
            return handle.read(limit).decode("utf-8", "replace")
    except OSError:
        return None


def _cmdline(proc_root: Path, pid: str) -> str:
    text = _read(proc_root / pid / "cmdline", 4096) or ""
    return text.split("\0", 1)[0].strip()


def _status(proc_root: Path, pid: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in (_read(proc_root / pid / "status", 8192) or "").splitlines():
        if line.startswith("Uid:"):
            fields = line.split()
            if len(fields) > 1 and fields[1].isdigit():
                out["uid"] = int(fields[1])
        elif line.startswith("PPid:"):
            fields = line.split()
            if len(fields) > 1 and fields[1].isdigit():
                out["ppid"] = int(fields[1])
    return out


def _mnt_ns(proc_root: Path, pid: str) -> str:
    try:
        return os.readlink(proc_root / pid / "ns" / "mnt")
    except OSError:
        return ""


def list_processes(proc_root: Path) -> list[dict[str, Any]]:
    try:
        pids = sorted((entry.name for entry in proc_root.iterdir() if entry.name.isdigit()), key=int)
    except OSError:
        return []
    rows = []
    for pid in pids:
        name = _cmdline(proc_root, pid)
        if not name:
            continue
        rows.append({"pid": pid, "name": name.rsplit("/", 1)[-1] if pid == "1" else name,
                     **_status(proc_root, pid)})
    return rows


def process_view(proc_root: Path, pid: str, markers: tuple[str, ...], probe: Probe | None,
                 init_ns: str, host_mounts: int | None = None) -> dict[str, Any]:
    text = _read(proc_root / pid / "mountinfo")
    view: dict[str, Any] = {}
    if text is None:
        view["mountinfo"] = "unreadable"
    else:
        view.update(mount_summary(parse_mountinfo(text), markers))
    ns = _mnt_ns(proc_root, pid)
    if ns and init_ns:
        view["sameNamespaceAsInit"] = ns == init_ns
    if probe is not None:
        try:
            view["probe"] = probe(pid) or "unknown"
        except Exception as exc:  # noqa: BLE001 - one probe never costs the section
            view["probe"] = f"error:{exc.__class__.__name__}"
    view["verdict"] = verdict(view, host_mounts)
    return view


def verdict(view: dict[str, Any], host_mounts: int | None = None) -> str:
    """visible / unmounted / unknown for one process.

    ``probe`` (dev:ino or content of a payload slot seen through /proc/<pid>/root)
    is decisive; mountinfo alone only says "unmounted" when the host namespace
    carries LuoShu font mounts and this process carries none (metamodule setups
    may mount LuoShu's files without LuoShu's paths, so no mounts is not proof)."""
    probe = view.get("probe")
    if view.get("luoshuMounts", 0) > 0 or probe == "visible" or view.get("sameNamespaceAsInit") is True:
        return "visible"
    if probe in ("hidden", "stock"):
        return "unmounted"
    if host_mounts and view.get("luoshuMounts") == 0:
        return "unmounted"
    return "unknown"


def payload_probe(payload: Any, proc_root: Path, host_root: Path, probes: list[str]) -> Probe | None:
    """probe(pid) for the first payload slot in ``probes``: is the file seen through
    /proc/<pid>/root LuoShu's (identity, else size+sha256)?  Results are cached by
    the visible file's identity, so a namespace is hashed once, not per process."""
    if payload is None or not probes:
        return None
    logical = probes[0]
    cache: dict[tuple[int, int, int], bool] = {}

    def shows(visible: Path) -> bool | None:
        try:
            st = os.stat(visible)
        except OSError:
            return None
        if (st.st_dev, st.st_ino) in payload.ids:
            return True
        key = (st.st_dev, st.st_ino, st.st_size)
        if key not in cache:
            cache[key] = bool(payload.same_content(logical, visible))
        return cache[key]

    host = shows(host_root / logical.lstrip("/"))

    def probe(pid: str) -> str:
        seen = shows(proc_root / pid / "root" / logical.lstrip("/"))
        if seen is True:
            return "visible"
        if seen is False:
            return "hidden" if host is True else "stock"
        return "unknown"

    return probe


# ---------------------------------------------------------------- conclusion
def conclude(section: dict[str, Any]) -> dict[str, Any]:
    """Machine verdicts + causes + one Chinese sentence for the App."""
    facts = section.get("settings", {})
    impl = section.get("zygisk", {}).get("impl", "none")
    procs = section.get("processes", {})
    init = procs.get("init", {})
    host_visible = init.get("verdict") == "visible"
    causes: list[str] = []
    if not host_visible:
        result = {"host": init.get("verdict", "unknown"), "app": "unknown", "webview": "unknown",
                  "causes": ["host-not-mounted" if init.get("verdict") == "unmounted" else "host-unknown"]}
        result["summary"] = ("全局命名空间里看不到洛书字体（未应用字体、未重启或挂载失败），先确认字体已应用并重启。"
                             if init.get("verdict") == "unmounted" else
                             "未能确认洛书挂载在全局命名空间可见（可能未应用字体、未重启，或没有 Root 权限）。")
        return result

    zygote = procs.get("zygote", {})
    if zygote.get("verdict") == "unmounted":
        causes.append("zygote-level-unmount")

    apps = procs.get("apps", {})
    checked, hidden = apps.get("checked", 0), apps.get("unmounted", 0)
    if checked == 0:
        app = "unknown"
    elif hidden == 0:
        app = "visible"
    elif hidden == checked:
        app = "unmounted"
    else:
        app = "partial"

    wz = procs.get("webview_zygote", {})
    renderers = procs.get("webviewRenderers", [])
    web_states = [wz.get("verdict")] if wz else []
    web_states += [row.get("verdict") for row in renderers]
    web_states = [state for state in web_states if state in ("visible", "unmounted")]
    if not web_states:
        web = "unknown"
    elif all(state == "visible" for state in web_states):
        web = "visible"
    else:
        web = "unmounted"
    if web == "unmounted":
        if facts.get("webviewZygoteUmount") == "1":
            causes.append("webview_zygote_umount")
        if impl == "NeoZygisk":
            causes.append("neozygisk-webview-denylist")
        if "zygote-level-unmount" not in causes and impl not in ("NeoZygisk",) \
                and facts.get("webviewZygoteUmount") != "1":
            causes.append("webview-unknown")
    if app in ("partial", "unmounted"):
        if facts.get("kernelUmount") == "1":
            causes.append("kernel_umount-per-app")
        if impl in ("NeoZygisk", "ReZygisk", "ZygiskNext", "MagiskBuiltin"):
            causes.append(f"{impl}-denylist")
    if impl == "NeoZygisk" and section.get("neoZygisk", {}).get("luoshuMountsTargeted"):
        causes.append("neozygisk-source-match")

    app_text = {
        "visible": f"App 侧：抽查 {checked} 个进程都能看到洛书挂载",
        "partial": f"App 侧：{hidden}/{checked} 个进程被卸载了模块挂载（管理器里对这些应用开了“卸载模块”/排除列表）",
        "unmounted": f"App 侧：抽查的 {checked} 个进程全部看不到洛书挂载",
        "unknown": "App 侧：没有可抽查的运行中应用",
    }[app]
    if web == "visible":
        web_text = "WebView：可见"
    elif web == "unknown":
        web_text = "WebView：当前没有运行中的 WebView 进程，无法判断"
    elif "webview_zygote_umount" in causes:
        web_text = "WebView：被 webview_zygote_umount 卸载（可在 KernelSU 管理器关闭）"
    elif "neozygisk-webview-denylist" in causes:
        web_text = "WebView：NeoZygisk 会把 webview_zygote 一律按排除列表处理，洛书挂载被卸掉"
    elif "zygote-level-unmount" in causes:
        web_text = "WebView：zygote 本身已看不到洛书挂载（zygote 级卸载）"
    else:
        web_text = "WebView：看不到洛书挂载，原因未识别，请导出诊断反馈"
    if "zygote-level-unmount" in causes and app != "visible":
        app_text += "（zygote 级卸载，所有 App 都受影响）"
    note = ""
    if "neozygisk-source-match" in causes and (app != "visible" or web == "unmounted"):
        note = "；洛书 overlay 的 source 名会被 NeoZygisk 当作 root 痕迹卸载"
    return {"host": "visible", "app": app, "webview": web, "causes": causes,
            "summary": f"{app_text}；{web_text}{note}。"}


# ---------------------------------------------------------------- section
def build(*, module: Path | None, proc_root: Path = Path("/proc"), facts_text: str | None = None,
          probe: Probe | None = None, max_apps: int = MAX_APPS) -> dict[str, Any]:
    """The umountVisibility section. ``facts_text`` None runs the facts script."""
    reason = ""
    if facts_text is None:
        facts_text, reason = collect_facts(module)
    facts = parse_facts(facts_text)
    markers = module_markers(module)
    processes = list_processes(proc_root)
    by_pid = {row["pid"]: row for row in processes}
    init_ns = _mnt_ns(proc_root, "1")

    section_procs: dict[str, Any] = {}
    init_text = _read(proc_root / "1" / "mountinfo")
    init_rows = parse_mountinfo(init_text) if init_text is not None else []
    # PID 1 route: the namespace system_server and zygote inherit at boot.
    init_view = process_view(proc_root, "1", markers, probe, "")
    section_procs["init"] = init_view
    host_mounts = init_view.get("luoshuMounts") or 0

    def view(pid: str) -> dict[str, Any]:
        return process_view(proc_root, pid, markers, probe, init_ns, host_mounts)

    def first(names: tuple[str, ...]) -> str | None:
        for row in processes:
            if row["name"] in names:
                return row["pid"]
        return None

    for role, names in (("system_server", ("system_server",)), ("zygote", ("zygote64", "zygote")),
                        ("webview_zygote", ("webview_zygote",))):
        pid = first(names)
        if pid is not None:
            section_procs[role] = {"process": by_pid[pid]["name"], **view(pid)}

    wz_pids = {row["pid"] for row in processes if row["name"] == "webview_zygote"}
    renderers = []
    for row in processes:
        if SANDBOX_TOKEN not in row["name"]:
            continue
        parent = by_pid.get(str(row.get("ppid", "")), {}).get("name", "")
        if str(row.get("ppid", "")) not in wz_pids and "webview" not in row["name"].lower():
            continue
        renderers.append({"process": row["name"].split(":", 1)[0] + SANDBOX_TOKEN,
                          "parent": parent or "unknown", **view(row["pid"])})
        if len(renderers) >= MAX_RENDERERS:
            break
    section_procs["webviewRenderers"] = renderers

    apps = {"checked": 0, "visible": 0, "unmounted": 0, "unknown": 0, "samples": [], "unmountedSamples": []}
    for row in processes:
        uid = row.get("uid")
        if uid is None or not (APP_UID_MIN <= uid % 100000 <= APP_UID_MAX):
            continue
        if not _PACKAGE.match(row["name"]) or SANDBOX_TOKEN in row["name"]:
            continue
        if apps["checked"] >= max_apps:
            apps["truncated"] = True
            break
        state = view(row["pid"])
        apps["checked"] += 1
        apps[state["verdict"]] = apps.get(state["verdict"], 0) + 1
        sample = {"process": row["name"], "verdict": state["verdict"],
                  "luoshuMounts": state.get("luoshuMounts"), **({"probe": state["probe"]} if "probe" in state else {})}
        if state["verdict"] == "unmounted" and len(apps["unmountedSamples"]) < MAX_SAMPLES:
            apps["unmountedSamples"].append(sample)
        elif len(apps["samples"]) < MAX_SAMPLES:
            apps["samples"].append(sample)
    section_procs["apps"] = apps

    impl = zygisk_impl(facts)
    mine = [row for row in init_rows if _is_font_target(row["target"]) and _is_luoshu(row, markers)]
    module_rows = [row for row in init_rows if _is_root_trace(row)]
    section: dict[str, Any] = {
        "schema": SCHEMA,
        "readOnly": True,
        "manager": facts.get("manager", "unknown"),
        "managerVersion": facts.get("ksudVersion") or facts.get("apdVersion") or facts.get("magiskVersion") or "",
        "ksuKernelVersion": _int_or(facts.get("ksuKernelVersion")),
        "kernelUmount": facts.get("kernelUmount", "n/a"),
        "webviewZygoteUmount": facts.get("webviewZygoteUmount", "n/a"),
        "kernelUmountManagedBy": [item for item in str(facts.get("kernelUmountManagedBy", "")).split() if item][:8],
        "magisk": {"zygisk": facts.get("magiskZygisk", "n/a"), "denylist": facts.get("magiskDenylist", "n/a")},
        "zygisk": impl,
        "hiders": facts.get("hiderModule", []),
        "overlaySources": sorted({row["source"] for row in mine}),
        "neoZygisk": {
            # unmount.cpp: zygote-level unmount takes every mount whose source is the
            # root implementation's name or whose root is under /adb/modules, and
            # aborts when one of them sits exactly on /product.
            "luoshuMountsTargeted": sum(_is_root_trace(row) for row in mine),
            "productOverlayBlocksZygoteUnmount": any(row["target"] == "/product" for row in module_rows),
        },
        "dmesg": {"readable": facts.get("dmesgReadable") == "1",
                  "umountForUid": _int_or(facts.get("dmesgUmountUid")),
                  "umountFontTargets": _int_or(facts.get("dmesgUmountFonts"))},
        "preload": {"module": facts.get("preloadModule", "unknown")},
        "processes": section_procs,
        "settings": {key: facts.get(key, "n/a") for key in ("kernelUmount", "webviewZygoteUmount")},
    }
    if reason:
        section["factsUnavailable"] = reason
    elif facts_text and FACTS_SCHEMA not in facts_text:
        section["factsUnavailable"] = "schema-mismatch"
    section["conclusion"] = conclude(section)
    return section
