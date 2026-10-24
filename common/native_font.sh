#!/system/bin/sh
# 洛书「全局字体增强（Zygisk）」配置层。默认关闭。
#
#   native_font.sh prepare          由 zygisk/<abi>.so 的 root companion 每次开机调用（字体未就绪时
#                                   由后续应用进程节流重新请求）：把开关、排除名单和已挂载可见的
#                                   洛书正文字体编译成 zygisk/runtime/config.bin、faces.bin（带本次
#                                   boot_id），让出原因写入 runtime/state.conf 的 reason=。
#   native_font.sh status           App 读取开关与本次开机的加载状态（一行 JSON）。
#   native_font.sh set KEY 0|1      App 写开关（KEY: enabled、verbose），重启后生效。
#
# 没有 Zygisk 时 zygisk/*.so 不会被加载，prepare 也不会被调用，本脚本对系统没有任何影响。
# 任何一步失败都只会让 Zygisk 库读不到可用配置并跳过，不改变任何进程。
set +e
MODDIR="${LUOSHU_NATIVE_FONT_MODDIR:-${MODDIR:-}}"
[ -n "$MODDIR" ] || MODDIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)
CONF_DIR="$MODDIR/config"
CONF="$CONF_DIR/native-font.conf"
EXCLUDE="$CONF_DIR/native-font-exclude.list"
FORCE="$CONF_DIR/native-font-force.list"
LEGACY_DIR="${LUOSHU_NATIVE_FONT_LEGACY_DIR:-/data/adb/luoshu_native_font}"
ZDIR="$MODDIR/zygisk"
RUNTIME="$ZDIR/runtime"
BOOT_ID_FILE="${LUOSHU_NATIVE_FONT_BOOT_ID:-/proc/sys/kernel/random/boot_id}"

nf_conf_value() {
    sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n '
}

nf_bool() {
    case "$1" in 1|true|on|yes) echo 1 ;; *) echo 0 ;; esac
}

# 新配置优先；新配置不存在时只读兼容旧的独立模块路径。
nf_setting() {
    _nf_key="$1"
    if [ -f "$CONF" ]; then
        _nf_v=$(nf_conf_value "$CONF" "$_nf_key")
        case "$_nf_key" in
            java_font) [ -n "$_nf_v" ] || _nf_v=1 ;;
        esac
        nf_bool "$_nf_v"
        return 0
    fi
    case "$_nf_key" in
        enabled) [ -f "$LEGACY_DIR/enabled" ] && echo 1 || echo 0 ;;
        verbose) [ -f "$LEGACY_DIR/verbose" ] && echo 1 || echo 0 ;;
        java_font) [ -f "$LEGACY_DIR/java_font.off" ] && echo 0 || echo 1 ;;
        allow_newer_api) [ -f "$LEGACY_DIR/allow_newer_api" ] && echo 1 || echo 0 ;;
        *) echo 0 ;;
    esac
}

nf_list() {
    # $1 = new path, $2 = legacy file name
    if [ -f "$1" ]; then echo "$1"; elif [ ! -f "$CONF" ] && [ -f "$LEGACY_DIR/$2" ]; then echo "$LEGACY_DIR/$2"; fi
}

nf_abi() {
    case "${LUOSHU_NATIVE_FONT_ABI:-$(getprop ro.product.cpu.abi 2>/dev/null)}" in
        arm64-v8a) echo arm64-v8a ;;
        armeabi-v7a|armeabi) echo armeabi-v7a ;;
        x86_64) echo x86_64 ;;
        x86) echo x86 ;;
        *) echo arm64-v8a ;;
    esac
}

nf_boot_id() {
    head -n1 "$BOOT_ID_FILE" 2>/dev/null | tr -d '\r\n '
}

nf_size() {
    stat -L -c '%s' "$1" 2>/dev/null || wc -c < "$1" 2>/dev/null | tr -d ' \r\n'
}

nf_inode() {
    stat -L -c '%d:%i' "$1" 2>/dev/null
}

# 洛书正文字体在模块里的位置：公开负载 system/fonts，或私有负载 .luoshu-payload/system/fonts。
nf_face_dir() {
    for _nf_d in "$MODDIR/system/fonts" "$MODDIR/.luoshu-payload/system/fonts"; do
        for _nf_f in "$_nf_d"/LuoShu-[1-9][0-9][0-9]*.ttf "$_nf_d"/LuoShu-[1-9][0-9][0-9]*.otf; do
            [ -s "$_nf_f" ] && { printf '%s\n' "$_nf_d"; return 0; }
        done
    done
    return 1
}

