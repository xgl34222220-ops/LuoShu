#!/system/bin/sh
# 洛书 - ROM 适配层 (rom_adapters.sh)
# 提供通用 ROM 回退映射；ColorOS、HyperOS、OriginOS 与 Flyme 的分区感知增强层会在运行时覆盖对应入口。
#
# 新增 ROM 适配方法：
#   1. 用诊断脚本在真机上采集 /system/etc/fonts.xml、font_fallback.xml、
#      /system/fonts/ 目录清单
#   2. 找出该 ROM 实际渲染系统文字用到的物理字体文件名（注意：不能只看 fonts.xml，
#      HyperOS 等 ROM 有不经过 fonts.xml 的隐藏字体机制，要以 /system/fonts/ 实际
#      文件名 + 系统显示效果验证为准）
#   3. 在下面新增 get_all_<rom>_files() + copy_as_<rom>()，并在 apply_font_by_rom()
#      里加一个分支

# 校验字体文件复制是否成功（防御性检查）：确认目标文件存在且不是空文件/异常小文件。
# 正常字体文件至少几十 KB 起步，如果复制后小于 1KB，大概率是复制失败或者源文件本身
# 有问题——这种畸形字体文件如果被系统的 native 字体渲染引擎解析，容易直接把整个
# 进程崩掉而不是优雅报错，所以在复制阶段就要能发现，而不是留到运行时才暴露，
# 也方便以后遇到"应用闪退"这类反馈时，能直接从日志里判断是不是这一步出的问题
_verify_font_copy() {
    f="$1"
    if [ ! -s "$f" ]; then
        _log_step "  警告：$(basename "$f") 复制后为空或不存在，可能导致相关文字渲染异常"
        return 1
    fi
    fsize=$(wc -c < "$f" 2>/dev/null | tr -d '[:space:]')
    case "$fsize" in ''|*[!0-9]*) fsize=0 ;; esac
    if [ "$fsize" -lt 1024 ]; then
        _log_step "  警告：$(basename "$f") 只有 ${fsize} 字节，明显小于正常字体文件，可能已损坏"
        return 1
    fi
    return 0
}

# 为同一份字体创建多个 ROM 别名时优先使用硬链接。几十个别名共享同一组
# 数据块，既保持每个目标路径都是普通字体文件，也避免把 20MB 字体复制成
# 1GB 以上。若文件系统不支持硬链接则自动退回普通复制，不牺牲兼容性。
_font_store_reset() {
    dest_dir="$1"
    rm -rf "$dest_dir/.luoshu-font-store" 2>/dev/null || true
    mkdir -p "$dest_dir/.luoshu-font-store" 2>/dev/null || true
    chmod 755 "$dest_dir/.luoshu-font-store" 2>/dev/null || true
}

_font_anchor() {
    src="$1"
    dest_dir="$2"
    key="$3"
    anchor="$dest_dir/.luoshu-font-store/${key}.font"
    module="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    normalizer="$module/common/font_metrics_normalize.py"
    rm -f "$anchor" 2>/dev/null || true

    if [ -f "$normalizer" ]; then
        if type _luoshu_font_config_exec >/dev/null 2>&1; then
            _luoshu_font_config_exec "$normalizer" --input "$src" --output "$anchor" >/dev/null 2>&1 || return 1
        elif [ -x "$module/common/python/bin/luoshu-python" ]; then
            pyroot="$module/common/python"
            PYTHONHOME="$pyroot"             PYTHONPATH="$pyroot/lib/python3.14:$pyroot/lib/python3.14/site-packages"             LD_LIBRARY_PATH="$pyroot/lib:$pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"                 "$pyroot/bin/luoshu-python" "$normalizer" --input "$src" --output "$anchor" >/dev/null 2>&1 || return 1
        elif command -v python3 >/dev/null 2>&1; then
            python3 "$normalizer" --input "$src" --output "$anchor" >/dev/null 2>&1 || return 1
        else
            return 1
        fi
    else
        cp -f "$src" "$anchor" 2>/dev/null || return 1
    fi
    chmod 644 "$anchor" 2>/dev/null || true
    echo "$anchor"
}

