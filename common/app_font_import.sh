#!/system/bin/sh
# App-only font import engine: ordinary fonts, module ZIPs and installed root modules.
set +e

MODULE_DIR="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="${USER_FONTS_DIR:-$LUOSHU_PUBLIC_DIR/fonts}"
FONT_PACKAGE_PY="$MODULE_DIR/common/font_package_import.py"
PYROOT="$MODULE_DIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"

_import_json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }

app_cache_path_allowed() {
    case "$1" in
        /data/user/0/io.github.xgl34222220.luoshu/cache/font-import/*|/data/data/io.github.xgl34222220.luoshu/cache/font-import/*|\
        /data/user/0/io.github.xgl34222220.luoshu.debug/cache/font-import/*|/data/data/io.github.xgl34222220.luoshu.debug/cache/font-import/*) return 0 ;;
        *) return 1 ;;
    esac
}

_import_safe_name() {
    _raw=$(basename "$1" | tr -d '\r\n')
    _ext=${_raw##*.}; _stem=${_raw%.*}
    case "$_ext" in TTF) _ext=ttf ;; OTF) _ext=otf ;; TTC) _ext=ttc ;; esac
    _stem=$(printf '%s' "$_stem" | sed 's#[\\/:*?"<>|]#_#g; s/^[. ]*//; s/[. ]*$//' | cut -c1-150)
    [ -n "$_stem" ] || _stem=font
    printf '%s.%s\n' "$_stem" "$_ext"
}

_import_find_duplicate() {
    _src="$1"
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        cmp -s "$_src" "$_f" 2>/dev/null && { printf '%s\n' "$_f"; return 0; }
    done
    return 1
}

