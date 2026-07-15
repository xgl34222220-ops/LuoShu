#!/system/bin/sh
set +e
# ============================================================
# 洛书 - 工具函数库 (util_functions.sh)
# 作者：惜故里丶
# 版本：v13.3 Beta2
# 功能：提供字体模块所需的所有通用工具函数
# ============================================================

# ---------- 模块路径定义 ----------
# 允许外部覆盖（font_manager.sh 会在加载前设置 MODULE_DIR）
MODULE_DIR="${MODULE_DIR:-/data/adb/modules/LuoShu}"
CONFIG_DIR="${MODULE_DIR}/config"
FONT_DIR="${MODULE_DIR}/fonts"
LOG_DIR="${MODULE_DIR}/logs"
LOG_FILE="${LOG_DIR}/fontswitch.log"
LUOSHU_PUBLIC_DIR="/sdcard/LuoShu"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
USER_EMOJI_DIR="$LUOSHU_PUBLIC_DIR/emoji"
USER_REPORT_DIR="$LUOSHU_PUBLIC_DIR/reports"
LEGACY_FONTS_DIR="/sdcard/Fonts"


# 创建公开目录并兼容迁移旧版 /sdcard/Fonts。迁移采用复制而不是移动，
# 避免用户仍使用旧版模块时找不到原文件。
ensure_public_storage() {
    mkdir -p "$USER_FONTS_DIR" "$USER_EMOJI_DIR" "$USER_REPORT_DIR" 2>/dev/null || true
    chmod 0775 "$LUOSHU_PUBLIC_DIR" "$USER_FONTS_DIR" "$USER_EMOJI_DIR" "$USER_REPORT_DIR" 2>/dev/null || true
    if [ -d "$LEGACY_FONTS_DIR" ]; then
        for _old in "$LEGACY_FONTS_DIR"/*.ttf "$LEGACY_FONTS_DIR"/*.otf "$LEGACY_FONTS_DIR"/*.ttc \
                    "$LEGACY_FONTS_DIR"/*.TTF "$LEGACY_FONTS_DIR"/*.OTF "$LEGACY_FONTS_DIR"/*.TTC; do
            [ -f "$_old" ] || continue
            _name=$(basename "$_old")
            [ -e "$USER_FONTS_DIR/$_name" ] || cp -f "$_old" "$USER_FONTS_DIR/$_name" 2>/dev/null || true
        done
    fi
}

# ---------- 颜色定义 ----------
# Magisk ui_print 不支持 ANSI，只在终端使用
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ---------- 全局变量 ----------
ROOT_MANAGER="unknown"
ROOT_MANAGER_VER="unknown"
ROOT_MANAGER_VER_CODE=0
IS_COLOROS="false"
COLOROS_VERSION=""
IS_HYPEROS="false"
HYPEROS_VERSION=""
ANDROID_API=0

# ============================================================
# 初始化模块
# ============================================================
init_module() {
    ensure_public_storage
    init_logging
    check_android_version
    check_magisk_version
    check_coloros
    check_hyperos
    log_message "INFO" "洛书模块已初始化 | Root管理器: $ROOT_MANAGER | Android API: $ANDROID_API | ColorOS: $IS_COLOROS | HyperOS: $IS_HYPEROS"
}

# ============================================================
# 日志系统
# ============================================================
init_logging() {
    # 创建日志目录
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR" 2>/dev/null || true
    fi
    # 限制日志大小（保留最近 500 行）
    if [ -f "$LOG_FILE" ]; then
        lines=$(wc -l < "$LOG_FILE" 2>/dev/null || echo 0)
        if [ "$lines" -gt 1000 ]; then
            tail -n 500 "$LOG_FILE" > "$LOG_FILE.tmp" 2>/dev/null
            mv "$LOG_FILE.tmp" "$LOG_FILE" 2>/dev/null || true
        fi
    fi
}

log_message() {
    level="$1"
    msg="$2"
    timestamp=$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "unknown")
    # 确保日志目录存在
    if [ -d "$LOG_DIR" ]; then
        echo "[$timestamp] [$level] $msg" >> "$LOG_FILE" 2>/dev/null || true
    fi
}

# ============================================================
# 检查 Root 管理器（Magisk / KernelSU / SukiSU）
# ============================================================
check_magisk_version() {
    ROOT_MANAGER="unknown"
    ROOT_MANAGER_VER="unknown"
    ROOT_MANAGER_VER_CODE=0

    # 注意：这里不能 source /data/adb/magisk/util_functions.sh！
    # 那是 Magisk 官方安装流程内部专用的工具函数集，不是给第三方模块调用的 API。
    # 它的某些版本在被以非预期方式加载时会触发内部前置检查，检查不通过就调用它
    # 自己的 abort()（内部就是 exit），用 `.` source 方式加载时这个 exit 会直接把
    # 外层 customize.sh 一并杀死，导致整个模块安装中断失败。
    # 而且完全没有必要 source 它：Magisk 在执行 customize.sh 之前，早就把
    # $MAGISK_VER_CODE / $MAGISK_VER 这些变量注入到环境里了，KernelSU 也同理
    # 会注入 $KSU_VER_CODE 等，直接读现成的环境变量即可。

    # 检测 Magisk（版本号 >= 20400）
    if [ -n "$MAGISK_VER_CODE" ] && [ "$MAGISK_VER_CODE" -ge 20400 ] 2>/dev/null; then
        ROOT_MANAGER="Magisk"
        ROOT_MANAGER_VER="$MAGISK_VER"
        ROOT_MANAGER_VER_CODE="$MAGISK_VER_CODE"
        return 0
    fi

    # 检测 KernelSU / SukiSU
    if [ "$KSU" = "true" ] || [ -n "$KSU_VER_CODE" ] 2>/dev/null; then
        if [ -n "$SUKISU" ] || [ -n "$SUKISU_VER" ] 2>/dev/null; then
            ROOT_MANAGER="SukiSU"
            ROOT_MANAGER_VER="${SUKISU_VER:-${KSU_VER:-unknown}}"
            ROOT_MANAGER_VER_CODE="${SUKISU_VER_CODE:-${KSU_VER_CODE:-0}}"
        else
            ROOT_MANAGER="KernelSU"
            ROOT_MANAGER_VER="${KSU_VER:-unknown}"
            ROOT_MANAGER_VER_CODE="${KSU_VER_CODE:-0}"
        fi
        return 0
    fi

    # 尝试从环境变量再次检测（某些版本）
    if [ -n "$APATCH" ] || [ -n "$APATCH_VER_CODE" ] 2>/dev/null; then
        ROOT_MANAGER="APatch"
        ROOT_MANAGER_VER="${APATCH_VER:-unknown}"
        ROOT_MANAGER_VER_CODE="${APATCH_VER_CODE:-0}"
        return 0
    fi

    log_message "WARN" "未能检测到 Root 管理器"
    return 1
}

# ============================================================
# 检测 Android 版本
# ============================================================
check_android_version() {
    ANDROID_API=0
    if [ -f /system/build.prop ]; then
        ANDROID_API=$(grep -m1 '^ro.build.version.sdk=' /system/build.prop 2>/dev/null | cut -d'=' -f2 | tr -d '[:space:]')
    fi
    if [ -z "$ANDROID_API" ] || [ "$ANDROID_API" -eq 0 ] 2>/dev/null; then
        # fallback：通过 getprop
        ANDROID_API=$(getprop ro.build.version.sdk 2>/dev/null || echo 0)
    fi
    # 确保是数字
    case "$ANDROID_API" in
        ''|*[!0-9]*) ANDROID_API=0 ;;
    esac
}

# ============================================================
# 检测 ColorOS
# ============================================================
check_coloros() {
    IS_COLOROS="false"
    COLOROS_VERSION=""

    if [ -f /system/build.prop ]; then
        if grep -q "ro.build.version.oplusrom" /system/build.prop 2>/dev/null; then
            IS_COLOROS="true"
            COLOROS_VERSION=$(grep "ro.build.version.oplusrom" /system/build.prop 2>/dev/null | cut -d'=' -f2 | tr -d '[:space:]')
        fi
    fi

    # getprop 即使属性不存在通常也会返回 0；必须同时确认属性值非空。
    # 原来的仅检查返回码会把所有 Android ROM（包括 HyperOS）误判为 ColorOS。
    if [ "$IS_COLOROS" = "false" ]; then
        _oplus_ver=$(getprop ro.build.version.oplusrom 2>/dev/null)
        if [ -n "$_oplus_ver" ]; then
            IS_COLOROS="true"
            COLOROS_VERSION="$_oplus_ver"
        elif [ -d /data/oplus/os ] || [ -d /system_ext/oplus ]; then
            IS_COLOROS="true"
            COLOROS_VERSION="unknown"
        fi
    fi

    if [ "$IS_COLOROS" = "true" ]; then
        log_message "INFO" "检测到 ColorOS 版本: $COLOROS_VERSION"
    fi
}

# ============================================================
# 检测 HyperOS / MIUI（小米/红米/POCO）
# ============================================================
# HyperOS 优先用 ro.mi.os.version.* 判断（MIUI 时代没有这几个属性）
# 找不到再退回 ro.miui.ui.version.code 判断老 MIUI 机型
check_hyperos() {
    IS_HYPEROS="false"
    HYPEROS_VERSION=""

    if getprop ro.mi.os.version.name >/dev/null 2>&1 && [ -n "$(getprop ro.mi.os.version.name 2>/dev/null)" ]; then
        IS_HYPEROS="true"
        HYPEROS_VERSION=$(getprop ro.mi.os.version.name 2>/dev/null || echo "")
    elif getprop ro.miui.ui.version.code >/dev/null 2>&1 && [ -n "$(getprop ro.miui.ui.version.code 2>/dev/null)" ]; then
        IS_HYPEROS="true"
        HYPEROS_VERSION="MIUI-$(getprop ro.miui.ui.version.code 2>/dev/null || echo "")"
    fi

    if [ "$IS_HYPEROS" = "true" ]; then
        log_message "INFO" "检测到 HyperOS/MIUI 版本: $HYPEROS_VERSION"
    fi
}

# ============================================================
# 从文件名提取字体族名（关键函数）
# 支持字重后缀的移除（英文和中文后缀变体）
# ============================================================
detect_font_family() {
    result="${1%.*}"
    case "$result" in *"-Regular") result="${result%-Regular}" ;; esac
    case "$result" in *"-Bold") result="${result%-Bold}" ;; esac
    case "$result" in *"-Light") result="${result%-Light}" ;; esac
    case "$result" in *"-Medium") result="${result%-Medium}" ;; esac
    case "$result" in *"-SemiBold") result="${result%-SemiBold}" ;; esac
    case "$result" in *"-Thin") result="${result%-Thin}" ;; esac
    case "$result" in *"-Black") result="${result%-Black}" ;; esac
    case "$result" in *"-Heavy") result="${result%-Heavy}" ;; esac
    case "$result" in *"-Italic") result="${result%-Italic}" ;; esac
    case "$result" in *"-Oblique") result="${result%-Oblique}" ;; esac
    case "$result" in *"-Condensed") result="${result%-Condensed}" ;; esac
    case "$result" in *"-Extended") result="${result%-Extended}" ;; esac
    case "$result" in *"-regular") result="${result%-regular}" ;; esac
    case "$result" in *"-bold") result="${result%-bold}" ;; esac
    case "$result" in *"-light") result="${result%-light}" ;; esac
    case "$result" in *"-medium") result="${result%-medium}" ;; esac
    case "$result" in *"-semibold") result="${result%-semibold}" ;; esac
    case "$result" in *"-thin") result="${result%-thin}" ;; esac
    case "$result" in *"-black") result="${result%-black}" ;; esac
    case "$result" in *"-heavy") result="${result%-heavy}" ;; esac
    case "$result" in *"-italic") result="${result%-italic}" ;; esac
    case "$result" in *"-oblique") result="${result%-oblique}" ;; esac
    case "$result" in *"-condensed") result="${result%-condensed}" ;; esac
    case "$result" in *"-extended") result="${result%-extended}" ;; esac
    case "$result" in *"-常规") result="${result%-常规}" ;; esac
    case "$result" in *"-粗体") result="${result%-粗体}" ;; esac
    case "$result" in *"-细体") result="${result%-细体}" ;; esac
    case "$result" in *"-中等") result="${result%-中等}" ;; esac
    case "$result" in *"-半粗") result="${result%-半粗}" ;; esac
    case "$result" in *"-极细") result="${result%-极细}" ;; esac
    case "$result" in *"-特粗") result="${result%-特粗}" ;; esac
    case "$result" in *"-重") result="${result%-重}" ;; esac
    case "$result" in *"-斜体") result="${result%-斜体}" ;; esac
    case "$result" in *"-轻") result="${result%-轻}" ;; esac
    while true; do
        case "$result" in " ") result="" ;; *[[:space:]]) result="${result%?}" ;; *-) result="${result%-}" ;; *_) result="${result%_}" ;; *) break ;; esac
    done
    echo "$result"
}

# ============================================================
# 字重相关辅助函数（原分别定义在 font_manager.sh，现移到这里做唯一来源，
# 这样 customize.sh 刷入阶段也能用它们做多字重映射，不用只等切换字体时才生效）
# ============================================================

# 从文件名提取字重标识
detect_font_weight() {
    filename="$1"
    lower=$(echo "$filename" | tr '[:upper:]' '[:lower:]')

    # 可变字体特殊标记
    case "$lower" in
        *variable*|*var*|*可变*|*vf*) echo "variable"; return ;;
    esac

    case "$lower" in
        *thin*|*极细*) echo "thin" ;;
        *light*|*细体*) echo "light" ;;
        *medium*|*中等*) echo "medium" ;;
        *semibold*|*半粗*) echo "semibold" ;;
        *bold*|*粗体*) echo "bold" ;;
        *black*|*heavy*|*特粗*|*重*) echo "black" ;;
        *) echo "regular" ;;
    esac
}

# 字重名首字母大写（纯 shell，不用 sed）
capitalize_first() {
    case "$1" in
        thin) echo "Thin" ;; light) echo "Light" ;; regular) echo "Regular" ;;
        medium) echo "Medium" ;; semibold) echo "SemiBold" ;; bold) echo "Bold" ;;
        black) echo "Black" ;; variable) echo "Variable" ;; *) echo "$1" ;;
    esac
}

# 字重排序权重（用于排序显示）
weight_sort_order() {
    case "$1" in
        thin) echo 1 ;;
        light) echo 2 ;;
        regular) echo 3 ;;
        medium) echo 4 ;;
        semibold) echo 5 ;;
        bold) echo 6 ;;
        black) echo 7 ;;
        variable) echo 0 ;;
        *) echo 9 ;;
    esac
}

# 扫描字体族的字重变体，依赖 $USER_FONTS_DIR（customize.sh 和 font_manager.sh
# 都会在调用这些函数之前设置好这个变量）
# 输出格式："字重1,字重2,字重3"
scan_family_weights() {
    family="$1"
    weights=""
    for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$f" ] || continue
        name=$(basename "$f")
        fam=$(detect_font_family "$name")
        [ "$fam" = "$family" ] || continue
        w=$(detect_font_weight "$name")
        case ",$weights," in *",$w,"*) ;; *) weights="$weights,$w" ;; esac
    done
    case "$weights" in ,*) weights="${weights#,}" ;; esac
    echo "$weights"
}

# 获取字体族中指定字重的文件路径
get_weight_file() {
    family="$1"
    target_w="$2"
    fallback_file=""
    for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$f" ] || continue
        name=$(basename "$f")
        fam=$(detect_font_family "$name")
        [ "$fam" = "$family" ] || continue
        [ -z "$fallback_file" ] && fallback_file="$f"
        w=$(detect_font_weight "$name")
        [ "$w" = "$target_w" ] && { echo "$f"; return; }
    done
    [ -n "$fallback_file" ] && echo "$fallback_file"
}

# ============================================================
# 判断字体文件是否为等宽字体
# ============================================================
is_monospace_font() {
    filename="$1"
    case "$filename" in
        *Mono*|*mono*|*Courier*|*courier*|*Code*|*code*|*Consolas*|*consolas*|*JetBrains*|*jetbrains*|*FiraCode*|*firacode*)
            return 0 ;;
        *) return 1 ;;
    esac
}

# ============================================================
# 判断字体文件是否为衬线字体
# ============================================================
is_serif_font() {
    filename="$1"
    case "$filename" in
        *Serif*|*serif*|*Song*|*song*|*宋*|*明体*|*明朝*)
            return 0 ;;
        *) return 1 ;;
    esac
}

# ============================================================
# 判断字体是否为可变字体
# ============================================================
is_variable_font() {
    filepath="$1"
    if [ ! -f "$filepath" ]; then
        return 1
    fi
    # 检查文件名中是否包含 Variable 或 VF
    basename=$(basename "$filepath")
    case "$basename" in
        *Variable*|*variable*|*VF*|*vf*|*VF*) return 0 ;;
    esac
    # 通过字体表检查（可变字体包含 fvar 表）；Android 环境没有 strings 时直接二进制搜索。
    if command -v strings >/dev/null 2>&1; then
        strings "$filepath" 2>/dev/null | grep -q "fvar" && return 0
    else
        grep -a -q "fvar" "$filepath" 2>/dev/null && return 0
    fi
    return 1
}

# ============================================================
# 读取字体配置
# 支持 font.conf 配置文件和自动推断
# ============================================================
read_font_config() {
    font_id="$1"
    key="$2"
    config_file="$FONT_DIR/$font_id/font.conf"
    module_font_dir="$MODULE_DIR/fonts"

    # 先尝试从模块内置配置读取
    if [ -f "$config_file" ]; then
        value=$(grep -E "^${key}=" "$config_file" 2>/dev/null | cut -d'=' -f2- | head -n1)
        if [ -n "$value" ]; then
            echo "$value"
            return 0
        fi
    fi

    # 尝试从用户字体目录的配置读取
    user_config="$USER_FONTS_DIR/$font_id.conf"
    if [ -f "$user_config" ]; then
        value=$(grep -E "^${key}=" "$user_config" 2>/dev/null | cut -d'=' -f2- | head -n1)
        if [ -n "$value" ]; then
            echo "$value"
            return 0
        fi
    fi

    # 自动生成默认值
    case "$key" in
        name)
            echo "$font_id" ;;
        description)
            echo "自定义字体" ;;
        version)
            echo "1.0" ;;
        author)
            echo "用户" ;;
        supports_latin)
            echo "true" ;;
        supports_cjk)
            # 根据字体名称推断 CJK 支持（纯 shell case，兼容 toybox）
            case "$font_id" in
                *[Cc][Jj][Kk]*|*[Mm]i[Ss]ans*|*[Mm][Ii][Uu][Ii]*|*[Oo]ppo*|*[Hh]armony*|*Heiti*|*heiti*|*[Ss]ongti*|*Songti*|*[Kk]aiti*|*[Ww]enkai*|*[Pp]ing[Ff]ang*|*[Nn]oto*[Ss][Cc]*|*花轮丸*|*得意黑*|*霞鹜*|*思源*|*Sarasa*|*LXGW*|*Maple*|*MapleMono*)
                    echo "true" ;;
                *) echo "false" ;;
            esac
            ;;
        has_monospace)
            case "$font_id" in
                *[Mm]ono*|*[Cc]ourier*|*[Cc]ode*|*[Cc]onsolas*|*[Jj]et[Bb]rains*|*[Ff]ira[Cc]ode*|*等宽*)
                    echo "true" ;;
                *) echo "false" ;;
            esac
            ;;
        has_serif)
            case "$font_id" in
                *[Ss]erif*|*[Ss]ong*|*宋*|*明体*|*明朝*)
                    echo "true" ;;
                *) echo "false" ;;
            esac
            ;;
        is_variable)
            # 需要实际检查字体文件
            font_file=$(find_font_file "$font_id")
            if [ -n "$font_file" ] && is_variable_font "$font_file"; then
                echo "true"
            else
                echo "false"
            fi
            ;;
        *)
            echo "" ;;
    esac
}

# ============================================================
# 查找字体族的第一个字体文件路径
# ============================================================
find_font_file() {
    font_id="$1"
    search_dirs="$USER_FONTS_DIR $LEGACY_FONTS_DIR $MODULE_DIR/system/fonts $MODULE_DIR/fonts"

    for dir in $search_dirs; do
        [ -d "$dir" ] || continue
        for f in "$dir"/*.ttf "$dir"/*.otf "$dir"/*.ttc "$dir"/*.TTF "$dir"/*.OTF "$dir"/*.TTC; do
            [ -f "$f" ] || continue
            fam=$(detect_font_family "$(basename "$f")")
            if [ "$fam" = "$font_id" ]; then
                echo "$f"
                return 0
            fi
        done
    done
    echo ""
}

# ============================================================
# 扫描已安装的字体族（从模块 system/fonts/）
# ============================================================
scan_installed_families() {
    dir="${1:-$MODULE_DIR/system/fonts}"
    families=""
    if [ -d "$dir" ]; then
        for f in "$dir"/*.ttf "$dir"/*.otf "$dir"/*.ttc "$dir"/*.TTF "$dir"/*.OTF "$dir"/*.TTC; do
            [ -f "$f" ] || continue
            fam=$(detect_font_family "$(basename "$f")")
            case " $families " in
                *" $fam "*) ;;
                *) families="$families $fam" ;;
            esac
        done
    fi
    # 去除首尾空格
    echo "$families" | sed 's/^ *//;s/ *$//'
}