_font_alias() {
    anchor="$1"
    dest="$2"
    rm -f "$dest" 2>/dev/null || true
    ln "$anchor" "$dest" 2>/dev/null || cp -f "$anchor" "$dest" 2>/dev/null || return 1
    chmod 644 "$dest" 2>/dev/null || true
}

# 用于 system/fonts -> system_ext/product 的跨目录别名。它们都位于模块目录的
# 同一 /data 文件系统，通常可以共享 inode；不支持时仍安全退回复制。
link_or_copy_font() {
    src="$1"
    dest="$2"
    rm -f "$dest" 2>/dev/null || true
    ln "$src" "$dest" 2>/dev/null || cp -f "$src" "$dest" 2>/dev/null || return 1
    chmod 644 "$dest" 2>/dev/null || true
}

# 只为 ROM 真正存在的目标创建别名，避免 Hybrid Mount 为不存在的路径
# 生成大量 staging 节点，降低 No space left on device / 挂载上限风险。
_rom_font_target_exists() {
    _name="$1"
    for _root in /system/fonts /system_ext/fonts /product/fonts /my_product/fonts /vendor/fonts; do
        [ -e "$_root/${_name}.ttf" ] || [ -e "$_root/${_name}.otf" ] || [ -e "$_root/${_name}.ttc" ] && return 0
    done
    return 1
}

_rom_exact_target_exists() {
    _file="$1"
    for _root in /system/fonts /system_ext/fonts /product/fonts /my_product/fonts /vendor/fonts; do
        [ -e "$_root/$_file" ] && return 0
    done
    return 1
}

# ============================================================
# ColorOS（OPPO/一加/realme 同属 oplus 系）
# ============================================================
# 已通过真机数据（ColorOS16 / PLK110）核对，48/50 个文件命中
# 分区感知映射由 coloros_global.sh 负责；这里仅保留缺少增强层时的最小回退。

# ColorOS 里字重专属文件（用于第三步"额外覆盖"，Regular 已在基础8个里处理过）
_coloros_extra_names() {
    echo "SysSans-En-Bold SysSans-En-Light SysSans-En-Medium SysSans-En-Thin SysSans-En-Black SysFont-Bold SysFont-Light SysFont-Medium SysFont-Thin SysFont-Black SysFont-Hans-Bold SysFont-Hans-Light SysFont-Hans-Medium SysFont-Hans-Thin SysFont-Hant-Bold SysFont-Hant-Light SysFont-Hant-Medium SysFont-Hant-Thin SysSans-Hant-Bold SysSans-Hant-Light SysSans-Hant-Medium SysSans-Hans-Bold SysSans-Hans-Light SysSans-Hans-Medium SysFont-Static-Bold SysFont-Static-Light SysFont-Static-Medium DINCondensedBold DINPro-Bold DINPro-Medium DINPro-Regular OPPODIN-Bold OPPODIN-Medium OPPODIN-Regular OPPODINCondensed-Bold OPPODINCondensed-Medium OPPODINCondensed-Regular Opposans-En-Regular Opposans-Hans-Regular Opposans-En-Bold Opposans-Hans-Bold Opposans-En-Medium Opposans-Hans-Medium Opposans-En-Light Opposans-Hans-Light OPSans-En-Regular Roboto-Regular Roboto-Medium Roboto-Bold Roboto-Light Roboto-Thin RobotoFlex-Regular RobotoStatic-Regular GoogleSans-Regular GoogleSans-Medium GoogleSans-Bold GoogleSansText-Regular GoogleSansText-Medium GoogleSansText-Bold GoogleSansFlex-Regular SourceSansPro-Regular SourceSansPro-SemiBold SourceSansPro-Bold"
}

if ! type get_all_coloros_names >/dev/null 2>&1; then
    get_all_coloros_names() {
        printf '%s\n' "SysSans-Hant-Regular SysSans-Hans-Regular SysFont-Static-Regular SysFont-Hant-Regular SysFont-Hans-Regular SysFont-Regular SysSans-En-Regular $(_coloros_extra_names)"
    }
fi