# 字体对系统可见：/system/fonts/LuoShu-NNN 与模块文件大小一致；或（逐文件 bind 时附加文件不可见）
# 模块里指向同一字体的槽位文件（ColorOS SysSans-*、HyperOS MiSans* 等，硬链接或符号链接）
# 在对应分区的真实路径上可见且大小一致。
nf_faces_visible() {
    _nf_dir="$1"
    _nf_root="${LUOSHU_NATIVE_FONT_SYSROOT:-}"
    _nf_ids=''
    for _nf_f in "$_nf_dir"/LuoShu-[1-9][0-9][0-9]*.ttf "$_nf_dir"/LuoShu-[1-9][0-9][0-9]*.otf; do
        [ -s "$_nf_f" ] || continue
        _nf_sz=$(nf_size "$_nf_f")
        _nf_sys="$_nf_root/system/fonts/${_nf_f##*/}"
        [ -f "$_nf_sys" ] && [ "$(nf_size "$_nf_sys")" = "$_nf_sz" ] && return 0
        _nf_ids="$_nf_ids $(nf_inode "$_nf_f")=$_nf_sz"
    done
    [ -n "$_nf_ids" ] || return 1
    _nf_base="${_nf_dir%/system/fonts}"
    for _nf_pdir in "$_nf_base"/*/fonts; do
        [ -d "$_nf_pdir" ] || continue
        _nf_part="${_nf_pdir%/fonts}"
        _nf_part="${_nf_part##*/}"
        for _nf_slot in "$_nf_pdir"/*; do
            [ -f "$_nf_slot" ] || continue
            case "${_nf_slot##*/}" in LuoShu-*) continue ;; esac
            _nf_id=$(nf_inode "$_nf_slot")
            [ -n "$_nf_id" ] || continue
            case "$_nf_ids " in
                *" $_nf_id="*) ;;
                *) continue ;;
            esac
            _nf_sz=${_nf_ids#*" $_nf_id="}
            _nf_sz=${_nf_sz%% *}
            _nf_sys="$_nf_root/$_nf_part/fonts/${_nf_slot##*/}"
            [ -f "$_nf_sys" ] && [ "$(nf_size "$_nf_sys")" = "$_nf_sz" ] && return 0
        done
    done
    return 1
}

# ---- ROM 槽位布局：模块里没有 LuoShu-NNN，正文字体直接写成 ROM 的主正文槽位文件 ----------------
# ColorOS SysSans-Hans-*/SysFont-*（/system、/my_product 等分区）、HyperOS MiSansVF/100..900.ttf/
# Roboto-*、OriginOS vivo/fonts、通用 AOSP Roboto-*。这些文件在模块里就是洛书写入的正文字体
# （原厂 fallback 留在下层分区，不会出现在模块里）。

