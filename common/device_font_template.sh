#!/system/bin/sh
# LuoShu trusted stock font-template capture.
# A template is valid only when Android is running the ROM default font and LuoShu has
# no generated font/XML payload in its module tree. Active-font boots may reuse an
# already trusted template for the same ROM, but can never refresh it.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
PYROOT="$MODDIR/common/python"
PYTHON="$PYROOT/bin/luoshu-python"
ENGINE="$MODDIR/common/device_font_template.py"
OUT="$MODDIR/config/device-font-template.json"
KEY="$MODDIR/config/device-font-template.key"
STATE="$MODDIR/config/device-font-template.state"
PENDING="$MODDIR/config/device-font-template-pending.conf"
LOG="$MODDIR/logs/device-font-template.log"
LOCK="$MODDIR/.device-font-template.lock"
CAPTURE_REVISION=2

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

hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum | awk '{print $1}'
    else
        cksum | awk '{print $1 ":" $2}'
    fi
}

rom_key() {
    {
        getprop ro.build.fingerprint 2>/dev/null
        getprop ro.build.version.incremental 2>/dev/null
        getprop ro.product.device 2>/dev/null
        getprop ro.build.version.sdk 2>/dev/null
    } | hash_stream
}

active_font() {
    _dft_active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_dft_active" ] || _dft_active=default
    printf '%s\n' "$_dft_active"
}

collect_xml() {
    _dft_out="$1"
    : > "$_dft_out" || return 1
    for _dft_base in \
        /system/etc /system_ext/etc /product/etc /vendor/etc /odm/etc /oem/etc \
        /my_product/etc /my_engineering/etc /my_company/etc /my_preload/etc /my_region/etc /my_stock/etc \
        /oplus_product/etc /oplus_engineering/etc /oplus_version/etc /oplus_region/etc \
        /mi_ext/etc /cust/etc; do
        [ -d "$_dft_base" ] || continue
        find "$_dft_base" -maxdepth 3 -type f \( \
            -name 'fonts.xml' -o -name 'font_fallback.xml' -o \
            -name 'fonts_*.xml' -o -name 'font_fallback_*.xml' -o \
            -name '*font*customization*.xml' -o -name '*fonts*customization*.xml' \
        \) -print 2>/dev/null >> "$_dft_out"
    done
    [ -f /data/fonts/config/config.xml ] && printf '%s\n' /data/fonts/config/config.xml >> "$_dft_out"
    awk 'NF && !seen[$0]++' "$_dft_out" > "$_dft_out.unique" 2>/dev/null && mv -f "$_dft_out.unique" "$_dft_out"
    [ -s "$_dft_out" ]
}

source_key() {
    _dft_xml_list="$1"
    {
        rom_key
        while IFS= read -r _dft_xml; do
            [ -f "$_dft_xml" ] || continue
            stat -c '%n|%s|%Y|%i' "$_dft_xml" 2>/dev/null || ls -ln "$_dft_xml" 2>/dev/null
        done < "$_dft_xml_list"
    } | hash_stream
}

template_parts() {
    printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust'
}

capture_clean_reason() {
    _dft_active=$(active_font)
    if [ "$_dft_active" != default ]; then
        printf 'active-font:%s\n' "$_dft_active"
        return 1
    fi

    _dft_boot_state=$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-boot.conf" 2>/dev/null | head -n1)
    case "$_dft_boot_state" in prepared|booting)
        printf 'payload-transaction:%s\n' "$_dft_boot_state"
        return 1
        ;;
    esac
    if grep -q '^state=installed$' "$MODDIR/config/device-font-engine.conf" 2>/dev/null; then
        printf 'device-payload-installed\n'
        return 1
    fi

    for _dft_part in $(template_parts); do
        _dft_fonts="$MODDIR/$_dft_part/fonts"
        if [ -d "$_dft_fonts" ] && find "$_dft_fonts" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' -o -iname '*.otc' \) -print -quit 2>/dev/null | grep -q .; then
            printf 'module-font-payload:%s\n' "$_dft_part"
            return 1
        fi
        _dft_etc="$MODDIR/$_dft_part/etc"
        if [ -d "$_dft_etc" ] && grep -RIlE 'LuoShu(Mono|Slot)?-' "$_dft_etc" --include='*.xml' 2>/dev/null | head -n1 | grep -q .; then
            printf 'module-xml-payload:%s\n' "$_dft_part"
            return 1
        fi
    done
    printf 'clean\n'
    return 0
}

trusted_matches_rom() {
    [ -s "$OUT" ] && [ -s "$KEY" ] && [ -s "$STATE" ] || return 1
    [ "$(sed -n 's/^state=//p' "$STATE" 2>/dev/null | head -n1)" = trusted ] || return 1
    [ "$(sed -n 's/^captureRevision=//p' "$STATE" 2>/dev/null | head -n1)" = "$CAPTURE_REVISION" ] || return 1
    _dft_expected_rom=$(sed -n 's/^romKey=//p' "$STATE" 2>/dev/null | head -n1)
    _dft_expected_source=$(sed -n 's/^sourceKey=//p' "$STATE" 2>/dev/null | head -n1)
    [ -n "$_dft_expected_rom" ] && [ "$_dft_expected_rom" = "$(rom_key)" ] || return 1
    [ -n "$_dft_expected_source" ] && [ "$_dft_expected_source" = "$(cat "$KEY" 2>/dev/null)" ] || return 1
    grep -q '"captureRevision":2' "$OUT" 2>/dev/null || return 1
    return 0
}

