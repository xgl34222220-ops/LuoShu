#!/system/bin/sh
# Fast App font library index. Directory enumeration is immediate; metadata cache is optional.
set +e

MODULE_DIR="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
CONFIG_DIR="${CONFIG_DIR:-$MODULE_DIR/config}"
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="${USER_FONTS_DIR:-$LUOSHU_PUBLIC_DIR/fonts}"
FONT_META_CACHE="${FONT_META_CACHE:-$CONFIG_DIR/font-metadata}"
INDEX_PY="$MODULE_DIR/common/app_font_index.py"
PYROOT="$MODULE_DIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
INDEX_JSON="$CONFIG_DIR/app_font_index.json"
INDEX_KEY="$CONFIG_DIR/app_font_index.key"
INDEX_WORKER_PID="$CONFIG_DIR/app_font_index_worker.pid"
INDEX_REVISION="$CONFIG_DIR/app_font_index.revision"

_app_index_filename_family() {
    _aif_name=$(basename "$1"); _aif_name=${_aif_name%.*}
    for _aif_suffix in Variable variable VF vf Italic italic Oblique oblique Regular regular Normal normal Roman roman Book book Thin thin ExtraLight extralight UltraLight ultralight Light light Medium medium SemiBold semibold DemiBold demibold Bold bold ExtraBold extrabold UltraBold ultrabold Black black Heavy heavy; do
        case "$_aif_name" in *-"$_aif_suffix") _aif_name=${_aif_name%-"$_aif_suffix"} ;; *_"$_aif_suffix") _aif_name=${_aif_name%_"$_aif_suffix"} ;; esac
    done
    [ -n "$_aif_name" ] || _aif_name=UnknownFont
    printf '%s\n' "$_aif_name"
}

_app_index_filename_weight() {
    _aiw_name=$(basename "$1" | tr '[:upper:]' '[:lower:]')
    case "$_aiw_name" in
        *thin*) echo 100 ;; *extralight*|*ultralight*|*w200*) echo 200 ;; *light*|*w300*) echo 300 ;;
        *medium*|*w500*) echo 500 ;; *semibold*|*demibold*|*w600*) echo 600 ;; *extrabold*|*ultrabold*|*w800*) echo 800 ;;
        *black*|*heavy*|*w900*) echo 900 ;; *bold*|*w700*) echo 700 ;; *) echo 400 ;;
    esac
}

_app_index_magic_format() {
    _aif_magic=$(dd if="$1" bs=1 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n\r')
    case "$_aif_magic" in 00010000|74727565|00020000) echo TTF ;; 4f54544f) echo OTF ;; 74746366) echo TTC ;; *) echo UNKNOWN ;; esac
}

_app_index_meta_conf() {
    _aim_file="$1"
    _aim_mtime=$(stat -c %Y "$_aim_file" 2>/dev/null || echo 0)
    _aim_bytes=$(wc -c <"$_aim_file" 2>/dev/null | tr -d '[:space:]'); case "$_aim_bytes" in ''|*[!0-9]*) _aim_bytes=0 ;; esac
    _aim_key=$(printf '%s|%s|%s' "$_aim_file" "$_aim_mtime" "$_aim_bytes" | cksum | awk '{print $1"-"$2}')
    printf '%s/%s.conf\n' "$FONT_META_CACHE" "$_aim_key"
}

_app_index_directory_key() {
    _aik_tmp="$CONFIG_DIR/.app-font-key.$$"
    : >"$_aik_tmp" 2>/dev/null || return 1
    for _aik_file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_aik_file" ] || continue
        _aik_size=$(wc -c <"$_aik_file" 2>/dev/null | tr -d '[:space:]')
        _aik_mtime=$(stat -c %Y "$_aik_file" 2>/dev/null || echo 0)
        printf '%s|%s|%s\n' "$(basename "$_aik_file")" "$_aik_size" "$_aik_mtime" >>"$_aik_tmp"
    done
    sort "$_aik_tmp" 2>/dev/null | cksum | awk '{print $1"-"$2}'
    rm -f "$_aik_tmp" 2>/dev/null || true
}

_app_index_run_python() {
    _aip_records="$1"; _aip_current="$2"; _aip_output="$3"
    if [ -x "$PYBIN" ] && [ -f "$INDEX_PY" ]; then
        PYTHONHOME="$PYROOT" PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$PYBIN" "$INDEX_PY" --records "$_aip_records" --current "$_aip_current" >"$_aip_output" 2>/dev/null
        return $?
    fi
    if command -v python3 >/dev/null 2>&1; then python3 "$INDEX_PY" --records "$_aip_records" --current "$_aip_current" >"$_aip_output" 2>/dev/null; return $?; fi
    return 1
}