# copy_as_coloros: 把用户字体覆盖为 ColorOS 认识的文件名
#   src        用户选择的字体文件
#   dest_dir   目标目录（安装时是 $MODPATH/system/fonts，切换时是模块已挂载的 system/fonts）
#   mode       full（刷入/首次安装） | quick（切换字体）；两种模式都只生成目标别名，
#              原厂 fallback 由 Overlay 下层保留
#   font_family 可选，若提供且用户字体族有多个字重文件，会额外生成字重变体
copy_as_coloros() {
    src="$1"
    dest_dir="$2"
    mode="${3:-full}"
    font_family="${4:-}"
    sys_count=0
    coloros_count=0
    extra_count=0
    weight_count=0

    # Overlay 目录只需放真正要替换的文件；未出现的原厂 fallback 会自然从
    # 下层 /system/fonts 保留。复制整套原厂字体既无必要，也会让模块暴涨。
    for cname in $(get_all_coloros_names); do
        rm -f "$dest_dir/${cname}.ttf" 2>/dev/null
    done
    _font_store_reset "$dest_dir"
    regular_anchor=$(_font_anchor "$src" "$dest_dir" "regular") || return 1

    _log_step "  正在应用用户字体（ColorOS）..."
    base_names="SysSans-Hant-Regular SysSans-Hans-Regular SysFont-Static-Regular SysFont-Hant-Regular SysFont-Hans-Regular SysFont-Regular SysSans-En-Regular"
    bad_count=0
    for name in $base_names; do
        _rom_font_target_exists "$name" || continue
        if _font_alias "$regular_anchor" "$dest_dir/${name}.ttf"; then
            if _verify_font_copy "$dest_dir/${name}.ttf"; then
                coloros_count=$((coloros_count + 1))
            else
                bad_count=$((bad_count + 1))
            fi
        fi
    done
    _log_step "  已覆盖 $coloros_count 个 ColorOS 基础字体文件"
    [ "$bad_count" -gt 0 ] && _log_step "  ⚠ 其中 $bad_count 个校验异常，请检查源字体文件是否完整"

    for name in $(_coloros_extra_names); do
        _rom_font_target_exists "$name" || continue
        if _font_alias "$regular_anchor" "$dest_dir/${name}.ttf"; then
            extra_count=$((extra_count + 1))
        fi
    done
    [ "$extra_count" -gt 0 ] && _log_step "  已覆盖 $extra_count 个额外字体文件（数字/英文粗体等）"

    # 多字重支持：如果用户字体族提供了 Bold/Medium/Light 等文件，生成对应字重变体
    if [ -n "$font_family" ] && type scan_family_weights >/dev/null 2>&1; then
        weights=$(scan_family_weights "$font_family")
        weight_base="SysSans-Hant SysSans-Hans SysFont-Static SysFont-Myanmar SysFont-Hant SysFont-Hans SysFont SysSans-En"
        for w in $(echo "$weights" | tr ',' ' '); do
            [ "$w" = "regular" ] && continue
            w_file=$(get_weight_file "$font_family" "$w")
            [ -z "$w_file" ] && continue
            w_cap=$(capitalize_first "$w")
            w_anchor=$(_font_anchor "$w_file" "$dest_dir" "$w") || continue
            for base in $weight_base; do
                dest_name="${base}-${w_cap}.ttf"
                _rom_exact_target_exists "$dest_name" || continue
                if _font_alias "$w_anchor" "$dest_dir/$dest_name"; then
                    weight_count=$((weight_count + 1))
                fi
            done
        done
        [ "$weight_count" -gt 0 ] && _log_step "  已创建 $weight_count 个字重变体文件（Bold/Medium/Light等）"
    fi
    return 0
}

