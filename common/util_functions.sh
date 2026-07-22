#!/system/bin/sh
set +e
# ============================================================
# 洛书 - 工具函数库 (util_functions.sh)
# 作者：惜故里丶
# 版本：v2.0.0
# 功能：提供字体模块所需的所有通用工具函数
# ============================================================

# ---------- 模块路径定义 ----------
# 允许外部覆盖（font_manager.sh 会在加载前设置 MODULE_DIR）
MODULE_DIR="${MODULE_DIR:-/data/adb/modules/LuoShu}"
CONFIG_DIR="${MODULE_DIR}/config"
FONT_DIR="${MODULE_DIR}/fonts"
LOG_DIR="${MODULE_DIR}/logs"
LOG_FILE="${LOG_DIR}/fontswitch.log"
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
USER_REPORT_DIR="$LUOSHU_PUBLIC_DIR/reports"
USER_IMPORT_DIR="$LUOSHU_PUBLIC_DIR/import"
LEGACY_FONTS_DIR="${LEGACY_FONTS_DIR:-/sdcard/Fonts}"


# 创建公开目录并兼容迁移旧版 /sdcard/Fonts。迁移采用复制而不是移动，
# 避免用户仍使用旧版模块时找不到原文件。
ensure_public_storage() {
    mkdir -p "$USER_FONTS_DIR" "$USER_REPORT_DIR" "$USER_IMPORT_DIR" 2>/dev/null || true
    chmod 0775 "$LUOSHU_PUBLIC_DIR" "$USER_FONTS_DIR" "$USER_REPORT_DIR" "$USER_IMPORT_DIR" 2>/dev/null || true
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
    case "$result" in *"-ExtraBold") result="${result%-ExtraBold}" ;; esac
    case "$result" in *"-UltraBold") result="${result%-UltraBold}" ;; esac
    case "$result" in *"-ExtraLight") result="${result%-ExtraLight}" ;; esac
    case "$result" in *"-UltraLight") result="${result%-UltraLight}" ;; esac
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
    case "$result" in *"-extrabold") result="${result%-extrabold}" ;; esac
    case "$result" in *"-ultrabold") result="${result%-ultrabold}" ;; esac
    case "$result" in *"-extralight") result="${result%-extralight}" ;; esac
    case "$result" in *"-ultralight") result="${result%-ultralight}" ;; esac
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
        *thin*|*-100.*|*_100.*|*极细*) echo "thin" ;;
        *extralight*|*ultralight*|*extra-light*|*ultra-light*|*-200.*|*_200.*) echo "extralight" ;;
        *light*|*-300.*|*_300.*|*细体*) echo "light" ;;
        *medium*|*-500.*|*_500.*|*中等*) echo "medium" ;;
        *semibold*|*demibold*|*-600.*|*_600.*|*半粗*) echo "semibold" ;;
        *extrabold*|*ultrabold*|*extra-bold*|*ultra-bold*|*-800.*|*_800.*) echo "extrabold" ;;
        *bold*|*-700.*|*_700.*|*粗体*) echo "bold" ;;
        *black*|*heavy*|*-900.*|*_900.*|*特粗*|*重体*) echo "black" ;;
        *) echo "regular" ;;
    esac
}

# 字重名首字母大写（纯 shell，不用 sed）
capitalize_first() {
    case "$1" in
        thin) echo "Thin" ;; extralight) echo "ExtraLight" ;; light) echo "Light" ;;
        regular) echo "Regular" ;; medium) echo "Medium" ;; semibold) echo "SemiBold" ;;
        bold) echo "Bold" ;; extrabold) echo "ExtraBold" ;; black) echo "Black" ;;
        variable) echo "Variable" ;; *) echo "$1" ;;
    esac
}

# 字重排序权重（用于排序显示）
weight_sort_order() {
    case "$1" in
        thin) echo 1 ;;
        extralight) echo 2 ;;
        light) echo 3 ;;
        regular) echo 4 ;;
        medium) echo 5 ;;
        semibold) echo 6 ;;
        bold) echo 7 ;;
        extrabold) echo 8 ;;
        black) echo 9 ;;
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
    # 统一按从细到粗排序，避免文件名/目录顺序导致 WebUI 标签顺序混乱。
    sorted=""
    for _role in variable thin extralight light regular medium semibold bold extrabold black; do
        case ",$weights," in
            *",$_role,"*) [ -n "$sorted" ] && sorted="$sorted,"; sorted="$sorted$_role" ;;
        esac
    done
    echo "$sorted"
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