# 模块里会出现字体的目录（公开负载与私有负载）：<part>/fonts、system/<part>/fonts、<part>/vivo/fonts。
nf_slot_dirs() {
    for _nf_b in "$MODDIR" "$MODDIR/.luoshu-payload"; do
        for _nf_d in "$_nf_b"/system/fonts "$_nf_b"/*/fonts "$_nf_b"/system/*/fonts "$_nf_b"/*/vivo/fonts; do
            [ -d "$_nf_d" ] && printf '%s\n' "$_nf_d"
        done
    done
}

# 主正文槽位的档位与档内顺序（"tier order"，都是 1 最高）；不是正文槽（等宽/时钟/emoji/符号/衬线/
# 斜体/窄体/数字/叠加层/其它文字体系/字体集合）时失败。ColorOS 的 SysFont-* 原厂是指向 flip-font 目录
# 的符号链接，所以同档里 SysSans-* 排在 SysFont-* 前面。
nf_slot_rank() {
    _nf_n=$(printf '%s' "$1" | tr 'A-Z' 'a-z')
    case "$_nf_n" in
        *.ttf|*.otf) ;;
        *) return 1 ;;
    esac
    case "$_nf_n" in
        luoshu*|*mono*|*code*|*clock*|*emoji*|*symbol*|*serif*|*italic*|*oblique*|*condensed*|*narrow*|\
        *din*|*overlay*|*myanmar*|*arabic*|*thai*|*hebrew*|*deva*|*bengali*|*tamil*|*khmer*|*lao*|\
        *georgian*|*armenian*|*ethiopic*|*tibetan*|*mongolian*|*uyghur*|*sinhala*|*korean*) return 1 ;;
    esac
    case "$_nf_n" in
        syssans-hans-*|opposans-hans-*|oplussans*hans*|misansvf.ttf|[1-9]00.ttf|350.ttf|\
        vivosans*|vivo-sans*|originsans*|origin-sans*|iqoosans*|harmonyos_sans_sc*)
            echo '1 1' ;;
        sysfont-hans-*|misansl3.otf) echo '1 2' ;;
        syssans-hant-*|opposans-*|oplussans*|oplusosui-*|opsans-*|misanstcvf.ttf|harmonyos_sans*) echo '2 1' ;;
        sysfont-*) echo '2 2' ;;
        syssans-*|misanslatinvf.ttf|roboto-*|robotostatic-*|robotoflex-*|googlesans*|notosans-regular*|\
        droidsans*|sourcesanspro-*)
            echo '3 1' ;;
        *) return 1 ;;
    esac
}

# 存在的最高档位里的全部候选（避免组合字体时混进仅英文的槽位），档内按顺序排好，一行一个路径。
nf_slot_candidates() {
    _nf_best=9
    _nf_list=''
    for _nf_d in $(nf_slot_dirs); do
        for _nf_f in "$_nf_d"/*; do
            [ -s "$_nf_f" ] || continue
            _nf_r=$(nf_slot_rank "${_nf_f##*/}") || continue
            _nf_t=${_nf_r% *}
            [ "$_nf_t" -le "$_nf_best" ] || continue
            if [ "$_nf_t" -lt "$_nf_best" ]; then _nf_best="$_nf_t"; _nf_list=''; fi
            _nf_list="$_nf_list${_nf_r#* }	$_nf_f
"
        done
    done
    [ -n "$_nf_list" ] || return 1
    printf '%s' "$_nf_list" | sort -s -n -k1,1 | cut -f2-
}

# OS/2 usWeightClass（单字体 sfnt；读不到时失败）。只用 od，不依赖 awk/python。
nf_os2_weight() {
    _nf_file="$1"
    # shellcheck disable=SC2046
    set -- $(od -An -tu1 -v -N 6 "$_nf_file" 2>/dev/null)
    [ $# -eq 6 ] || return 1
    case "$1.$2.$3.$4" in 0.1.0.0|79.84.84.79|116.114.117.101) ;; *) return 1 ;; esac
    _nf_nt=$(( $5 * 256 + $6 ))
    [ "$_nf_nt" -gt 0 ] && [ "$_nf_nt" -le 64 ] || return 1
    # shellcheck disable=SC2046
    set -- $(od -An -tu1 -v -j 12 -N $(( _nf_nt * 16 )) "$_nf_file" 2>/dev/null)
    while [ $# -ge 16 ]; do
        if [ "$1.$2.$3.$4" = 79.83.47.50 ]; then
            _nf_off=$(( (($9 * 256 + ${10}) * 256 + ${11}) * 256 + ${12} ))
            # shellcheck disable=SC2046
            set -- $(od -An -tu1 -v -j $(( _nf_off + 4 )) -N 2 "$_nf_file" 2>/dev/null)
            [ $# -eq 2 ] || return 1
            _nf_w=$(( $1 * 256 + $2 ))
            [ "$_nf_w" -ge 1 ] && [ "$_nf_w" -le 1000 ] || return 1
            echo "$_nf_w"
            return 0
        fi
        shift 16
    done
    return 1
}

# 文件名里的字重（HyperOS 100..900.ttf 或 Thin/Light/Regular/Medium/Bold… 后缀）；没有时 400。
nf_name_weight() {
    _nf_n=$(printf '%s' "${1%.*}" | tr 'A-Z' 'a-z')
    case "$_nf_n" in
        [1-9]00|350) echo "$_nf_n" ;;
        *extralight*|*ultralight*) echo 200 ;;
        *semilight*|*demilight*) echo 350 ;;
        *thin*|*hairline*) echo 100 ;;
        *light*) echo 300 ;;
        *semibold*|*demibold*) echo 600 ;;
        *extrabold*|*ultrabold*) echo 800 ;;
        *bold*) echo 700 ;;
        *medium*) echo 500 ;;
        *black*|*heavy*) echo 900 ;;
        *) echo 400 ;;
    esac
}

