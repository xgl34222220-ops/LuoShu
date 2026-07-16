#!/system/bin/sh
# 洛书 v13.4 Beta2 Hotfix6 - 字体管理核心（静态多字重调节 + 即时字重刷新）

# 关键：禁用严格错误终止，避免任何命令失败导致脚本退出
set +e

# ---------- 确定模块目录 ----------
# 注意：本文件被 post-fs-data.sh / customize.sh source，绝不能使用 exit
# 任何 exit 都会终止父脚本，导致 Magisk 显示刷写失败
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(cd "${0%/*}/.." && pwd)"
    elif [ -f "${0%/*}/../../module.prop" ]; then
        MODDIR="$(cd "${0%/*}/../.." && pwd)"
    elif [ -f "/data/adb/modules/LuoShu/module.prop" ]; then
        MODDIR="/data/adb/modules/LuoShu"
    else
        echo "警告：无法确定模块目录，使用默认值" >&2
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODULE_DIR/config"
BACKUP_DIR="$MODULE_DIR/backup"
SYSTEM_FONTS_DIR="$MODULE_DIR/system/fonts"
SYSTEM_ETC_DIR="$MODULE_DIR/system/etc"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
FONT_LIST_CONF="$CONFIG_DIR/font_list.conf"
LUOSHU_PUBLIC_DIR="/sdcard/LuoShu"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
USER_EMOJI_DIR="$LUOSHU_PUBLIC_DIR/emoji"
USER_REPORT_DIR="$LUOSHU_PUBLIC_DIR/reports"
USER_IMPORT_DIR="$LUOSHU_PUBLIC_DIR/import"
LEGACY_FONTS_DIR="/sdcard/Fonts"
ACTIVE_EMOJI_CONF="$CONFIG_DIR/active_emoji.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
EMOJI_REBOOT_REQUIRED="$CONFIG_DIR/emoji_reboot_required.conf"
FONT_WEIGHT_REBOOT_REQUIRED="$CONFIG_DIR/font_weight_reboot_required.conf"
SWITCH_TASK_FILE="$CONFIG_DIR/switch_task.conf"
EMOJI_TASK_FILE="$CONFIG_DIR/emoji_task.conf"
NATIVE_BIN="$MODULE_DIR/bin/luoshud"
FONT_WEIGHT_CONF="$CONFIG_DIR/font_weight.conf"
FONT_WEIGHT_ORIGINAL_CONF="$CONFIG_DIR/font_weight_original.conf"

# ---------- 加载共享工具函数 ----------
# detect_font_family 等基础函数统一由 util_functions.sh 提供
# 避免在多个文件中重复定义
if [ -f "$MODULE_DIR/common/util_functions.sh" ]; then
    . "$MODULE_DIR/common/util_functions.sh"
fi
if [ -f "$MODULE_DIR/common/font_check.sh" ]; then
    . "$MODULE_DIR/common/font_check.sh"
fi
if [ -f "$MODULE_DIR/common/font_import.sh" ]; then
    . "$MODULE_DIR/common/font_import.sh"
fi
if type ensure_public_storage >/dev/null 2>&1; then ensure_public_storage; fi

# 加载 ROM 适配层（copy_as_coloros / copy_as_hyperos / apply_font_by_rom 等）
# 与 customize.sh 共用同一份逻辑，避免两处各写一套导致后续改一处漏一处
if [ -f "$MODULE_DIR/common/rom_adapters.sh" ]; then
    . "$MODULE_DIR/common/rom_adapters.sh"
fi

# font_manager.sh 每次都是独立新进程被 WebUI/CLI 调用，不经过开机时的
# init_module()，所以这里必须自己重新探测一次 ROM，不能指望全局变量已被设置
if type check_coloros >/dev/null 2>&1; then check_coloros; fi
if type check_hyperos >/dev/null 2>&1; then check_hyperos; fi

# 降级保护：如果 util_functions.sh 未被加载（例如手动运行脚本），
# 提供最小化 detect_font_family 实现以保证基本功能可用
if ! type detect_font_family >/dev/null 2>&1; then
    detect_font_family() {
        result="${1%.*}"
        # 去掉常见字重后缀
        case "$result" in
            *"-Regular"|*"-Bold"|*"-Light"|*"-Medium"|*"-Thin"|*"-Black"|*"-Heavy")
                result="${result%-*}" ;;
            *"-regular"|*"-bold"|*"-light"|*"-medium"|*"-thin"|*"-black"|*"-heavy")
                result="${result%-*}" ;;
        esac
        echo "$result"
    }
fi

# ---------- 工具函数 ----------
# 注：detect_font_weight / capitalize_first / weight_sort_order /
# scan_family_weights / get_weight_file 已迁移到 util_functions.sh
# 统一维护（customize.sh 和 font_manager.sh 都会用到，避免两处维护两份）

# 格式化文件大小：17432 → 17.0 KB，17840000 → 17.0 MB
format_filesize() {
    bytes="$1"
    if [ -z "$bytes" ] || [ "$bytes" = "0" ]; then
        echo "未知"
        return
    fi
    if [ "$bytes" -lt 1024 ]; then
        echo "${bytes} B"
    elif [ "$bytes" -lt 1048576 ]; then
        kb=$((bytes / 1024))
        echo "${kb} KB"
    elif [ "$bytes" -lt 1073741824 ]; then
        mb_int=$((bytes / 1048576))
        mb_frac=$(((bytes % 1048576) / 104857))
        echo "${mb_int}.${mb_frac} MB"
    else
        gb_int=$((bytes / 1073741824))
        gb_frac=$(((bytes % 1073741824) / 107374182))
        echo "${gb_int}.${gb_frac} GB"
    fi
}

# 获取所有字体的统计信息
get_font_stats() {
    total_count=0
    total_bytes=0
    weight_dist=""
    for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$f" ] || continue
        name=$(basename "$f")
        case "$name" in SysFont*|SysSans*) continue ;; esac
        fam=$(detect_font_family "$name")
        w=$(detect_font_weight "$name")
        total_count=$((total_count + 1))
        # 用 ls -l + awk 获取大小（比 set -- 更可靠，不受文件名空格影响）
        fbytes=$(ls -l "$f" 2>/dev/null | awk '{print $5}')
        case "$fbytes" in ''|*[!0-9]*) fbytes=0 ;; esac
        total_bytes=$((total_bytes + fbytes))
        # 统计字重分布
        case ",$weight_dist," in *",$fam:$w,"*) ;; *) weight_dist="$weight_dist,$fam:$w" ;; esac
    done
    # 去掉 weight_dist 开头的逗号（纯 shell，不用 sed）
    case "$weight_dist" in ,*) weight_dist="${weight_dist#,}" ;; esac
    printf '{"totalFiles":%d,"totalSize":"%s","weightDist":"%s"}' "$total_count" "$(format_filesize "$total_bytes")" "$weight_dist"
}

# 扫描用户字体族（基础版，去重）
scan_user_families() {
    result=""
    [ -d "$USER_FONTS_DIR" ] || return
    for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$f" ] || continue
        fam=$(detect_font_family "$(basename "$f")")
        case "$fam" in SysFont*|SysSans*) continue ;; esac
        case " $result " in *" $fam "*) ;; *) result="$result $fam" ;; esac
    done
    case "$result" in " "*) result="${result# }" ;; esac
    while true; do case "$result" in " "*) result="${result# }" ;; *) break ;; esac; done
    echo "$result"
}

# WebUI 使用逐行字体族列表，完整保留文件名中的空格和括号。
scan_user_families_lines() {
    [ -d "$USER_FONTS_DIR" ] || return 0
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        _fam=$(detect_font_family "$(basename "$_f")")
        case "$_fam" in SysFont*|SysSans*|'') continue ;; esac
        printf '%s\n' "$_fam"
    done | awk '!seen[$0]++'
}

# 扫描字体族的字重变体、获取指定字重文件：scan_family_weights() /
# get_weight_file() 已迁移到 util_functions.sh 统一维护

get_current_font_id() {
    active=""
    [ -f "$ACTIVE_FONT_CONF" ] && active=$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '\r\n')
    [ -z "$active" ] && active="default"
    echo "$active"
}

# 降级保护：若 rom_adapters.sh 未能加载（理论上不该发生），提供最小化兜底，
# 避免 apply_font_by_rom / get_all_coloros_names 未定义导致脚本报错
if ! type get_all_coloros_names >/dev/null 2>&1; then
    get_all_coloros_names() { echo ""; }
fi
if ! type get_all_hyperos_files >/dev/null 2>&1; then
    get_all_hyperos_files() { echo ""; }
fi
if ! type apply_font_by_rom >/dev/null 2>&1; then
    apply_font_by_rom() {
        _src="$1"; _dest="$2"
        names="SysSans-Hant-Regular SysSans-Hans-Regular SysFont-Static-Regular SysFont-Myanmar SysFont-Hant-Regular SysFont-Hans-Regular SysFont-Regular SysSans-En-Regular"
        for _name in $names; do
            cp -f "$_src" "$_dest/${_name}.ttf" 2>/dev/null
        done
    }
fi

# ---------- 安全覆盖范围 / 重启保护 / Emoji ----------
get_managed_text_files() {
    if [ "$IS_COLOROS" = "true" ]; then
        for _n in $(get_all_coloros_names); do printf '%s.ttf\n' "$_n"; done
    elif [ "$IS_HYPEROS" = "true" ]; then
        get_all_hyperos_files
    else
        echo "Roboto-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf NotoSansCJK-Regular.ttc NotoSansSC-Regular.otf NotoSansTC-Regular.otf"
    fi
}

clear_managed_text_fonts() {
    for _f in $(get_managed_text_files); do
        rm -f "$SYSTEM_FONTS_DIR/$_f" "$MODULE_DIR/system_ext/fonts/$_f" "$MODULE_DIR/product/fonts/$_f" 2>/dev/null || true
    done
    rm -rf "$SYSTEM_FONTS_DIR/.luoshu-font-store" 2>/dev/null || true
    # Direct Bind 的 GMS 桥接源与当前正文字体绑定，切换或恢复默认时必须清理。
    rm -rf "$CONFIG_DIR/gms_bridge" "$CONFIG_DIR"/.gms_bridge.* 2>/dev/null || true
    rm -rf /data/fonts/luoshu 2>/dev/null || true
}

get_current_emoji_id() {
    _active="default"
    [ -f "$ACTIVE_EMOJI_CONF" ] && _active=$(head -n1 "$ACTIVE_EMOJI_CONF" 2>/dev/null | tr -d '\r\n')
    [ -z "$_active" ] && _active="default"
    echo "$_active"
}

find_emoji_file() {
    _id="$1"
    for _f in "$USER_EMOJI_DIR"/*.ttf "$USER_EMOJI_DIR"/*.otf "$USER_EMOJI_DIR"/*.ttc \
              "$USER_EMOJI_DIR"/*.TTF "$USER_EMOJI_DIR"/*.OTF "$USER_EMOJI_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        _base=$(basename "$_f")
        _name="${_base%.*}"
        [ "$_name" = "$_id" ] && { echo "$_f"; return 0; }
    done
    return 1
}

clear_managed_emoji_fonts() {
    rm -f "$SYSTEM_FONTS_DIR/NotoColorEmoji.ttf" "$SYSTEM_FONTS_DIR/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
    rm -rf "$SYSTEM_FONTS_DIR/.luoshu-emoji-store" 2>/dev/null || true
}

switch_emoji() {
    _id="$1"
    [ -z "$_id" ] && { echo "错误：未指定 Emoji 字体" >&2; return 1; }
    if [ -f "$EMOJI_REBOOT_REQUIRED" ]; then
        echo "错误：本次开机已更改 Emoji，请先重启手机后再切换" >&2
        return 3
    fi
    mkdir -p "$SYSTEM_FONTS_DIR" "$CONFIG_DIR" "$USER_EMOJI_DIR" 2>/dev/null || true
    clear_managed_emoji_fonts
    if [ "$_id" != "default" ]; then
        _src=$(find_emoji_file "$_id")
        [ -f "$_src" ] || { echo "错误：Emoji 字体 $_id 不存在" >&2; return 1; }
        if type font_validate >/dev/null 2>&1 && ! font_validate "$_src" emoji; then
            echo "错误：$FONT_CHECK_ERROR" >&2
            return 4
        fi
        mkdir -p "$SYSTEM_FONTS_DIR/.luoshu-emoji-store" 2>/dev/null || true
        _anchor="$SYSTEM_FONTS_DIR/.luoshu-emoji-store/current.font"
        cp -f "$_src" "$_anchor" 2>/dev/null || return 1
        chmod 644 "$_anchor" 2>/dev/null || true
        ln "$_anchor" "$SYSTEM_FONTS_DIR/NotoColorEmoji.ttf" 2>/dev/null || cp -f "$_anchor" "$SYSTEM_FONTS_DIR/NotoColorEmoji.ttf" 2>/dev/null || return 1
        if [ -e /system/fonts/NotoColorEmojiLegacy.ttf ]; then
            ln "$_anchor" "$SYSTEM_FONTS_DIR/NotoColorEmojiLegacy.ttf" 2>/dev/null || cp -f "$_anchor" "$SYSTEM_FONTS_DIR/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
        fi
        chmod 644 "$SYSTEM_FONTS_DIR"/NotoColorEmoji*.ttf 2>/dev/null || true
    fi
    echo "$_id" > "$ACTIVE_EMOJI_CONF"
    printf 'emoji=%s\ntime=%s\n' "$_id" "$(date +%s)" > "$EMOJI_REBOOT_REQUIRED"
    chmod 644 "$ACTIVE_EMOJI_CONF" "$EMOJI_REBOOT_REQUIRED" 2>/dev/null || true
    return 0
}

find_text_font_file() {
    _font_id="$1"
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        _fam=$(detect_font_family "$(basename "$_f")")
        case "$_fam" in SysFont*|SysSans*) continue ;; esac
        [ "$_fam" = "$_font_id" ] && { echo "$_f"; return 0; }
    done
    return 1
}

# ---------- 切换字体 ----------
switch_font() {
    SWITCH_LOCK="$MODULE_DIR/.font_switch.lock"
    if [ -e "$SWITCH_LOCK" ]; then
        old_pid=$(cat "$SWITCH_LOCK" 2>/dev/null)
        if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
            echo "错误：字体正在切换中，请稍候" >&2
            return 2
        fi
        rm -f "$SWITCH_LOCK" 2>/dev/null || true
    fi
    if [ -f "$TEXT_REBOOT_REQUIRED" ]; then
        echo "错误：本次开机已更改文字字体，请先重启手机后再切换" >&2
        return 3
    fi
    echo $$ > "$SWITCH_LOCK"
    trap 'rm -f "$SWITCH_LOCK" 2>/dev/null' EXIT

    font_id="$1"
    [ -z "$font_id" ] && { echo "错误：未指定字体" >&2; return 1; }
    mkdir -p "$CONFIG_DIR" 2>/dev/null || true
    if ! type luoshu_db_use_direct >/dev/null 2>&1 || ! luoshu_db_use_direct; then
        mkdir -p "$SYSTEM_FONTS_DIR" 2>/dev/null || true
    fi

    if [ -f "$ACTIVE_FONT_CONF" ]; then
        current_backup=$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '\r\n')
        if [ -n "$current_backup" ] && [ "$current_backup" != "default" ] && [ "$current_backup" != "$font_id" ]; then
            echo "$current_backup" > "$CONFIG_DIR/previous_font.conf"
        fi
    fi

    src_file=""
    if [ "$font_id" != "default" ]; then
        src_file=$(find_text_font_file "$font_id")
        if [ ! -f "$src_file" ]; then
            echo "错误：字体 $font_id 不存在于 $USER_FONTS_DIR" >&2
            return 1
        fi
        if type font_validate >/dev/null 2>&1 && ! font_validate "$src_file" text; then
            echo "错误：$FONT_CHECK_ERROR" >&2
            return 4
        fi
    fi

    # 只删除洛书管理的文字目标，Emoji、符号与 ROM fallback 永远保留。
    clear_managed_text_fonts
    if [ "$font_id" = "default" ]; then
        if [ -f "$MODULE_DIR/common/play_font_bridge" ]; then
            MODDIR="$MODULE_DIR" sh "$MODULE_DIR/common/play_font_bridge" restore >/dev/null 2>&1 || true
        fi
        echo "  [洛书] 已恢复 ROM 原始文字字体（Emoji 保持独立设置）"
    else
        apply_font_by_rom "$src_file" "$SYSTEM_FONTS_DIR" "quick" "$font_id" || {
            echo "错误：ROM 字体映射失败" >&2
            return 5
        }
        if [ "$IS_COLOROS" = "true" ] && { ! type luoshu_db_use_direct >/dev/null 2>&1 || ! luoshu_db_use_direct; }; then
            mkdir -p "$MODULE_DIR/system_ext/fonts" "$MODULE_DIR/product/fonts" 2>/dev/null || true
            for _n in $(get_all_coloros_names); do
                _src="$SYSTEM_FONTS_DIR/${_n}.ttf"
                [ -f "$_src" ] || continue
                [ -e "/system_ext/fonts/${_n}.ttf" ] && link_or_copy_font "$_src" "$MODULE_DIR/system_ext/fonts/${_n}.ttf" 2>/dev/null || true
                [ -e "/product/fonts/${_n}.ttf" ] && link_or_copy_font "$_src" "$MODULE_DIR/product/fonts/${_n}.ttf" 2>/dev/null || true
            done
        fi
    fi

    echo "$font_id" > "$ACTIVE_FONT_CONF"
    chmod 644 "$ACTIVE_FONT_CONF" "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true

    # Direct Bind 的文字负载全部保存在 direct_map/config；清掉旧版本遗留的
    # 空分区目录，避免 Hybrid Mount、Mountify 或 meta-overlayfs 再次 staging。
    if type luoshu_db_use_direct >/dev/null 2>&1 && luoshu_db_use_direct; then
        rm -rf "$MODULE_DIR/system_ext" "$MODULE_DIR/product" 2>/dev/null || true
        rmdir "$SYSTEM_FONTS_DIR" "$MODULE_DIR/system" 2>/dev/null || true
    fi

    if [ -n "$font_id" ] && [ "$font_id" != "default" ]; then
        recent_file="$CONFIG_DIR/recent_fonts.conf"
        recent_list=""
        recent_count=0
        if [ -f "$recent_file" ]; then
            while IFS= read -r line; do
                [ -z "$line" ] && continue
                [ "$line" = "$font_id" ] && continue
                if [ "$recent_count" -lt 9 ]; then
                    recent_list="$recent_list$line\n"
                    recent_count=$((recent_count + 1))
                fi
            done < "$recent_file"
        fi
        printf '%s\n%b' "$font_id" "$recent_list" > "$recent_file" 2>/dev/null || true
    fi

    # 不热重启 SystemUI、不立即改写 /data/fonts、不在当前进程做 GMS bind。
    # 统一在完整重启后由 post-fs-data/service 安全同步，避免第二次热切换死机。
    printf 'font=%s\ntime=%s\n' "$font_id" "$(date +%s)" > "$TEXT_REBOOT_REQUIRED"
    echo "$font_id" > "$CONFIG_DIR/last_switch_result.conf"
    date '+%Y-%m-%d %H:%M:%S' > "$CONFIG_DIR/last_switch_time.conf" 2>/dev/null || true
    chmod 644 "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true
    return 0
}

# ---------- WebUI 预览字体同步 ----------
# 将用户字体文件同步到 webroot/fonts/ 目录，供 WebUI 预览用
# 使用缓存检查，只在文件变化时才同步，避免每次请求都重建
sync_preview_fonts() {
    webroot="${MODULE_DIR}/webroot"
    preview_dir="${webroot}/fonts"
    cache_file="${preview_dir}/.sync_cache"
    
    mkdir -p "$preview_dir" 2>/dev/null
    
    # 检查是否需要同步（用户字体目录有更新）
    need_sync="false"
    latest_mtime=0
    
    # 获取用户字体目录最新修改时间
    for src in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$src" ] || continue
        mtime=$(stat -c %Y "$src" 2>/dev/null || echo 0)
        [ "$mtime" -gt "$latest_mtime" ] && latest_mtime="$mtime"
    done
    
    # 没有字体文件，清理预览目录
    if [ "$latest_mtime" -eq 0 ]; then
        for f in "$preview_dir"/*.ttf "$preview_dir"/*.otf "$preview_dir"/*.ttc "$preview_dir"/*.TTF "$preview_dir"/*.OTF "$preview_dir"/*.TTC; do
            [ -f "$f" ] && rm -f "$f" 2>/dev/null
        done
        rm -f "$cache_file" 2>/dev/null
        return 0
    fi
    
    # 检查缓存
    if [ -f "$cache_file" ]; then
        cached_mtime=$(cat "$cache_file" 2>/dev/null || echo 0)
        # 如果缓存时间 >= 最新文件时间，跳过同步
        if [ "$cached_mtime" -ge "$latest_mtime" ]; then
            return 0
        fi
    fi
    
    # 需要同步：清除旧文件，创建新链接
    for f in "$preview_dir"/*.ttf "$preview_dir"/*.otf "$preview_dir"/*.ttc "$preview_dir"/*.TTF "$preview_dir"/*.OTF "$preview_dir"/*.TTC; do
        [ -f "$f" ] && rm -f "$f" 2>/dev/null
    done
    
    for src in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$src" ] || continue
        name=$(basename "$src")
        case "$name" in SysFont*|SysSans*) continue ;; esac
        ln -f "$src" "$preview_dir/$name" 2>/dev/null || cp -f "$src" "$preview_dir/$name" 2>/dev/null
        chmod 644 "$preview_dir/$name" 2>/dev/null
    done
    
    # 写入缓存时间
    echo "$latest_mtime" > "$cache_file" 2>/dev/null
}


sync_emoji_preview_fonts() {
    _preview_dir="$MODULE_DIR/webroot/emoji"
    mkdir -p "$_preview_dir" "$USER_EMOJI_DIR" 2>/dev/null || true
    rm -f "$_preview_dir"/*.ttf "$_preview_dir"/*.otf "$_preview_dir"/*.ttc 2>/dev/null || true
    for _src in "$USER_EMOJI_DIR"/*.ttf "$USER_EMOJI_DIR"/*.otf "$USER_EMOJI_DIR"/*.ttc \
                "$USER_EMOJI_DIR"/*.TTF "$USER_EMOJI_DIR"/*.OTF "$USER_EMOJI_DIR"/*.TTC; do
        [ -f "$_src" ] || continue
        _name=$(basename "$_src")
        ln -f "$_src" "$_preview_dir/$_name" 2>/dev/null || cp -f "$_src" "$_preview_dir/$_name" 2>/dev/null || true
        chmod 644 "$_preview_dir/$_name" 2>/dev/null || true
    done
}

write_emoji_task() {
    _task="$1"; _state="$2"; _emoji="$3"; _message="$4"; _started="$5"; _finished="$6"
    _tmp="${EMOJI_TASK_FILE}.tmp.$$"
    {
        printf 'task=%s\n' "$_task"
        printf 'state=%s\n' "$_state"
        printf 'emoji=%s\n' "$_emoji"
        printf 'message=%s\n' "$_message"
        printf 'started=%s\n' "$_started"
        printf 'finished=%s\n' "$_finished"
    } > "$_tmp"
    mv -f "$_tmp" "$EMOJI_TASK_FILE" 2>/dev/null || true
    chmod 644 "$EMOJI_TASK_FILE" 2>/dev/null || true
}

# ---------- 异步切换任务状态 ----------
json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

write_switch_task() {
    task_id="$1"
    task_state="$2"
    task_font="$3"
    task_message="$4"
    task_started="$5"
    task_finished="$6"
    tmp_file="${SWITCH_TASK_FILE}.tmp.$$"
    {
        printf 'task=%s\n' "$task_id"
        printf 'state=%s\n' "$task_state"
        printf 'font=%s\n' "$task_font"
        printf 'message=%s\n' "$task_message"
        printf 'started=%s\n' "$task_started"
        printf 'finished=%s\n' "$task_finished"
    } > "$tmp_file" 2>/dev/null
    mv -f "$tmp_file" "$SWITCH_TASK_FILE" 2>/dev/null || true
    chmod 644 "$SWITCH_TASK_FILE" 2>/dev/null || true
}

read_task_value() {
    key="$1"
    [ -f "$SWITCH_TASK_FILE" ] || return 0
    sed -n "s/^${key}=//p" "$SWITCH_TASK_FILE" 2>/dev/null | head -n 1
}

# ---------- 用户反馈（系统通知为尽力而为，WebUI 弹窗为可靠兜底） ----------
notify_user() {
    _title="$1"; _message="$2"; _tag="${3:-luoshu}"
    if command -v cmd >/dev/null 2>&1; then
        cmd notification post -S bigtext -t "$_title" "$_tag" "$_message" >/dev/null 2>&1 && return 0
        cmd notification post -t "$_title" "$_tag" "$_message" >/dev/null 2>&1 && return 0
    fi
    return 1
}

# ---------- Android 全局字重调节 ----------
# Android 12+ 使用 secure.font_weight_adjustment 调整系统字体粗细。
# 为保证 ColorOS / HyperOS 稳定，洛书只开放 AOSP 常用安全范围 -100..300，
# 对应名义字重 300..700。设置写入后立即请求字体服务刷新；已打开应用可能需重新打开。
font_weight_normalize_int() {
    _v="$1"
    case "$_v" in
        ''|null|undefined|2147483647|-2147483648|*[!0-9-]*) echo 0 ;;
        *) echo "$_v" ;;
    esac
}

font_weight_get_system() {
    if command -v settings >/dev/null 2>&1; then
        _fw=$(settings get secure font_weight_adjustment 2>/dev/null)
        font_weight_normalize_int "$_fw"
    else
        echo 0
    fi
}

font_weight_get_saved() {
    if [ -f "$FONT_WEIGHT_CONF" ]; then
        _fw=$(sed -n 's/^adjustment=//p' "$FONT_WEIGHT_CONF" 2>/dev/null | head -n1)
    else
        _fw=$(font_weight_get_system)
    fi
    font_weight_normalize_int "$_fw"
}

font_weight_get_desired() {
    if [ -f "$FONT_WEIGHT_CONF" ]; then
        _fw=$(sed -n 's/^weight=//p' "$FONT_WEIGHT_CONF" 2>/dev/null | head -n1)
    else
        _fw=$((400 + $(font_weight_get_system)))
    fi
    case "$_fw" in ''|*[!0-9]*) _fw=400 ;; esac
    [ "$_fw" -lt 300 ] 2>/dev/null && _fw=300
    [ "$_fw" -gt 700 ] 2>/dev/null && _fw=700
    echo "$_fw"
}

font_weight_backup_original() {
    [ -s "$FONT_WEIGHT_ORIGINAL_CONF" ] && return 0
    mkdir -p "$CONFIG_DIR" 2>/dev/null || true
    _original=$(font_weight_get_system)
    printf 'adjustment=%s\n' "$_original" > "$FONT_WEIGHT_ORIGINAL_CONF" 2>/dev/null || return 1
    chmod 0644 "$FONT_WEIGHT_ORIGINAL_CONF" 2>/dev/null || true
}

font_weight_set() {
    _weight="$1"
    case "$_weight" in ''|*[!0-9]*) return 2 ;; esac
    [ "$_weight" -ge 300 ] 2>/dev/null || return 2
    [ "$_weight" -le 700 ] 2>/dev/null || return 2
    command -v settings >/dev/null 2>&1 || return 5
    _adjustment=$((_weight - 400))
    font_weight_backup_original || return 1
    settings put secure font_weight_adjustment "$_adjustment" >/dev/null 2>&1 || return 4
    mkdir -p "$CONFIG_DIR" 2>/dev/null || true
    {
        printf 'weight=%s\n' "$_weight"
        printf 'adjustment=%s\n' "$_adjustment"
        printf 'time=%s\n' "$(date +%s)"
    } > "$FONT_WEIGHT_CONF" 2>/dev/null || return 1
    chmod 0644 "$FONT_WEIGHT_CONF" 2>/dev/null || true
    # 字重设置本身可运行时刷新，不再标记为“必须完整重启”。
    rm -f "$FONT_WEIGHT_REBOOT_REQUIRED" 2>/dev/null || true
    cmd font system --update >/dev/null 2>&1 || true
    am broadcast -a android.intent.action.CONFIGURATION_CHANGED >/dev/null 2>&1 || true
    return 0
}

font_weight_reset() {
    command -v settings >/dev/null 2>&1 || return 5
    _restore=0
    [ -f "$FONT_WEIGHT_ORIGINAL_CONF" ] && _restore=$(sed -n 's/^adjustment=//p' "$FONT_WEIGHT_ORIGINAL_CONF" 2>/dev/null | head -n1)
    _restore=$(font_weight_normalize_int "$_restore")
    settings put secure font_weight_adjustment "$_restore" >/dev/null 2>&1 || return 4
    rm -f "$FONT_WEIGHT_CONF" 2>/dev/null || true
    rm -f "$FONT_WEIGHT_REBOOT_REQUIRED" 2>/dev/null || true
    cmd font system --update >/dev/null 2>&1 || true
    am broadcast -a android.intent.action.CONFIGURATION_CHANGED >/dev/null 2>&1 || true
    return 0
}

font_weight_status_json() {
    _supported=false
    command -v settings >/dev/null 2>&1 && _supported=true
    _system=$(font_weight_get_system)
    _saved=$(font_weight_get_saved)
    _desired=$(font_weight_get_desired)
    _original=0
    [ -f "$FONT_WEIGHT_ORIGINAL_CONF" ] && _original=$(sed -n 's/^adjustment=//p' "$FONT_WEIGHT_ORIGINAL_CONF" 2>/dev/null | head -n1)
    _original=$(font_weight_normalize_int "$_original")
    printf '{"status":"ok","data":{"supported":%s,"weight":%s,"adjustment":%s,"systemAdjustment":%s,"originalAdjustment":%s,"min":300,"max":700,"step":10}}\n' \
        "$_supported" "$_desired" "$_saved" "$_system" "$_original"
}

# ---------- WebUI 接口 ----------
handle_action() {
    action="$1"
    param="$2"
    current=$(get_current_font_id 2>/dev/null)

    # 同步预览字体到 webroot/fonts/（供 WebUI 用相对路径加载，避免 file:// CORS 限制）
    sync_preview_fonts 2>/dev/null || true
    sync_emoji_preview_fonts 2>/dev/null || true

    # WebUI 列表统一走受控 Shell 扫描，避免旧原生工具执行过时路径或清理逻辑。

    case "$action" in
        list)
            # WebUI 列表缓存：字体目录及当前字体未变化时直接返回 JSON。
            # 避免每次打开页面重复执行多轮文件扫描与字重归类。
            list_cache_json="$CONFIG_DIR/webui_font_list.json"
            list_cache_key="$CONFIG_DIR/webui_font_list.key"
            dir_stamp=$(stat -c '%Y:%s' "$USER_FONTS_DIR" 2>/dev/null || echo '0:0')
            current_key="v13426|${current}|${dir_stamp}"
            cached_key=$(cat "$list_cache_key" 2>/dev/null)
            if [ "$param" != "refresh" ] && [ "$cached_key" = "$current_key" ] && [ -s "$list_cache_json" ] && grep -q '"status":"ok"' "$list_cache_json" 2>/dev/null; then
                cat "$list_cache_json"
                return 0
            fi
            fam_list_file="$CONFIG_DIR/.webui_families.$$"
            scan_user_families_lines > "$fam_list_file" 2>/dev/null || : > "$fam_list_file"
            {
            first="true"
            total_bytes=0
            font_count=$(grep -c . "$fam_list_file" 2>/dev/null)
            [ -n "$font_count" ] || font_count=0

            while IFS= read -r fam; do
                [ -n "$fam" ] || continue
                wfile_tmp=$(get_weight_file "$fam" "regular")
                [ -z "$wfile_tmp" ] && wfile_tmp=$(get_weight_file "$fam" "bold")
                if [ -f "$wfile_tmp" ]; then
                    fb=$(wc -c < "$wfile_tmp" 2>/dev/null | tr -d '[:space:]')
                    case "$fb" in ''|*[!0-9]*) fb=0 ;; esac
                    total_bytes=$((total_bytes + fb))
                fi
            done < "$fam_list_file"

            native_available=false; [ -x "$NATIVE_BIN" ] && native_available=true
            printf '{"status":"ok","data":{"current":"%s","scanner":{"primary":"shell","nativeAvailable":%s},"stats":{"count":%d,"totalSize":"%s"},"fonts":[' "$(json_escape "$current")" "$native_available" "$font_count" "$(format_filesize "$total_bytes")"

            while IFS= read -r fam; do
                [ -n "$fam" ] || continue
                [ "$first" = "true" ] || printf ','
                fw=$(scan_family_weights "$fam")
                weights_json=""
                variants_json=""
                weight_count=0
                _old_ifs="$IFS"; IFS=','
                for w in $fw; do
                    [ -n "$w" ] || continue
                    [ -n "$weights_json" ] && weights_json="$weights_json,"
                    weights_json="$weights_json\"$(json_escape "$w")\""
                    weight_count=$((weight_count + 1))
                    _variant_file=$(get_weight_file "$fam" "$w")
                    if [ -f "$_variant_file" ]; then
                        _variant_name=$(basename "$_variant_file")
                        [ -n "$variants_json" ] && variants_json="$variants_json,"
                        variants_json="$variants_json\"$(json_escape "$w")\":\"./fonts/$(json_escape "$_variant_name")\""
                    fi
                done
                IFS="$_old_ifs"
                wfile=$(get_weight_file "$fam" "regular")
                [ -z "$wfile" ] && wfile=$(get_weight_file "$fam" "bold")
                [ -z "$wfile" ] && wfile=$(get_weight_file "$fam" "medium")
                if [ ! -f "$wfile" ]; then
                    while IFS= read -r _candidate; do
                        [ -f "$_candidate" ] || continue
                        [ "$(detect_font_family "$(basename "$_candidate")")" = "$fam" ] && { wfile="$_candidate"; break; }
                    done <<EOF_FONTS
$(find "$USER_FONTS_DIR" -maxdepth 1 -type f 2>/dev/null)
EOF_FONTS
                fi
                fbytes=$(wc -c < "$wfile" 2>/dev/null | tr -d '[:space:]')
                case "$fbytes" in ''|*[!0-9]*) fbytes=0 ;; esac
                if type font_detect_format >/dev/null 2>&1; then
                    fformat=$(font_detect_format "$wfile" 2>/dev/null)
                else
                    fformat="${wfile##*.}"
                    case "$fformat" in [Tt][Tt][Ff]) fformat="TTF" ;; [Oo][Tt][Ff]) fformat="OTF" ;; [Tt][Tt][Cc]) fformat="TTC" ;; *) fformat="UNKNOWN" ;; esac
                fi
                fvalid=true; fwarning=""; ferror=""
                if type font_validate >/dev/null 2>&1; then
                    if font_validate "$wfile" text 2>/dev/null; then
                        fwarning="$FONT_CHECK_WARNING"
                    else
                        fvalid=false; ferror="$FONT_CHECK_ERROR"
                    fi
                fi
                fvariable=false
                if type is_variable_font >/dev/null 2>&1 && is_variable_font "$wfile"; then fvariable=true; fi
                family_type=single
                [ "$weight_count" -ge 2 ] && family_type=static-family
                [ "$fvariable" = true ] && family_type=variable
                ftime=$(stat -c '%y' "$wfile" 2>/dev/null | cut -c1-10)
                fname=$(basename "$wfile" 2>/dev/null)
                printf '{"id":"%s","name":"%s","weights":[%s],"variants":{%s},"familyType":"%s","file":"./fonts/%s","size":"%s","bytes":%s,"format":"%s","valid":%s,"warning":"%s","error":"%s","variable":%s,"date":"%s"}' \
                    "$(json_escape "$fam")" "$(json_escape "$fam")" "$weights_json" "$variants_json" "$(json_escape "$family_type")" "$(json_escape "$fname")" "$(format_filesize "$fbytes")" "$fbytes" "$(json_escape "$fformat")" "$fvalid" "$(json_escape "$fwarning")" "$(json_escape "$ferror")" "$fvariable" "$(json_escape "$ftime")"
                first="false"
            done < "$fam_list_file"
            printf ']}}\n'
            } | tee "$list_cache_json"
            rm -f "$fam_list_file" 2>/dev/null || true
            echo "$current_key" > "$list_cache_key" 2>/dev/null || true
            ;;
        import_list)
            if type import_list_json >/dev/null 2>&1; then
                import_list_json
            else
                printf '{"status":"error","message":"ZIP 导入组件不可用"}\n'
            fi
            ;;
        import_zip)
            if [ -z "$param" ]; then
                printf '{"status":"error","message":"未指定 ZIP 字体包"}\n'
            elif type import_zip_package >/dev/null 2>&1; then
                import_zip_package "$param"
            else
                printf '{"status":"error","message":"ZIP 导入组件不可用"}\n'
            fi
            ;;
        font_weight_status)
            font_weight_status_json
            ;;
        font_weight_set)
            if font_weight_set "$param"; then
                _adj=$(font_weight_get_saved)
                printf '{"status":"ok","data":{"weight":%s,"adjustment":%s,"message":"字体粗细已即时写入；未更新的应用请重新打开，必要时仅刷新系统界面"}}\n' "$(font_weight_get_desired)" "$_adj"
            else
                _rc=$?
                case "$_rc" in
                    2) _msg="字重超出安全范围（仅支持 300–700）" ;;
                    5) _msg="当前系统不支持字体粗细调节" ;;
                    *) _msg="无法写入系统字体粗细设置" ;;
                esac
                printf '{"status":"error","message":"%s"}\n' "$(json_escape "$_msg")"
            fi
            ;;
        font_weight_reset)
            if font_weight_reset; then
                printf '{"status":"ok","data":{"weight":%s,"adjustment":%s,"message":"已恢复系统原始字体粗细"}}\n' "$(font_weight_get_desired)" "$(font_weight_get_system)"
            else
                printf '{"status":"error","message":"无法恢复系统字体粗细"}\n'
            fi
            ;;
        native_status)
            _legacy_count=0
            for _nf in "$LEGACY_FONTS_DIR"/*.ttf "$LEGACY_FONTS_DIR"/*.otf "$LEGACY_FONTS_DIR"/*.ttc \
                       "$LEGACY_FONTS_DIR"/*.TTF "$LEGACY_FONTS_DIR"/*.OTF "$LEGACY_FONTS_DIR"/*.TTC; do
                [ -f "$_nf" ] && _legacy_count=$((_legacy_count + 1))
            done
            if [ -x "$NATIVE_BIN" ]; then
                printf '{"status":"ok","data":{"available":true,"arch":"arm64-v8a","legacyFonts":%d,"mode":"diagnostic-fallback"}}\n' "$_legacy_count"
            else
                printf '{"status":"ok","data":{"available":false,"arch":"","legacyFonts":%d,"mode":"shell-only"}}\n' "$_legacy_count"
            fi
            ;;
        native_scan)
            if [ ! -x "$NATIVE_BIN" ]; then
                printf '{"status":"error","message":"原生扫描器不可用"}\n'
            elif [ ! -d "$LEGACY_FONTS_DIR" ]; then
                printf '{"status":"error","message":"原生扫描器仅兼容旧目录 /sdcard/Fonts"}\n'
            else
                _native_out=$("$NATIVE_BIN" scan 2>/dev/null)
                if [ -n "$_native_out" ] && printf '%s' "$_native_out" | grep -q '"status":"ok"'; then
                    printf '%s\n' "$_native_out"
                else
                    printf '{"status":"error","message":"原生扫描失败，继续使用 Shell 扫描"}\n'
                fi
            fi
            ;;
        current)
            printf '{"status":"ok","data":{"current":"%s"}}\n' "$current"
            ;;
        switch)
            if [ -z "$param" ]; then
                printf '{"status":"error","message":"未指定字体"}\n'
            elif switch_font "$param" 2>&1; then
                printf '{"status":"ok","data":{"font":"%s","message":"已切换，重启手机后生效"}}\n' "$param"
            else
                printf '{"status":"error","message":"切换失败"}\n'
            fi
            ;;
        switch_async)
            # 创建可查询的后台任务。WebUI 只在 state=success 后显示“应用完成”。
            if [ -z "$param" ]; then
                printf '{"status":"error","message":"未指定字体"}\n'
            elif [ -f "$TEXT_REBOOT_REQUIRED" ]; then
                printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'
            else
                if [ -e "$MODULE_DIR/.font_switch.lock" ]; then
                    lock_pid=$(cat "$MODULE_DIR/.font_switch.lock" 2>/dev/null)
                    if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
                        printf '{"status":"error","message":"字体正在切换中，请稍候"}\n'
                        return 0
                    fi
                    rm -f "$MODULE_DIR/.font_switch.lock" 2>/dev/null || true
                fi
                mkdir -p "$MODULE_DIR/logs" "$CONFIG_DIR"
                task_id="$(date +%s)-$$"
                task_started=$(date +%s)
                write_switch_task "$task_id" "running" "$param" "正在应用字体" "$task_started" ""
                (
                    echo "[$(date '+%Y-%m-%d %H:%M:%S')] async switch start: $param task=$task_id" >> "$MODULE_DIR/logs/fontswitch.log" 2>/dev/null
                    if switch_font "$param" >> "$MODULE_DIR/logs/fontswitch.log" 2>&1; then
                        task_finished=$(date +%s)
                        write_switch_task "$task_id" "success" "$param" "字体已准备，必须重启手机后全局生效" "$task_started" "$task_finished"
                        notify_user "洛书" "文字字体已准备：$param。请完整重启手机。" "luoshu-text" || true
                        echo "[$(date '+%Y-%m-%d %H:%M:%S')] async switch success: $param task=$task_id" >> "$MODULE_DIR/logs/fontswitch.log" 2>/dev/null
                    else
                        task_rc=$?
                        task_finished=$(date +%s)
                        write_switch_task "$task_id" "failed" "$param" "切换失败（代码 $task_rc）" "$task_started" "$task_finished"
                        echo "[$(date '+%Y-%m-%d %H:%M:%S')] async switch failed: $param rc=$task_rc task=$task_id" >> "$MODULE_DIR/logs/fontswitch.log" 2>/dev/null
                    fi
                ) &
                printf '{"status":"ok","data":{"font":"%s","task":"%s","message":"任务已开始"}}\n' "$(json_escape "$param")" "$(json_escape "$task_id")"
            fi
            ;;
        switch_status)
            if [ ! -s "$SWITCH_TASK_FILE" ]; then
                printf '{"status":"error","message":"暂无切换任务"}\n'
            else
                saved_task=$(read_task_value task)
                if [ -n "$param" ] && [ "$param" != "$saved_task" ]; then
                    printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'
                else
                    task_state=$(read_task_value state)
                    task_font=$(read_task_value font)
                    task_message=$(read_task_value message)
                    task_started=$(read_task_value started)
                    task_finished=$(read_task_value finished)
                    printf '{"status":"ok","data":{"task":"%s","state":"%s","font":"%s","message":"%s","started":%s,"finished":%s}}\n' \
                        "$(json_escape "$saved_task")" "$(json_escape "$task_state")" "$(json_escape "$task_font")" "$(json_escape "$task_message")" \
                        "${task_started:-0}" "${task_finished:-0}"
                fi
            fi
            ;;
        restart_ui)
            pkill -f com.android.systemui 2>/dev/null || pkill -f systemui 2>/dev/null || true
            cmd activity write-settings 2>/dev/null || true
            printf '{"status":"ok","data":{"message":"系统界面已重启"}}\n'
            ;;
        refresh)
            cmd font system --update 2>/dev/null || true
            printf '{"status":"ok","data":{"message":"字体缓存已刷新"}}\n'
            ;;
        recent)
            recent_file="$CONFIG_DIR/recent_fonts.conf"
            recent_json=""
            if [ -f "$recent_file" ]; then
                while IFS= read -r line; do
                    line=$(printf '%s' "$line" | tr -d '\r\n')
                    [ -z "$line" ] && continue
                    [ -n "$recent_json" ] && recent_json="$recent_json,"
                    recent_json="$recent_json\"$(json_escape "$line")\""
                done < "$recent_file"
            fi
            printf '{"status":"ok","data":{"recent":[%s]}}\n' "$recent_json"
            ;;
        report)
            _report_font=""
            [ "$current" = "default" ] || _report_font=$(find_text_font_file "$current")
            _report_path=$(sh "$MODULE_DIR/common/font_report.sh" "$_report_font" 2>/dev/null | tail -n1)
            if [ -n "$_report_path" ] && [ -f "$_report_path" ]; then
                printf '{"status":"ok","data":{"path":"%s","message":"诊断报告已生成"}}\n' "$(json_escape "$_report_path")"
            else
                printf '{"status":"error","message":"诊断报告生成失败"}\n'
            fi
            ;;
        validate)
            _file=$(find_text_font_file "$param")
            if [ -f "$_file" ] && type font_check_json >/dev/null 2>&1; then
                _check=$(font_check_json "$_file" text 2>/dev/null | tr -d '\n')
                printf '{"status":"ok","data":%s}\n' "$_check"
            else
                printf '{"status":"error","message":"未找到字体或检测器不可用"}\n'
            fi
            ;;
        reboot_required)
            _text=false; _emoji=false; _weight=false
            [ -f "$TEXT_REBOOT_REQUIRED" ] && _text=true
            [ -f "$EMOJI_REBOOT_REQUIRED" ] && _emoji=true
            # 清理旧版本遗留标记；字重调整不再要求完整重启。
            rm -f "$FONT_WEIGHT_REBOOT_REQUIRED" 2>/dev/null || true
            _required=false
            if [ "$_text" = true ] || [ "$_emoji" = true ]; then _required=true; fi
            printf '{"status":"ok","data":{"required":%s,"text":%s,"emoji":%s,"weight":%s}}\n' "$_required" "$_text" "$_emoji" "$_weight"
            ;;
        reboot_device)
            printf '{"status":"ok","data":{"message":"正在重启手机"}}\n'
            (sleep 1; svc power reboot 2>/dev/null || reboot 2>/dev/null) &
            ;;
        emoji_list)
            _current=$(get_current_emoji_id)
            _first=true
            printf '{"status":"ok","data":{"current":"%s","path":"%s","emojis":[' "$(json_escape "$_current")" "$(json_escape "$USER_EMOJI_DIR")"
            for _f in "$USER_EMOJI_DIR"/*.ttf "$USER_EMOJI_DIR"/*.otf "$USER_EMOJI_DIR"/*.ttc \
                      "$USER_EMOJI_DIR"/*.TTF "$USER_EMOJI_DIR"/*.OTF "$USER_EMOJI_DIR"/*.TTC; do
                [ -f "$_f" ] || continue
                _base=$(basename "$_f")
                _id="${_base%.*}"
                _bytes=$(wc -c < "$_f" 2>/dev/null | tr -d '[:space:]')
                case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
                _fmt=$(font_detect_format "$_f" 2>/dev/null || echo UNKNOWN)
                _valid=false; _color=false; _warning=""; _error=""
                if font_validate "$_f" emoji 2>/dev/null; then
                    _valid=true; _color="$FONT_CHECK_COLOR"; _warning="$FONT_CHECK_WARNING"
                else
                    _error="$FONT_CHECK_ERROR"
                fi
                [ "$_first" = true ] || printf ','
                printf '{"id":"%s","name":"%s","file":"./emoji/%s","size":"%s","bytes":%s,"format":"%s","valid":%s,"color":%s,"warning":"%s","error":"%s"}' \
                    "$(json_escape "$_id")" "$(json_escape "$_id")" "$(json_escape "$_base")" "$(format_filesize "$_bytes")" "$_bytes" "$(json_escape "$_fmt")" "$_valid" "$_color" "$(json_escape "$_warning")" "$(json_escape "$_error")"
                _first=false
            done
            printf ']}}\n'
            ;;
        emoji_switch_async)
            if [ -z "$param" ]; then
                printf '{"status":"error","message":"未指定 Emoji 字体"}\n'
            elif [ -f "$EMOJI_REBOOT_REQUIRED" ]; then
                printf '{"status":"error","message":"本次开机已更改 Emoji，请先重启手机"}\n'
            else
                _task="emoji-$(date +%s)-$$"; _started=$(date +%s)
                write_emoji_task "$_task" running "$param" "正在应用 Emoji" "$_started" ""
                (
                    if switch_emoji "$param" >> "$MODULE_DIR/logs/fontswitch.log" 2>&1; then
                        write_emoji_task "$_task" success "$param" "Emoji 已准备，重启后生效" "$_started" "$(date +%s)"
                        notify_user "洛书" "Emoji 已准备：$param。请完整重启手机。" "luoshu-emoji" || true
                    else
                        _rc=$?
                        write_emoji_task "$_task" failed "$param" "Emoji 应用失败（代码 $_rc）" "$_started" "$(date +%s)"
                    fi
                ) &
                printf '{"status":"ok","data":{"task":"%s","emoji":"%s"}}\n' "$(json_escape "$_task")" "$(json_escape "$param")"
            fi
            ;;
        emoji_status)
            if [ ! -s "$EMOJI_TASK_FILE" ]; then
                printf '{"status":"error","message":"暂无 Emoji 任务"}\n'
            else
                _saved=$(sed -n 's/^task=//p' "$EMOJI_TASK_FILE" | head -n1)
                if [ -n "$param" ] && [ "$param" != "$_saved" ]; then
                    printf '{"status":"error","message":"Emoji 任务不存在"}\n'
                else
                    _state=$(sed -n 's/^state=//p' "$EMOJI_TASK_FILE" | head -n1)
                    _emoji=$(sed -n 's/^emoji=//p' "$EMOJI_TASK_FILE" | head -n1)
                    _msg=$(sed -n 's/^message=//p' "$EMOJI_TASK_FILE" | head -n1)
                    printf '{"status":"ok","data":{"task":"%s","state":"%s","emoji":"%s","message":"%s"}}\n' \
                        "$(json_escape "$_saved")" "$(json_escape "$_state")" "$(json_escape "$_emoji")" "$(json_escape "$_msg")"
                fi
            fi
            ;;
        delete)
            if [ -z "$param" ]; then
                printf '{"status":"error","message":"未指定字体"}\n'
            elif [ "$param" = "$current" ] && [ -f "$TEXT_REBOOT_REQUIRED" ]; then
                printf '{"status":"error","message":"当前字体已等待重启，请先重启后再删除"}\n'
            else
                if [ "$param" = "$current" ]; then
                    if ! switch_font "default" >/dev/null 2>&1; then
                        printf '{"status":"error","message":"无法先恢复系统默认字体"}\n'
                        return 0
                    fi
                    current="default"
                fi
                del_count=0
                for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
                    [ -f "$f" ] || continue
                    tmp_name=$(basename "$f")
                    tmp_fam=$(detect_font_family "$tmp_name")
                    if [ "$tmp_fam" = "$param" ]; then
                        rm -f "$f" 2>/dev/null && del_count=$((del_count + 1))
                    fi
                done
                if [ "$del_count" -gt 0 ]; then
                    rm -f "$CONFIG_DIR/webui_font_list.key" "$CONFIG_DIR/webui_font_list.json" 2>/dev/null || true
                    printf '{"status":"ok","data":{"deleted":%d,"message":"已删除 %d 个文件"}}\n' "$del_count" "$del_count"
                else
                    printf '{"status":"error","message":"未找到字体文件"}\n'
                fi
            fi
            ;;
        *)
            printf '{"status":"error","message":"未知操作"}\n'
            ;;
    esac
    return 0
}

# ---------- 调试日志 ----------
LOGFILE="$MODULE_DIR/logs/fontswitch.log"
log_debug() {
    # 仅在 LOG_LEVEL=DEBUG 时记录调试日志
    if [ "${LOG_LEVEL:-INFO}" = "DEBUG" ] && [ -d "$MODULE_DIR/logs" ]; then
        echo "[$(date '+%H:%M:%S' 2>/dev/null)] [DEBUG] $1" >> "$LOGFILE" 2>/dev/null || true
    fi
}

# ---------- 命令行 ----------
# 被 post-fs-data/customize source 时只提供函数，不能执行 CLI 或 exit 父脚本。
case "${0##*/}" in
    post-fs-data.sh|customize.sh|service.sh|uninstall.sh) return 0 2>/dev/null || true ;;