# ============================================================
# 扫描用户字体（从 /sdcard/LuoShu/fonts/）
# ============================================================
scan_user_families() {
    dir="$USER_FONTS_DIR"
    families=""
    if [ -d "$dir" ]; then
        for f in "$dir"/*.ttf "$dir"/*.otf "$dir"/*.ttc "$dir"/*.TTF "$dir"/*.OTF "$dir"/*.TTC; do
            [ -f "$f" ] || continue
            fam=$(detect_font_family "$(basename "$f")")
            case " $families " in
                *" $fam "*) ;;
                *) families="$families $fam" ;;
            esac
        done
    fi
    echo "$families" | sed 's/^ *//;s/ *$//'
}

# ============================================================
# 获取单个字体信息 JSON
# ============================================================
get_font_info_json() {
    font_id="$1"
    name=$(read_font_config "$font_id" "name")
    desc=$(read_font_config "$font_id" "description")
    version=$(read_font_config "$font_id" "version")
    author=$(read_font_config "$font_id" "author")
    cjk=$(read_font_config "$font_id" "supports_cjk")
    mono=$(read_font_config "$font_id" "has_monospace")
    serif=$(read_font_config "$font_id" "has_serif")
    variable=$(read_font_config "$font_id" "is_variable")

    # JSON 转义
    name=$(echo "$name" | sed 's/"/\\"/g')
    desc=$(echo "$desc" | sed 's/"/\\"/g')
    version=$(echo "$version" | sed 's/"/\\"/g')
    author=$(echo "$author" | sed 's/"/\\"/g')

    printf '{"id":"%s","name":"%s","description":"%s","version":"%s","author":"%s","supports_cjk":%s,"has_monospace":%s,"has_serif":%s,"is_variable":%s}' \
        "$font_id" "$name" "$desc" "$version" "$author" "$cjk" "$mono" "$serif" "$variable"
}

