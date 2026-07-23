#!/system/bin/sh
# LuoShu Android updatable-font named-family bridge.
#
# Android 12+ merges /data/fonts/config/config.xml after the system font XML.
# Downloaded Google Sans named families therefore override systemless GoogleSans files.
# LuoShu fixes this before FontManagerService starts: keep every signed font file and
# updatedFontDir entry, remove only Google/Product Sans family declarations from the
# persistent config view, and expose the same family names from the active LuoShu fonts.
set +e

_luoshu_provider_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_provider_config_dir() {
    printf '%s/config/font-provider-overlay\n' "$(_luoshu_provider_module)"
}

LUOSHU_PROVIDER_DATA_XML="${LUOSHU_PROVIDER_DATA_XML:-/data/fonts/config/config.xml}"
LUOSHU_PROVIDER_SYSTEM_XML="${LUOSHU_PROVIDER_SYSTEM_XML:-/system/etc/fonts.xml}"
LUOSHU_PROVIDER_STATE="${LUOSHU_PROVIDER_STATE:-$(_luoshu_provider_module)/config/font-provider-overlay.conf}"
LUOSHU_PROVIDER_BACKUP_SUFFIX=".luoshu-bak"

luoshu_provider_log() {
    _lpl_module="$(_luoshu_provider_module)"
    mkdir -p "$_lpl_module/logs" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$_lpl_module/logs/provider_cache.log" 2>/dev/null || true
}

_luoshu_provider_python() {
    _lpp_module="$(_luoshu_provider_module)"
    _lpp_root="$_lpp_module/common/python"
    _lpp_bin="$_lpp_root/bin/luoshu-python"
    [ -x "$_lpp_bin" ] || return 1
    PYTHONHOME="$_lpp_root" \
    PYTHONPATH="$_lpp_root/lib/python3.14:$_lpp_root/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_lpp_root/lib:$_lpp_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_lpp_bin" "$@"
}

_luoshu_provider_mount_is_ours() {
    _lpmi_target="$1"
    _lpmi_source="$2"
    [ -r /proc/self/mountinfo ] && [ -f "$_lpmi_source" ] && [ -f "$_lpmi_target" ] || return 1
    awk -v target="$_lpmi_target" '$5 == target { found=1 } END { exit !found }' \
        /proc/self/mountinfo 2>/dev/null || return 1
    _lpmi_source_id=$(stat -c '%d:%i' "$_lpmi_source" 2>/dev/null)
    _lpmi_target_id=$(stat -c '%d:%i' "$_lpmi_target" 2>/dev/null)
    [ -n "$_lpmi_source_id" ] && [ "$_lpmi_source_id" = "$_lpmi_target_id" ]
}

_luoshu_provider_unmount_one() {
    _lpu_target="$1"
    _lpu_source="$2"
    if _luoshu_provider_mount_is_ours "$_lpu_target" "$_lpu_source"; then
        umount "$_lpu_target" 2>/dev/null || umount -l "$_lpu_target" 2>/dev/null || return 1
    fi
    return 0
}

_luoshu_provider_restore_legacy_files() {
    [ -d /data/fonts/files ] || return 0
    find /data/fonts/files -type f -name "*${LUOSHU_PROVIDER_BACKUP_SUFFIX}" 2>/dev/null |
    while IFS= read -r _lpr_backup; do
        [ -f "$_lpr_backup" ] || continue
        _lpr_original="${_lpr_backup%$LUOSHU_PROVIDER_BACKUP_SUFFIX}"
        cp -f "$_lpr_backup" "$_lpr_original" 2>/dev/null || continue
        chmod 0644 "$_lpr_original" 2>/dev/null || true
        rm -f "$_lpr_backup" 2>/dev/null || true
    done
}

_luoshu_provider_valid_font() {
    _lpvf="$1"
    [ -f "$_lpvf" ] || return 1
    _lpvf_size=$(wc -c < "$_lpvf" 2>/dev/null | tr -d '[:space:]')
    case "$_lpvf_size" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_lpvf_size" -ge 1024 ] || return 1
    _lpvf_magic=$(dd if="$_lpvf" bs=4 count=1 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')
    case "$_lpvf_magic" in 00010000|4f54544f|74746366) return 0 ;; *) return 1 ;; esac
}

