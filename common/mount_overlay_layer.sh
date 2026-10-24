#!/system/bin/sh
# LuoShu read-only ext4 loop lower for the self OverlayFS backend.
#
# OverlayFS refuses a lower layer that lives on a filesystem with
# case-insensitive lookup enabled (Linux Documentation/filesystems/
# overlayfs.rst; the kernel logs "overlayfs: case-insensitive capable
# filesystem on ... not supported"). On devices whose /data is F2FS with the
# encoding/casefold feature, the module payload is such a lower. This file
# builds a small ext4 image from the payload with casefold explicitly off
# (mke2fs(8): -O ^casefold, populated with -d), attaches it with a loop mount
# (mount(8) -o loop), mirrors the payload's SELinux labels, checks content and
# labels, remounts it read-only and journals it in mounts.list so the regular
# reverse-order rollback releases it after the overlay and the captured lower.
#
# It is sourced lazily by mount_self_backend.sh only after an overlay attempt
# failed with a new casefold rejection. Every failure releases whatever this
# file created, in reverse order, and returns 1 so the caller keeps the
# existing per-file bind fallback.
set +e

LUOSHU_OVERLAY_COMPAT_SOURCE=''

_luoshu_ovll_log() {
    type _luoshu_self_log >/dev/null 2>&1 && _luoshu_self_log "$*"
    return 0
}

_luoshu_ovll_dir() {
    printf '%s/work/overlay-%s\n' "$(_luoshu_self_state_root)" "$1"
}

_luoshu_ovll_mountinfo() {
    printf '%s\n' "${LUOSHU_SELF_MOUNTINFO:-/proc/self/mountinfo}"
}

# Mount options column ($6) of the newest mountinfo entry for a mount point.
_luoshu_ovll_mount_opts() {
    awk -v t="$1" '$5 == t { opts = $6; seen = 1 } END { if (seen) print opts; exit !seen }' \
        "$(_luoshu_ovll_mountinfo)" 2>/dev/null
}

# Only Android's e2fsprogs build is trusted to provide -d population. An
# explicitly configured formatter (tests, custom ROM paths) is used as-is and
# never silently replaced by a different binary.
_luoshu_ovll_formatter() {
    if [ "${LUOSHU_OVERLAY_FORMATTER+set}" = set ]; then
        [ -n "$LUOSHU_OVERLAY_FORMATTER" ] && [ -x "$LUOSHU_OVERLAY_FORMATTER" ] || return 1
        printf '%s\n' "$LUOSHU_OVERLAY_FORMATTER"
        return 0
    fi
    for _lovf_bin in /system/bin/mke2fs /vendor/bin/mke2fs /system/xbin/mke2fs; do
        [ -x "$_lovf_bin" ] && { printf '%s\n' "$_lovf_bin"; return 0; }
    done
    return 1
}

_luoshu_ovll_selinux_wanted() {
    [ "${LUOSHU_OVERLAY_SKIP_SELINUX:-0}" != 1 ] || return 1
    [ -e "${LUOSHU_OVERLAY_SELINUXFS:-/sys/fs/selinux}/enforce" ] || return 1
    return 0
}

# Prints the SELinux context of a path (toybox `ls -Zd`), empty when unknown.
_luoshu_ovll_context() {
    ls -Zd "$1" 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i ~ /^u:[a-z_]+:[A-Za-z0-9_]+:/) { print $i; exit } }'
}

# Image size: payload KiB plus 25% and a fixed 4 MiB for metadata; inode count
# from the entry count with headroom. Both are bounded so a bad reading never
# produces a zero or absurd image.
_luoshu_ovll_size_kib() {
    _lovs_kib=$(du -sk "$1" 2>/dev/null | awk 'NR == 1 { print $1 }')
    case "$_lovs_kib" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' $((_lovs_kib + _lovs_kib / 4 + 4096))
}

_luoshu_ovll_inodes() {
    _lovi_count=$(find "$1" 2>/dev/null | wc -l | tr -d ' ')
    case "$_lovi_count" in ''|*[!0-9]*) _lovi_count=0 ;; esac
    printf '%s\n' $((_lovi_count + 64))
}