# ============================================================
# 获取所有可用字体的 JSON（供 WebUI 用）
# ============================================================
get_all_fonts_json() {
    current_font=$(get_current_font_id)
    installed=$(scan_installed_families)
    user=$(scan_user_families)

    # 合并去重（先已安装，再用户字体）
    all="$installed"
    for fam in $user; do
        case " $all " in
            *" $fam "*) ;;
            *) all="$all $fam" ;;
        esac
    done

    first=true
    printf '['

    # 先输出当前字体（如果存在）
    if [ -n "$current_font" ] && [ "$current_font" != "default" ]; then
        for fam in $all; do
            [ "$fam" = "$current_font" ] || continue
            [ "$first" = true ] || printf ','
            first=false
            get_font_info_json "$fam"
        done
    fi

    # 再输出 default 选项
    if [ "$first" = true ]; then
        first=false
    else
        printf ','
    fi
    printf '{"id":"default","name":"系统默认","description":"使用系统原始字体","version":"","author":"","supports_cjk":true,"has_monospace":true,"has_serif":true,"is_variable":false}'

    # 最后输出其他字体
    for fam in $all; do
        [ "$fam" = "$current_font" ] && continue
        [ -z "$fam" ] && continue
        printf ','
        get_font_info_json "$fam"
    done

    printf ']'
}

