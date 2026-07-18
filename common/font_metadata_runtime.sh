#!/system/bin/sh
# LuoShu real font metadata runtime. Sourced by font_check.sh after util_functions.sh.
set +e

MODULE_DIR="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
CONFIG_DIR="${CONFIG_DIR:-$MODULE_DIR/config}"
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="${USER_FONTS_DIR:-$LUOSHU_PUBLIC_DIR/fonts}"
FONT_META_PY="$MODULE_DIR/common/font_metadata.py"
FONT_META_PYROOT="$MODULE_DIR/common/python"
FONT_META_PYBIN="$FONT_META_PYROOT/bin/luoshu-python"
FONT_META_CACHE="$CONFIG_DIR/font-metadata"

_font_filename_family() {
    _r=$(basename "$1"); _r=${_r%.*}
    for _s in Variable variable VF vf Italic italic Oblique oblique Regular regular Normal normal Roman roman Book book Thin thin ExtraLight extralight UltraLight ultralight Light light Medium medium SemiBold semibold DemiBold demibold Bold bold ExtraBold extrabold UltraBold ultrabold Black black Heavy heavy 常规 粗体 细体 中等 半粗 极细 特粗 斜体; do
        case "$_r" in *-"$_s") _r=${_r%-"$_s"} ;; *_"$_s") _r=${_r%_"$_s"} ;; esac
    done
    while :; do case "$_r" in *-) _r=${_r%-} ;; *_) _r=${_r%_} ;; *' ') _r=${_r%?} ;; *) break ;; esac; done
    [ -n "$_r" ] || _r="UnknownFont"
    printf '%s\n' "$_r"
}

_font_role_for_number() {
    _n="$1"; case "$_n" in ''|*[!0-9]*) _n=400 ;; esac
    if [ "$_n" -le 149 ] 2>/dev/null; then echo thin
    elif [ "$_n" -le 249 ] 2>/dev/null; then echo extralight
    elif [ "$_n" -le 349 ] 2>/dev/null; then echo light
    elif [ "$_n" -le 449 ] 2>/dev/null; then echo regular
    elif [ "$_n" -le 549 ] 2>/dev/null; then echo medium
    elif [ "$_n" -le 649 ] 2>/dev/null; then echo semibold
    elif [ "$_n" -le 749 ] 2>/dev/null; then echo bold
    elif [ "$_n" -le 849 ] 2>/dev/null; then echo extrabold
    else echo black; fi
}

font_role_number() {
    case "$1" in
        ''|regular|normal) echo 400 ;; thin) echo 100 ;; extralight|ultralight) echo 200 ;;
        light) echo 300 ;; medium) echo 500 ;; semibold|demibold) echo 600 ;;
        bold) echo 700 ;; extrabold|ultrabold) echo 800 ;; black|heavy) echo 900 ;;
        variable) echo 400 ;; *[!0-9]*) echo 400 ;; *) echo "$1" ;;
    esac
}

