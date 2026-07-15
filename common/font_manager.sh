#!/system/bin/sh
# 洛书 v12.8 - 字体管理核心（硬链接精简版）

# 关键：禁用严格错误终止，避免任何命令失败导致脚本退出
set +e

# ---------- 确定模块目录 ----------
# 注意：本文件被 post-fs-data.sh / customize.sh source，绝不能使用 exit
# 任何 exit 都会终止父脚本，导致 Magisk 显示刷写失败
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../../module.prop" ]; then
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
USER_FONTS_DIR="/sdcard/Fonts"

# ---------- 加载共享工具函数 ----------
# detect_font_family 等基础函数统一由 util_functions.sh 提供
# 避免在多个文件中重复定义
if [ -f "$MODULE_DIR/common/util_functions.sh" ]; then
    . "$MODULE_DIR/common/util_functions.sh"
fi

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
    for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF; do
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
    for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF; do
        [ -f "$f" ] || continue
        fam=$(detect_font_family "$(basename "$f")")
        case "$fam" in SysFont*|SysSans*) continue ;; esac
        case " $result " in *" $fam "*) ;; *) result="$result $fam" ;; esac
    done
    case "$result" in " "*) result="${result# }" ;; esac
    while true; do case "$result" in " "*) result="${result# }" ;; *) break ;; esac; done
    echo "$result"
}

# 扫描字体族的字重变体、获取指定字重文件：scan_family_weights() /
# get_weight_file() 已迁移到 util_functions.sh 统一维护

get_current_font_id() {
    active=""
    [ -f "$ACTIVE_FONT_CONF" ] && active=$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '[:space:]')
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

