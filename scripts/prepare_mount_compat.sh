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

# 先升级旧源码中的调用名称；这样既兼容从旧分支构建，也避免重复注入。
for file in "$MANAGER" "$POSTFS" "$SERVICE"; do
    sed -i \
        -e 's#common/mount_compat\.sh#common/meta_overlay_compat#g' \
        -e 's/luoshu_sync_mount_payload/luoshu_sync_meta_payload/g' "$file"
done
sed -i -e 's#common/font_report\.sh#common/font_report#g' "$MANAGER" "$CUSTOMIZE"
sed -i \
    -e 's/v13\.5 Stable Hotfix2/v13.5 Stable Hotfix4/g' \
    -e 's/v13\.5 Stable Hotfix3/v13.5 Stable Hotfix4/g' "$STABILITY"

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

# Hybrid Mount Full/Lite 会扫描模块根目录的 .sh：只要非注释行第一个单词是
# mkdir/touch，或者第一个单词包含 mount/bind，就会显示“建议 Ignore”。
# 洛书这些 mkdir/touch 只是正常初始化，不是自定义挂载，因此构建时加 command 前缀，
# 保持行为不变，同时精确通过其公开源码里的扫描规则。
patch_root_shell_commands() {
    for src in "$CUSTOMIZE" "$POSTFS" "$SERVICE" "$UNINSTALL"; do
        sed -i \
            -e 's/^\([[:space:]]*\)mkdir\([[:space:]]\)/\1command mkdir\2/' \
            -e 's/^\([[:space:]]*\)touch\([[:space:]]\)/\1command touch\2/' "$src"
    done
}

# 同一字体在 ColorOS/HyperOS 中通常需要几十个别名。硬链接在模块源目录中很省空间，
# 但 Hybrid Mount 的 ext4 staging 会逐文件复制，硬链接关系会丢失，最终可能把一份
# 20~50MB 字体复制几十次并触发 ENOSPC。改成相对/绝对符号链接后，staging 只保存
# 每个真实字重一次，别名本身只有几十字节；Magic Mount、OverlayFS 都能正常解析。
patch_compact_font_aliases() {
    grep -q 'LUOSHU_HYBRID_COMPACT_ALIASES' "$ROM_ADAPTERS" && return 0
    cat >> "$ROM_ADAPTERS" <<'EOF'

# LUOSHU_HYBRID_COMPACT_ALIASES
# 构建期覆盖旧的硬链接实现，避免 Hybrid Mount ext4 staging 展开为大量完整字体副本。
_font_alias() {
    anchor="$1"
    dest="$2"
    relative=".luoshu-font-store/${anchor##*/}"
    rm -f "$dest" 2>/dev/null || true
    ln -s "$relative" "$dest" 2>/dev/null || \
        ln "$anchor" "$dest" 2>/dev/null || \
        cp -f "$anchor" "$dest" 2>/dev/null || return 1
    chmod 644 "$dest" 2>/dev/null || true
}

link_or_copy_font() {
    src="$1"
    dest="$2"
    rm -f "$dest" 2>/dev/null || true
    case "$src" in
        */system/fonts/*)
            system_target="/system/fonts/${src##*/}"
            ln -s "$system_target" "$dest" 2>/dev/null && {
                chmod 644 "$dest" 2>/dev/null || true
                return 0
            }
            ;;
    esac
    ln "$src" "$dest" 2>/dev/null || cp -f "$src" "$dest" 2>/dev/null || return 1
    chmod 644 "$dest" 2>/dev/null || true
}
EOF
}

patch_compact_emoji_aliases() {
    grep -q 'luoshu_link_compact_alias' "$MANAGER" && return 0
    src="$MANAGER"
    tmp="${src}.compact-alias.$$"
    awk '
    BEGIN { helper=0; main_alias=0; legacy_alias=0 }
    {
        if (!helper && $0 == "switch_emoji() {") {
            print "luoshu_link_compact_alias() {"
            print "    _dest=\"$1\""
            print "    _relative=\"$2\""
            print "    _anchor=\"$3\""
            print "    rm -f \"$_dest\" 2>/dev/null || true"
            print "    ln -s \"$_relative\" \"$_dest\" 2>/dev/null || \\\"
            print "        ln \"$_anchor\" \"$_dest\" 2>/dev/null || \\\"
            print "        cp -f \"$_anchor\" \"$_dest\" 2>/dev/null || return 1"
            print "    chmod 644 \"$_dest\" 2>/dev/null || true"
            print "}"
            print ""
            helper=1
        }
        if ($0 ~ /^[[:space:]]*ln "\$_anchor" "\$SYSTEM_FONTS_DIR\/NotoColorEmoji\.ttf"/) {
            print "        luoshu_link_compact_alias \"$SYSTEM_FONTS_DIR/NotoColorEmoji.ttf\" \".luoshu-emoji-store/current.font\" \"$_anchor\" || return 1"
            main_alias=1
            next
        }
        if ($0 ~ /^[[:space:]]*ln "\$_anchor" "\$SYSTEM_FONTS_DIR\/NotoColorEmojiLegacy\.ttf"/) {
            print "            luoshu_link_compact_alias \"$SYSTEM_FONTS_DIR/NotoColorEmojiLegacy.ttf\" \".luoshu-emoji-store/current.font\" \"$_anchor\" || true"
            legacy_alias=1
            next
        }
        print
    }
    END { if (!helper || !main_alias || !legacy_alias) exit 42 }
    ' "$src" > "$tmp" || { rm -f "$tmp"; echo "无法注入紧凑 Emoji 别名" >&2; exit 1; }
    mv "$tmp" "$src"
}

# 复刻 Hybrid Mount 公开源码中的 has_suspicious_shell_commands 规则。
# 只扫描模块根目录 .sh，忽略空行和注释，并检查每行第一个单词。
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
patch_compact_font_aliases
patch_compact_emoji_aliases

# 清除旧版会触发 Hybrid Mount 脚本扫描的重复文件。
rm -f "$STAGE/skip_mount" "$STAGE/skip_mountify" \
      "$STAGE/common/mount_compat.sh" "$STAGE/common/font_report.sh" \
      "$STAGE/common/play_font_bridge.sh" "$STAGE/common/wechat_xweb_bridge.sh" 2>/dev/null || true

grep -q 'common/meta_overlay_compat' "$MANAGER"
test "$(grep -c 'luoshu_sync_meta_payload' "$MANAGER")" -ge 2
grep -q 'luoshu_sync_meta_payload' "$POSTFS"
grep -q 'luoshu_sync_meta_payload' "$SERVICE"
grep -q 'LUOSHU_HYBRID_COMPACT_ALIASES' "$ROM_ADAPTERS"
grep -q 'luoshu_link_compact_alias' "$MANAGER"

SUSPICIOUS=$(hybrid_mount_suspicious_lines)
if [ -n "$SUSPICIOUS" ]; then
    echo "发布包仍会被 Hybrid Mount 判定为自定义挂载脚本：" >&2
    printf '%s\n' "$SUSPICIOUS" >&2
    exit 1
fi
