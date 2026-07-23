#!/system/bin/sh
# LuoShu v2.2 device font template capture.
# Read-only: discovers Android/OEM font XML and records each real slot's metrics.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
PYROOT="$MODDIR/common/python"
PYTHON="$PYROOT/bin/luoshu-python"
ENGINE="$MODDIR/common/device_font_template.py"
OUT="$MODDIR/config/device-font-template.json"
KEY="$MODDIR/config/device-font-template.key"
LOG="$MODDIR/logs/device-font-template.log"
LOCK="$MODDIR/.device-font-template.lock"

log_template() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$LOG" 2>/dev/null || true
}

python_run() {
    [ -x "$PYTHON" ] && [ -f "$ENGINE" ] || return 1
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYTHON" "$ENGINE" "$@"
}

collect_xml() {
    _out="$1"
    : > "$_out" || return 1
    for _base in \
        /system/etc /system_ext/etc /product/etc /vendor/etc /odm/etc /oem/etc \
        /my_product/etc /my_engineering/etc /my_company/etc /my_preload/etc /my_region/etc /my_stock/etc \
        /oplus_product/etc /oplus_engineering/etc /oplus_version/etc /oplus_region/etc \
        /mi_ext/etc /cust/etc; do
        [ -d "$_base" ] || continue
        find "$_base" -maxdepth 3 -type f \( \
            -name 'fonts.xml' -o -name 'font_fallback.xml' -o \
            -name 'fonts_*.xml' -o -name 'font_fallback_*.xml' -o \
            -name '*font*customization*.xml' -o -name '*fonts*customization*.xml' \
        \) -print 2>/dev/null >> "$_out"
    done
    [ -f /data/fonts/config/config.xml ] && printf '%s\n' /data/fonts/config/config.xml >> "$_out"
    awk 'NF && !seen[$0]++' "$_out" > "$_out.unique" 2>/dev/null && mv -f "$_out.unique" "$_out"
    [ -s "$_out" ]
}

build_fingerprint() {
    _xml_list="$1"
    {
        getprop ro.build.fingerprint 2>/dev/null
        getprop ro.build.version.incremental 2>/dev/null
        getprop ro.product.device 2>/dev/null
        while IFS= read -r _xml; do
            [ -f "$_xml" ] || continue
            stat -c '%n|%s|%Y' "$_xml" 2>/dev/null || ls -ln "$_xml" 2>/dev/null
        done < "$_xml_list"
    } | if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}'
    else
        cksum | awk '{print $1 ":" $2}'
    fi
}

capture_template() {
    _force="${1:-0}"
    mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || return 1
    if ! mkdir "$LOCK" 2>/dev/null; then
        log_template "已有模板采集任务在运行"
        return 0
    fi
    trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT HUP INT TERM

    _xml_list="$MODDIR/config/.device-font-xml.$$"
    collect_xml "$_xml_list" || {
        rm -f "$_xml_list" 2>/dev/null || true
        log_template "没有找到可读取的系统字体 XML"
        return 1
    }
    _fingerprint=$(build_fingerprint "$_xml_list")
    _old=$(cat "$KEY" 2>/dev/null)
    if [ "$_force" != 1 ] && [ -n "$_fingerprint" ] && [ "$_fingerprint" = "$_old" ] && [ -s "$OUT" ]; then
        rm -f "$_xml_list" 2>/dev/null || true
        log_template "设备字体模板未变化，跳过重建"
        return 0
    fi

    set -- --output "$OUT.tmp" --fingerprint "$_fingerprint"
    while IFS= read -r _xml; do
        [ -f "$_xml" ] && set -- "$@" --xml "$_xml"
    done < "$_xml_list"
    for _root in \
        /system/fonts /system_ext/fonts /product/fonts /vendor/fonts /odm/fonts /oem/fonts \
        /my_product/fonts /my_engineering/fonts /my_company/fonts /my_preload/fonts /my_region/fonts /my_stock/fonts \
        /oplus_product/fonts /oplus_engineering/fonts /oplus_version/fonts /oplus_region/fonts \
        /mi_ext/fonts /cust/fonts /data/fonts/files; do
        [ -d "$_root" ] && set -- "$@" --font-root "$_root"
    done

    _result=$(python_run "$@" 2>> "$LOG")
    _rc=$?
    rm -f "$_xml_list" 2>/dev/null || true
    if [ "$_rc" -ne 0 ] || [ ! -s "$OUT.tmp" ]; then
        rm -f "$OUT.tmp" 2>/dev/null || true
        log_template "设备字体模板采集失败：code=$_rc result=$_result"
        return 1
    fi
    chmod 0600 "$OUT.tmp" 2>/dev/null || true
    mv -f "$OUT.tmp" "$OUT" 2>/dev/null || return 1
    printf '%s\n' "$_fingerprint" > "$KEY" 2>/dev/null || true
    chmod 0600 "$KEY" 2>/dev/null || true
    log_template "设备字体模板采集完成：$_result"
    return 0
}

case "${1:-ensure}" in
    ensure) capture_template 0 ;;
    refresh) capture_template 1 ;;
    path) printf '%s\n' "$OUT" ;;
    key) cat "$KEY" 2>/dev/null ;;
    *) echo "Usage: $0 {ensure|refresh|path|key}" >&2; exit 2 ;;
esac