# ============================================================
# HyperOS / MIUI（小米/红米/POCO）
# ============================================================
# 通过真机数据核对（HyperOS3 V816 / 25060RK16C）：
# - fonts.xml / font_fallback.xml 里的 sans-serif family 指向 Roboto-*.ttf，
#   官方注释标明这只是"空壳字体，提供度量参数"，不是真正显示用的字体
# - 真正显示中英文用的是 /system/fonts/ 下的 MiSansVF.ttf（默认）、
#   MiSansLatinVF.ttf（拉丁）、MiSansTCVF.ttf（繁体）、MiSansL3.otf（简体，
#   唯一被 XML 显式引用的 MiSans 文件）、MiSansVF_Overlay.ttf（叠加层），
#   这几个文件不经过 fonts.xml，是小米在 framework 层写死加载的
# - /system/fonts/ 下还有 17 个其他文字体系专用的 MiSans*VF.ttf（阿拉伯语/
#   泰语/日语/韩语/藏语等），必须保留不动，否则这些语言会变方块
# - 数字命名的 100.ttf~900.ttf 是无名 family（自动加入默认候选）里引用的
#   权重变体，虽然真机上目前只有 200/300/400/700.ttf 四个文件是真实存在的，
#   但为兼容其他机型/未来版本，10个粗细全部生成
get_all_hyperos_files() {
    echo "MiSansVF.ttf MiSansVF_Overlay.ttf MiSansLatinVF.ttf MiSansTCVF.ttf MiSansL3.otf 100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf Roboto-Thin.ttf Roboto-ThinItalic.ttf Roboto-ExtraLight.ttf Roboto-ExtraLightItalic.ttf Roboto-Light.ttf Roboto-LightItalic.ttf Roboto-Regular.ttf Roboto-Italic.ttf Roboto-Medium.ttf Roboto-MediumItalic.ttf Roboto-SemiBold.ttf Roboto-SemiBoldItalic.ttf Roboto-Bold.ttf Roboto-BoldItalic.ttf Roboto-ExtraBold.ttf Roboto-ExtraBoldItalic.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf"
}

# copy_as_hyperos: 把用户字体覆盖为 HyperOS/MIUI 认识的文件名
#   src         用户选择的字体文件（作为 Regular/默认字重）
#   dest_dir    目标目录
#   mode        full（刷入） | quick（切换）
#   font_family 可选，若提供且用户字体族有多个字重文件，会额外做字重映射
copy_as_hyperos() {
    src="$1"
    dest_dir="$2"
    mode="${3:-full}"
    font_family="${4:-}"
    sys_count=0
    core_count=0
    weight_count=0

    for cfile in $(get_all_hyperos_files); do
        rm -f "$dest_dir/$cfile" 2>/dev/null
    done
    _font_store_reset "$dest_dir"
    regular_anchor=$(_font_anchor "$src" "$dest_dir" "regular") || return 1

    _log_step "  正在应用用户字体（HyperOS/MIUI）..."
    bad_count=0
    for cfile in $(get_all_hyperos_files); do
        _rom_exact_target_exists "$cfile" || continue
        if _font_alias "$regular_anchor" "$dest_dir/$cfile"; then
            if _verify_font_copy "$dest_dir/$cfile"; then
                core_count=$((core_count + 1))
            else
                bad_count=$((bad_count + 1))
            fi
        fi
    done
    _log_step "  已覆盖 $core_count 个 HyperOS/MIUI 核心字体文件"
    [ "$bad_count" -gt 0 ] && _log_step "  ⚠ 其中 $bad_count 个校验异常，请检查源字体文件是否完整"

    # 多字重支持：数字文件（100~900）跟字重数值天然对应，直接精确映射；
    # Roboto 系列按字重名映射；MiSans 那 5 个核心文件本身是变量字体容器/
    # 单一设计，没法按静态字重文件拆分，固定用 Regular（已在上面覆盖过）
    if [ -n "$font_family" ] && type scan_family_weights >/dev/null 2>&1; then
        weights=$(scan_family_weights "$font_family")
        for w in $(echo "$weights" | tr ',' ' '); do
            [ "$w" = "regular" ] && continue
            w_file=$(get_weight_file "$font_family" "$w")
            [ -z "$w_file" ] && continue

            case "$w" in
                thin) num=100; rb="Thin" ;;
                extralight) num=200; rb="ExtraLight" ;;
                light) num=300; rb="Light" ;;
                medium) num=500; rb="Medium" ;;
                semibold) num=600; rb="SemiBold" ;;
                bold) num=700; rb="Bold" ;;
                extrabold) num=800; rb="ExtraBold" ;;
                black) num=900; rb="ExtraBold" ;;  # HyperOS Roboto 系列没有 Black，用 ExtraBold 顶替
                *) num=""; rb="" ;;
            esac

            w_anchor=$(_font_anchor "$w_file" "$dest_dir" "$w") || continue
            if [ -n "$num" ] && _rom_exact_target_exists "${num}.ttf"; then
                if _font_alias "$w_anchor" "$dest_dir/${num}.ttf"; then
                    weight_count=$((weight_count + 1))
                fi
            fi
            if [ -n "$rb" ]; then
                for dest_name in "Roboto-${rb}.ttf" "Roboto-${rb}Italic.ttf"; do
                    _rom_exact_target_exists "$dest_name" || continue
                    if _font_alias "$w_anchor" "$dest_dir/$dest_name"; then
                        weight_count=$((weight_count + 1))
                    fi
                done
            fi
        done
        [ "$weight_count" -gt 0 ] && _log_step "  已创建 $weight_count 个字重变体文件（Bold/Medium/Light等）"
    fi
    return 0
}