_import_commit_file() {
    _src="$1"; _requested="$2"; _origin="$3"
    IMPORT_STATE=failed; IMPORT_FILE=""; IMPORT_FAMILY=""; IMPORT_WEIGHTS=""; IMPORT_VARIABLE=false; IMPORT_ERROR=""
    [ -f "$_src" ] || { IMPORT_ERROR="字体文件不存在"; return 1; }
    _size=$(wc -c <"$_src" 2>/dev/null | tr -d '[:space:]'); case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
    [ "$_size" -ge 12 ] 2>/dev/null && [ "$_size" -le 134217728 ] 2>/dev/null || { IMPORT_ERROR="字体文件大小异常或超过 128 MB"; return 1; }
    _name=$(_import_safe_name "$_requested")
    _ext=${_name##*.}; case "$_ext" in ttf|otf|ttc) ;; *) IMPORT_ERROR="仅支持 TTF、OTF 或 TTC 字体"; return 1 ;; esac
    mkdir -p "$USER_FONTS_DIR" "$MODULE_DIR/config/font-metadata" 2>/dev/null || { IMPORT_ERROR="无法创建字体目录"; return 1; }
    _duplicate=$(_import_find_duplicate "$_src")
    if [ -f "$_duplicate" ]; then
        font_metadata_conf "$_duplicate" >/dev/null 2>&1 || true
        IMPORT_STATE=duplicate; IMPORT_FILE=$(basename "$_duplicate"); IMPORT_FAMILY=${FONT_META_FAMILY:-$(_font_filename_family "$_duplicate")}
        IMPORT_WEIGHTS=${FONT_META_WEIGHTS:-${FONT_META_WEIGHT:-400}}; IMPORT_VARIABLE=${FONT_META_VARIABLE:-false}
        return 0
    fi
    _dest="$USER_FONTS_DIR/$_name"; _stem=${_name%.*}; _index=2
    while [ -e "$_dest" ]; do _name="${_stem}-${_index}.${_ext}"; _dest="$USER_FONTS_DIR/$_name"; _index=$((_index + 1)); done
    _tmp="$USER_FONTS_DIR/.app-import-$$-${_name}"
    cp -f "$_src" "$_tmp" 2>/dev/null || { IMPORT_ERROR="无法复制字体到用户目录"; return 1; }
    chmod 0644 "$_tmp" 2>/dev/null || true
    if type font_validate >/dev/null 2>&1 && ! font_validate "$_tmp" text; then
        IMPORT_ERROR=${FONT_CHECK_ERROR:-字体文件校验失败}; rm -f "$_tmp"; return 1
    fi
    # font_metadata_conf uses shell-global scratch variables. Running it before the
    # final move used to overwrite _tmp, so mv targeted a metadata-cache temp file.
    if ! mv -f "$_tmp" "$_dest" 2>/dev/null; then
        # Some shared-storage FUSE implementations reject rename. Fall back to a
        # direct copy and keep the same validation/metadata path afterwards.
        cp -f "$_src" "$_dest" 2>/dev/null || { rm -f "$_tmp" "$_dest"; IMPORT_ERROR="无法提交字体文件"; return 1; }
        rm -f "$_tmp" 2>/dev/null || true
    fi
    chmod 0644 "$_dest" 2>/dev/null || true
    font_metadata_conf "$_dest" >/dev/null 2>&1 || true
    IMPORT_STATE=imported; IMPORT_FILE="$_name"; IMPORT_FAMILY=${FONT_META_FAMILY:-$(_font_filename_family "$_dest")}
    IMPORT_WEIGHTS=${FONT_META_WEIGHTS:-${FONT_META_WEIGHT:-400}}; IMPORT_VARIABLE=${FONT_META_VARIABLE:-false}; IMPORT_ORIGIN="$_origin"
    rm -f "$MODULE_DIR/config/webui_font_list.json" "$MODULE_DIR/config/webui_font_list.key" 2>/dev/null || true
    return 0
}

import_app_font() {
    _src="$1"; _requested="$2"
    app_cache_path_allowed "$_src" || { printf '{"status":"error","message":"字体来源不是受信任的 App 私有缓存"}\n'; return 1; }
    _import_commit_file "$_src" "$_requested" app || {
        printf '{"status":"error","message":"%s"}\n' "$(_import_json_escape "$IMPORT_ERROR")"; return 1
    }
    _imported=true; [ "$IMPORT_STATE" = duplicate ] && _imported=false
    printf '{"status":"ok","data":{"imported":%s,"duplicate":%s,"file":"%s","family":"%s","weights":[%s],"variable":%s,"origin":"app"}}\n' \
        "$_imported" "$([ "$IMPORT_STATE" = duplicate ] && echo true || echo false)" \
        "$(_import_json_escape "$IMPORT_FILE")" "$(_import_json_escape "$IMPORT_FAMILY")" "$IMPORT_WEIGHTS" "$IMPORT_VARIABLE"
}

_import_package_extract() {
    _zip="$1"; _out="$2"; _report="$3"
    [ -x "$PYBIN" ] && [ -f "$FONT_PACKAGE_PY" ] || return 1
    mkdir -p "$_out" 2>/dev/null || return 1
    PYTHONHOME="$PYROOT" PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$FONT_PACKAGE_PY" "$_zip" "$_out" >"$_report" 2>"$_report.err"
}

import_app_package() {
    _src="$1"; _requested="$2"
    app_cache_path_allowed "$_src" || { printf '{"status":"error","message":"模块包来源不是受信任的 App 私有缓存"}\n'; return 1; }
    case "$(printf '%s' "$_requested" | tr '[:upper:]' '[:lower:]')" in *.zip) ;; *) printf '{"status":"error","message":"请选择 Magisk 字体模块 ZIP"}\n'; return 1 ;; esac
    _root="$MODULE_DIR/cache/app-font-package/$$"; _extract="$_root/fonts"; _report="$_root/report.json"
    rm -rf "$_root" 2>/dev/null || true; mkdir -p "$_root" 2>/dev/null || true
    if ! _import_package_extract "$_src" "$_extract" "$_report"; then
        _msg=$(sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' "$_report.err" "$_report" 2>/dev/null | tail -n1)
        [ -n "$_msg" ] || _msg="无法解析字体模块 ZIP"
        rm -rf "$_root"; printf '{"status":"error","message":"%s"}\n' "$(_import_json_escape "$_msg")"; return 1
    fi
    _imported=0; _duplicates=0; _failed=0; _families=""; _first_error=""
    for _font in "$_extract"/*; do
        [ -f "$_font" ] || continue
        _display=$(basename "$_font"); _display=${_display#???-}
        if _import_commit_file "$_font" "$_display" "module-zip"; then
            if [ "$IMPORT_STATE" = imported ]; then _imported=$((_imported + 1)); else _duplicates=$((_duplicates + 1)); fi
            case "|$_families|" in *"|$IMPORT_FAMILY|"*) ;; *) _families="${_families:+$_families|}$IMPORT_FAMILY" ;; esac
        else
            _failed=$((_failed + 1)); [ -n "$_first_error" ] || _first_error="$IMPORT_ERROR"
        fi
    done
    _module=false; grep -q '"modulePackage":true' "$_report" 2>/dev/null && _module=true
    rm -rf "$_root" 2>/dev/null || true
    printf '{"status":"ok","data":{"package":"%s","modulePackage":%s,"imported":%s,"duplicates":%s,"failed":%s,"families":"%s","firstError":"%s"}}\n' \
        "$(_import_json_escape "$_requested")" "$_module" "$_imported" "$_duplicates" "$_failed" \
        "$(_import_json_escape "$(printf '%s' "$_families" | tr '|' '、')")" "$(_import_json_escape "$_first_error")"
}

_import_module_name() {
    _dir="$1"; _prop="$_dir/module.prop"; _name=""
    [ -f "$_prop" ] && _name=$(sed -n 's/^name=//p' "$_prop" | head -n1 | tr -d '\r')
    [ -n "$_name" ] || _name=$(basename "$_dir")
    printf '%s\n' "$_name"
}

import_installed_font_modules() {
    _imported=0; _duplicates=0; _failed=0; _modules=0; _seen_files=0; _names=""; _first_error=""
    for _root in /data/adb/modules /data/adb/modules_update; do
        [ -d "$_root" ] || continue
        for _module in "$_root"/*; do
            [ -d "$_module" ] || continue
            _id=$(basename "$_module")
            case "$_id" in LuoShu|luoshu|.*) continue ;; esac
            [ -f "$_module/remove" ] && continue
            [ -f "$_module/disable" ] && continue
            [ -f "$_module/module.prop" ] || continue
            _module_fonts=0; _module_name=$(_import_module_name "$_module")
            while IFS= read -r _font; do
                [ -f "$_font" ] || continue
                case "$_font" in */cache/*|*/webroot/*|*/backup/*|*/.luoshu-font-store/*) continue ;; esac
                _seen_files=$((_seen_files + 1)); [ "$_seen_files" -le 500 ] 2>/dev/null || break
                if _import_commit_file "$_font" "$(basename "$_font")" "installed-module:$_id"; then
                    _module_fonts=$((_module_fonts + 1))
                    if [ "$IMPORT_STATE" = imported ]; then _imported=$((_imported + 1)); else _duplicates=$((_duplicates + 1)); fi
                else
                    _failed=$((_failed + 1)); [ -n "$_first_error" ] || _first_error="$IMPORT_ERROR"
                fi
            done <<EOF
$(find "$_module" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) 2>/dev/null)
EOF
            if [ "$_module_fonts" -gt 0 ] 2>/dev/null; then
                _modules=$((_modules + 1)); _names="${_names:+$_names、}$_module_name"
            fi
        done
    done
    printf '{"status":"ok","data":{"modules":%s,"moduleNames":"%s","imported":%s,"duplicates":%s,"failed":%s,"firstError":"%s"}}\n' \
        "$_modules" "$(_import_json_escape "$_names")" "$_imported" "$_duplicates" "$_failed" "$(_import_json_escape "$_first_error")"
}