# lsnf-config 只认 LuoShu-<三位数字>：限定在 100..900。
nf_face_weight() {
    _nf_fw=$(nf_os2_weight "$1") || _nf_fw=$(nf_name_weight "${1##*/}")
    [ "$_nf_fw" -ge 100 ] 2>/dev/null || _nf_fw=100
    [ "$_nf_fw" -le 900 ] || _nf_fw=900
    echo "$_nf_fw"
}

# 模块实际提供的主正文槽位文件：按字重去重（同字重保留排在前面的），最多 8 个。输出 "weight<TAB>path"。
nf_slot_faces() {
    _nf_list=$(nf_slot_candidates) || return 1
    _nf_seen=' '
    _nf_count=0
    _nf_old_ifs=$IFS
    IFS='
'
    for _nf_f in $_nf_list; do
        IFS=$_nf_old_ifs
        [ "$_nf_count" -lt 8 ] || break
        _nf_w=$(nf_face_weight "$_nf_f")
        case "$_nf_seen" in *" $_nf_w "*) continue ;; esac
        _nf_seen="$_nf_seen$_nf_w "
        _nf_count=$((_nf_count + 1))
        printf '%s\t%s\n' "$_nf_w" "$_nf_f"
    done
    IFS=$_nf_old_ifs
    [ "$_nf_count" -gt 0 ]
}

# 模块文件在系统上的真实路径：<base>/system/fonts/X → /system/fonts/X；<base>/my_product/fonts/X →
# /my_product/fonts/X；<base>/system/product/fonts/X → /product/fonts/X（Magisk 式 system/<part>）。
nf_real_path() {
    _nf_rel="$1"
    case "$_nf_rel" in
        "$MODDIR/.luoshu-payload/"*) _nf_rel=${_nf_rel#"$MODDIR/.luoshu-payload/"} ;;
        "$MODDIR/"*) _nf_rel=${_nf_rel#"$MODDIR/"} ;;
        *) return 1 ;;
    esac
    case "$_nf_rel" in
        system/fonts/*) ;;
        system/*/*) _nf_rel=${_nf_rel#system/} ;;
    esac
    printf '/%s\n' "$_nf_rel"
}

# 槽位文件对系统可见：同档任一候选槽位在对应分区真实路径上大小一致（说明本次负载已挂载）。
nf_slot_faces_visible() {
    _nf_root="${LUOSHU_NATIVE_FONT_SYSROOT:-}"
    for _nf_f in "$@"; do
        _nf_real=$(nf_real_path "$_nf_f") || continue
        _nf_sz=$(nf_size "$_nf_f")
        [ -f "$_nf_root$_nf_real" ] && [ "$(nf_size "$_nf_root$_nf_real")" = "$_nf_sz" ] && return 0
    done
    return 1
}

# Zygisk 库按 LuoShu-<weight> 名字在模块目录 zygisk/runtime/faces/ 下打开槽位字体：硬链接（同一
# inode，不占空间），不行再用相对符号链接，最后复制。先在临时目录建好再替换。
nf_link_face() {
    ln "$1" "$2" 2>/dev/null && return 0
    _nf_rel=${1#"$MODDIR/"}
    [ "$_nf_rel" != "$1" ] && ln -s "../../../$_nf_rel" "$2" 2>/dev/null && [ -s "$2" ] && return 0
    rm -f "$2"
    cp -f "$1" "$2" 2>/dev/null
}

nf_write_slot_aliases() {
    _nf_tmpd="$RUNTIME/faces.tmp"
    rm -rf "$_nf_tmpd"
    mkdir -p "$_nf_tmpd" || return 1
    _nf_old_ifs=$IFS
    IFS='
'
    for _nf_line in $1; do
        IFS=$_nf_old_ifs
        _nf_w=${_nf_line%%"	"*}
        _nf_f=${_nf_line#*"	"}
        case "$_nf_f" in *.[Oo][Tt][Ff]) _nf_ext=otf ;; *) _nf_ext=ttf ;; esac
        nf_link_face "$_nf_f" "$_nf_tmpd/LuoShu-$_nf_w.$_nf_ext" || { rm -rf "$_nf_tmpd"; return 1; }
        chmod 0644 "$_nf_tmpd/LuoShu-$_nf_w.$_nf_ext" 2>/dev/null
        printf 'face %s <- %s\n' "LuoShu-$_nf_w.$_nf_ext" "$_nf_f"
    done
    IFS=$_nf_old_ifs
    chmod 0755 "$_nf_tmpd" 2>/dev/null
    rm -rf "$RUNTIME/faces"
    mv -f "$_nf_tmpd" "$RUNTIME/faces" || return 1
}

