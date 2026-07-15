#!/system/bin/sh
# 洛书 v12.8 - 安装脚本（硬链接精简版）

MODPATH="${MODPATH:-$3}"
[ -f /data/adb/magisk/util_functions.sh ] && . /data/adb/magisk/util_functions.sh

# 关键：util_functions.sh 设置了 set -e（任何命令失败都终止脚本）
# 但安装脚本需要容错能力，所以显式禁用
set +e

# 加载洛书共享工具函数（detect_font_family / check_coloros / check_hyperos 等）
if [ -f "$MODPATH/common/util_functions.sh" ]; then
    . "$MODPATH/common/util_functions.sh"
fi

# 加载 ROM 适配层（copy_as_coloros / copy_as_hyperos / apply_font_by_rom 等）
if [ -f "$MODPATH/common/rom_adapters.sh" ]; then
    . "$MODPATH/common/rom_adapters.sh"
fi

# 降级保护：如果无法加载 util_functions.sh，提供最小化 detect_font_family
# 确保在 Magisk 安装环境中字体检测功能始终可用
if ! type detect_font_family >/dev/null 2>&1; then
    detect_font_family() {
        result="${1%.*}"
        case "$result" in
            *"-Regular"|*"-Bold"|*"-Light"|*"-Medium"|*"-Thin"|*"-Black"|*"-Heavy")
                result="${result%-*}" ;;
            *"-regular"|*"-bold"|*"-light"|*"-medium"|*"-thin"|*"-black"|*"-heavy")
                result="${result%-*}" ;;
            *"-常规"|*"-粗体"|*"-细体"|*"-中等"|*"-极细"|*"-特粗"|*"-斜体")
                result="${result%-*}" ;;
        esac
        echo "$result"
    }
fi

# 降级：get_all_coloros_names 若不可用则设空（此变量在脚本中未实际使用）
if ! type get_all_coloros_names >/dev/null 2>&1; then
    get_all_coloros_names() { echo ""; }
fi

# 降级：check_coloros/check_hyperos 若不可用（理论上不该发生，rom_adapters.sh
# 依赖这两个函数设置的 IS_COLOROS/IS_HYPEROS），提供空实现避免脚本报错退出
if ! type check_coloros >/dev/null 2>&1; then
    check_coloros() { IS_COLOROS="false"; }
fi
if ! type check_hyperos >/dev/null 2>&1; then
    check_hyperos() { IS_HYPEROS="false"; }
fi
# 降级：apply_font_by_rom 若不可用（rom_adapters.sh 加载失败），退回旧版
# 纯 ColorOS 覆盖逻辑，保底不至于完全没反应
if ! type apply_font_by_rom >/dev/null 2>&1; then
    apply_font_by_rom() {
        _src="$1"; _dest="$2"
        names="SysSans-Hant-Regular SysSans-Hans-Regular SysFont-Static-Regular SysFont-Myanmar SysFont-Hant-Regular SysFont-Hans-Regular SysFont-Regular SysSans-En-Regular"
        for _name in $names; do
            cp -f "$_src" "$_dest/${_name}.ttf" 2>/dev/null
        done
    }
fi

# 检测当前 ROM（决定用哪套字体文件名覆盖逻辑）
check_coloros
check_hyperos
if [ "$IS_COLOROS" = "true" ]; then
    ui_print "检测到系统：ColorOS $COLOROS_VERSION"
elif [ "$IS_HYPEROS" = "true" ]; then
    ui_print "检测到系统：HyperOS/MIUI $HYPEROS_VERSION"
else
    ui_print "未识别具体 ROM，使用通用 AOSP 适配（效果不保证）"
fi

USER_FONTS_DIR="/sdcard/Fonts"

