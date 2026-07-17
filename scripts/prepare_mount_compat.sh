#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STAGE=${1:-$ROOT}
MANAGER="$STAGE/common/font_manager.sh"
POSTFS="$STAGE/post-fs-data.sh"
SERVICE="$STAGE/service.sh"

for file in "$MANAGER" "$POSTFS" "$SERVICE" "$STAGE/common/mount_compat.sh"; do
    test -f "$file"
done

patch_manager() {
    src="$1"
    tmp="${src}.mount-compat.$$"
    awk '
    BEGIN { import_block=0; sourced=0; emoji_hook=0; text_hook=0 }
    {
        print
        if ($0 ~ /if \[ -f "\$MODULE_DIR\/common\/font_import\.sh" \]; then/) {
            import_block=1
            next
        }
        if (import_block && $0 == "fi") {
            print "if [ -f \"$MODULE_DIR/common/mount_compat.sh\" ]; then"
            print "    . \"$MODULE_DIR/common/mount_compat.sh\""
            print "fi"
            import_block=0
            sourced=1
            next
        }
        if ($0 ~ /chmod 644 "\$ACTIVE_EMOJI_CONF" "\$EMOJI_REBOOT_REQUIRED"/) {
            print "    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true"
            emoji_hook=1
            next
        }
        if ($0 ~ /chmod 644 "\$ACTIVE_FONT_CONF" "\$SYSTEM_FONTS_DIR"\/\*/) {
            print "    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true"
            text_hook=1
            next
        }
    }
    END {
        if (!sourced || !emoji_hook || !text_hook) exit 42
    }
    ' "$src" > "$tmp" || { rm -f "$tmp"; echo "无法注入 font_manager 元模块兼容钩子" >&2; exit 1; }
    mv "$tmp" "$src"
}

patch_postfs() {
    src="$1"
    tmp="${src}.mount-compat.$$"
    awk '
    BEGIN { inserted=0 }
    {
        print
        if (!inserted && $0 ~ /mkdir -p "\$MODDIR\/config"/) {
            print "[ -f \"$MODDIR/common/mount_compat.sh\" ] && . \"$MODDIR/common/mount_compat.sh\""
            print "type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true"
            inserted=1
        }
    }
    END { if (!inserted) exit 42 }
    ' "$src" > "$tmp" || { rm -f "$tmp"; echo "无法注入 post-fs-data 元模块兼容钩子" >&2; exit 1; }
    mv "$tmp" "$src"
}

patch_service() {
    src="$1"
    tmp="${src}.mount-compat.$$"
    awk '
    BEGIN { inserted=0 }
    {
        print
        if (!inserted && $0 ~ /log_service "INFO" "服务脚本开始执行/) {
            print "    if [ -f \"$MODDIR/common/mount_compat.sh\" ]; then"
            print "        . \"$MODDIR/common/mount_compat.sh\""
            print "        luoshu_sync_mount_payload 2>/dev/null || true"
            print "    fi"
            inserted=1
        }
    }
    END { if (!inserted) exit 42 }
    ' "$src" > "$tmp" || { rm -f "$tmp"; echo "无法注入 service 元模块兼容钩子" >&2; exit 1; }
    mv "$tmp" "$src"
}

if ! grep -q 'common/mount_compat.sh' "$MANAGER"; then patch_manager "$MANAGER"; fi
if ! grep -q 'luoshu_sync_mount_payload' "$POSTFS"; then patch_postfs "$POSTFS"; fi
if ! grep -q 'luoshu_sync_mount_payload' "$SERVICE"; then patch_service "$SERVICE"; fi

# 构建时确保模块没有携带 skip_mount / skip_mountify，避免元模块直接跳过洛书。
rm -f "$STAGE/skip_mount" "$STAGE/skip_mountify" 2>/dev/null || true

grep -q 'common/mount_compat.sh' "$MANAGER"
test "$(grep -c 'luoshu_sync_mount_payload' "$MANAGER")" -ge 2
grep -q 'luoshu_sync_mount_payload' "$POSTFS"
grep -q 'luoshu_sync_mount_payload' "$SERVICE"