_app_index_schedule_metadata() {
    [ "$1" = true ] || return 0
    if [ -s "$INDEX_WORKER_PID" ]; then
        _ai_old=$(cat "$INDEX_WORKER_PID" 2>/dev/null)
        [ -n "$_ai_old" ] && kill -0 "$_ai_old" 2>/dev/null && return 0
    fi
    (
        echo $$ >"$INDEX_WORKER_PID" 2>/dev/null || true
        _ai_changed=false
        for _ai_meta_file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
            [ -f "$_ai_meta_file" ] || continue
            _ai_conf=$(_app_index_meta_conf "$_ai_meta_file")
            [ -s "$_ai_conf" ] && continue
            ( font_metadata_conf "$_ai_meta_file" >/dev/null 2>&1 )
            [ -s "$_ai_conf" ] && _ai_changed=true
        done
        [ "$_ai_changed" = true ] && date +%s >"$INDEX_REVISION" 2>/dev/null || true
        rm -f "$INDEX_WORKER_PID" 2>/dev/null || true
    ) </dev/null >/dev/null 2>&1 &
}

app_fonts_json() {
    _aij_force="${1:-}"
    mkdir -p "$USER_FONTS_DIR" "$CONFIG_DIR" "$FONT_META_CACHE" 2>/dev/null || true
    _aij_current=$(head -n1 "$CONFIG_DIR/active_font.conf" 2>/dev/null | tr -d '\r\n'); [ -n "$_aij_current" ] || _aij_current=default
    _aij_revision=$(cat "$INDEX_REVISION" 2>/dev/null); [ -n "$_aij_revision" ] || _aij_revision=0
    _aij_key="$(_app_index_directory_key)|$_aij_revision"
    _aij_saved=$(cat "$INDEX_KEY" 2>/dev/null)
    if [ "$_aij_force" != refresh ] && [ "$_aij_saved" = "$_aij_key|$_aij_current" ] && [ -s "$INDEX_JSON" ] && grep -q '"status":"ok"' "$INDEX_JSON" 2>/dev/null; then
        cat "$INDEX_JSON"; return 0
    fi

    _aij_records="$CONFIG_DIR/.app-font-records.$$"; _aij_output="$CONFIG_DIR/.app-font-index.$$"
    : >"$_aij_records" 2>/dev/null || { printf '{"status":"error","message":"无法创建字体索引"}\n'; return 1; }
    _aij_pending=false
    for _aij_file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_aij_file" ] || continue
        case "$(basename "$_aij_file")" in .app-import-*|.*) continue ;; esac
        _aij_bytes=$(wc -c <"$_aij_file" 2>/dev/null | tr -d '[:space:]'); case "$_aij_bytes" in ''|*[!0-9]*) _aij_bytes=0 ;; esac
        _aij_format=$(_app_index_magic_format "$_aij_file")
        _aij_valid=true; _aij_error=""
        if [ "$_aij_bytes" -lt 4096 ] 2>/dev/null; then _aij_valid=false; _aij_error="字体文件过小（${_aij_bytes} 字节）"; fi
        [ "$_aij_format" != UNKNOWN ] || { _aij_valid=false; _aij_error="无法识别字体格式"; }
        _aij_conf=$(_app_index_meta_conf "$_aij_file")
        _aij_metadata=false; _aij_family=""; _aij_weights=""; _aij_variable=false
        if [ -s "$_aij_conf" ] && grep -q '^status=ok$' "$_aij_conf" 2>/dev/null; then
            _aij_metadata=true
            _aij_family=$(sed -n 's/^family=//p' "$_aij_conf" | head -n1)
            _aij_weights=$(sed -n 's/^weights=//p' "$_aij_conf" | head -n1)
            _aij_variable=$(sed -n 's/^variable=//p' "$_aij_conf" | head -n1)
        else
            _aij_pending=true
        fi
        [ -n "$_aij_family" ] || _aij_family=$(_app_index_filename_family "$_aij_file")
        [ -n "$_aij_weights" ] || _aij_weights=$(_app_index_filename_weight "$_aij_file")
        case "$_aij_variable" in true|false) ;; *) _aij_variable=false ;; esac
        _aij_date=$(stat -c '%y' "$_aij_file" 2>/dev/null | cut -c1-10)
        _aij_relative=$(basename "$_aij_file")
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$_aij_file" "$_aij_family" "$_aij_weights" "$_aij_variable" "$_aij_format" "$_aij_bytes" "$_aij_date" "$_aij_valid" "$_aij_error" "$_aij_metadata" "$_aij_relative" >>"$_aij_records"
    done

    if _app_index_run_python "$_aij_records" "$_aij_current" "$_aij_output" && [ -s "$_aij_output" ]; then
        mv -f "$_aij_output" "$INDEX_JSON" 2>/dev/null || cp -f "$_aij_output" "$INDEX_JSON" 2>/dev/null
        printf '%s\n' "$_aij_key|$_aij_current" >"$INDEX_KEY" 2>/dev/null || true
        cat "$INDEX_JSON"
    else
        printf '{"status":"error","message":"字体快速索引生成失败"}\n'
    fi
    rm -f "$_aij_records" "$_aij_output" 2>/dev/null || true
    _app_index_schedule_metadata "$_aij_pending"
}
