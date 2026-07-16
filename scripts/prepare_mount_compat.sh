#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STAGE=${1:-$ROOT}
MANAGER="$STAGE/common/font_manager.sh"
POSTFS="$STAGE/post-fs-data.sh"
SERVICE="$STAGE/service.sh"
CUSTOMIZE="$STAGE/customize.sh"
STABILITY="$STAGE/common/stability.sh"
COMPAT="$STAGE/common/meta_overlay_compat"

for file in "$MANAGER" "$POSTFS" "$SERVICE" "$CUSTOMIZE" "$STABILITY" "$COMPAT"; do
    test -f "$file"
done

# 先升级旧源码中的调用名称；这样既兼容从旧分支构建，也避免重复注入。
for file in "$MANAGER" "$POSTFS" "$SERVICE"; do
    sed -i \
        -e 's#common/mount_compat\.sh#common/meta_overlay_compat#g' \
        -e 's/luoshu_sync_mount_payload/luoshu_sync_meta_payload/g' "$file"
done
sed -i -e 's#common/font_report\.sh#common/font_report#g' "$MANAGER" "$CUSTOMIZE"
sed -i -e 's/v13\.5 Stable Hotfix2/v13.5 Stable Hotfix3/g' "$STABILITY"

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

if ! grep -q 'common/meta_overlay_compat' "$MANAGER"; then patch_manager "$MANAGER"; fi
if ! grep -q 'luoshu_sync_meta_payload' "$POSTFS"; then patch_postfs "$POSTFS"; fi
if ! grep -q 'luoshu_sync_meta_payload' "$SERVICE"; then patch_service "$SERVICE"; fi

# 清除旧版会触发 Hybrid Mount 脚本扫描的重复文件。
rm -f "$STAGE/skip_mount" "$STAGE/skip_mountify" \
      "$STAGE/common/mount_compat.sh" "$STAGE/common/font_report.sh" \
      "$STAGE/common/play_font_bridge.sh" "$STAGE/common/wechat_xweb_bridge.sh" 2>/dev/null || true

grep -q 'common/meta_overlay_compat' "$MANAGER"
test "$(grep -c 'luoshu_sync_meta_payload' "$MANAGER")" -ge 2
grep -q 'luoshu_sync_meta_payload' "$POSTFS"
grep -q 'luoshu_sync_meta_payload' "$SERVICE"
