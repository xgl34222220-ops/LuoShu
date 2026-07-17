#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STAGE=${1:-$ROOT}
MANAGER="$STAGE/common/font_manager.sh"
POSTFS="$STAGE/post-fs-data.sh"
POSTMOUNT="$STAGE/post-mount.sh"
SERVICE="$STAGE/service.sh"
SWITCH="$STAGE/common/font_switch_v141.sh"
MIX="$STAGE/common/font_mix.sh"
MOUNT="$STAGE/common/mount_compat.sh"
for file in "$MANAGER" "$POSTFS" "$POSTMOUNT" "$SERVICE" "$SWITCH" "$MIX" "$MOUNT"; do test -f "$file"; done

# 旧管理器只需要能加载兼容库；v14.1 的真实切换与组合引擎已经自行同步负载。
if ! grep -q 'mount_compat.sh' "$MANAGER"; then
    _tmp="${MANAGER}.mount.$$"
    awk '
    BEGIN{inserted=0}
    {
        print
        if (!inserted && $0 ~ /font_import\.sh/ && $0 ~ /if \[/) { waiting=1; next }
        if (waiting && $0 == "fi") {
            print "if [ -f \"$MODULE_DIR/common/mount_compat.sh\" ]; then"
            print "    . \"$MODULE_DIR/common/mount_compat.sh\""
            print "fi"
            inserted=1; waiting=0
        }
    }
    END{if(!inserted) exit 42}
    ' "$MANAGER" > "$_tmp" || { rm -f "$_tmp"; echo '无法加载 font_manager 元模块兼容库' >&2; exit 1; }
    mv "$_tmp" "$MANAGER"
fi

# APatch 的 post-fs-data 必须保持轻量，不在阻塞阶段做元模块镜像复制。
! grep -q 'luoshu_sync_mount_payload' "$POSTFS"
grep -q 'mount_compat.sh' "$POSTMOUNT"
grep -q 'luoshu_sync_mount_payload' "$POSTMOUNT"
grep -q 'mount_compat.sh' "$SERVICE"
grep -q 'luoshu_sync_mount_payload' "$SERVICE"
grep -q 'mount_compat.sh' "$SWITCH"
grep -q 'luoshu_sync_mount_payload' "$SWITCH"
grep -q 'mount_compat.sh' "$MIX"
grep -q 'luoshu_sync_mount_payload' "$MIX"
rm -f "$STAGE/magic" "$STAGE/skip_mount" "$STAGE/skip_mountify" "$STAGE/remove" "$STAGE/disable" 2>/dev/null || true