_luoshu_provider_pick_name() {
    for _lppn in "$@"; do
        _luoshu_provider_valid_font "/system/fonts/$_lppn" || continue
        printf '%s\n' "$_lppn"
        return 0
    done
    return 1
}

_luoshu_provider_select_fonts() {
    LUOSHU_PROVIDER_REGULAR=$(_luoshu_provider_pick_name \
        LuoShu-400.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf \
        Roboto-Regular.ttf SysFont-Regular.ttf OPSans-En-Regular.ttf) || return 1
    LUOSHU_PROVIDER_MEDIUM=$(_luoshu_provider_pick_name \
        LuoShu-500.ttf GoogleSans-Medium.ttf GoogleSansText-Medium.ttf \
        SourceSansPro-SemiBold.ttf SysFont-Regular.ttf "$LUOSHU_PROVIDER_REGULAR") || \
        LUOSHU_PROVIDER_MEDIUM="$LUOSHU_PROVIDER_REGULAR"
    LUOSHU_PROVIDER_BOLD=$(_luoshu_provider_pick_name \
        LuoShu-700.ttf GoogleSans-Bold.ttf GoogleSansText-Bold.ttf \
        SourceSansPro-Bold.ttf SysFont-Regular.ttf "$LUOSHU_PROVIDER_MEDIUM" \
        "$LUOSHU_PROVIDER_REGULAR") || LUOSHU_PROVIDER_BOLD="$LUOSHU_PROVIDER_REGULAR"
    export LUOSHU_PROVIDER_REGULAR LUOSHU_PROVIDER_MEDIUM LUOSHU_PROVIDER_BOLD
}

_luoshu_provider_match_metadata() {
    _lpmm_source="$1"
    _lpmm_target="$2"
    _lpmm_uid=$(stat -c '%u' "$_lpmm_target" 2>/dev/null)
    _lpmm_gid=$(stat -c '%g' "$_lpmm_target" 2>/dev/null)
    _lpmm_mode=$(stat -c '%a' "$_lpmm_target" 2>/dev/null)
    [ -n "$_lpmm_uid" ] && [ -n "$_lpmm_gid" ] && chown "$_lpmm_uid:$_lpmm_gid" "$_lpmm_source" 2>/dev/null || true
    chmod "${_lpmm_mode:-644}" "$_lpmm_source" 2>/dev/null || true
    if command -v chcon >/dev/null 2>&1; then
        chcon --reference="$_lpmm_target" "$_lpmm_source" 2>/dev/null || true
    fi
}

_luoshu_provider_bind_one() {
    _lpbo_source="$1"
    _lpbo_target="$2"
    mount --bind "$_lpbo_source" "$_lpbo_target" 2>/dev/null || return 1
    mount -o remount,bind,ro "$_lpbo_target" 2>/dev/null || true
    _luoshu_provider_mount_is_ours "$_lpbo_target" "$_lpbo_source"
}