# 洛书当前应用的正文字体。不依赖本次开机的加载验证（它在开机后期才完成，而 prepare 在第一个应用
# 进程时就运行）：active_font 非 default、无待重启/待重建、模块内有正文字体且已对系统可见才写
# faces.bin；上一次验证明确 failed 时让出。不满足时把原因写到 NF_REASON（细节写 NF_REASON_DETAIL）。
# 正文字体来源按优先级：LuoShu-<weight> → ROM 适配写出的主正文槽位文件（含各分区 */fonts 与私有负载）。
nf_write_faces() {
    _nf_active=$(head -n1 "$CONF_DIR/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_nf_active" ] && [ "$_nf_active" != default ] || { NF_REASON=no-active-font; return 1; }
    [ ! -s "$CONF_DIR/text_reboot_required.conf" ] || { NF_REASON=reboot-required; return 1; }
    [ ! -s "$CONF_DIR/font-payload-rebuild-pending.conf" ] || { NF_REASON=payload-rebuild-pending; return 1; }
    _nf_verify="$CONF_DIR/device-font-load-verification.conf"
    if [ "$(nf_conf_value "$_nf_verify" state)" = failed ] && \
       [ "$(sed -n 's/^activeFont=//p' "$_nf_verify" 2>/dev/null | head -n1 | tr -d '\r\n')" = "$_nf_active" ]; then
        NF_REASON=verify-failed
        return 1
    fi
    set --
    if _nf_dir=$(nf_face_dir); then
        rm -rf "$RUNTIME/faces"
        nf_faces_visible "$_nf_dir" || { NF_REASON=font-not-mounted; return 1; }
        for _nf_f in "$_nf_dir"/LuoShu-[1-9][0-9][0-9]*.ttf "$_nf_dir"/LuoShu-[1-9][0-9][0-9]*.otf; do
            [ -s "$_nf_f" ] && set -- "$@" "$_nf_f"
        done
    elif _nf_slots=$(nf_slot_faces); then
        _nf_old_ifs=$IFS
        IFS='
'
        for _nf_line in $_nf_slots; do set -- "$@" "${_nf_line#*"	"}"; done
        IFS=$_nf_old_ifs
        _nf_cands=$(nf_slot_candidates)
        IFS='
'
        # shellcheck disable=SC2086
        if ! nf_slot_faces_visible $_nf_cands; then
            IFS=$_nf_old_ifs
            NF_REASON=font-not-mounted
            NF_REASON_DETAIL="槽位未在系统路径可见：$(for _nf_f in "$@"; do nf_real_path "$_nf_f"; done | tr '\n' ' ')"
            return 1
        fi
        IFS=$_nf_old_ifs
        nf_write_slot_aliases "$_nf_slots" || { NF_REASON=faces-build-failed; return 1; }
        set --
        for _nf_f in "$RUNTIME/faces"/LuoShu-*; do
            [ -s "$_nf_f" ] && set -- "$@" "$_nf_f"
        done
    else
        rm -rf "$RUNTIME/faces"
        NF_REASON=no-luoshu-faces
        NF_REASON_DETAIL="未找到 LuoShu-NNN 或主正文槽位：$(nf_slot_dirs | tr '\n' ' ')"
        [ -n "$(nf_slot_dirs)" ] || NF_REASON_DETAIL="模块内没有字体目录：$MODDIR/{,.luoshu-payload/}{system/fonts,*/fonts,system/*/fonts,*/vivo/fonts}"
        return 1
    fi
    rm -f "$RUNTIME/faces.bin.tmp"
    if "$TOOL" faces --out "$RUNTIME/faces.bin.tmp" "$@" && [ -s "$RUNTIME/faces.bin.tmp" ]; then
        chmod 0644 "$RUNTIME/faces.bin.tmp" 2>/dev/null
        mv -f "$RUNTIME/faces.bin.tmp" "$RUNTIME/faces.bin" && return 0
    fi
    rm -f "$RUNTIME/faces.bin.tmp"
    NF_REASON=faces-build-failed
    return 1
}