# ============================================================
# 获取当前字体 ID
# ============================================================
get_current_font_id() {
    active=""
    
    # 尝试读取配置文件
    if [ -f "$CONFIG_DIR/active_font.conf" ]; then
        active=$(head -n1 "$CONFIG_DIR/active_font.conf" 2>/dev/null | tr -d '\r\n')
    fi
    
    # 如果配置是 default 或空，推断实际字体
    if [ -z "$active" ] || [ "$active" = "default" ]; then
        installed=""
        if [ -d "$MODULE_DIR/system/fonts" ]; then
            for f in "$MODULE_DIR/system/fonts"/*.ttf "$MODULE_DIR/system/fonts"/*.otf "$MODULE_DIR/system/fonts"/*.ttc; do
                [ -f "$f" ] || continue
                name=$(basename "$f")
                case "$name" in
                    NotoColorEmoji*|NotoColorEmojiFlags*|NotoSansSymbols*) continue ;;
                esac
                installed=$(detect_font_family "$name")
                break
            done
        fi
        # system/fonts 没找到则扫描公开字体目录
        if [ -z "$installed" ] && [ -d "$USER_FONTS_DIR" ]; then
            for f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
                [ -f "$f" ] || continue
                installed=$(detect_font_family "$(basename "$f")")
                break
            done
        fi
        [ -n "$installed" ] && active="$installed"
    fi
    
    [ -z "$active" ] && active="default"
    echo "$active"
}

# ============================================================
# 备份原始字体（首次安装时调用）
# ============================================================
backup_original_fonts() {
    backup_dir="$MODULE_DIR/backup"
    marker="$backup_dir/.backup_done"

    # 已备份则跳过
    [ -f "$marker" ] && return 0

    log_message "INFO" "备份原始字体..."
    mkdir -p "$backup_dir" 2>/dev/null || {
        log_message "ERROR" "无法创建备份目录"
        return 1
    }

    # 尝试从挂载点查找原始字体
    sys_fonts="/system/fonts"
    if [ -d "$sys_fonts" ]; then
        for f in "$sys_fonts"/*.ttf "$sys_fonts"/*.otf "$sys_fonts"/*.ttc; do
            [ -f "$f" ] || continue
            cp -f "$f" "$backup_dir/" 2>/dev/null || true
        done
    fi

    touch "$marker" 2>/dev/null || true
    log_message "INFO" "原始字体备份完成"
}

# ============================================================
# 设置字体文件权限
# ============================================================
set_font_permissions() {
    target_dir="$1"
    [ -d "$target_dir" ] || return 1

    # 设置目录权限
    chmod 755 "$target_dir" 2>/dev/null || true

    # 设置字体文件权限
    for f in "$target_dir"/*.ttf "$target_dir"/*.otf "$target_dir"/*.ttc "$target_dir"/*.TTF "$target_dir"/*.OTF "$target_dir"/*.TTC; do
        [ -f "$f" ] || continue
        chown 0:0 "$f" 2>/dev/null || true
        chmod 644 "$f" 2>/dev/null || true
    done

    log_message "INFO" "字体权限已设置: $target_dir"
}

# ============================================================
# 刷新字体缓存
# ============================================================
refresh_font_cache() {
    log_message "INFO" "刷新字体缓存..."

    # 通用 Android 字体缓存刷新
    if command -v cmd >/dev/null 2>&1; then
        cmd font system --update >/dev/null 2>&1 || true
    fi

    # ColorOS 特定刷新
    if [ "$IS_COLOROS" = "true" ]; then
        if [ -f /system/bin/oplus-font ]; then
            oplus-font refresh >/dev/null 2>&1 || true
        fi
        # 尝试重启字体相关服务
        stop oplus-font >/dev/null 2>&1 || true
        start oplus-font >/dev/null 2>&1 || true
    fi

    log_message "INFO" "字体缓存刷新完成"
}

# ============================================================
# 字重映射：将文件名后缀映射到 Android 标准字重
# ============================================================
map_font_weight() {
    filename="$1"
    lower_name=$(echo "$filename" | tr '[:upper:]' '[:lower:]')

    case "$lower_name" in
        *thin*)       echo 100 ;;
        *extralight*|*ultralight*|*w200*) echo 200 ;;
        *light*|*w300*) echo 300 ;;
        *regular*|*normal*|*roman*|*book*|*w400*) echo 400 ;;
        *medium*|*w500*) echo 500 ;;
        *semibold*|*demibold*|*w600*) echo 600 ;;
        *bold*|*w700*) echo 700 ;;
        *extrabold*|*ultrabold*|*w800*) echo 800 ;;
        *black*|*heavy*|*w900*) echo 900 ;;
        *) echo 400 ;;  # 默认 Regular
    esac
}

# ============================================================
# 获取字体的样式属性（是否为斜体）
# ============================================================
map_font_style() {
    filename="$1"
    lower_name=$(echo "$filename" | tr '[:upper:]' '[:lower:]')

    case "$lower_name" in
        *italic*|*oblique*|*slant*|*斜体*)
            echo "italic" ;;
        *)
            echo "normal" ;;
    esac
}

# ============================================================
# 安全复制（带校验）
# ============================================================
safe_copy() {
    src="$1"
    dst="$2"

    [ -f "$src" ] || { log_message "ERROR" "源文件不存在: $src"; return 1; }

    cp -f "$src" "$dst" 2>/dev/null || {
        log_message "ERROR" "复制失败: $src -> $dst"
        return 1
    }

    # 校验（使用 stat 替代 wc -c，兼容 Magisk toybox）
    if [ -f "$dst" ]; then
        src_size=$(stat -c "%s" "$src" 2>/dev/null || ls -l "$src" 2>/dev/null | awk '{print $5}')
        dst_size=$(stat -c "%s" "$dst" 2>/dev/null || ls -l "$dst" 2>/dev/null | awk '{print $5}')
        if [ -n "$src_size" ] && [ "$src_size" = "$dst_size" ] && [ "$src_size" -gt 0 ] 2>/dev/null; then
            return 0
        else
            log_message "ERROR" "文件校验失败: $src -> $dst"
            return 1
        fi
    fi
    return 1
}

# ============================================================
# ColorOS 所有已知字体文件名（统一来源，全模块使用）
# 包含：常规SysFont/SysSans + DIN锁屏时钟字体 + Opposans系列
# ============================================================
get_all_coloros_names() {
    echo "SysSans-Hant-Regular SysSans-Hans-Regular SysFont-Static-Regular SysFont-Myanmar SysFont-Hant-Regular SysFont-Hans-Regular SysFont-Regular SysSans-En-Regular SysSans-En-Bold SysSans-En-Light SysSans-En-Medium SysSans-En-Thin SysSans-En-Black SysFont-Bold SysFont-Light SysFont-Medium SysFont-Thin SysFont-Black SysFont-Hans-Bold SysFont-Hans-Light SysFont-Hans-Medium SysFont-Hans-Thin SysFont-Hant-Bold SysFont-Hant-Light SysFont-Hant-Medium SysFont-Hant-Thin SysSans-Hant-Bold SysSans-Hant-Light SysSans-Hant-Medium SysSans-Hans-Bold SysSans-Hans-Light SysSans-Hans-Medium SysFont-Static-Bold SysFont-Static-Light SysFont-Static-Medium DINCondensedBold DINPro-Bold DINPro-Medium DINPro-Regular OPPODIN-Bold OPPODIN-Medium OPPODIN-Regular OPPODINCondensed-Bold OPPODINCondensed-Medium OPPODINCondensed-Regular Opposans-En-Regular Opposans-Hans-Regular Opposans-En-Bold Opposans-Hans-Bold Opposans-En-Medium Opposans-Hans-Medium Opposans-En-Light Opposans-Hans-Light"
}

# ============================================================
# 日志级别控制（可通过 LOG_LEVEL 环境变量控制详细程度）
# 级别：DEBUG=0, INFO=1, WARN=2, ERROR=3
# 默认 INFO，DEBUG 仅在 LOG_LEVEL=DEBUG 时输出
# ============================================================
LOG_LEVEL="${LOG_LEVEL:-INFO}"
log_level_value() {
    case "$1" in
        DEBUG) echo 0 ;; INFO) echo 1 ;; WARN) echo 2 ;; ERROR) echo 3 ;;
        *) echo 1 ;;
    esac
}
should_log() {
    min_level="$1"
    current_val=$(log_level_value "$LOG_LEVEL")
    min_val=$(log_level_value "$min_level")
    [ "$current_val" -le "$min_val" ] 2>/dev/null && return 0 || return 1
}

# ============================================================
# 提取字体族名中的字重标识（用于 fonts.xml 生成）
# ============================================================
get_weight_from_filename() {
    filename="$1"
    map_font_weight "$filename"
}