esac
case "$1" in
    切换|switch)
        [ -z "$2" ] && { echo "用法：洛书 切换 <字体名>"; return 1 2>/dev/null || exit 1; }
        echo ""
        echo "  正在切换字体..."
        switch_font "$2"
        echo ""
        echo "╔══════════════════════════════════╗"
        printf '║  ✓ 已切换到：%-22s ║\n' "$2"
        echo "║  重启手机后字体完全生效          ║"
        echo "║  请重启手机完成应用；重启前不可再次切换 ║"
        echo "╚══════════════════════════════════╝"
        echo ""
        ;;
    列表|list)
        echo ""
        current=$(get_current_font_id)
        fams=$(scan_user_families)
        # 计算数量
        idx=0
        for _ in $fams; do idx=$((idx + 1)); done
        total=$idx

        printf '╔══════════════ 可用字体'
        [ "$total" -gt 0 ] && printf ' (%d款)' "$total"
        printf ' ══════════════╗\n'
        echo "║                                              ║"

        idx=0
        if [ "$total" -eq 0 ]; then
            echo "║  未找到字体，请将 .ttf 放入 /sdcard/LuoShu/fonts/   ║"
        else
            for fam in $fams; do
                idx=$((idx + 1))
                # 获取该族 Regular 字体大小
                wfile=$(get_weight_file "$fam" "regular")
                [ -z "$wfile" ] && wfile=$(get_weight_file "$fam" "bold")
                size_str="  -"
                if [ -f "$wfile" ]; then
                    fb=$(ls -l "$wfile" 2>/dev/null | awk '{print $5}')
                    case "$fb" in ''|*[!0-9]*) fb=0 ;; esac
                    size_str=$(format_filesize "$fb")
                fi
                # 获取字重列表
                fw=$(scan_family_weights "$fam")
                weight_str=$(echo "$fw" | tr ',' ' ')
                if [ "$fam" = "$current" ]; then
                    printf '║  ▶ %2d. \033[1;36m%-24s\033[0m' "$idx" "$fam"
                else
                    printf '║    %2d. %-24s' "$idx" "$fam"
                fi
                printf ' %-10s' "$size_str"
                printf ' %-22s' "$weight_str"
                printf ' ║\n'
            done
        fi
        echo "║                                              ║"
        echo "╚══════════════════════════════════════════════╝"
        echo ""
        echo "  切换：洛书 切换 <字体名>    详情：洛书 当前"
        ;;
    当前|current)
        current=$(get_current_font_id)
        echo ""
        echo "╔══════════════════════════════════╗"
        printf '║  当前字体：\033[1;36m%-22s\033[0m ║\n' "$current"
        echo "╚══════════════════════════════════╝"
        echo ""
        ;;
    重启界面|restart_ui)
        echo ""
        echo "  正在重启系统界面..."
        pkill -f com.android.systemui 2>/dev/null || pkill -f systemui 2>/dev/null || true
        cmd activity write-settings 2>/dev/null || true
        echo ""
        echo "╔══════════════════════════════════╗"
        echo "║  ✓ 系统界面已重启！              ║"
        echo "║  字体已即时生效                  ║"
        echo "╚══════════════════════════════════╝"
        echo ""
        ;;
    删除|delete|del)
        [ -z "$2" ] && { echo "用法：洛书 删除 <字体名>"; return 1 2>/dev/null || exit 1; }
        echo ""
        echo "  正在删除字体：$2 ..."
        del_count=0
        for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
            [ -f "$f" ] || continue
            tmp_name=$(basename "$f")
            tmp_fam=$(detect_font_family "$tmp_name")
            if [ "$tmp_fam" = "$2" ]; then
                rm -f "$f" 2>/dev/null && del_count=$((del_count + 1))
            fi
        done
        echo ""
        if [ "$del_count" -gt 0 ]; then
            echo "╔══════════════════════════════════╗"
            printf '║  ✓ 已删除：%-22s ║\n' "$2"
            printf '║  %d 个文件已移除                  ║\n' "$del_count"
            current=$(get_current_font_id)
            if [ "$2" = "$current" ]; then
                switch_font "default" 2>/dev/null || true
                echo "║  已自动恢复系统默认字体          ║"
            fi
            echo "╚══════════════════════════════════╝"
        else
            echo "╔══════════════════════════════════╗"
            printf '║  ✗ 未找到字体：%-20s ║\n' "$2"
            echo "╚══════════════════════════════════╝"
            return 1 2>/dev/null || exit 1
        fi
        echo ""
        ;;
    刷新|refresh)
        cmd font system --update 2>/dev/null || true
        echo "✓ 字体缓存已刷新"
        ;;
    回滚|rollback)
        echo ""
        if [ -f "$CONFIG_DIR/previous_font.conf" ]; then
            prev=$(head -n1 "$CONFIG_DIR/previous_font.conf" 2>/dev/null | tr -d '\r\n')
            if [ -n "$prev" ]; then
                switch_font "$prev"
                echo "╔══════════════════════════════════╗"
                printf '║  ✓ 已回滚到：%-20s ║\n' "$prev"
                echo "║  重启手机后生效                  ║"
                echo "╚══════════════════════════════════╝"
            else
                echo "╔══════════════════════════════════╗"
                echo "║  ✗ 没有上一个字体记录            ║"
                echo "╚══════════════════════════════════╝"
            fi
        else
            echo "╔══════════════════════════════════╗"
            echo "║  ✗ 没有可回滚的字体记录          ║"
            echo "╚══════════════════════════════════╝"
        fi
        echo ""
        ;;
    action)
        handle_action "$2" "$3"
        ;;
    *)
        current=$(get_current_font_id)
        echo ""
        echo "╔══════════════════════════════════════╗"
        echo "║        洛 书  v13.4 Beta2 Hotfix6                   ║"
        echo "║        演宇宙之理，塑文字之骨        ║"
        echo "╠══════════════════════════════════════╣"
        printf '║  当前字体：\033[1;36m%-24s\033[0m║\n' "$current"
        echo "╠══════════════════════════════════════╣"
        echo "║  用法：                              ║"
        echo "║    洛书 切换 <字体名>  切换到指定字体║"
        echo "║    洛书 列表           列出可用字体  ║"
        echo "║    洛书 当前           显示当前字体  ║"
        echo "║    洛书 删除 <字体名>  删除字体文件  ║"
        echo "║    洛书 重启界面       重启系统UI    ║"
        echo "║    洛书 刷新           刷新字体缓存  ║"
        echo "║    洛书 回滚           回滚上一字体  ║"
        echo "╠══════════════════════════════════════╣"
        echo "║  切换后必须重启手机完成应用       ║"
        echo "║  或重启手机完全生效                  ║"
        echo "╚══════════════════════════════════════╝"
        echo ""
        ;;
esac

# 确保脚本始终以 0 退出（避免 exec 报错）
exit 0
