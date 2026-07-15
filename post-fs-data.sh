#!/system/bin/sh
# ============================================================
# 洛书 - 启动挂载脚本 (post-fs-data.sh)
# 作者：惜故里丶
# 版本：v12.8
# 功能：系统启动早期执行，验证和修复字体配置
# ============================================================

# 禁用严格错误终止（util_functions.sh 可能设置 set -e）
set +e

MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"

# 加载工具函数
if [ -f "$MODULE_DIR/common/util_functions.sh" ]; then
    # shellcheck source=/dev/null
    . "$MODULE_DIR/common/util_functions.sh"
else
    return 0
fi
if [ -f "$MODULE_DIR/common/rom_adapters.sh" ]; then
    . "$MODULE_DIR/common/rom_adapters.sh"
fi

init_module

log_message "INFO" "===== post-fs-data 开始 ====="

# ---------- 1. 我们不替换 fonts.xml ----------
# 因为我们只替换字体文件（文件名和系统原始文件一样）
# 系统继续使用原始的 /system/etc/fonts.xml
# 这样保留了所有字体族定义（符号字体、各种语言回退等）
# 避免 emoji 数字（1️⃣2️⃣3️⃣）等显示方块
if [ -f "$MODULE_DIR/system/etc/fonts.xml" ]; then
    # 如果旧版本遗留了 fonts.xml，删除它
    rm -f "$MODULE_DIR/system/etc/fonts.xml"
    log_message "INFO" "已删除旧版本遗留的 fonts.xml，使用系统原始配置"
fi

# ---------- 2. 确保字体文件权限正确 ----------
if [ -d "$MODULE_DIR/system/fonts" ]; then
    set_perm_recursive "$MODULE_DIR/system/fonts" 0 0 0755 0644
    log_message "INFO" "字体文件权限已修复"
fi

# ---------- 2.5 Overlay fallback ----------
# 模块中不存在的字体文件会由下层 ROM 原目录直接提供。不要把原厂字体复制
# 到模块，否则每次启动都会重新制造数百 MB 到 1GB 的冗余文件。
log_message "INFO" "精简模式：原厂 fallback 由 Overlay 下层保留"

# ---------- 3. 修复 ColorOS 字体路径 ----------
if [ "$IS_COLOROS" = "true" ]; then
    if [ -d /data/fonts ]; then
        SYNCED_COUNT=0
        for cname in $(get_all_coloros_names); do
            cfile="$MODULE_DIR/system/fonts/${cname}.ttf"
            if [ -f "$cfile" ]; then
                DEST_FILE="/data/fonts/${cname}.ttf"
                if [ ! -f "$DEST_FILE" ] || [ "$cfile" -nt "$DEST_FILE" ]; then
                    cp -f "$cfile" "$DEST_FILE" 2>/dev/null && {
                        chmod 644 "$DEST_FILE" 2>/dev/null || true
                        SYNCED_COUNT=$((SYNCED_COUNT + 1))
                    }
                fi
            fi
        done
        if [ "$SYNCED_COUNT" -gt 0 ]; then
            log_message "INFO" "ColorOS 字体同步完成（$SYNCED_COUNT 个文件）"
        fi
        set_font_permissions /data/fonts
    fi

    # 同步 DIN 字体到 system_ext/fonts/（ColorOS 锁屏大时钟等可能从此加载）
    if [ -d "$MODULE_DIR/system_ext/fonts" ]; then
        SYS_EXT_SYNCED=0
        for cname in $(get_all_coloros_names); do
            cfile="$MODULE_DIR/system/fonts/${cname}.ttf"
            dest="$MODULE_DIR/system_ext/fonts/${cname}.ttf"
            if [ -f "$cfile" ] && [ ! -f "$dest" ]; then
                link_or_copy_font "$cfile" "$dest" 2>/dev/null && SYS_EXT_SYNCED=$((SYS_EXT_SYNCED + 1))
            fi
        done
        if [ "$SYS_EXT_SYNCED" -gt 0 ]; then
            log_message "INFO" "system_ext/fonts/ 同步完成（$SYS_EXT_SYNCED 个文件）"
        fi
        set_perm_recursive "$MODULE_DIR/system_ext/fonts" 0 0 0755 0644
    fi

    # 同步 DIN 字体到 product/fonts/
    if [ -d "$MODULE_DIR/product/fonts" ]; then
        PROD_SYNCED=0
        for cname in $(get_all_coloros_names); do
            cfile="$MODULE_DIR/system/fonts/${cname}.ttf"
            dest="$MODULE_DIR/product/fonts/${cname}.ttf"
            if [ -f "$cfile" ] && [ ! -f "$dest" ]; then
                link_or_copy_font "$cfile" "$dest" 2>/dev/null && PROD_SYNCED=$((PROD_SYNCED + 1))
            fi
        done
        if [ "$PROD_SYNCED" -gt 0 ]; then
            log_message "INFO" "product/fonts/ 同步完成（$PROD_SYNCED 个文件）"
        fi
        set_perm_recursive "$MODULE_DIR/product/fonts" 0 0 0755 0644
    fi
fi

# ---------- 4. 确保配置目录存在 ----------
if [ ! -d "$MODULE_DIR/config" ]; then
    mkdir -p "$MODULE_DIR/config" 2>/dev/null || true
fi

if [ ! -f "$MODULE_DIR/config/active_font.conf" ]; then
    echo "default" > "$MODULE_DIR/config/active_font.conf" 2>/dev/null || true
    chmod 644 "$MODULE_DIR/config/active_font.conf" 2>/dev/null || true
fi

if [ ! -f "$MODULE_DIR/config/font_list.conf" ]; then
    echo "default" > "$MODULE_DIR/config/font_list.conf" 2>/dev/null || true
    chmod 644 "$MODULE_DIR/config/font_list.conf" 2>/dev/null || true
fi

# ---------- 5. 确保日志目录存在 ----------
if [ ! -d "$MODULE_DIR/logs" ]; then
    mkdir -p "$MODULE_DIR/logs" 2>/dev/null || true
fi

# ---------- 6. 同步预览字体到 webroot/fonts/ ----------
# 这样 WebUI 可以用相对路径加载字体，避免 file:// CORS 限制
if [ -f "$MODULE_DIR/common/font_manager.sh" ]; then
    . "$MODULE_DIR/common/font_manager.sh" 2>/dev/null || true
    sync_preview_fonts 2>/dev/null || true
    log_message "INFO" "预览字体已同步到 webroot/fonts/"
fi

log_message "INFO" "===== post-fs-data 完成 ====="