_luoshu_provider_generate() {
    _lpg_data_in="$1"
    _lpg_data_out="$2"
    _lpg_system_in="$3"
    _lpg_system_out="$4"
    _lpg_report="$5"
    rm -f "$_lpg_data_out" "$_lpg_system_out" "$_lpg_report" 2>/dev/null || true

    _luoshu_provider_python - \
        "$_lpg_data_in" "$_lpg_data_out" "$_lpg_system_in" "$_lpg_system_out" \
        "$LUOSHU_PROVIDER_REGULAR" "$LUOSHU_PROVIDER_MEDIUM" "$LUOSHU_PROVIDER_BOLD" \
        "$_lpg_report" <<'PY_LUOSHU_PROVIDER'
from __future__ import annotations

import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

data_in = Path(sys.argv[1])
data_out = Path(sys.argv[2])
system_in = Path(sys.argv[3])
system_out = Path(sys.argv[4])
regular = sys.argv[5]
medium = sys.argv[6]
bold = sys.argv[7]
report = Path(sys.argv[8])

blocked = re.compile(r"^(?:google[-_\s]*sans|product[-_\s]*sans)", re.I)
family_names = (
    ("google-sans", 400, regular),
    ("google-sans-text", 400, regular),
    ("google-sans-flex", 400, regular),
    ("google-sans-display", 400, regular),
    ("product-sans", 400, regular),
    ("google-sans-medium", 500, medium),
    ("google-sans-text-medium", 500, medium),
    ("google-sans-display-medium", 500, medium),
    ("google-sans-bold", 700, bold),
    ("google-sans-text-bold", 700, bold),
    ("google-sans-display-bold", 700, bold),
)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def norm(value: str) -> str:
    return re.sub(r"[\s_]+", "-", value.strip().lower())


def atomic_write(tree: ET.ElementTree, output: Path, mode: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="    ")
    fd, temp = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    try:
        tree.write(temp, encoding="utf-8", xml_declaration=True)
        os.chmod(temp, mode)
        os.replace(temp, output)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass

# PersistentSystemFontConfig uses <family name="..."><font name="PostScriptName"/></family>.
# Keep lastModifiedDate and every updatedFontDir so FontManagerService keeps signed files.
data_tree = ET.parse(data_in)
removed: list[str] = []
for parent in data_tree.getroot().iter():
    for child in list(parent):
        if local(child.tag) != "family":
            continue
        name = child.attrib.get("name", "")
        if name and blocked.match(norm(name)):
            removed.append(name)
            parent.remove(child)
if not removed:
    raise SystemExit(3)
atomic_write(data_tree, data_out, 0o600)

# System fonts.xml is parsed before the persistent updatable config. Add the family names here;
# after the filtered persistent view is loaded, nothing later can override them.
system_tree = ET.parse(system_in)
root = system_tree.getroot()
namespace = root.tag.split("}", 1)[0] + "}" if root.tag.startswith("{") else ""
for parent in root.iter():
    for child in list(parent):
        if local(child.tag) == "family" and blocked.match(norm(child.attrib.get("name", ""))):
            parent.remove(child)
for name, weight, filename in family_names:
    family = ET.SubElement(root, namespace + "family", {"name": name})
    font = ET.SubElement(family, namespace + "font", {"weight": str(weight), "style": "normal"})
    font.text = filename
atomic_write(system_tree, system_out, 0o644)

# Structural validation: only blocked named families disappear from data config, and all
# injected family names point to a basename in /system/fonts.
check_data = ET.parse(data_out).getroot()
for node in check_data.iter():
    if local(node.tag) == "family" and blocked.match(norm(node.attrib.get("name", ""))):
        raise SystemExit(4)
check_system = ET.parse(system_out).getroot()
seen = set()
for node in check_system.iter():
    if local(node.tag) == "family":
        seen.add(norm(node.attrib.get("name", "")))
required = {name for name, _, _ in family_names}
if not required.issubset(seen):
    raise SystemExit(5)
if any("/" in filename or not filename for _, _, filename in family_names):
    raise SystemExit(6)

report.write_text(
    "removed=" + str(len(removed)) + "\n"
    + "\n".join(f"family={name}" for name in sorted(set(removed))) + "\n"
    + f"regular={regular}\nmedium={medium}\nbold={bold}\n",
    encoding="utf-8",
)
PY_LUOSHU_PROVIDER
}

luoshu_provider_cache_sync() {
    _lpcs_source="${1:-custom}"
    mkdir -p "${LUOSHU_PROVIDER_STATE%/*}" 2>/dev/null || true
    {
        printf 'mode=pending-reboot\n'
        printf 'font=%s\n' "$(head -n1 "$(_luoshu_provider_module)/config/active_font.conf" 2>/dev/null | tr -d '\r\n')"
        printf 'source=%s\n' "$_lpcs_source"
        printf 'time=%s\n' "$(date +%s)"
    } > "$LUOSHU_PROVIDER_STATE" 2>/dev/null || true
    chmod 0644 "$LUOSHU_PROVIDER_STATE" 2>/dev/null || true
    return 0
}

luoshu_provider_cache_restore() {
    _lpcr_dir="$(_luoshu_provider_config_dir)"
    _lpcr_data="$_lpcr_dir/data-config.xml"
    _lpcr_system="$_lpcr_dir/system-fonts.xml"
    _luoshu_provider_unmount_one "$LUOSHU_PROVIDER_DATA_XML" "$_lpcr_data" || true
    _luoshu_provider_unmount_one "$LUOSHU_PROVIDER_SYSTEM_XML" "$_lpcr_system" || true
    _luoshu_provider_restore_legacy_files
    rm -rf "$_lpcr_dir" 2>/dev/null || true
    rm -f "$LUOSHU_PROVIDER_STATE" 2>/dev/null || true
    return 0
}

