#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STAGE=${1:-$ROOT}
MANAGER="$STAGE/common/font_manager.sh"
ROM_ADAPTERS="$STAGE/common/rom_adapters.sh"
POSTFS="$STAGE/post-fs-data.sh"
SERVICE="$STAGE/service.sh"
CUSTOMIZE="$STAGE/customize.sh"
UNINSTALL="$STAGE/uninstall.sh"
STABILITY="$STAGE/common/stability.sh"
COMPAT="$STAGE/common/meta_overlay_compat"

for file in "$MANAGER" "$ROM_ADAPTERS" "$POSTFS" "$SERVICE" "$CUSTOMIZE" "$UNINSTALL" "$STABILITY" "$COMPAT"; do
    test -f "$file"
done

for file in "$MANAGER" "$POSTFS" "$SERVICE"; do
    sed -i \
        -e 's#common/mount_compat\.sh#common/meta_overlay_compat#g' \
        -e 's/luoshu_sync_mount_payload/luoshu_sync_meta_payload/g' "$file"
done
sed -i -e 's#common/font_report\.sh#common/font_report#g' "$MANAGER" "$CUSTOMIZE"
sed -i \
    -e 's/v13\.5 Stable Hotfix2/v13.5 Stable Hotfix5/g' \
    -e 's/v13\.5 Stable Hotfix3/v13.5 Stable Hotfix5/g' \
    -e 's/v13\.5 Stable Hotfix4/v13.5 Stable Hotfix5/g' "$STABILITY"

patch_manager() {
    src="$1"
    tmp="${src}.meta-compat.$$"
    awk '
    BEGIN { import_block=0; sourced=0; emoji_hook=0; text_hook=0 }
    {
        print
        if ($0 ~ /if \[ -f "\$MODULE_DIR\/common\/font_import\.sh" \]; then/) {
            import_block=1
            next
        }
        if (import_block && $0 == "fi") {
            print "if [ -f \"$MODULE_DIR/common/meta_overlay_compat\" ]; then"
            print "    . \"$MODULE_DIR/common/meta_overlay_compat\""
            print "fi"
            import_block=0
            sourced=1
            next
        }
        if ($0 ~ /chmod 644 "\$ACTIVE_EMOJI_CONF" "\$EMOJI_REBOOT_REQUIRED"/) {
            print "    type luoshu_sync_meta_payload >/dev/null 2>&1 && luoshu_sync_meta_payload 2>/dev/null || true"
            emoji_hook=1
            next
        }
        if ($0 ~ /chmod 644 "\$ACTIVE_FONT_CONF" "\$SYSTEM_FONTS_DIR"\/\*/) {
            print "    type luoshu_sync_meta_payload >/dev/null 2>&1 && luoshu_sync_meta_payload 2>/dev/null || true"
            text_hook=1
            next
        }
    }
    END { if (!sourced || !emoji_hook || !text_hook) exit 42 }
    ' "$src" > "$tmp" || { rm -f "$tmp"; echo "无法注入 font_manager 元模块兼容钩子" >&2; exit 1; }
    mv "$tmp" "$src"
}

patch_postfs() {
    src="$1"
    tmp="${src}.meta-compat.$$"
    awk '
    BEGIN { inserted=0 }
    {
        print
        if (!inserted && $0 ~ /mkdir -p "\$MODDIR\/config"/) {
            print "[ -f \"$MODDIR/common/meta_overlay_compat\" ] && . \"$MODDIR/common/meta_overlay_compat\""
            print "type luoshu_sync_meta_payload >/dev/null 2>&1 && luoshu_sync_meta_payload 2>/dev/null || true"
            inserted=1
        }
    }
    END { if (!inserted) exit 42 }
    ' "$src" > "$tmp" || { rm -f "$tmp"; echo "无法注入 post-fs-data 元模块兼容钩子" >&2; exit 1; }
    mv "$tmp" "$src"
}