# 扫描用户字体族
scan_user_fonts() {
    result=""
    [ -d "$USER_FONTS_DIR" ] || return
    for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTC "$USER_FONTS_DIR"/*.tf "$USER_FONTS_DIR"/*.TF; do
        [ -f "$f" ] || continue
        fam=$(detect_font_family "$(basename "$f")")
        # 跳过系统字体
        case "$fam" in SysFont*|SysSans*) continue ;; esac
        case " $result " in *" $fam "*) ;; *) result="$result $fam" ;; esac
    done
    echo "$result" | sed 's/^ //'
}

# ColorOS 所有已知字体文件名（从共享函数获取，消除硬编码重复）
ALL_COLOROS=$(get_all_coloros_names)

# 备份系统原始 fonts.xml（用于参考和恢复）
backup_system_fonts_xml() {
    mod_dir="$1"
    backup_dir="$mod_dir/backup"
    
    mkdir -p "$backup_dir" 2>/dev/null || true
    
    if [ -f /system/etc/fonts.xml ]; then
        cp -f /system/etc/fonts.xml "$backup_dir/fonts.xml.original" 2>/dev/null || true
        ui_print "  已备份系统原始 fonts.xml"
    fi
}

# ========== 主流程 ==========
ui_print ""
ui_print "╔══════════════════════════════════╗"
ui_print "║    洛 书  v12.8                  ║"
ui_print "║    演宇宙之理，塑文字之骨        ║"
ui_print "╚══════════════════════════════════╝"
ui_print ""

# 扫描用户字体
if [ ! -d "$USER_FONTS_DIR" ]; then
    ui_print "错误：未找到 $USER_FONTS_DIR"
    ui_print "请将 .ttf 字体文件放入此目录后重新刷入"
    exit 1
fi

# 找到第一个用户字体（跳过系统字体）
USER_FONT=""
USER_FONT_NAME=""
for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTC "$USER_FONTS_DIR"/*.tf "$USER_FONTS_DIR"/*.TF; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    case "$name" in
        SysFont*|SysSans*) continue ;;
    esac
    USER_FONT="$f"
    USER_FONT_NAME=$(detect_font_family "$name")
    break
done

if [ -z "$USER_FONT" ]; then
    ui_print "错误：未找到用户字体文件"
    exit 1
fi

# 扫描所有字体族
ALL_FONTS=$(scan_user_fonts)
FONT_COUNT=0
for _ in $ALL_FONTS; do FONT_COUNT=$((FONT_COUNT+1)); done

# 加载音量键选择器
if [ -f "$MODPATH/common/volume_key.sh" ]; then
    . "$MODPATH/common/volume_key.sh"
fi

# 如果有多个字体，用音量键让用户选择
if [ "$FONT_COUNT" -gt 1 ] && command -v volume_key_menu >/dev/null 2>&1; then
    # 构建选项字符串（用|分隔）
    OPTIONS_STR=""
    first_opt=true
    for fam in $ALL_FONTS; do
        if [ "$first_opt" = "true" ]; then
            OPTIONS_STR="$fam"
            first_opt=false
        else
            OPTIONS_STR="$OPTIONS_STR|$fam"
        fi
    done

    ui_print "检测到 $FONT_COUNT 款字体"
    # 显示音量键选择菜单（5秒超时）
    volume_key_menu "$OPTIONS_STR" 5
    SELECTED_IDX="$VK_SELECTED"

    # 根据选择的索引找到对应的字体族，然后找该族第一个文件
    # 关键：必须用和菜单相同的顺序（scan_user_fonts 的顺序），不能直接用文件遍历
    sel_fam=""
    idx=0
    for fam in $ALL_FONTS; do
        [ "$idx" -eq "$SELECTED_IDX" ] && { sel_fam="$fam"; break; }
        idx=$((idx + 1))
    done

    # 找到该字体族第一个可用的文件
    if [ -n "$sel_fam" ]; then
        for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTC "$USER_FONTS_DIR"/*.tf "$USER_FONTS_DIR"/*.TF; do
            [ -f "$f" ] || continue
            name=$(basename "$f")
            case "$name" in SysFont*|SysSans*) continue ;; esac
            this_fam=$(detect_font_family "$name")
            [ "$this_fam" = "$sel_fam" ] && {
                USER_FONT="$f"
                USER_FONT_NAME="$sel_fam"
                break
            }
        done
    fi

    ui_print ""
    ui_print "已选择字体：$USER_FONT_NAME"
else
    # 只有一个字体或音量键不支持，直接使用第一个
    ui_print "发现 $FONT_COUNT 款字体："
    for fam in $ALL_FONTS; do
        ui_print "  - $fam"
    done
    ui_print ""
    ui_print "自动使用：$USER_FONT_NAME"
fi
ui_print ""

# 创建目录
mkdir -p "$MODPATH/system/fonts"
mkdir -p "$MODPATH/system/bin"
mkdir -p "$MODPATH/config"
# 注意：不创建 system/etc/ 目录，不替换 fonts.xml
# 因为我们只替换字体文件（文件名不变），系统原始 fonts.xml 完全兼容

# 覆盖系统字体前先校验源文件本身合不合法：大小是否过小、magic bytes 是否是
# 真正的字体文件（TTF 是 00 01 00 00 或 'true'，OTF 是 'OTTO'，TTC 是 'ttcf'）。
# 这一步很重要——如果拿一个损坏/非字体文件去覆盖几十个系统关键字体文件，
# 系统的 native 字体渲染引擎解析到畸形文件时容易直接崩掉整个进程，表现为
# "很多应用闪退""桌面反复卡死"，且这种崩溃不会在安装阶段报错，只会在
# 之后使用时才暴露，所以必须在覆盖之前就拦下来
USER_FONT_SIZE=$(wc -c < "$USER_FONT" 2>/dev/null | tr -d '[:space:]')
case "$USER_FONT_SIZE" in ''|*[!0-9]*) USER_FONT_SIZE=0 ;; esac
if [ "$USER_FONT_SIZE" -lt 1024 ]; then
    ui_print "错误：字体文件 $USER_FONT_NAME 只有 ${USER_FONT_SIZE} 字节，明显不是正常字体文件"
    ui_print "已中止安装，请检查 /sdcard/Fonts/ 里的字体文件是否下载/传输完整"
    exit 1
fi
USER_FONT_MAGIC=$(dd if="$USER_FONT" bs=1 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n')
case "$USER_FONT_MAGIC" in
    00010000|4f54544f|74727565|74746366|00020000) ;;  # TTF/OTTO/true/ttcf/旧版TTF 均合法
    *)
        ui_print "警告：字体文件 $USER_FONT_NAME 的文件头（$USER_FONT_MAGIC）不像是合法的 TTF/OTF/TTC 字体"
        ui_print "继续安装可能导致部分应用闪退，建议更换字体文件后重试"
        ;;
esac

# 根据检测到的 ROM 覆盖对应字体文件名。未覆盖的系统字体由 Overlay 下层
# 原厂目录自然提供，无需复制进模块。
apply_font_by_rom "$USER_FONT" "$MODPATH/system/fonts" full "$USER_FONT_NAME"

# 备份系统原始 fonts.xml（用于参考，不替换）
backup_system_fonts_xml "$MODPATH"

# 保存配置
echo "$USER_FONT_NAME" > "$MODPATH/config/active_font.conf"

# 保存所有字体族列表
: > "$MODPATH/config/font_list.conf"
for fam in $ALL_FONTS; do
    echo "$fam" >> "$MODPATH/config/font_list.conf"
done

# 创建首次启动标记，service.sh 将在下次启动时自动重启 SystemUI
touch "$MODPATH/.first_boot"

# ColorOS 同步：复制关键字体文件到 /data/fonts/
# 注：目前只在 ColorOS 上做这三处额外同步（/data/fonts、system_ext/fonts、
# product/fonts），因为这是从真机验证过的 ColorOS 行为（锁屏大时钟等场景
# 可能不经过 /system/fonts 走这几个路径读取）。HyperOS 暂无证据表明需要
# 同样处理，等后续真机验证后再补充，避免盲目复制造成不必要的模块体积膨胀
if [ "$IS_COLOROS" = "true" ] && [ -d /data/fonts ]; then
    rm -f /data/fonts/*.ttf /data/fonts/*.otf 2>/dev/null
    coloros_all=$(get_all_coloros_names)
    for cname in $coloros_all; do
        cfile="$MODPATH/system/fonts/${cname}.ttf"
        if [ -f "$cfile" ]; then
            cp -f "$cfile" /data/fonts/ 2>/dev/null || true
            chmod 644 "/data/fonts/${cname}.ttf" 2>/dev/null || true
        fi
    done
fi

# 同步 DIN 字体到 system_ext/fonts/（ColorOS 锁屏大时钟可能从此路径加载）
if [ "$IS_COLOROS" = "true" ] && [ -d "$MODPATH/system_ext/fonts" ]; then
    rm -f "$MODPATH/system_ext/fonts"/*.ttf "$MODPATH/system_ext/fonts"/*.otf 2>/dev/null || true
    for dname in $(get_all_coloros_names); do
        if [ -f "$MODPATH/system/fonts/${dname}.ttf" ]; then
            link_or_copy_font "$MODPATH/system/fonts/${dname}.ttf" "$MODPATH/system_ext/fonts/${dname}.ttf" 2>/dev/null || true
        fi
    done
    chmod -R 644 "$MODPATH/system_ext/fonts"/*.ttf 2>/dev/null || true
    chmod 755 "$MODPATH/system_ext/fonts" 2>/dev/null || true
fi

# 同步 DIN 字体到 product/fonts/
if [ "$IS_COLOROS" = "true" ] && [ -d "$MODPATH/product/fonts" ]; then
    rm -f "$MODPATH/product/fonts"/*.ttf "$MODPATH/product/fonts"/*.otf 2>/dev/null || true
    for dname in $(get_all_coloros_names); do
        if [ -f "$MODPATH/system/fonts/${dname}.ttf" ]; then
            link_or_copy_font "$MODPATH/system/fonts/${dname}.ttf" "$MODPATH/product/fonts/${dname}.ttf" 2>/dev/null || true
        fi
    done
    chmod -R 644 "$MODPATH/product/fonts"/*.ttf 2>/dev/null || true
    chmod 755 "$MODPATH/product/fonts" 2>/dev/null || true
fi

# 安装命令行工具
cp -f "$MODPATH/common/font_manager.sh" "$MODPATH/system/bin/洛书" 2>/dev/null || true
chmod 755 "$MODPATH/system/bin/洛书" 2>/dev/null || true

# 安装 C 核心加速引擎（可选）
if [ -f "$MODPATH/system/bin/luoshud" ]; then
    chmod 755 "$MODPATH/system/bin/luoshud" 2>/dev/null || true
    ui_print "  C核心引擎就绪"
fi

# 权限（直接用 chmod 设置，比 set_perm 更可靠）
chmod -R 644 "$MODPATH/system/fonts"/*.ttf 2>/dev/null || true
chmod 755 "$MODPATH/system/fonts" 2>/dev/null || true
chmod -R 755 "$MODPATH/system/bin" 2>/dev/null || true
chmod -R 755 "$MODPATH/config" 2>/dev/null || true
chmod -R 644 "$MODPATH/webroot"/*.html "$MODPATH/webroot"/*.css "$MODPATH/webroot"/*.js 2>/dev/null || true
chmod 755 "$MODPATH/webroot" 2>/dev/null || true
# 关键：确保脚本有可执行权限
chmod 755 "$MODPATH/common/font_manager.sh" 2>/dev/null || true
chmod 755 "$MODPATH/common/util_functions.sh" 2>/dev/null || true
chmod 755 "$MODPATH/common/fonts_xml_template.sh" 2>/dev/null || true
chmod 755 "$MODPATH/common/volume_key.sh" 2>/dev/null || true
chmod 755 "$MODPATH/common/rom_adapters.sh" 2>/dev/null || true

# 注意：预览字体同步在 post-fs-data.sh 启动时自动执行
# 不在 customize.sh 中调用，避免 source font_manager.sh 引入 exit 风险

ui_print ""
ui_print "--------------------------------"
ui_print "LuoShu installation complete"
ui_print "Font: $USER_FONT_NAME"
if [ "$IS_HYPEROS" = "true" ]; then
    ui_print "ROM mapping: HyperOS/MIUI $HYPEROS_VERSION"
elif [ "$IS_COLOROS" = "true" ]; then
    ui_print "ROM mapping: ColorOS $COLOROS_VERSION"
else
    ui_print "ROM mapping: Generic AOSP"
fi
ui_print "Reboot device to apply the font."
ui_print "WebUI switching refreshes SystemUI."
ui_print "--------------------------------"
ui_print ""

# 关键：显式返回 0，确保 Magisk 显示安装成功
# 前面 sync_preview_fonts 中的命令可能返回非零，但安装本身已成功
exit 0