# Must run from post-fs-data before FontManagerService initializes its shared font map.
luoshu_provider_cache_boot() {
    _lpcb_active="${1:-default}"
    _lpcb_dir="$(_luoshu_provider_config_dir)"
    _lpcb_data="$_lpcb_dir/data-config.xml"
    _lpcb_system="$_lpcb_dir/system-fonts.xml"
    _lpcb_report="$_lpcb_dir/report.conf"

    if [ -z "$_lpcb_active" ] || [ "$_lpcb_active" = default ]; then
        luoshu_provider_cache_restore
        return 0
    fi

    [ -s "$LUOSHU_PROVIDER_DATA_XML" ] && [ -s "$LUOSHU_PROVIDER_SYSTEM_XML" ] || return 2
    _luoshu_provider_select_fonts || {
        luoshu_provider_log '动态 Google Sans 桥未找到可用的洛书系统字体'
        return 1
    }

    mkdir -p "$_lpcb_dir" 2>/dev/null || return 1
    _luoshu_provider_unmount_one "$LUOSHU_PROVIDER_DATA_XML" "$_lpcb_data" || true
    _luoshu_provider_unmount_one "$LUOSHU_PROVIDER_SYSTEM_XML" "$_lpcb_system" || true

    _luoshu_provider_generate "$LUOSHU_PROVIDER_DATA_XML" "$_lpcb_data" \
        "$LUOSHU_PROVIDER_SYSTEM_XML" "$_lpcb_system" "$_lpcb_report"
    _lpcb_rc=$?
    if [ "$_lpcb_rc" -eq 3 ]; then
        rm -rf "$_lpcb_dir" 2>/dev/null || true
        return 2
    elif [ "$_lpcb_rc" -ne 0 ]; then
        rm -rf "$_lpcb_dir" 2>/dev/null || true
        luoshu_provider_log "动态 Google Sans 配置生成失败：code=$_lpcb_rc"
        return 1
    fi

    _luoshu_provider_match_metadata "$_lpcb_data" "$LUOSHU_PROVIDER_DATA_XML"
    _luoshu_provider_match_metadata "$_lpcb_system" "$LUOSHU_PROVIDER_SYSTEM_XML"

    if ! _luoshu_provider_bind_one "$_lpcb_system" "$LUOSHU_PROVIDER_SYSTEM_XML"; then
        rm -rf "$_lpcb_dir" 2>/dev/null || true
        luoshu_provider_log '无法在 FontManagerService 初始化前挂载系统字体配置'
        return 1
    fi
    if ! _luoshu_provider_bind_one "$_lpcb_data" "$LUOSHU_PROVIDER_DATA_XML"; then
        _luoshu_provider_unmount_one "$LUOSHU_PROVIDER_SYSTEM_XML" "$_lpcb_system" || true
        rm -rf "$_lpcb_dir" 2>/dev/null || true
        luoshu_provider_log '无法在 FontManagerService 初始化前挂载动态字体配置'
        return 1
    fi

    _lpcb_removed=$(sed -n 's/^removed=//p' "$_lpcb_report" 2>/dev/null | head -n1)
    {
        printf 'mode=mounted-preboot\n'
        printf 'font=%s\n' "$_lpcb_active"
        printf 'removed=%s\n' "${_lpcb_removed:-0}"
        printf 'regular=%s\n' "$LUOSHU_PROVIDER_REGULAR"
        printf 'medium=%s\n' "$LUOSHU_PROVIDER_MEDIUM"
        printf 'bold=%s\n' "$LUOSHU_PROVIDER_BOLD"
        printf 'time=%s\n' "$(date +%s)"
    } > "$LUOSHU_PROVIDER_STATE" 2>/dev/null || true
    chmod 0644 "$LUOSHU_PROVIDER_STATE" "$_lpcb_report" 2>/dev/null || true
    luoshu_provider_log "开机前动态 Google Sans 桥已启用：移除 ${_lpcb_removed:-0} 个覆盖 family"
    return 0
}
