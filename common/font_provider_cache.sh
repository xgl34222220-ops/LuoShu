#!/system/bin/sh
# LuoShu Android downloadable-font named-family bridge.
#
# Android 12+ FontManagerService appends named families from
# /data/fonts/config/config.xml after /system/etc/fonts.xml. Later definitions win,
# so Google Sans downloaded by GMS can bypass LuoShu's systemless font payload.
#
# LuoShu does not overwrite signed /data/fonts/files content. While a custom font is
# active, this helper:
#   1. creates a read-only view of config.xml without Google/Product Sans families;
#   2. creates a read-only view of fonts.xml that defines those family names with the
#      currently mounted LuoShu system fonts.
# Signed font files, fs-verity metadata, downloadable Emoji and unrelated families
# remain untouched.
set +e

_luoshu_provider_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_provider_config() {
    printf '%s/config\n' "$(_luoshu_provider_module)"
}

LUOSHU_PROVIDER_CONFIG_XML="${LUOSHU_PROVIDER_CONFIG_XML:-/data/fonts/config/config.xml}"
LUOSHU_PROVIDER_SYSTEM_XML="${LUOSHU_PROVIDER_SYSTEM_XML:-/system/etc/fonts.xml}"
LUOSHU_PROVIDER_OVERLAY_DIR="${LUOSHU_PROVIDER_OVERLAY_DIR:-/data/fonts/config}"
LUOSHU_PROVIDER_CONFIG_OVERLAY="${LUOSHU_PROVIDER_CONFIG_OVERLAY:-$LUOSHU_PROVIDER_OVERLAY_DIR/.luoshu-provider-config.xml}"
LUOSHU_PROVIDER_SYSTEM_OVERLAY="${LUOSHU_PROVIDER_SYSTEM_OVERLAY:-$LUOSHU_PROVIDER_OVERLAY_DIR/.luoshu-system-fonts.xml}"
LUOSHU_PROVIDER_STATE="${LUOSHU_PROVIDER_STATE:-$(_luoshu_provider_config)/font-provider-overlay.conf}"
LUOSHU_PROVIDER_REPORT="${LUOSHU_PROVIDER_REPORT:-$(_luoshu_provider_config)/font-provider-overlay-report.conf}"
LUOSHU_PROVIDER_BACKUP_SUFFIX=".luoshu-bak"

luoshu_provider_log() {
    _lpl_mod="$(_luoshu_provider_module)"
    mkdir -p "$_lpl_mod/logs" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$_lpl_mod/logs/provider_cache.log" 2>/dev/null || true
}

_luoshu_provider_python() {
    _lpp_mod="$(_luoshu_provider_module)"
    _lpp_root="$_lpp_mod/common/python"
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
    [ -r /proc/self/mountinfo ] || return 1
    awk -v target="$_lpmi_target" -v source="$_lpmi_source" '
        $5 == target && index($0, source) { found=1 }
        END { exit !found }
    ' /proc/self/mountinfo 2>/dev/null
}

_luoshu_provider_unmount_one() {
    _lpu_target="$1"
    _lpu_source="$2"
    if _luoshu_provider_mount_is_ours "$_lpu_target" "$_lpu_source"; then
        umount "$_lpu_target" 2>/dev/null || \
            umount -l "$_lpu_target" 2>/dev/null || return 1
    fi
    return 0
}

_luoshu_provider_unmount_all() {
    # Reverse order: dynamic config was mounted last.
    _luoshu_provider_unmount_one "$LUOSHU_PROVIDER_CONFIG_XML" "$LUOSHU_PROVIDER_CONFIG_OVERLAY" || true
    _luoshu_provider_unmount_one "$LUOSHU_PROVIDER_SYSTEM_XML" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" || true
}

_luoshu_provider_restore_legacy_files() {
    [ -d /data/fonts/files ] || return 0
    _lpr_marker="$(_luoshu_provider_config)/.provider-legacy-restored.$$"
    rm -f "$_lpr_marker" 2>/dev/null || true
    find /data/fonts/files -type f -name "*${LUOSHU_PROVIDER_BACKUP_SUFFIX}" 2>/dev/null |
    while IFS= read -r _lpr_backup; do
        [ -f "$_lpr_backup" ] || continue
        _lpr_original="${_lpr_backup%$LUOSHU_PROVIDER_BACKUP_SUFFIX}"
        if cp -f "$_lpr_backup" "$_lpr_original" 2>/dev/null; then
            chmod 0644 "$_lpr_original" 2>/dev/null || true
            rm -f "$_lpr_backup" 2>/dev/null || true
            printf '.\n' >> "$_lpr_marker" 2>/dev/null
        fi
    done
    if [ -f "$_lpr_marker" ]; then
        _lpr_count=$(wc -l < "$_lpr_marker" 2>/dev/null | tr -d '[:space:]')
        rm -f "$_lpr_marker" 2>/dev/null || true
        luoshu_provider_log "已恢复旧版直接写入的 ${_lpr_count:-0} 个动态字体缓存文件"
    fi
}