# ============================================================
# 通用 AOSP 兜底（未识别的 ROM）
# ============================================================
# 只覆盖标准 AOSP 命名，不保证在深度定制 ROM 上生效，仅作为"至少不报错、
# 尽量生效"的保底方案
get_all_generic_files() {
    echo "Roboto-Regular.ttf Roboto-Bold.ttf Roboto-Italic.ttf Roboto-BoldItalic.ttf Roboto-Medium.ttf Roboto-Light.ttf Roboto-Thin.ttf Roboto-Black.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf NotoSans-Regular.ttf DroidSans.ttf DroidSans-Bold.ttf"
}

copy_as_generic() {
    src="$1"
    dest_dir="$2"
    mode="${3:-full}"
    sys_count=0
    core_count=0

    for cfile in $(get_all_generic_files); do
        rm -f "$dest_dir/$cfile" 2>/dev/null
    done
    _font_store_reset "$dest_dir"
    regular_anchor=$(_font_anchor "$src" "$dest_dir" "regular") || return 1

    _log_step "  正在应用用户字体（通用 AOSP，未识别具体 ROM，效果不保证）..."
    bad_count=0
    for cfile in $(get_all_generic_files); do
        _rom_exact_target_exists "$cfile" || continue
        if _font_alias "$regular_anchor" "$dest_dir/$cfile"; then
            if _verify_font_copy "$dest_dir/$cfile"; then
                core_count=$((core_count + 1))
            else
                bad_count=$((bad_count + 1))
            fi
        fi
    done
    if [ "$core_count" -eq 0 ]; then
        for cfile in Roboto-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf NotoSans-Regular.ttf; do
            _font_alias "$regular_anchor" "$dest_dir/$cfile" && core_count=$((core_count + 1))
        done
        _log_step "  未检测到标准目标，已使用最小 AOSP 兼容映射"
    fi
    _log_step "  已覆盖 $core_count 个通用字体文件"
    [ "$bad_count" -gt 0 ] && _log_step "  ⚠ 其中 $bad_count 个校验异常，请检查源字体文件是否完整"
    return 0
}

# ============================================================
# 统一分发入口
# ============================================================
# apply_font_by_rom: 根据 IS_COLOROS / IS_HYPEROS 全局变量选择对应适配逻辑
# 调用前必须先执行过 check_coloros / check_hyperos（util_functions.sh 提供）
apply_font_by_rom() {
    src="$1"
    dest_dir="$2"
    mode="${3:-full}"
    font_family="${4:-}"

    # HyperOS 优先：避免兼容属性同时存在时误走 ColorOS 文件映射。
    if [ "$IS_HYPEROS" = "true" ]; then
        copy_as_hyperos "$src" "$dest_dir" "$mode" "$font_family"
    elif [ "$IS_COLOROS" = "true" ]; then
        copy_as_coloros "$src" "$dest_dir" "$mode" "$font_family"
    else
        copy_as_generic "$src" "$dest_dir" "$mode"
    fi
}

# 内部日志辅助：customize.sh 环境用 ui_print，font_manager.sh 环境用 echo
_log_step() {
    if command -v ui_print >/dev/null 2>&1; then
        ui_print "$1"
    else
        echo "  [洛书] $1"
    fi
}