mark_pending() {
    _dft_reason="$1"
    _dft_rom="$2"
    _dft_tmp="${PENDING}.tmp.$$"
    {
        printf 'state=pending-stock-boot\n'
        printf 'reason=%s\n' "$_dft_reason"
        printf 'romKey=%s\n' "$_dft_rom"
        printf 'activeFont=%s\n' "$(active_font)"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_dft_tmp" 2>/dev/null || return 1
    mv -f "$_dft_tmp" "$PENDING" 2>/dev/null || return 1
    chmod 0600 "$PENDING" 2>/dev/null || true
    log_template "原厂模板等待默认字体重启后采集：$_dft_reason"
}

capture_template() {
    _dft_force="${1:-0}"
    mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || return 1

    if [ "$_dft_force" != 1 ] && trusted_matches_rom; then
        rm -f "$PENDING" 2>/dev/null || true
        log_template '可信原厂模板与当前 ROM 一致，保持冻结'
        return 0
    fi

    _dft_rom=$(rom_key)
    _dft_reason=$(capture_clean_reason)
    _dft_clean_rc=$?
    if [ "$_dft_clean_rc" -ne 0 ]; then
        mark_pending "$_dft_reason" "$_dft_rom" || true
        return 2
    fi

    if ! mkdir "$LOCK" 2>/dev/null; then
        log_template '已有模板采集任务在运行'
        return 0
    fi
    trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT HUP INT TERM

    _dft_xml_list="$MODDIR/config/.device-font-xml.$$"
    collect_xml "$_dft_xml_list" || {
        rm -f "$_dft_xml_list" 2>/dev/null || true
        log_template '没有找到可读取的系统字体 XML'
        return 1
    }
    _dft_source=$(source_key "$_dft_xml_list")

    set -- --output "$OUT.tmp" --fingerprint "$_dft_rom" --capture-revision "$CAPTURE_REVISION"
    while IFS= read -r _dft_xml; do
        [ -f "$_dft_xml" ] && set -- "$@" --xml "$_dft_xml"
    done < "$_dft_xml_list"
    for _dft_root in \
        /system/fonts /system_ext/fonts /product/fonts /vendor/fonts /odm/fonts /oem/fonts \
        /my_product/fonts /my_engineering/fonts /my_company/fonts /my_preload/fonts /my_region/fonts /my_stock/fonts \
        /oplus_product/fonts /oplus_engineering/fonts /oplus_version/fonts /oplus_region/fonts \
        /mi_ext/fonts /cust/fonts /data/fonts/files; do
        [ -d "$_dft_root" ] && set -- "$@" --font-root "$_dft_root"
    done

    _dft_result=$(python_run "$@" 2>> "$LOG")
    _dft_rc=$?
    rm -f "$_dft_xml_list" 2>/dev/null || true
    if [ "$_dft_rc" -ne 0 ] || [ ! -s "$OUT.tmp" ] || ! grep -q '"captureRevision":2' "$OUT.tmp" 2>/dev/null; then
        rm -f "$OUT.tmp" 2>/dev/null || true
        log_template "可信原厂模板采集失败：code=$_dft_rc result=$_dft_result"
        return 1
    fi

    chmod 0600 "$OUT.tmp" 2>/dev/null || true
    mv -f "$OUT.tmp" "$OUT" 2>/dev/null || return 1
    printf '%s\n' "$_dft_source" > "$KEY.tmp.$$" 2>/dev/null || return 1
    mv -f "$KEY.tmp.$$" "$KEY" 2>/dev/null || return 1
    {
        printf 'state=trusted\n'
        printf 'captureRevision=%s\n' "$CAPTURE_REVISION"
        printf 'romKey=%s\n' "$_dft_rom"
        printf 'sourceKey=%s\n' "$_dft_source"
        printf 'activeFont=default\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$STATE.tmp.$$" 2>/dev/null || return 1
    mv -f "$STATE.tmp.$$" "$STATE" 2>/dev/null || return 1
    chmod 0600 "$OUT" "$KEY" "$STATE" 2>/dev/null || true
    rm -f "$PENDING" 2>/dev/null || true
    log_template "可信原厂字体模板已冻结：$_dft_result"
    return 0
}

case "${1:-ensure}" in
    ensure) capture_template 0 ;;
    refresh) capture_template 1 ;;
    trusted) trusted_matches_rom ;;
    status)
        if trusted_matches_rom; then
            printf 'trusted\n'
        elif [ -s "$PENDING" ]; then
            printf 'pending\n'
        else
            printf 'missing\n'
        fi
        ;;
    invalidate)
        rm -f "$STATE" "$PENDING" 2>/dev/null || true
        ;;
    path) printf '%s\n' "$OUT" ;;
    key) cat "$KEY" 2>/dev/null ;;
    *) echo "Usage: $0 {ensure|refresh|trusted|status|invalidate|path|key}" >&2; exit 2 ;;
esac