# ---------- 切换字体 ----------
switch_font() {
    font_id="$1"

    # 备份当前字体（用于回滚）
    if [ -f "$ACTIVE_FONT_CONF" ]; then
        current_backup=$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '[:space:]')
        if [ -n "$current_backup" ] && [ "$current_backup" != "default" ] && [ "$current_backup" != "$font_id" ]; then
            echo "$current_backup" > "$CONFIG_DIR/previous_font.conf"
        fi
    fi

    [ -z "$font_id" ] && { echo "错误：未指定字体" >&2; return 1; }
    
    # 找到对应的字体文件
    src_file=""
    if [ "$font_id" != "default" ]; then
        for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF; do
            [ -f "$f" ] || continue
            fam=$(detect_font_family "$(basename "$f")")
            case "$fam" in SysFont*|SysSans*) continue ;; esac
            [ "$fam" = "$font_id" ] && { src_file="$f"; break; }
        done
        
        if [ -z "$src_file" ]; then
            echo "错误：字体 $font_id 不存在于 $USER_FONTS_DIR" >&2
            return 1
        fi
    fi
    
    if [ "$font_id" = "default" ]; then
        rm -f "$SYSTEM_FONTS_DIR"/*.ttf "$SYSTEM_FONTS_DIR"/*.otf "$SYSTEM_FONTS_DIR"/*.ttc 2>/dev/null
        rm -rf "$SYSTEM_FONTS_DIR/.luoshu-font-store" 2>/dev/null || true
        # Overlay 中移除目标文件后，下层 ROM 原字体会自动恢复，无需复制。
        echo "  [洛书] 已恢复 ROM 原始字体（Overlay 下层）"
    else
        # 使用 quick 模式：只替换 ROM 对应的核心文件，不重新复制所有系统字体
        # 这样切换速度从 5-10 秒缩短到 1 秒以内
        apply_font_by_rom "$src_file" "$SYSTEM_FONTS_DIR" "quick" "$font_id"
    fi
    
    # 注意：不替换 fonts.xml，系统继续使用原始的 fonts.xml
    # 因为我们只替换字体文件（文件名不变），原始 fonts.xml 完全兼容
    echo "$font_id" > "$ACTIVE_FONT_CONF"

    # 记录到最近使用列表
    if [ -n "$font_id" ] && [ "$font_id" != "default" ]; then
        recent_file="$CONFIG_DIR/recent_fonts.conf"
        # 读取现有列表，去掉重复，限制10条
        recent_list=""
        recent_count=0
        if [ -f "$recent_file" ]; then
            while IFS= read -r line; do
                line=$(echo "$line" | tr -d '[:space:]')
                [ -z "$line" ] && continue
                [ "$line" = "$font_id" ] && continue
                if [ "$recent_count" -lt 9 ]; then
                    recent_list="$recent_list$line
"
                    recent_count=$((recent_count + 1))
                fi
            done < "$recent_file"
        fi
        # 新字体放最前面
        printf '%s\n%s' "$font_id" "$recent_list" > "$recent_file" 2>/dev/null || true
    fi

    chmod 644 "$ACTIVE_FONT_CONF" 2>/dev/null
    chmod 644 "$SYSTEM_FONTS_DIR"/* 2>/dev/null
    
    # ColorOS 专属同步：/data/fonts、system_ext/fonts、product/fonts
    # 这三处是真机验证过的 ColorOS 行为（锁屏大时钟等场景可能不经过
    # /system/fonts），HyperOS 暂无证据需要，故只在 ColorOS 上执行
    if [ "$IS_COLOROS" = "true" ]; then
        all_names=$(get_all_coloros_names)
        if [ -d /data/fonts ]; then
            for cname in $all_names; do
                cfile="$SYSTEM_FONTS_DIR/${cname}.ttf"
                if [ -f "$cfile" ]; then
                    cp -f "$cfile" /data/fonts/ 2>/dev/null || true
                    chmod 644 "/data/fonts/${cname}.ttf" 2>/dev/null || true
                fi
            done
        fi
        if [ -d "$MODULE_DIR/system_ext/fonts" ]; then
            for cname in $all_names; do
                cfile="$SYSTEM_FONTS_DIR/${cname}.ttf"
                if [ -f "$cfile" ]; then
                    link_or_copy_font "$cfile" "$MODULE_DIR/system_ext/fonts/${cname}.ttf" 2>/dev/null || true
                fi
            done
        fi
        if [ -d "$MODULE_DIR/product/fonts" ]; then
            for cname in $all_names; do
                cfile="$SYSTEM_FONTS_DIR/${cname}.ttf"
                if [ -f "$cfile" ]; then
                    link_or_copy_font "$cfile" "$MODULE_DIR/product/fonts/${cname}.ttf" 2>/dev/null || true
                fi
            done
        fi
    fi
    
    # Android 16 / GMS 动态字体在 /data/fonts/files，切换字体后同步重绑。
    # 恢复默认时只卸载 bind mount，不改写 GMS 原文件。
    if [ -f "$MODULE_DIR/common/play_font_bridge.sh" ]; then
        if [ "$font_id" = "default" ]; then
            MODDIR="$MODULE_DIR" sh "$MODULE_DIR/common/play_font_bridge.sh" restore >/dev/null 2>&1 || true
        else
            MODDIR="$MODULE_DIR" sh "$MODULE_DIR/common/play_font_bridge.sh" now >/dev/null 2>&1 || true
        fi
    fi

    # ========== 切换完成提示 ==========
    # 字体文件已替换，只请求系统字体服务刷新。Android 16 的字体配置由
    # FontManagerService 管理，直接删除 /data/system/font_config.xml 可能造成
    # 服务重建期间应用闪退，因此不再手工删除系统配置文件。
    cmd font system --update >/dev/null 2>&1 || true
    if [ -f /system/bin/oplus-font ]; then
        oplus-font refresh >/dev/null 2>&1 || true
    fi
    # 注意：需要手动重启手机才能完全生效
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
    for src in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF; do
        [ -f "$src" ] || continue
        mtime=$(stat -c %Y "$src" 2>/dev/null || echo 0)
        [ "$mtime" -gt "$latest_mtime" ] && latest_mtime="$mtime"
    done
    
    # 没有字体文件，清理预览目录
    if [ "$latest_mtime" -eq 0 ]; then
        for f in "$preview_dir"/*.ttf "$preview_dir"/*.otf "$preview_dir"/*.TTF "$preview_dir"/*.OTF; do
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
    for f in "$preview_dir"/*.ttf "$preview_dir"/*.otf "$preview_dir"/*.TTF "$preview_dir"/*.OTF; do
        [ -f "$f" ] && rm -f "$f" 2>/dev/null
    done
    
    for src in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF; do
        [ -f "$src" ] || continue
        name=$(basename "$src")
        case "$name" in SysFont*|SysSans*) continue ;; esac
        ln -f "$src" "$preview_dir/$name" 2>/dev/null || cp -f "$src" "$preview_dir/$name" 2>/dev/null
        chmod 644 "$preview_dir/$name" 2>/dev/null
    done
    
    # 写入缓存时间
    echo "$latest_mtime" > "$cache_file" 2>/dev/null
}

# ---------- WebUI 接口 ----------
handle_action() {
    action="$1"
    param="$2"
    current=$(get_current_font_id 2>/dev/null)

    # 同步预览字体到 webroot/fonts/（供 WebUI 用相对路径加载，避免 file:// CORS 限制）
    sync_preview_fonts 2>/dev/null || true

    # ── C 核心加速引擎桥接 ──
    # 如果 C 二进制可用，用于 scan（纯扫描）操作。
    # 注意：list 操作不走 C 核心，因为 WebUI 需要 file/date 字段用于字体预览，
    # 而 C scan 输出不含这些字段。list 始终走 Shell 路径以保证数据完整。
    NATIVE_BIN="$MODULE_DIR/system/bin/luoshud"
    if [ -x "$NATIVE_BIN" ]; then
        case "$action" in
            scan)
                output=$("$NATIVE_BIN" scan 2>/dev/null)
                if [ -n "$output" ] && echo "$output" | grep -q '"status":"ok"'; then
                    echo "$output" | sed "s/\"data\":{/\"data\":{\"current\":\"$current\",/"
                    return 0
                fi
                log_debug "[bridge] C core failed, falling back to shell"
                ;;
        esac
    fi

    case "$action" in
        list)
            # WebUI 列表缓存：字体目录及当前字体未变化时直接返回 JSON。
            # 避免每次打开页面重复执行多轮文件扫描与字重归类。
            list_cache_json="$CONFIG_DIR/webui_font_list.json"
            list_cache_key="$CONFIG_DIR/webui_font_list.key"
            dir_stamp=$(stat -c '%Y:%s' "$USER_FONTS_DIR" 2>/dev/null || echo '0:0')
            current_key="${current}|${dir_stamp}"
            cached_key=$(cat "$list_cache_key" 2>/dev/null)
            if [ "$param" != "refresh" ] && [ "$cached_key" = "$current_key" ] && [ -s "$list_cache_json" ] && grep -q '"status":"ok"' "$list_cache_json" 2>/dev/null; then
                cat "$list_cache_json"
                return 0
            fi
            {
            user_fams=$(scan_user_families 2>/dev/null)
            first="true"
            total_bytes=0
            font_count=0
            
            # 先计算总大小和数量
            log_debug "[list] 开始扫描 $font_count 个字体族"
            for fam in $user_fams; do
                font_count=$((font_count + 1))
                wfile_tmp=$(get_weight_file "$fam" "regular")
                [ -z "$wfile_tmp" ] && wfile_tmp=$(get_weight_file "$fam" "bold")
                [ -z "$wfile_tmp" ] && {
                    for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf; do
                        [ -f "$f" ] || continue
                        tn=$(basename "$f")
                        tf=$(detect_font_family "$tn")
                        [ "$tf" = "$fam" ] && { wfile_tmp="$f"; break; }
                    done
                }
                if [ -f "$wfile_tmp" ]; then
                    fb=$(ls -l "$wfile_tmp" 2>/dev/null | awk '{print $5}')
                    case "$fb" in ''|*[!0-9]*) fb=0 ;; esac
                    total_bytes=$((total_bytes + fb))
                    log_debug "[list] fam=$fam file=$(basename "$wfile_tmp") size=$fb"
                else
                    log_debug "[list] fam=$fam wfile_tmp='' NOT FOUND"
                fi
            done
            
            printf '{"status":"ok","data":{"current":"%s","stats":{"count":%d,"totalSize":"%s"},"fonts":[' "$current" "$font_count" "$(format_filesize "$total_bytes")"
            
            for fam in $user_fams; do
                [ "$first" = "true" ] || printf ','
                fw=$(scan_family_weights "$fam")
                # 构建字重 JSON 数组
                weights_json=""
                for w in $(echo "$fw" | tr ',' ' '); do
                    [ -n "$weights_json" ] && weights_json="$weights_json,"
                    weights_json="$weights_json\"$w\""
                done
                # 获取该字体族第一个文件的路径
                wfile=$(get_weight_file "$fam" "regular")
                [ -z "$wfile" ] && wfile=$(get_weight_file "$fam" "bold")
                [ -z "$wfile" ] && wfile=$(get_weight_file "$fam" "medium")
                [ -z "$wfile" ] && {
                    for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf; do
                        [ -f "$f" ] || continue
                        tmp_name=$(basename "$f")
                        tmp_fam=$(detect_font_family "$tmp_name")
                        [ "$tmp_fam" = "$fam" ] && { wfile="$f"; break; }
                    done
                }
                # 获取文件大小（ls -l + awk，不受文件名空格影响）
                fbytes=$(ls -l "$wfile" 2>/dev/null | awk '{print $5}')
                case "$fbytes" in ''|*[!0-9]*) fbytes=0 ;; esac
                # 文件格式（纯 shell 提取扩展名）
                fformat="${wfile##*.}"
                case "$fformat" in [Tt][Tt][Ff]) fformat="TTF" ;; [Oo][Tt][Ff]) fformat="OTF" ;; *) fformat="$fformat" ;; esac
                # 修改日期（ls -l 第6=月 第7=日 第8=时间/年，多方式尝试）
                ftime=""
                # 方式1: stat %y
                ftime=$(stat -c '%y' "$wfile" 2>/dev/null | cut -c1-10)
                # 方式2: 从 ls -l 构造（简化显示 月-日）
                if [ -z "$ftime" ]; then
                    ftime="$6-$7"
                fi
                # 使用相对路径 ./fonts/xxx.ttf（避免 file:// CORS 限制）
                fname=$(basename "$wfile" 2>/dev/null)
                printf '{"id":"%s","name":"%s","weights":[%s],"file":"./fonts/%s","size":"%s","bytes":%s,"format":"%s","date":"%s"}' "$fam" "$fam" "$weights_json" "$fname" "$(format_filesize "$fbytes")" "$fbytes" "$fformat" "$ftime"
                first="false"
            done
            printf ']}}\n'
            } | tee "$list_cache_json"
            echo "$current_key" > "$list_cache_key" 2>/dev/null || true
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
                    line=$(echo "$line" | tr -d '[:space:]')
                    [ -z "$line" ] && continue
                    [ -n "$recent_json" ] && recent_json="$recent_json,"
                    recent_json="$recent_json\"$line\""
                done < "$recent_file"
            fi
            printf '{"status":"ok","data":{"recent":[%s]}}\n' "$recent_json"
            ;;
        delete)
            if [ -z "$param" ]; then
                printf '{"status":"error","message":"未指定字体"}\n'
            else
                del_count=0
                for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF; do
                    [ -f "$f" ] || continue
                    tmp_name=$(basename "$f")
                    tmp_fam=$(detect_font_family "$tmp_name")
                    if [ "$tmp_fam" = "$param" ]; then
                        rm -f "$f" 2>/dev/null && del_count=$((del_count + 1))
                    fi
                done
                if [ "$del_count" -gt 0 ]; then
                    if [ "$param" = "$current" ]; then
                        switch_font "default" 2>/dev/null || true
                        echo "default" > "$ACTIVE_FONT_CONF"
                    fi
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
        echo "║  或执行「洛书 重启界面」立即刷新 ║"
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
            echo "║  未找到字体，请将 .ttf 放入 /sdcard/Fonts/   ║"
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
        for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF; do
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
            prev=$(head -n1 "$CONFIG_DIR/previous_font.conf" 2>/dev/null | tr -d '[:space:]')
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
        echo "║        洛 书  v12.8                   ║"
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
        echo "║  切换后可「重启界面」立即生效       ║"
        echo "║  或重启手机完全生效                  ║"
        echo "╚══════════════════════════════════════╝"
        echo ""
        ;;
esac

# 确保脚本始终以 0 退出（避免 exec 报错）
exit 0