_luoshu_provider_dynamic_google_present() {
    [ -f "$LUOSHU_PROVIDER_CONFIG_XML" ] || return 1
    grep -Eiq 'google[-_ ]?sans|product[-_ ]?sans' "$LUOSHU_PROVIDER_CONFIG_XML" 2>/dev/null && return 0
    [ -d /data/fonts/files ] || return 1
    find /data/fonts/files -type f \( -iname 'GoogleSans*' -o -iname 'ProductSans*' \) \
        -print -quit 2>/dev/null | grep -q .
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

_luoshu_provider_pick_font() {
    for _lppf in "$@"; do
        _luoshu_provider_valid_font "$_lppf" || continue
        printf '%s\n' "${_lppf##*/}"
        return 0
    done
    return 1
}

_luoshu_provider_select_fonts() {
    LUOSHU_PROVIDER_REGULAR=$(_luoshu_provider_pick_font \
        /system/fonts/LuoShu-400.ttf \
        /system/fonts/GoogleSans-Regular.ttf \
        /system/fonts/GoogleSansText-Regular.ttf \
        /system/fonts/Roboto-Regular.ttf \
        /system/fonts/SysFont-Regular.ttf) || return 1

    LUOSHU_PROVIDER_MEDIUM=$(_luoshu_provider_pick_font \
        /system/fonts/LuoShu-500.ttf \
        /system/fonts/GoogleSans-Medium.ttf \
        /system/fonts/GoogleSansText-Medium.ttf \
        /system/fonts/SourceSansPro-SemiBold.ttf \
        "/system/fonts/$LUOSHU_PROVIDER_REGULAR") || LUOSHU_PROVIDER_MEDIUM="$LUOSHU_PROVIDER_REGULAR"

    LUOSHU_PROVIDER_BOLD=$(_luoshu_provider_pick_font \
        /system/fonts/LuoShu-700.ttf \
        /system/fonts/GoogleSans-Bold.ttf \
        /system/fonts/GoogleSansText-Bold.ttf \
        /system/fonts/SourceSansPro-Bold.ttf \
        "/system/fonts/$LUOSHU_PROVIDER_MEDIUM" \
        "/system/fonts/$LUOSHU_PROVIDER_REGULAR") || LUOSHU_PROVIDER_BOLD="$LUOSHU_PROVIDER_REGULAR"

    export LUOSHU_PROVIDER_REGULAR LUOSHU_PROVIDER_MEDIUM LUOSHU_PROVIDER_BOLD
    return 0
}

_luoshu_provider_generate_overlays() {
    _lpgo_dynamic_input="$1"
    _lpgo_dynamic_output="$2"
    _lpgo_system_input="$3"
    _lpgo_system_output="$4"
    _lpgo_report="$5"

    rm -f "$_lpgo_dynamic_output" "$_lpgo_system_output" "$_lpgo_report" 2>/dev/null || true
    _luoshu_provider_python - \
        "$_lpgo_dynamic_input" "$_lpgo_dynamic_output" \
        "$_lpgo_system_input" "$_lpgo_system_output" \
        "$LUOSHU_PROVIDER_REGULAR" "$LUOSHU_PROVIDER_MEDIUM" "$LUOSHU_PROVIDER_BOLD" \
        "$_lpgo_report" <<'PY_LUOSHU_PROVIDER'
from __future__ import annotations

import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

dynamic_input = Path(sys.argv[1])
dynamic_output = Path(sys.argv[2])
system_input = Path(sys.argv[3])
system_output = Path(sys.argv[4])
regular_name = sys.argv[5]
medium_name = sys.argv[6]
bold_name = sys.argv[7]
report_path = Path(sys.argv[8])

BLOCKED = re.compile(r"(google[-_\s]*sans|product[-_\s]*sans)", re.I)
FAMILIES = (
    ("google-sans", 400, regular_name),
    ("google-sans-text", 400, regular_name),
    ("google-sans-flex", 400, regular_name),
    ("google-sans-display", 400, regular_name),
    ("product-sans", 400, regular_name),
    ("google-sans-medium", 500, medium_name),
    ("google-sans-text-medium", 500, medium_name),
    ("google-sans-display-medium", 500, medium_name),
    ("google-sans-bold", 700, bold_name),
    ("google-sans-text-bold", 700, bold_name),
    ("google-sans-display-bold", 700, bold_name),
)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalized(value: str) -> str:
    return re.sub(r"[\s_]+", "-", value.strip().lower())


def blocked(value: str) -> bool:
    return bool(BLOCKED.search(normalized(value)))


def namespace_tag(root: ET.Element, name: str) -> str:
    if root.tag.startswith("{") and "}" in root.tag:
        return root.tag.split("}", 1)[0] + "}" + name
    return name


def atomic_write(tree: ET.ElementTree, output: Path, mode: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="    ")
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    try:
        tree.write(temporary, encoding="utf-8", xml_declaration=True)
        os.chmod(temporary, mode)
        os.replace(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


# Keep every signed directory and every non-Google family declaration intact.
dynamic_tree = ET.parse(dynamic_input)
removed: list[str] = []
for parent in dynamic_tree.getroot().iter():
    for child in list(parent):
        if local_name(child.tag) != "family":
            continue
        name = child.attrib.get("name", "")
        if name and blocked(name):
            removed.append(name)
            parent.remove(child)
if not removed:
    raise SystemExit(3)
atomic_write(dynamic_tree, dynamic_output, 0o600)

# Add authoritative Google/Product Sans names to the active system font map.
system_tree = ET.parse(system_input)
root = system_tree.getroot()
family_tag = namespace_tag(root, "family")
font_tag = namespace_tag(root, "font")
existing: dict[str, list[ET.Element]] = {}
for family in root.iter():
    if local_name(family.tag) != "family":
        continue
    name = normalized(family.attrib.get("name", ""))
    if name:
        existing.setdefault(name, []).append(family)

for family_name, weight, filename in FAMILIES:
    candidates = existing.get(family_name, [])
    family = candidates[-1] if candidates else ET.SubElement(
        root, family_tag, {"name": family_name}
    )
    family.attrib["name"] = family_name
    for key in ("lang", "variant", "fallbackFor", "fallbackfor", "supportedAxes"):
        family.attrib.pop(key, None)
    for child in list(family):
        if local_name(child.tag) == "font":
            family.remove(child)
    font = ET.SubElement(
        family,
        font_tag,
        {"weight": str(weight), "style": "normal"},
    )
    font.text = filename

atomic_write(system_tree, system_output, 0o644)
report_path.write_text(
    "removed=" + str(len(removed)) + "\n"
    + "\n".join(f"family={name}" for name in sorted(set(removed))) + "\n"
    + f"regular={regular_name}\nmedium={medium_name}\nbold={bold_name}\n",
    encoding="utf-8",
)
PY_LUOSHU_PROVIDER
}

_luoshu_provider_match_metadata() {
    _lpm_source="$1"
    _lpm_target="$2"
    _lpm_uid=$(stat -c '%u' "$_lpm_target" 2>/dev/null)
    _lpm_gid=$(stat -c '%g' "$_lpm_target" 2>/dev/null)
    _lpm_mode=$(stat -c '%a' "$_lpm_target" 2>/dev/null)
    [ -n "$_lpm_uid" ] && [ -n "$_lpm_gid" ] && chown "$_lpm_uid:$_lpm_gid" "$_lpm_source" 2>/dev/null || true
    chmod "${_lpm_mode:-644}" "$_lpm_source" 2>/dev/null || true

    if command -v ls >/dev/null 2>&1 && command -v chcon >/dev/null 2>&1; then
        _lpm_context=$(ls -Zd "$_lpm_target" 2>/dev/null | awk '{print $1}')
        case "$_lpm_context" in *:*:*:*) chcon "$_lpm_context" "$_lpm_source" 2>/dev/null || true ;; esac
    fi
}

_luoshu_provider_bind_one() {
    _lpb_source="$1"
    _lpb_target="$2"
    mount --bind "$_lpb_source" "$_lpb_target" 2>/dev/null || return 1
    mount -o remount,bind,ro "$_lpb_target" 2>/dev/null || true
    _luoshu_provider_mount_is_ours "$_lpb_target" "$_lpb_source"
}

luoshu_provider_cache_sync() {
    _lpcs_font="${1:-custom}"
    _lpcs_cfg="$(_luoshu_provider_config)"
    mkdir -p "$_lpcs_cfg" 2>/dev/null || true
    {
        printf 'mode=pending-reboot\n'
        printf 'font=%s\n' "$(head -n1 "$_lpcs_cfg/active_font.conf" 2>/dev/null | tr -d '\r\n')"
        printf 'source=%s\n' "$_lpcs_font"
        printf 'time=%s\n' "$(date +%s)"
    } > "$LUOSHU_PROVIDER_STATE" 2>/dev/null || true
    chmod 0644 "$LUOSHU_PROVIDER_STATE" 2>/dev/null || true
    luoshu_provider_log "已准备 Android 动态 Google Sans 命名字体桥；完整重启后生效"
    return 0
}

luoshu_provider_cache_restore() {
    _luoshu_provider_unmount_all
    _luoshu_provider_restore_legacy_files
    rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
        "$LUOSHU_PROVIDER_STATE" "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
    return 0
}

# Called from post-fs-data before FontManagerService builds the system font map.
luoshu_provider_cache_boot() {
    _lpcb_active="${1:-default}"
    _lpcb_cfg="$(_luoshu_provider_config)"

    if [ "$_lpcb_active" = default ] || [ -z "$_lpcb_active" ]; then
        luoshu_provider_cache_restore
        return 0
    fi

    _luoshu_provider_restore_legacy_files
    _luoshu_provider_dynamic_google_present || return 2
    [ -s "$LUOSHU_PROVIDER_CONFIG_XML" ] && [ -s "$LUOSHU_PROVIDER_SYSTEM_XML" ] || return 2
    _luoshu_provider_select_fonts || {
        luoshu_provider_log "未找到可供 Google Sans family 使用的洛书系统字体"
        return 1
    }

    mkdir -p "$LUOSHU_PROVIDER_OVERLAY_DIR" "$_lpcb_cfg" 2>/dev/null || return 1
    _luoshu_provider_unmount_all

    if ! _luoshu_provider_generate_overlays \
        "$LUOSHU_PROVIDER_CONFIG_XML" "$LUOSHU_PROVIDER_CONFIG_OVERLAY" \
        "$LUOSHU_PROVIDER_SYSTEM_XML" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
        "$LUOSHU_PROVIDER_REPORT"; then
        _lpcb_rc=$?
        rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
            "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
        luoshu_provider_log "动态字体命名字体桥生成失败：code=$_lpcb_rc"
        return 1
    fi

    grep -Eiq 'google[-_ ]?sans|product[-_ ]?sans' "$LUOSHU_PROVIDER_CONFIG_OVERLAY" 2>/dev/null && {
        rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
            "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
        luoshu_provider_log "净化后的动态配置仍包含 Google/Product Sans，拒绝挂载"
        return 1
    }
    grep -Eq '<family[[:space:]][^>]*name="google-sans"' "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" 2>/dev/null || {
        rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
            "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
        luoshu_provider_log "系统字体配置没有生成 google-sans family，拒绝挂载"
        return 1
    }

    _luoshu_provider_match_metadata "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_XML"
    _luoshu_provider_match_metadata "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_CONFIG_XML"

    if ! _luoshu_provider_bind_one "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_XML"; then
        rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
            "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
        luoshu_provider_log "无法挂载系统 Google Sans 命名字体配置"
        return 1
    fi
    if ! _luoshu_provider_bind_one "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_CONFIG_XML"; then
        _luoshu_provider_unmount_one "$LUOSHU_PROVIDER_SYSTEM_XML" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" || true
        rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
            "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
        luoshu_provider_log "无法挂载动态字体配置隔离层"
        return 1
    fi

    _lpcb_removed=$(sed -n 's/^removed=//p' "$LUOSHU_PROVIDER_REPORT" 2>/dev/null | head -n1)
    {
        printf 'mode=mounted\n'
        printf 'font=%s\n' "$_lpcb_active"
        printf 'removed=%s\n' "${_lpcb_removed:-0}"
        printf 'regular=%s\n' "$LUOSHU_PROVIDER_REGULAR"
        printf 'medium=%s\n' "$LUOSHU_PROVIDER_MEDIUM"
        printf 'bold=%s\n' "$LUOSHU_PROVIDER_BOLD"
        printf 'time=%s\n' "$(date +%s)"
    } > "$LUOSHU_PROVIDER_STATE" 2>/dev/null || true
    chmod 0644 "$LUOSHU_PROVIDER_STATE" "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
    luoshu_provider_log "动态 Google Sans 命名字体桥已启用：移除 ${_lpcb_removed:-0} 个动态 family"
    return 0
}