patch_service() {
    src="$1"
    tmp="${src}.meta-compat.$$"
    awk '
    BEGIN { inserted=0 }
    {
        print
        if (!inserted && $0 ~ /log_service "INFO" "服务脚本开始执行/) {
            print "    if [ -f \"$MODDIR/common/meta_overlay_compat\" ]; then"
            print "        . \"$MODDIR/common/meta_overlay_compat\""
            print "        luoshu_sync_meta_payload 2>/dev/null || true"
            print "    fi"
            inserted=1
        }
    }
    END { if (!inserted) exit 42 }
    ' "$src" > "$tmp" || { rm -f "$tmp"; echo "无法注入 service 元模块兼容钩子" >&2; exit 1; }
    mv "$tmp" "$src"
}

patch_root_shell_commands() {
    for src in "$CUSTOMIZE" "$POSTFS" "$SERVICE" "$UNINSTALL"; do
        sed -i \
            -e 's/^\([[:space:]]*\)mkdir\([[:space:]]\)/\1command mkdir\2/' \
            -e 's/^\([[:space:]]*\)touch\([[:space:]]\)/\1command touch\2/' "$src"
    done
}

patch_staging_safe_font_aliases() {
    grep -q 'LUOSHU_HYBRID_STAGE_BUDGET' "$ROM_ADAPTERS" && return 0
    sed -i 's/base_names="SysSans-Hant-Regular SysSans-Hans-Regular/base_names="SysSans-Hans-Regular SysSans-Hant-Regular/' "$ROM_ADAPTERS"

    cat >> "$ROM_ADAPTERS" <<'EOF'

# LUOSHU_HYBRID_STAGE_BUDGET
# 禁止使用字体符号链接：部分 ROM 的字体服务会出现严重卡顿甚至假死。
# 恢复硬链接/普通文件，并按 Hybrid Mount staging 展开后的体积限制别名数量。
LUOSHU_FONT_STAGE_BUDGET=${LUOSHU_FONT_STAGE_BUDGET:-134217728}

_luoshu_font_size() {
    _f="$1"
    _n=$(wc -c < "$_f" 2>/dev/null | tr -d '[:space:]')
    case "$_n" in ''|*[!0-9]*) _n=0 ;; esac
    printf '%s' "$_n"
}

_font_store_reset() {
    dest_dir="$1"
    rm -rf "$dest_dir/.luoshu-font-store" 2>/dev/null || true
    mkdir -p "$dest_dir/.luoshu-font-store" 2>/dev/null || true
    chmod 755 "$dest_dir/.luoshu-font-store" 2>/dev/null || true
    LUOSHU_STAGE_USED=0
    LUOSHU_STAGE_ALIAS_COUNT=0
    LUOSHU_STAGE_ANCHORS=""
    LUOSHU_STAGE_BUDGET_WARNED=0
}

_font_anchor() {
    src="$1"
    dest_dir="$2"
    key="$3"
    anchor="$dest_dir/.luoshu-font-store/${key}.font"
    cp -f "$src" "$anchor" 2>/dev/null || return 1
    chmod 644 "$anchor" 2>/dev/null || true
    echo "$anchor"
}

_luoshu_register_anchor_cost() {
    _anchor="$1"
    case " $LUOSHU_STAGE_ANCHORS " in
        *" $_anchor "*) return 0 ;;
    esac
    _size=$(_luoshu_font_size "$_anchor")
    LUOSHU_STAGE_USED=$((LUOSHU_STAGE_USED + _size))
    LUOSHU_STAGE_ANCHORS="$LUOSHU_STAGE_ANCHORS $_anchor"
}

_luoshu_stage_budget_allows() {
    _src="$1"
    _size=$(_luoshu_font_size "$_src")
    _next=$((LUOSHU_STAGE_USED + _size))
    if [ "$LUOSHU_STAGE_ALIAS_COUNT" -gt 0 ] && [ "$_next" -gt "$LUOSHU_FONT_STAGE_BUDGET" ]; then
        if [ "$LUOSHU_STAGE_BUDGET_WARNED" -eq 0 ]; then
            _log_step "  已达到 Hybrid Mount 安全体积预算，低优先级字体别名将被跳过"
            LUOSHU_STAGE_BUDGET_WARNED=1
        fi
        return 1
    fi
    return 0
}