_luoshu_ovll_journal_add() {
    [ -n "${_lsme_mount_list:-}" ] || return 0
    printf '%s\n' "$1" >> "$_lsme_mount_list" 2>/dev/null
}

_luoshu_ovll_journal_remove() {
    [ -n "${_lsme_mount_list:-}" ] && [ -f "$_lsme_mount_list" ] || return 0
    awk -v t="$1" '$0 != t' "$_lsme_mount_list" > "$_lsme_mount_list.ovll" 2>/dev/null && \
        mv -f "$_lsme_mount_list.ovll" "$_lsme_mount_list" 2>/dev/null
    rm -f "$_lsme_mount_list.ovll" 2>/dev/null
    return 0
}

# Apply the payload's labels to the layer; entries the payload does not label
# inherit the label of the stock target directory they will be shown in.
_luoshu_ovll_apply_labels() {
    _lova_source="$1"
    _lova_layer="$2"
    _lova_fallback=$(_luoshu_ovll_context "$3")
    command -v chcon >/dev/null 2>&1 || return 1
    _lova_root_ctx=$(_luoshu_ovll_context "$3")
    [ -n "$_lova_root_ctx" ] || return 1
    chcon "$_lova_root_ctx" "$_lova_layer" 2>/dev/null || return 1
    ( cd "$_lova_source" 2>/dev/null && find . -mindepth 1 ) | while IFS= read -r _lova_rel; do
        _lova_rel=${_lova_rel#./}
        _lova_ctx=$(_luoshu_ovll_context "$_lova_source/$_lova_rel")
        [ -n "$_lova_ctx" ] || _lova_ctx="$_lova_fallback"
        chcon -h "$_lova_ctx" "$_lova_layer/$_lova_rel" 2>/dev/null || \
            chcon "$_lova_ctx" "$_lova_layer/$_lova_rel" 2>/dev/null || exit 1
    done
}

# The layer must hold exactly the payload: same entry list, same file bytes,
# and (when SELinux is in use) the label each entry was given.
_luoshu_ovll_verify() {
    _lovv_source="$1"
    _lovv_layer="$2"
    _lovv_target="$3"
    _lovv_src_list=$( (cd "$_lovv_source" 2>/dev/null && find . -mindepth 1 | sort) ) || return 1
    _lovv_dst_list=$( (cd "$_lovv_layer" 2>/dev/null && find . -mindepth 1 | sort) ) || return 1
    [ -n "$_lovv_src_list" ] && [ "$_lovv_src_list" = "$_lovv_dst_list" ] || return 1
    _lovv_fallback=''
    _luoshu_ovll_selinux_wanted && _lovv_fallback=$(_luoshu_ovll_context "$_lovv_target")
    printf '%s\n' "$_lovv_src_list" | while IFS= read -r _lovv_rel; do
        _lovv_rel=${_lovv_rel#./}
        if [ -f "$_lovv_source/$_lovv_rel" ] && [ ! -L "$_lovv_source/$_lovv_rel" ]; then
            cmp -s "$_lovv_source/$_lovv_rel" "$_lovv_layer/$_lovv_rel" || exit 1
        fi
        if [ -n "$_lovv_fallback" ]; then
            _lovv_want=$(_luoshu_ovll_context "$_lovv_source/$_lovv_rel")
            [ -n "$_lovv_want" ] || _lovv_want="$_lovv_fallback"
            [ "$(_luoshu_ovll_context "$_lovv_layer/$_lovv_rel")" = "$_lovv_want" ] || exit 1
        fi
    done
}

# Undo everything prepare created for KEY: unmount (detaching the autoclear
# loop device), drop the journal line, remove the mount point and image.
luoshu_overlay_release_ext4_layer() {
    _lovr_dir=$(_luoshu_ovll_dir "$1")
    if _luoshu_ovll_mount_opts "$_lovr_dir" >/dev/null; then
        _luoshu_umount_cmd "$_lovr_dir" >/dev/null 2>&1 || \
            _luoshu_umount_cmd -l "$_lovr_dir" >/dev/null 2>&1 || true
    fi
    _luoshu_ovll_journal_remove "$_lovr_dir"
    rm -rf "$_lovr_dir" "$_lovr_dir.img" 2>/dev/null
    LUOSHU_OVERLAY_COMPAT_SOURCE=''
    return 0
}

# prepare SOURCE TARGET KEY: on success LUOSHU_OVERLAY_COMPAT_SOURCE names a
# read-only ext4 mount holding SOURCE, already journaled in mounts.list.
luoshu_overlay_prepare_ext4_layer() {
    _lovp_source="$1"
    _lovp_target="$2"
    _lovp_key="$3"
    LUOSHU_OVERLAY_COMPAT_SOURCE=''
    [ -d "$_lovp_source" ] && [ -d "$_lovp_target" ] && [ -n "$_lovp_key" ] || return 1
    _lovp_dir=$(_luoshu_ovll_dir "$_lovp_key")
    _lovp_img="$_lovp_dir.img"
    luoshu_overlay_release_ext4_layer "$_lovp_key"

    _lovp_mkfs=$(_luoshu_ovll_formatter) || {
        _luoshu_ovll_log "未找到可用 mke2fs，跳过 ext4 loop 兼容层：$_lovp_target"
        return 1
    }
    _lovp_kib=$(_luoshu_ovll_size_kib "$_lovp_source") || return 1
    _lovp_inodes=$(_luoshu_ovll_inodes "$_lovp_source")
    mkdir -p "${_lovp_dir%/*}" 2>/dev/null || return 1
    rm -f "$_lovp_img" 2>/dev/null
    dd if=/dev/zero of="$_lovp_img" bs=1024 count=0 seek="$_lovp_kib" >/dev/null 2>&1 || {
        luoshu_overlay_release_ext4_layer "$_lovp_key"; return 1; }
    "$_lovp_mkfs" -q -t ext4 -b 4096 -I 256 -m 0 -N "$_lovp_inodes" \
        -O ^has_journal,^casefold -d "$_lovp_source" "$_lovp_img" >/dev/null 2>&1 || {
        _luoshu_ovll_log "mke2fs 生成 ext4 兼容层失败：$_lovp_target"
        luoshu_overlay_release_ext4_layer "$_lovp_key"; return 1; }

    mkdir -p "$_lovp_dir" 2>/dev/null || { luoshu_overlay_release_ext4_layer "$_lovp_key"; return 1; }
    _luoshu_mount_cmd -t ext4 -o loop,rw,noatime,nodev,nosuid "$_lovp_img" "$_lovp_dir" >/dev/null 2>&1 || {
        _luoshu_ovll_log "loop 挂载 ext4 兼容层失败：$_lovp_target"
        luoshu_overlay_release_ext4_layer "$_lovp_key"; return 1; }
    # Journal immediately: any later failure in this boot is undone by the
    # regular reverse-order rollback even if this function is interrupted.
    _luoshu_ovll_journal_add "$_lovp_dir"

    rmdir "$_lovp_dir/lost+found" 2>/dev/null || rm -rf "$_lovp_dir/lost+found" 2>/dev/null
    chmod 0755 "$_lovp_dir" 2>/dev/null
    if _luoshu_ovll_selinux_wanted; then
        _luoshu_ovll_apply_labels "$_lovp_source" "$_lovp_dir" "$_lovp_target" || {
            _luoshu_ovll_log "ext4 兼容层 SELinux 标签设置失败：$_lovp_target"
            luoshu_overlay_release_ext4_layer "$_lovp_key"; return 1; }
    fi
    _luoshu_mount_cmd -o remount,ro "$_lovp_dir" >/dev/null 2>&1 || {
        luoshu_overlay_release_ext4_layer "$_lovp_key"; return 1; }
    case ",$(_luoshu_ovll_mount_opts "$_lovp_dir")," in
        *,ro,*) ;;
        *)
            _luoshu_ovll_log "ext4 兼容层未能只读：$_lovp_target"
            luoshu_overlay_release_ext4_layer "$_lovp_key"; return 1 ;;
    esac
    _luoshu_ovll_verify "$_lovp_source" "$_lovp_dir" "$_lovp_target" || {
        _luoshu_ovll_log "ext4 兼容层内容或标签校验失败：$_lovp_target"
        luoshu_overlay_release_ext4_layer "$_lovp_key"; return 1; }

    LUOSHU_OVERLAY_COMPAT_SOURCE="$_lovp_dir"
    return 0
}