_font_find_argument_file() {
    _arg="$1"
    [ -f "$_arg" ] && { printf '%s\n' "$_arg"; return 0; }
    for _dir in "$USER_FONTS_DIR" "$MODULE_DIR/fonts" "$MODULE_DIR/system/fonts"; do
        [ -d "$_dir" ] || continue
        [ -f "$_dir/$_arg" ] && { printf '%s\n' "$_dir/$_arg"; return 0; }
        for _f in "$_dir"/*.ttf "$_dir"/*.otf "$_dir"/*.ttc "$_dir"/*.TTF "$_dir"/*.OTF "$_dir"/*.TTC; do
            [ -f "$_f" ] || continue
            [ "$(basename "$_f")" = "$_arg" ] && { printf '%s\n' "$_f"; return 0; }
        done
    done
    return 1
}

font_metadata_conf() {
    _file="$1"
    FONT_META_STATUS=error; FONT_META_FAMILY=""; FONT_META_SUBFAMILY=""; FONT_META_WEIGHT=400
    FONT_META_WEIGHTS=400; FONT_META_VARIABLE=false; FONT_META_COLLECTION=false
    FONT_META_AXIS_MIN=""; FONT_META_AXIS_DEFAULT=""; FONT_META_AXIS_MAX=""; FONT_META_FACE_COUNT=1
    [ -f "$_file" ] || return 1
    mkdir -p "$FONT_META_CACHE" 2>/dev/null || true
    _mtime=$(stat -c %Y "$_file" 2>/dev/null || echo 0)
    _bytes=$(wc -c <"$_file" 2>/dev/null | tr -d '[:space:]'); case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
    _key=$(printf '%s|%s|%s' "$_file" "$_mtime" "$_bytes" | cksum | awk '{print $1"-"$2}')
    _conf="$FONT_META_CACHE/${_key}.conf"
    if [ ! -s "$_conf" ] && [ -x "$FONT_META_PYBIN" ] && [ -f "$FONT_META_PY" ]; then
        _tmp="$_conf.tmp.$$"
        PYTHONHOME="$FONT_META_PYROOT" \
        PYTHONPATH="$FONT_META_PYROOT/lib/python3.14:$FONT_META_PYROOT/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$FONT_META_PYROOT/lib:$FONT_META_PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$FONT_META_PYBIN" "$FONT_META_PY" "$_file" --format conf >"$_tmp" 2>/dev/null
        if grep -q '^status=ok$' "$_tmp" 2>/dev/null; then mv -f "$_tmp" "$_conf"; else rm -f "$_tmp"; fi
    fi
    if [ -s "$_conf" ]; then
        FONT_META_STATUS=$(sed -n 's/^status=//p' "$_conf" | head -n1)
        FONT_META_FAMILY=$(sed -n 's/^family=//p' "$_conf" | head -n1)
        FONT_META_SUBFAMILY=$(sed -n 's/^subfamily=//p' "$_conf" | head -n1)
        FONT_META_WEIGHT=$(sed -n 's/^weight=//p' "$_conf" | head -n1)
        FONT_META_WEIGHTS=$(sed -n 's/^weights=//p' "$_conf" | head -n1)
        FONT_META_VARIABLE=$(sed -n 's/^variable=//p' "$_conf" | head -n1)
        FONT_META_COLLECTION=$(sed -n 's/^collection=//p' "$_conf" | head -n1)
        FONT_META_AXIS_MIN=$(sed -n 's/^axisMin=//p' "$_conf" | head -n1)
        FONT_META_AXIS_DEFAULT=$(sed -n 's/^axisDefault=//p' "$_conf" | head -n1)
        FONT_META_AXIS_MAX=$(sed -n 's/^axisMax=//p' "$_conf" | head -n1)
        FONT_META_FACE_COUNT=$(sed -n 's/^faceCount=//p' "$_conf" | head -n1)
        [ -n "$FONT_META_FAMILY" ] && return 0
    fi
    FONT_META_STATUS=fallback
    FONT_META_FAMILY=$(_font_filename_family "$_file")
    case "$(basename "$_file" | tr '[:upper:]' '[:lower:]')" in
        *thin*) FONT_META_WEIGHT=100 ;; *extralight*|*ultralight*|*w200*) FONT_META_WEIGHT=200 ;;
        *light*|*w300*) FONT_META_WEIGHT=300 ;; *medium*|*w500*) FONT_META_WEIGHT=500 ;;
        *semibold*|*demibold*|*w600*) FONT_META_WEIGHT=600 ;; *extrabold*|*ultrabold*|*w800*) FONT_META_WEIGHT=800 ;;
        *black*|*heavy*|*w900*) FONT_META_WEIGHT=900 ;; *bold*|*w700*) FONT_META_WEIGHT=700 ;; *) FONT_META_WEIGHT=400 ;;
    esac
    FONT_META_WEIGHTS=$FONT_META_WEIGHT
    grep -a -q 'fvar' "$_file" 2>/dev/null && FONT_META_VARIABLE=true
    return 0
}

font_family_for_file() { font_metadata_conf "$1" >/dev/null 2>&1; printf '%s\n' "$FONT_META_FAMILY"; }
font_weight_numbers_for_file() { font_metadata_conf "$1" >/dev/null 2>&1; printf '%s\n' "${FONT_META_WEIGHTS:-$FONT_META_WEIGHT}"; }
font_file_weight() { font_metadata_conf "$1" >/dev/null 2>&1; printf '%s\n' "${FONT_META_WEIGHT:-400}"; }
font_file_is_variable() { font_metadata_conf "$1" >/dev/null 2>&1; [ "$FONT_META_VARIABLE" = true ]; }
font_file_axis_min() { font_metadata_conf "$1" >/dev/null 2>&1; printf '%s\n' "$FONT_META_AXIS_MIN"; }
font_file_axis_default() { font_metadata_conf "$1" >/dev/null 2>&1; printf '%s\n' "$FONT_META_AXIS_DEFAULT"; }
font_file_axis_max() { font_metadata_conf "$1" >/dev/null 2>&1; printf '%s\n' "$FONT_META_AXIS_MAX"; }
is_variable_font() { font_file_is_variable "$1"; }

# Compatibility names used throughout older LuoShu scripts. They now resolve internal metadata first.
detect_font_family() {
    _f=$(_font_find_argument_file "$1")
    [ -f "$_f" ] && font_family_for_file "$_f" || _font_filename_family "$1"
}

detect_font_weight() {
    _f=$(_font_find_argument_file "$1")
    if [ -f "$_f" ]; then _font_role_for_number "$(font_file_weight "$_f")"; return; fi
    _base=$(basename "$1" | tr '[:upper:]' '[:lower:]')
    case "$_base" in *thin*) echo thin ;; *extralight*|*ultralight*) echo extralight ;; *light*) echo light ;;
        *medium*) echo medium ;; *semibold*|*demibold*) echo semibold ;; *extrabold*|*ultrabold*) echo extrabold ;;
        *black*|*heavy*) echo black ;; *bold*) echo bold ;; *) echo regular ;; esac
}

capitalize_first() {
    case "$1" in thin) echo Thin ;; extralight) echo ExtraLight ;; light) echo Light ;; regular) echo Regular ;;
        medium) echo Medium ;; semibold) echo SemiBold ;; bold) echo Bold ;; extrabold) echo ExtraBold ;;
        black) echo Black ;; variable) echo Variable ;; *) echo "$1" ;; esac
}

weight_sort_order() { font_role_number "$1"; }

family_files_lines() {
    _family="$1"
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        [ "$(font_family_for_file "$_f")" = "$_family" ] && printf '%s\n' "$_f"
    done
}

family_weight_numbers() {
    _family="$1"; _values=""
    while IFS= read -r _f; do
        [ -f "$_f" ] || continue
        _fw=$(font_weight_numbers_for_file "$_f")
        _oldifs="$IFS"; IFS=','
        for _n in $_fw; do
            case "$_n" in ''|*[!0-9]*) continue ;; esac
            case ",$__dummy,$_values," in *,$_n,*) ;; *) _values="${_values:+$_values,}$_n" ;; esac
        done
        IFS="$_oldifs"
    done <<EOF
$(family_files_lines "$_family")
EOF
    [ -n "$_values" ] || _values=400
    printf '%s\n' "$_values" | tr ',' '\n' | sort -n -u | paste -sd, -
}

scan_family_weights() {
    _nums=$(family_weight_numbers "$1"); _out=""; _oldifs="$IFS"; IFS=','
    for _n in $_nums; do _r=$(_font_role_for_number "$_n"); case ",$_out," in *,$_r,*) ;; *) _out="${_out:+$_out,}$_r" ;; esac; done
    IFS="$_oldifs"; printf '%s\n' "$_out"
}

family_file_for_weight() {
    _family="$1"; _target=$(font_role_number "$2"); _best=""; _score=99999
    while IFS= read -r _f; do
        [ -f "$_f" ] || continue
        if font_file_is_variable "$_f"; then printf '%s\n' "$_f"; return 0; fi
        _n=$(font_file_weight "$_f"); case "$_n" in ''|*[!0-9]*) _n=400 ;; esac
        _d=$((_n - _target)); [ "$_d" -ge 0 ] 2>/dev/null || _d=$((-_d))
        if [ -z "$_best" ] || [ "$_d" -lt "$_score" ] 2>/dev/null; then _best="$_f"; _score="$_d"; fi
    done <<EOF
$(family_files_lines "$_family")
EOF
    [ -n "$_best" ] && printf '%s\n' "$_best"
}
get_weight_file() { family_file_for_weight "$1" "$2"; }

scan_user_families_lines() {
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        _fam=$(font_family_for_file "$_f")
        case "$_fam" in ''|SysFont*|SysSans*|LuoShuAppMix) continue ;; esac
        printf '%s\n' "$_fam"
    done | awk '!seen[$0]++'
}