_font_alias() {
    anchor="$1"
    dest="$2"
    _luoshu_register_anchor_cost "$anchor"
    _luoshu_stage_budget_allows "$anchor" || return 1
    rm -f "$dest" 2>/dev/null || true
    ln "$anchor" "$dest" 2>/dev/null || cp -f "$anchor" "$dest" 2>/dev/null || return 1
    chmod 644 "$dest" 2>/dev/null || true
    _size=$(_luoshu_font_size "$anchor")
    LUOSHU_STAGE_USED=$((LUOSHU_STAGE_USED + _size))
    LUOSHU_STAGE_ALIAS_COUNT=$((LUOSHU_STAGE_ALIAS_COUNT + 1))
    return 0
}

link_or_copy_font() {
    src="$1"
    dest="$2"
    _luoshu_stage_budget_allows "$src" || return 1
    rm -f "$dest" 2>/dev/null || true
    ln "$src" "$dest" 2>/dev/null || cp -f "$src" "$dest" 2>/dev/null || return 1
    chmod 644 "$dest" 2>/dev/null || true
    _size=$(_luoshu_font_size "$src")
    LUOSHU_STAGE_USED=$((LUOSHU_STAGE_USED + _size))
    LUOSHU_STAGE_ALIAS_COUNT=$((LUOSHU_STAGE_ALIAS_COUNT + 1))
    return 0
}
EOF
}

hybrid_mount_suspicious_lines() {
    for src in "$STAGE"/*.sh; do
        [ -f "$src" ] || continue
        awk -v file="${src##*/}" '
        {
            line=$0
            sub(/^[[:space:]]+/, "", line)
            if (line == "" || substr(line, 1, 1) == "#") next
            count=split(line, words, /[[:space:]]+/)
            first=words[1]
            sub(/^[\\`]+/, "", first)
            bad=0
            if (first == "mount" || first == "mkdir" || first == "touch") bad=1
            if (first == "busybox" && count > 1 && (words[2] == "mount" || words[2] == "mkdir" || words[2] == "touch")) bad=1
            if (index(first, "mount") || index(first, "bind")) bad=1
            if (bad) print file ":" NR ":" $0
        }
        ' "$src"
    done
}

if ! grep -q 'common/meta_overlay_compat' "$MANAGER"; then patch_manager "$MANAGER"; fi
if ! grep -q 'luoshu_sync_meta_payload' "$POSTFS"; then patch_postfs "$POSTFS"; fi
if ! grep -q 'luoshu_sync_meta_payload' "$SERVICE"; then patch_service "$SERVICE"; fi
patch_root_shell_commands
patch_staging_safe_font_aliases

rm -f "$STAGE/skip_mount" "$STAGE/skip_mountify" \
      "$STAGE/common/mount_compat.sh" "$STAGE/common/font_report.sh" \
      "$STAGE/common/play_font_bridge.sh" "$STAGE/common/wechat_xweb_bridge.sh" 2>/dev/null || true

grep -q 'common/meta_overlay_compat' "$MANAGER"
test "$(grep -c 'luoshu_sync_meta_payload' "$MANAGER")" -ge 2
grep -q 'luoshu_sync_meta_payload' "$POSTFS"
grep -q 'luoshu_sync_meta_payload' "$SERVICE"
grep -q 'LUOSHU_HYBRID_STAGE_BUDGET' "$ROM_ADAPTERS"
! grep -q 'LUOSHU_HYBRID_COMPACT_ALIASES' "$ROM_ADAPTERS"
! grep -q 'luoshu_link_compact_alias' "$MANAGER"

SUSPICIOUS=$(hybrid_mount_suspicious_lines)
if [ -n "$SUSPICIOUS" ]; then
    echo "发布包仍会被 Hybrid Mount 判定为自定义挂载脚本：" >&2
    printf '%s\n' "$SUSPICIOUS" >&2
    exit 1
fi