nf_prepare() {
    TOOL="${LUOSHU_NATIVE_FONT_TOOL:-$ZDIR/bin/$(nf_abi)/lsnf-config}"
    OUT="$RUNTIME/config.bin"
    LOG="$RUNTIME/config.log"
    mkdir -p "$RUNTIME" || return 0
    [ -x "$TOOL" ] || chmod 0755 "$TOOL" 2>/dev/null
    # 同一次开机可能由 Zygisk 库重新请求 prepare：其它进程此时仍在读取，所以先写临时文件再替换。
    rm -f "$OUT.tmp" "$RUNTIME/faces.bin.tmp"
    : > "$LOG.faces"
    NF_REASON=''
    NF_REASON_DETAIL=''
    enabled=$(nf_setting enabled)
    # 洛书模块被禁用或待删除时整体关闭。
    if [ -f "$MODDIR/disable" ] || [ -f "$MODDIR/remove" ]; then enabled=0; NF_REASON=module-disabled; fi
    verbose=$(nf_setting verbose)
    java_font=$(nf_setting java_font)
    allow_newer=$(nf_setting allow_newer_api)

    if [ "$enabled" = 1 ] && [ "$java_font" = 1 ]; then
        nf_write_faces >> "$LOG.faces" 2>&1 || rm -f "$RUNTIME/faces.bin"
    else
        rm -f "$RUNTIME/faces.bin"
        [ -n "$NF_REASON" ] || { [ "$enabled" = 1 ] && NF_REASON=java-font-off || NF_REASON=disabled; }
    fi

    set -- build --out "$OUT.tmp" --enabled "$enabled" --verbose "$verbose" --java-font "$java_font" \
        --allow-newer-api "$allow_newer"
    [ -f "$ZDIR/defaults/exclude.list" ] && set -- "$@" --exclude "$ZDIR/defaults/exclude.list"
    _nf_ex=$(nf_list "$EXCLUDE" exclude.list)
    [ -n "$_nf_ex" ] && set -- "$@" --exclude "$_nf_ex"
    _nf_fo=$(nf_list "$FORCE" force.list)
    [ -n "$_nf_fo" ] && set -- "$@" --force "$_nf_fo"

    if "$TOOL" "$@" > "$LOG" 2>&1 && [ -s "$OUT.tmp" ]; then
        chmod 0644 "$OUT.tmp"
        mv -f "$OUT.tmp" "$OUT"
    else
        rm -f "$OUT.tmp" "$RUNTIME/faces.bin"
        # 名单等出错时仍写一份关闭状态的配置，避免每个进程反复请求 companion。
        if "$TOOL" build --out "$OUT.tmp" --enabled 0 --verbose 0 --java-font 0 --allow-newer-api 0 >> "$LOG" 2>&1 \
            && [ -s "$OUT.tmp" ]; then
            chmod 0644 "$OUT.tmp"
            mv -f "$OUT.tmp" "$OUT"
        else
            rm -f "$OUT.tmp" "$OUT"
        fi
        enabled=0
        NF_REASON=config-build-failed
    fi
    _nf_faces=0
    [ -s "$RUNTIME/faces.bin" ] && _nf_faces=1
    [ "$_nf_faces" = 0 ] || { NF_REASON=''; NF_REASON_DETAIL=''; }
    [ -z "$NF_REASON_DETAIL" ] || printf 'reason_detail: %s\n' "$NF_REASON_DETAIL" >> "$LOG.faces"
    {
        printf 'boot_id=%s\n' "$(nf_boot_id)"
        printf 'enabled=%s\n' "$enabled"
        printf 'faces=%s\n' "$_nf_faces"
        printf 'reason=%s\n' "$NF_REASON"
        printf 'reason_detail=%s\n' "$(printf '%s' "$NF_REASON_DETAIL" | tr -d '\r\n')"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$RUNTIME/state.conf.tmp" 2>/dev/null && mv -f "$RUNTIME/state.conf.tmp" "$RUNTIME/state.conf"
    chmod 0644 "$RUNTIME/state.conf" 2>/dev/null
    return 0
}

nf_json_bool() {
    [ "$1" = 1 ] && printf true || printf false
}

nf_status() {
    _nf_lib=0
    [ -f "$ZDIR/$(nf_abi).so" ] && _nf_lib=1
    _nf_loaded=0
    _nf_faces=0
    _nf_active_enabled=0
    _nf_reason=''
    _nf_detail=''
    _nf_now=$(nf_boot_id)
    if [ -n "$_nf_now" ] && [ "$(nf_conf_value "$RUNTIME/state.conf" boot_id)" = "$_nf_now" ]; then
        _nf_loaded=1
        _nf_faces=$(nf_bool "$(nf_conf_value "$RUNTIME/state.conf" faces)")
        _nf_active_enabled=$(nf_bool "$(nf_conf_value "$RUNTIME/state.conf" enabled)")
        _nf_reason=$(nf_conf_value "$RUNTIME/state.conf" reason | tr -cd 'a-z0-9-')
        _nf_detail=$(sed -n 's/^reason_detail=//p' "$RUNTIME/state.conf" 2>/dev/null | head -n1 | tr -d '"\\\r\n')
    fi
    _nf_legacy=0
    [ ! -f "$CONF" ] && [ -d "$LEGACY_DIR" ] && _nf_legacy=1
    printf '{"status":"ok","data":{"enabled":%s,"verbose":%s,"library":%s,"zygiskLoaded":%s,"activeEnabled":%s,"faces":%s,"facesReason":"%s","facesDetail":"%s","legacyConfig":%s}}\n' \
        "$(nf_json_bool "$(nf_setting enabled)")" "$(nf_json_bool "$(nf_setting verbose)")" \
        "$(nf_json_bool "$_nf_lib")" "$(nf_json_bool "$_nf_loaded")" \
        "$(nf_json_bool "$_nf_active_enabled")" "$(nf_json_bool "$_nf_faces")" "$_nf_reason" "$_nf_detail" \
        "$(nf_json_bool "$_nf_legacy")"
}

nf_set() {
    _nf_key="$1"
    case "$_nf_key" in
        enabled|verbose) ;;
        *) printf '{"status":"error","message":"未知设置项"}\n'; return 0 ;;
    esac
    case "$2" in
        0|1) _nf_val="$2" ;;
        *) printf '{"status":"error","message":"设置值必须为 0 或 1"}\n'; return 0 ;;
    esac
    mkdir -p "$CONF_DIR" 2>/dev/null
    # 首次写入时把旧路径的设置一并带过来，之后只读新配置。
    _nf_enabled=$(nf_setting enabled)
    _nf_verbose=$(nf_setting verbose)
    _nf_java=$(nf_setting java_font)
    _nf_newer=$(nf_setting allow_newer_api)
    case "$_nf_key" in
        enabled) _nf_enabled="$_nf_val" ;;
        verbose) _nf_verbose="$_nf_val" ;;
    esac
    if [ ! -f "$EXCLUDE" ] && [ ! -f "$CONF" ] && [ -f "$LEGACY_DIR/exclude.list" ]; then
        cp -f "$LEGACY_DIR/exclude.list" "$EXCLUDE" 2>/dev/null && chmod 0644 "$EXCLUDE" 2>/dev/null
    fi
    if [ ! -f "$FORCE" ] && [ ! -f "$CONF" ] && [ -f "$LEGACY_DIR/force.list" ]; then
        cp -f "$LEGACY_DIR/force.list" "$FORCE" 2>/dev/null && chmod 0644 "$FORCE" 2>/dev/null
    fi
    _nf_tmp="$CONF.tmp.$$"
    {
        printf '# 洛书全局字体增强（Zygisk）。修改后重启生效。\n'
        printf 'enabled=%s\n' "$_nf_enabled"
        printf 'verbose=%s\n' "$_nf_verbose"
        printf 'java_font=%s\n' "$_nf_java"
        printf 'allow_newer_api=%s\n' "$_nf_newer"
    } > "$_nf_tmp" 2>/dev/null && mv -f "$_nf_tmp" "$CONF" 2>/dev/null || {
        rm -f "$_nf_tmp" 2>/dev/null
        printf '{"status":"error","message":"无法写入全局字体增强配置"}\n'
        return 0
    }
    chmod 0644 "$CONF" 2>/dev/null
    nf_status
}

case "${1:-}" in
    prepare) nf_prepare ;;
    status) nf_status ;;
    set) nf_set "${2:-}" "${3:-}" ;;
    *) printf '{"status":"error","message":"未知全局字体增强命令"}\n' ;;
esac
exit 0
