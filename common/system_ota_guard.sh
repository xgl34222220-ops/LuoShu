#!/system/bin/sh
# LuoShu system OTA detection.
#
# After a successful font apply the ROM build (ro.build.fingerprint and
# ro.build.version.incremental) is recorded in config/system-build.conf. When a
# later boot reports a different fingerprint, the system was updated: the stock
# fonts LuoShu derived its payload from may have changed. Nothing is rebuilt or
# unmounted here; the existing stock rescan marker
# (config/stock_inventory_scan_pending, consumed by the pre-mount scan in
# post-fs-data/post-mount and by the deferred scan in service.sh) is set so the
# normal rescan/validation path runs, and the change is logged.
#
# Called from module_status.sh, which service.sh runs after sys.boot_completed=1.
#
# Early detection (luoshu_system_ota_early_boot) runs from the boot-loop guard's
# post-fs-data hook, before any LuoShu mount. On a fingerprint mismatch the
# generated XML overlay and the /data/fonts dynamic view were derived from the
# previous ROM, so this boot skips both: the generated XML is moved out of the
# payload for this boot only (the frozen self-mount then has no etc layer to
# mount) and font_safety.sh / the dynamic view helpers see the per-boot hold.
# Physical font slots still mount. The record itself is NOT updated here; the
# existing post-boot check above records the new build and requests the rescan.
# The held XML is put back on the next boot before anything validates it, so
# the payload manifest stays intact.
#
# Trusted rescan and automatic resume (config/system-ota-resume.conf). The
# per-boot hold above is unchanged; this state machine only decides whether a
# later boot keeps that same hold or resumes:
#
#   pending         an OTA hold started for this fingerprint.
#   rescan-trusted  the stock inventory was rescanned on this exact build
#                   (buildFingerprint == ro.build.fingerprint, rescan marker
#                   consumed); nothing is resumed yet.
#   apply-ready     the held XML was checked against this ROM: every font it
#                   names exists in the payload or on a stock partition. The
#                   next early boot puts it back (existing release path).
#   applied         that boot mounted (self-mount state ok) and completed.
#
# Any step that fails, or cannot be proven, keeps the hold: the next early boot
# holds the XML again through the same per-boot hold. A failed apply is never
# retried automatically for the same held XML; a new user apply (payload
# manifest identity changes, or LuoShu XML reappears in the payload) or a new
# OTA ends it. The module 'disable' file is never created here; on resume only a
# disable whose owner record (config/system-ota-disable-owner.conf) proves
# LuoShu created it is removed. A manager/user/other-module disable is never
# touched. Nothing depends on the root manager: Magisk, KernelSU (including
# late-load) and APatch all run the same post-fs-data hook and module_status.
set +e

luoshu_system_build_prop() {
    getprop "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_system_ota_file() {
    printf '%s/config/system-build.conf\n' "$1"
}

luoshu_system_ota_value() {
    sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_system_ota_log() {
    mkdir -p "$1/logs" 2>/dev/null || true
    printf '[%s] [SYSTEM-OTA] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$2" \
        >> "$1/logs/fontswitch.log" 2>/dev/null || true
}

# luoshu_system_ota_record MODDIR FINGERPRINT INCREMENTAL [PREVIOUS_FINGERPRINT]
luoshu_system_ota_record() {
    _lsor_file=$(luoshu_system_ota_file "$1")
    mkdir -p "${_lsor_file%/*}" 2>/dev/null || return 1
    {
        printf 'fingerprint=%s\n' "$2"
        printf 'incremental=%s\n' "$3"
        printf 'previousFingerprint=%s\n' "${4:-}"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_lsor_file}.tmp.$$" 2>/dev/null && mv -f "${_lsor_file}.tmp.$$" "$_lsor_file" 2>/dev/null || {
        rm -f "${_lsor_file}.tmp.$$" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$_lsor_file" 2>/dev/null || true
}

# luoshu_system_ota_check MODDIR ACTIVE_FONT MOUNT_STATE
# Returns 0 when an OTA was detected (rescan requested), 1 otherwise.
luoshu_system_ota_check() {
    _lsoc_module="$1"
    _lsoc_active="${2:-default}"
    _lsoc_mount="${3:-}"
    _lsoc_fp=$(luoshu_system_build_prop ro.build.fingerprint)
    [ -n "$_lsoc_fp" ] || return 1
    _lsoc_inc=$(luoshu_system_build_prop ro.build.version.incremental)
    _lsoc_file=$(luoshu_system_ota_file "$_lsoc_module")
    _lsoc_recorded=$(luoshu_system_ota_value "$_lsoc_file" fingerprint)

    if [ -n "$_lsoc_recorded" ] && [ "$_lsoc_recorded" != "$_lsoc_fp" ]; then
        _lsoc_old_inc=$(luoshu_system_ota_value "$_lsoc_file" incremental)
        mkdir -p "$_lsoc_module/config" 2>/dev/null || true
        : > "$_lsoc_module/config/stock_inventory_scan_pending" 2>/dev/null || true
        luoshu_system_ota_record "$_lsoc_module" "$_lsoc_fp" "$_lsoc_inc" "$_lsoc_recorded" >/dev/null 2>&1 || true
        luoshu_system_ota_log "$_lsoc_module" "检测到系统更新：${_lsoc_old_inc:-?} → ${_lsoc_inc:-?}（指纹 $_lsoc_recorded → $_lsoc_fp）；已标记重新扫描原厂字体并在下次挂载前校验，当前字体选择保留"
        if [ "$_lsoc_active" != default ]; then
            luoshu_system_ota_resume_begin "$_lsoc_module" "$_lsoc_recorded" "$_lsoc_fp" \
                "$(luoshu_system_ota_current_boot)" >/dev/null 2>&1 || true
        fi
        luoshu_system_ota_resume_post "$_lsoc_module" "$_lsoc_active" "$_lsoc_mount" >/dev/null 2>&1 || true
        return 0
    fi

    # Baseline: record the build only once a font is actually applied on it.
    if [ -z "$_lsoc_recorded" ] && [ "$_lsoc_active" != default ]; then
        case "$_lsoc_mount" in
            mounted|degraded|confirmed|verified)
                luoshu_system_ota_record "$_lsoc_module" "$_lsoc_fp" "$_lsoc_inc" >/dev/null 2>&1 || true
                ;;
        esac
    fi
    luoshu_system_ota_resume_post "$_lsoc_module" "$_lsoc_active" "$_lsoc_mount" >/dev/null 2>&1 || true
    return 1
}

luoshu_system_ota_hold_file() {
    printf '%s/config/system-ota-boot-hold.conf\n' "$1"
}

luoshu_system_ota_held_root() {
    printf '%s/.luoshu-ota-held-xml\n' "$1"
}

luoshu_system_ota_current_boot() {
    if [ -n "${LUOSHU_BOOTLOOP_BOOT_ID:-}" ]; then
        printf '%s\n' "$LUOSHU_BOOTLOOP_BOOT_ID"
        return 0
    fi
    cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n'
}

# True only during the boot that detected the mismatch.
luoshu_system_ota_boot_hold_active() {
    _lsobh_module="${1:-${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}}"
    _lsobh_file=$(luoshu_system_ota_hold_file "$_lsobh_module")
    [ -s "$_lsobh_file" ] || return 1
    _lsobh_boot=$(luoshu_system_ota_value "$_lsobh_file" bootId)
    [ -n "$_lsobh_boot" ] || return 1
    [ "$_lsobh_boot" = "$(luoshu_system_ota_current_boot)" ]
}

luoshu_system_ota_payload_root() {
    if [ -d "$1/.luoshu-payload" ] && [ ! -L "$1/.luoshu-payload" ]; then
        printf '%s/.luoshu-payload\n' "$1"
    else
        printf '%s\n' "$1"
    fi
}

luoshu_system_ota_parts() {
    printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust'
}

# Put XML held by an earlier OTA boot back into the payload. A file the user
# regenerated meanwhile (a newer apply) always wins over the held copy.
luoshu_system_ota_release_held_xml() {
    _lsorx_module="$1"
    _lsorx_held=$(luoshu_system_ota_held_root "$_lsorx_module")
    [ -d "$_lsorx_held" ] && [ ! -L "$_lsorx_held" ] || return 0
    _lsorx_payload=$(luoshu_system_ota_payload_root "$_lsorx_module")
    _lsorx_restored=0
    for _lsorx_part in $(luoshu_system_ota_parts); do
        for _lsorx_file in "$_lsorx_held/$_lsorx_part/etc"/*.xml; do
            [ -f "$_lsorx_file" ] && [ ! -L "$_lsorx_file" ] || continue
            _lsorx_target="$_lsorx_payload/$_lsorx_part/etc/${_lsorx_file##*/}"
            if [ -e "$_lsorx_target" ] || [ -L "$_lsorx_target" ]; then
                rm -f "$_lsorx_file" 2>/dev/null || true
                continue
            fi
            mkdir -p "${_lsorx_target%/*}" 2>/dev/null || continue
            mv -f "$_lsorx_file" "$_lsorx_target" 2>/dev/null && _lsorx_restored=$((_lsorx_restored + 1))
        done
    done
    rm -rf "$_lsorx_held" 2>/dev/null || true
    [ "$_lsorx_restored" -eq 0 ] || \
        luoshu_system_ota_log "$_lsorx_module" "已恢复上次系统更新首次开机暂停的 $_lsorx_restored 份字体 XML 覆盖"
    return 0
}

# luoshu_system_ota_early_boot MODDIR BOOT_ID
# Returns 0 when this boot holds back the XML overlay and dynamic view.
luoshu_system_ota_early_boot() {
    _lsoeb_module="$1"
    _lsoeb_boot="${2:-$(luoshu_system_ota_current_boot)}"
    [ -n "$_lsoeb_boot" ] || return 1
    _lsoeb_hold=$(luoshu_system_ota_hold_file "$_lsoeb_module")
    # post-fs-data may run more than once per boot (KernelSU/APatch, late-load).
    if [ "$(luoshu_system_ota_value "$_lsoeb_hold" bootId)" = "$_lsoeb_boot" ]; then
        return 0
    fi
    # Trusted-rescan resume: keep holding until the rescan and the held XML are
    # proven for this build (0), otherwise continue with the existing logic.
    if luoshu_system_ota_resume_early "$_lsoeb_module" "$_lsoeb_boot"; then
        return 0
    fi
    luoshu_system_ota_release_held_xml "$_lsoeb_module"

    _lsoeb_active=$(head -n1 "$_lsoeb_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lsoeb_active" ] && [ "$_lsoeb_active" != default ] || return 1
    _lsoeb_recorded=$(luoshu_system_ota_value "$(luoshu_system_ota_file "$_lsoeb_module")" fingerprint)
    [ -n "$_lsoeb_recorded" ] || return 1
    _lsoeb_fp=$(luoshu_system_build_prop ro.build.fingerprint)
    [ -n "$_lsoeb_fp" ] || return 1
    [ "$_lsoeb_fp" != "$_lsoeb_recorded" ] || return 1

    luoshu_system_ota_hold_xml "$_lsoeb_module" "$_lsoeb_boot" "$_lsoeb_fp" "$_lsoeb_recorded"
    _lsoeb_count="$LUOSHU_SYSTEM_OTA_HELD_COUNT"
    # The existing rescan marker: consumed by the pre-mount stock scan and the
    # deferred scan in service.sh.
    : > "$_lsoeb_module/config/stock_inventory_scan_pending" 2>/dev/null || true
    luoshu_system_ota_log "$_lsoeb_module" "开机早期检测到系统更新（指纹 $_lsoeb_recorded → $_lsoeb_fp）：本次启动跳过 XML 覆盖（暂停 $_lsoeb_count 份）与 /data/fonts 动态视图，只挂载字体文件槽，交给系统更新重扫处理"
    luoshu_system_ota_resume_begin "$_lsoeb_module" "$_lsoeb_recorded" "$_lsoeb_fp" "$_lsoeb_boot" >/dev/null 2>&1 || true
    return 0
}

# luoshu_system_ota_hold_xml MODDIR BOOT_ID FINGERPRINT PREVIOUS_FINGERPRINT
# The per-boot hold: move LuoShu's generated XML out of the payload and record
# the hold for this boot (font_safety.sh and the dynamic view helpers read it).
# Sets LUOSHU_SYSTEM_OTA_HELD_COUNT to the number of XML files moved now.
luoshu_system_ota_hold_xml() {
    _lsohx_module="$1"
    _lsohx_boot="$2"
    _lsohx_hold=$(luoshu_system_ota_hold_file "$_lsohx_module")
    _lsohx_payload=$(luoshu_system_ota_payload_root "$_lsohx_module")
    _lsohx_held=$(luoshu_system_ota_held_root "$_lsohx_module")
    _lsohx_count=0
    for _lsohx_part in $(luoshu_system_ota_parts); do
        for _lsohx_xml in "$_lsohx_payload/$_lsohx_part/etc"/*.xml; do
            [ -f "$_lsohx_xml" ] && [ ! -L "$_lsohx_xml" ] || continue
            grep -q 'LuoShu' "$_lsohx_xml" 2>/dev/null || continue
            mkdir -p "$_lsohx_held/$_lsohx_part/etc" 2>/dev/null || continue
            mv -f "$_lsohx_xml" "$_lsohx_held/$_lsohx_part/etc/${_lsohx_xml##*/}" 2>/dev/null && \
                _lsohx_count=$((_lsohx_count + 1))
        done
    done
    mkdir -p "$_lsohx_module/config" 2>/dev/null || true
    {
        printf 'bootId=%s\n' "$_lsohx_boot"
        printf 'fingerprint=%s\n' "$3"
        printf 'previousFingerprint=%s\n' "$4"
        printf 'heldXml=%s\n' "$_lsohx_count"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_lsohx_hold}.tmp.$$" 2>/dev/null && mv -f "${_lsohx_hold}.tmp.$$" "$_lsohx_hold" 2>/dev/null || {
        rm -f "${_lsohx_hold}.tmp.$$" 2>/dev/null || true
    }
    chmod 0644 "$_lsohx_hold" 2>/dev/null || true
    LUOSHU_SYSTEM_OTA_HELD_COUNT="$_lsohx_count"
    return 0
}

# ---------------------------------------------------------------------------
# Trusted rescan -> automatic resume state machine (see the header).
# ---------------------------------------------------------------------------

LUOSHU_SYSTEM_OTA_RESUME_SCHEMA='luoshu-ota-resume-v1'
LUOSHU_SYSTEM_OTA_DISABLE_OWNER_SCHEMA='luoshu-ota-disable-owner-v1'

luoshu_system_ota_resume_file() {
    printf '%s/config/system-ota-resume.conf\n' "$1"
}

luoshu_system_ota_disable_owner_file() {
    printf '%s/config/system-ota-disable-owner.conf\n' "$1"
}

luoshu_system_ota_resume_get() {
    _lsorg_file=$(luoshu_system_ota_resume_file "$1")
    [ -f "$_lsorg_file" ] && [ ! -L "$_lsorg_file" ] || return 1
    [ "$(luoshu_system_ota_value "$_lsorg_file" schema)" = "$LUOSHU_SYSTEM_OTA_RESUME_SCHEMA" ] || return 1
    luoshu_system_ota_value "$_lsorg_file" "$2"
}

luoshu_system_ota_resume_log() {
    mkdir -p "$1/logs" 2>/dev/null || true
    printf '[%s] [SYSTEM-OTA-RESUME] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$2" \
        >> "$1/logs/fontswitch.log" 2>/dev/null || true
}

luoshu_system_ota_hash_stdin() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum 2>/dev/null | awk '{print $1}'
    else
        cksum 2>/dev/null | awk '{print $1 "-" $2}'
    fi
}

# Identity of the generation the user applied: active font + payload manifest.
# A font switch rewrites the manifest, so a changed identity means the user
# applied a new generation on this ROM after the hold started.
luoshu_system_ota_generation_identity() {
    _lsogi_active=$(head -n1 "$1/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    _lsogi_manifest="$1/config/font-payload-manifest.conf"
    if [ -f "$_lsogi_manifest" ] && [ ! -L "$_lsogi_manifest" ]; then
        _lsogi_sum=$(luoshu_system_ota_hash_stdin < "$_lsogi_manifest")
    else
        _lsogi_sum=none
    fi
    printf '%s|%s\n' "${_lsogi_active:-default}" "${_lsogi_sum:-none}"
}

# Digest of the held XML set (relative path + bytes). Binds apply-ready and a
# failed apply to exactly the XML that was checked.
luoshu_system_ota_held_digest() {
    _lsohd_held=$(luoshu_system_ota_held_root "$1")
    {
        printf 'held-v1\n'
        if [ -d "$_lsohd_held" ] && [ ! -L "$_lsohd_held" ]; then
            for _lsohd_part in $(luoshu_system_ota_parts); do
                for _lsohd_xml in "$_lsohd_held/$_lsohd_part/etc"/*.xml; do
                    [ -f "$_lsohd_xml" ] && [ ! -L "$_lsohd_xml" ] || continue
                    printf '%s/etc/%s\n' "$_lsohd_part" "${_lsohd_xml##*/}"
                    cat "$_lsohd_xml" 2>/dev/null
                    printf '\n'
                done
            done
        fi
    } | luoshu_system_ota_hash_stdin
}

luoshu_system_ota_held_present() {
    _lsohp_held=$(luoshu_system_ota_held_root "$1")
    [ -d "$_lsohp_held" ] && [ ! -L "$_lsohp_held" ]
}

# True when LuoShu-generated XML is in the payload (written by a new apply).
luoshu_system_ota_payload_has_xml() {
    _lsophx_payload=$(luoshu_system_ota_payload_root "$1")
    for _lsophx_part in $(luoshu_system_ota_parts); do
        for _lsophx_xml in "$_lsophx_payload/$_lsophx_part/etc"/*.xml; do
            [ -f "$_lsophx_xml" ] && [ ! -L "$_lsophx_xml" ] || continue
            grep -q 'LuoShu' "$_lsophx_xml" 2>/dev/null && return 0
        done
    done
    return 1
}

# luoshu_system_ota_resume_write MODDIR KEY=VALUE...
# Rewrites the whole record atomically from the arguments.
luoshu_system_ota_resume_write() {
    _lsorw_module="$1"
    shift
    _lsorw_file=$(luoshu_system_ota_resume_file "$_lsorw_module")
    mkdir -p "${_lsorw_file%/*}" 2>/dev/null || return 1
    {
        printf 'schema=%s\n' "$LUOSHU_SYSTEM_OTA_RESUME_SCHEMA"
        for _lsorw_kv in "$@"; do
            case "$_lsorw_kv" in
                *=) continue ;;
                *=*) printf '%s\n' "$_lsorw_kv" | tr -d '\r\n'; printf '\n' ;;
            esac
        done
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_lsorw_file}.tmp.$$" 2>/dev/null && mv -f "${_lsorw_file}.tmp.$$" "$_lsorw_file" 2>/dev/null || {
        rm -f "${_lsorw_file}.tmp.$$" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$_lsorw_file" 2>/dev/null || true
    return 0
}

# luoshu_system_ota_resume_set MODDIR STATE [KEY=VALUE...]
# Moves to STATE, carrying the OTA identity fields from the current record.
luoshu_system_ota_resume_set() {
    _lsors_module="$1"
    _lsors_state="$2"
    shift 2
    luoshu_system_ota_resume_write "$_lsors_module" \
        "state=$_lsors_state" \
        "fingerprint=$(luoshu_system_ota_resume_get "$_lsors_module" fingerprint)" \
        "previousFingerprint=$(luoshu_system_ota_resume_get "$_lsors_module" previousFingerprint)" \
        "detectedBootId=$(luoshu_system_ota_resume_get "$_lsors_module" detectedBootId)" \
        "identity=$(luoshu_system_ota_resume_get "$_lsors_module" identity)" \
        "$@"
}

# luoshu_system_ota_resume_begin MODDIR PREVIOUS_FP FP BOOT_ID
# Starts 'pending' for FP. A record already tracking FP (not applied) is kept.
luoshu_system_ota_resume_begin() {
    _lsorb_module="$1"
    [ -n "$3" ] || return 1
    if [ "$(luoshu_system_ota_resume_get "$_lsorb_module" fingerprint)" = "$3" ]; then
        case "$(luoshu_system_ota_resume_get "$_lsorb_module" state)" in
            pending|rescan-trusted|apply-ready) return 0 ;;
        esac
    fi
    luoshu_system_ota_resume_write "$_lsorb_module" \
        state=pending \
        "fingerprint=$3" \
        "previousFingerprint=$2" \
        "detectedBootId=$4" \
        "identity=$(luoshu_system_ota_generation_identity "$_lsorb_module")" || return 1
    luoshu_system_ota_resume_log "$_lsorb_module" "系统更新暂停已登记（$2 → $3）：等待原厂字体重扫可信后再恢复 XML 覆盖"
    return 0
}

# luoshu_system_ota_stock_trusted MODDIR FINGERPRINT
# The stock inventory was rescanned on this build and the rescan marker is gone.
luoshu_system_ota_stock_trusted() {
    _lsost_module="$1"
    [ -n "$2" ] || return 1
    [ ! -e "$_lsost_module/config/stock_inventory_scan_pending" ] || return 1
    _lsost_inv="$_lsost_module/config/device_font_inventory.json"
    [ -f "$_lsost_inv" ] && [ ! -L "$_lsost_inv" ] && [ -s "$_lsost_inv" ] || return 1
    _lsost_fp=$(grep -o '"buildFingerprint"[[:space:]]*:[[:space:]]*"[^"]*"' "$_lsost_inv" 2>/dev/null | \
        head -n1 | sed 's/.*:[[:space:]]*"\([^"]*\)"$/\1/')
    [ -n "$_lsost_fp" ] && [ "$_lsost_fp" = "$2" ]
}

# Font file names (or absolute paths) referenced by <font> elements.
luoshu_system_ota_xml_fonts() {
    awk 'BEGIN { RS = "<" }
        /^font[ \t\r\n>]/ {
            if ($0 ~ /^[^>]*\/>/) next
            sub(/^[^>]*>/, "")
            gsub(/[ \t\r\n]/, "")
            if ($0 != "") print
        }' "$1" 2>/dev/null
}

# luoshu_system_ota_font_exists MODDIR NAME
# NAME exists in the payload or on a stock partition of the running ROM.
luoshu_system_ota_font_exists() {
    _lsofe_payload=$(luoshu_system_ota_payload_root "$1")
    _lsofe_root="${LUOSHU_SYSTEM_OTA_STOCK_ROOT:-}"
    case "$2" in
        ''|*..*) return 1 ;;
        /*)
            [ -f "$_lsofe_payload$2" ] && return 0
            [ -f "$_lsofe_root$2" ] && return 0
            return 1
            ;;
        */*) return 1 ;;
    esac
    for _lsofe_part in $(luoshu_system_ota_parts); do
        [ -f "$_lsofe_payload/$_lsofe_part/fonts/$2" ] && return 0
        [ -f "$_lsofe_root/$_lsofe_part/fonts/$2" ] && return 0
    done
    return 1
}

# luoshu_system_ota_held_xml_valid MODDIR
# Every font named by the held XML resolves on this ROM. Sets
# LUOSHU_SYSTEM_OTA_INVALID to the first missing names on failure.
luoshu_system_ota_held_xml_valid() {
    LUOSHU_SYSTEM_OTA_INVALID=''
    _lsohv_held=$(luoshu_system_ota_held_root "$1")
    luoshu_system_ota_held_present "$1" || return 0
    _lsohv_missing=0
    for _lsohv_part in $(luoshu_system_ota_parts); do
        for _lsohv_xml in "$_lsohv_held/$_lsohv_part/etc"/*.xml; do
            [ -f "$_lsohv_xml" ] && [ ! -L "$_lsohv_xml" ] || continue
            if [ ! -s "$_lsohv_xml" ] || [ ! -r "$_lsohv_xml" ]; then
                LUOSHU_SYSTEM_OTA_INVALID="$LUOSHU_SYSTEM_OTA_INVALID $_lsohv_part/etc/${_lsohv_xml##*/}(unreadable)"
                _lsohv_missing=$((_lsohv_missing + 1))
                continue
            fi
            for _lsohv_font in $(luoshu_system_ota_xml_fonts "$_lsohv_xml" | sort -u); do
                luoshu_system_ota_font_exists "$1" "$_lsohv_font" && continue
                _lsohv_missing=$((_lsohv_missing + 1))
                [ "$_lsohv_missing" -gt 5 ] || \
                    LUOSHU_SYSTEM_OTA_INVALID="$LUOSHU_SYSTEM_OTA_INVALID $_lsohv_font"
            done
        done
    done
    [ "$_lsohv_missing" -eq 0 ]
}

# luoshu_system_ota_resume_advance MODDIR FINGERPRINT
# pending -> rescan-trusted -> apply-ready, stopping at the first step that
# cannot be proven. Returns 0 only when the record is apply-ready.
luoshu_system_ota_resume_advance() {
    _lsora_module="$1"
    _lsora_fp="$2"
    _lsora_state=$(luoshu_system_ota_resume_get "$_lsora_module" state)
    case "$_lsora_state" in
        apply-ready) return 0 ;;
        pending|rescan-trusted) ;;
        *) return 1 ;;
    esac
    if ! luoshu_system_ota_stock_trusted "$_lsora_module" "$_lsora_fp"; then
        if [ "$_lsora_state" = rescan-trusted ]; then
            luoshu_system_ota_resume_set "$_lsora_module" pending reason=stock-rescan-no-longer-trusted >/dev/null 2>&1 || true
            luoshu_system_ota_resume_log "$_lsora_module" '原厂字体清单已不再可信（重扫待办或指纹不符），继续暂停 XML 覆盖'
        fi
        return 1
    fi
    _lsora_digest=$(luoshu_system_ota_held_digest "$_lsora_module")
    _lsora_failed=$(luoshu_system_ota_resume_get "$_lsora_module" applyFailedDigest)
    if [ "$_lsora_state" = pending ]; then
        luoshu_system_ota_resume_set "$_lsora_module" rescan-trusted \
            "trustedBootId=$(luoshu_system_ota_current_boot)" \
            "applyFailedDigest=$_lsora_failed" \
            "applyFailedReason=$(luoshu_system_ota_resume_get "$_lsora_module" applyFailedReason)" || return 1
        luoshu_system_ota_resume_log "$_lsora_module" "原厂字体重扫可信（清单指纹 = $_lsora_fp）"
    fi
    # A failed apply of this exact held XML is not retried automatically.
    if [ -n "$_lsora_failed" ] && [ "$_lsora_failed" = "$_lsora_digest" ]; then
        return 1
    fi
    if ! luoshu_system_ota_held_xml_valid "$_lsora_module"; then
        if [ "$(luoshu_system_ota_resume_get "$_lsora_module" invalidDigest)" != "$_lsora_digest" ]; then
            luoshu_system_ota_resume_set "$_lsora_module" rescan-trusted \
                "trustedBootId=$(luoshu_system_ota_resume_get "$_lsora_module" trustedBootId)" \
                "invalidDigest=$_lsora_digest" >/dev/null 2>&1 || true
            luoshu_system_ota_resume_log "$_lsora_module" "暂停的 XML 引用了新系统中不存在的字体：${LUOSHU_SYSTEM_OTA_INVALID# }；继续暂停，重新应用字体即可恢复"
        fi
        return 1
    fi
    luoshu_system_ota_resume_set "$_lsora_module" apply-ready \
        "trustedBootId=$(luoshu_system_ota_resume_get "$_lsora_module" trustedBootId)" \
        "readyDigest=$_lsora_digest" || return 1
    luoshu_system_ota_resume_log "$_lsora_module" '暂停的 XML 已按新系统原厂清单校验通过，下次开机自动恢复 XML 覆盖'
    return 0
}

luoshu_system_ota_mount_ok() {
    case "$1" in
        mounted|degraded|confirmed|verified) return 0 ;;
    esac
    return 1
}

# Remove $MODDIR/disable only when LuoShu's own owner record proves LuoShu
# created it (exact token match). A disable written by the user, the root
# manager or another module is never removed; a stale owner record of ours is.
luoshu_system_ota_release_owned_disable() {
    _lsorod_module="$1"
    _lsorod_owner=$(luoshu_system_ota_disable_owner_file "$_lsorod_module")
    [ -e "$_lsorod_owner" ] || [ -L "$_lsorod_owner" ] || return 0
    if [ -L "$_lsorod_owner" ] || [ ! -f "$_lsorod_owner" ] || \
       [ "$(luoshu_system_ota_value "$_lsorod_owner" schema)" != "$LUOSHU_SYSTEM_OTA_DISABLE_OWNER_SCHEMA" ]; then
        return 0
    fi
    _lsorod_token=$(luoshu_system_ota_value "$_lsorod_owner" token)
    case "$_lsorod_token" in
        luoshu-system-ota-v1:*) ;;
        *) return 0 ;;
    esac
    _lsorod_disable="$_lsorod_module/disable"
    if [ -f "$_lsorod_disable" ] && [ ! -L "$_lsorod_disable" ] && \
       [ "$(head -n1 "$_lsorod_disable" 2>/dev/null | tr -d '\r\n')" = "$_lsorod_token" ]; then
        rm -f "$_lsorod_disable" 2>/dev/null || return 1
        [ ! -e "$_lsorod_disable" ] || return 1
        luoshu_system_ota_resume_log "$_lsorod_module" '已移除洛书自己创建的 disable 标记'
    elif [ -e "$_lsorod_disable" ] || [ -L "$_lsorod_disable" ]; then
        luoshu_system_ota_resume_log "$_lsorod_module" '存在非洛书创建的 disable 标记，保持不动'
    fi
    rm -f "$_lsorod_owner" 2>/dev/null || return 1
    return 0
}

luoshu_system_ota_resume_mark_applied() {
    _lsorma_module="$1"
    luoshu_system_ota_release_owned_disable "$_lsorma_module" || return 1
    luoshu_system_ota_resume_set "$_lsorma_module" applied "reason=$2" \
        "appliedBootId=$3" >/dev/null 2>&1 || return 1
    luoshu_system_ota_resume_log "$_lsorma_module" "系统更新后的字体已恢复（$2）"
    return 0
}

luoshu_system_ota_resume_mark_failed() {
    _lsormf_module="$1"
    luoshu_system_ota_resume_set "$_lsormf_module" rescan-trusted \
        "trustedBootId=$(luoshu_system_ota_resume_get "$_lsormf_module" trustedBootId)" \
        "applyFailedDigest=$(luoshu_system_ota_resume_get "$_lsormf_module" readyDigest)" \
        "applyFailedReason=$2" \
        "applyFailedBootId=$3" >/dev/null 2>&1 || true
    luoshu_system_ota_resume_log "$_lsormf_module" "恢复 XML 覆盖的那次开机未通过（$2），重新暂停；不会自动重试，重新应用字体即可恢复"
    return 0
}

# luoshu_system_ota_resume_early MODDIR BOOT_ID
# Called before the existing early logic. Returns 0 when this boot keeps the
# hold (the per-boot hold is re-recorded here); 1 to continue with the existing
# logic (no record, stale record, resume now, or a newer apply).
luoshu_system_ota_resume_early() {
    _lsore_module="$1"
    _lsore_boot="$2"
    _lsore_state=$(luoshu_system_ota_resume_get "$_lsore_module" state) || return 1
    case "$_lsore_state" in
        pending|rescan-trusted|apply-ready) ;;
        *) return 1 ;;
    esac
    _lsore_fp=$(luoshu_system_build_prop ro.build.fingerprint)
    [ -n "$_lsore_fp" ] || return 1
    # Another OTA since: the existing detection starts a new hold.
    [ "$(luoshu_system_ota_resume_get "$_lsore_module" fingerprint)" = "$_lsore_fp" ] || return 1
    # The post-boot check has not recorded this build yet: the existing
    # detection still sees the mismatch and holds again.
    [ "$(luoshu_system_ota_value "$(luoshu_system_ota_file "$_lsore_module")" fingerprint)" = "$_lsore_fp" ] || return 1
    _lsore_active=$(head -n1 "$_lsore_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    if [ -z "$_lsore_active" ] || [ "$_lsore_active" = default ]; then
        # Nothing of LuoShu mounts; the user left the custom font.
        luoshu_system_ota_resume_mark_applied "$_lsore_module" default-font "$_lsore_boot" >/dev/null 2>&1 || true
        return 1
    fi
    _lsore_prev=$(luoshu_system_ota_resume_get "$_lsore_module" previousFingerprint)

    if [ "$_lsore_state" = apply-ready ]; then
        _lsore_apply_boot=$(luoshu_system_ota_resume_get "$_lsore_module" applyBootId)
        if [ "$_lsore_apply_boot" = "$_lsore_boot" ]; then
            return 1
        fi
        if [ -z "$_lsore_apply_boot" ]; then
            if [ "$(luoshu_system_ota_held_digest "$_lsore_module")" = \
                 "$(luoshu_system_ota_resume_get "$_lsore_module" readyDigest)" ] && \
               luoshu_system_ota_stock_trusted "$_lsore_module" "$_lsore_fp"; then
                luoshu_system_ota_resume_set "$_lsore_module" apply-ready \
                    "trustedBootId=$(luoshu_system_ota_resume_get "$_lsore_module" trustedBootId)" \
                    "readyDigest=$(luoshu_system_ota_resume_get "$_lsore_module" readyDigest)" \
                    "applyBootId=$_lsore_boot" || {
                        luoshu_system_ota_hold_xml "$_lsore_module" "$_lsore_boot" "$_lsore_fp" "$_lsore_prev"
                        return 0
                    }
                luoshu_system_ota_resume_log "$_lsore_module" '本次开机恢复系统更新前暂停的 XML 覆盖'
                return 1
            fi
            # The held XML or the inventory changed after approval.
            luoshu_system_ota_resume_set "$_lsore_module" pending reason=apply-ready-revoked >/dev/null 2>&1 || true
            luoshu_system_ota_resume_log "$_lsore_module" '暂停的 XML 或原厂清单在批准后发生变化，撤销自动恢复并继续暂停'
            luoshu_system_ota_hold_xml "$_lsore_module" "$_lsore_boot" "$_lsore_fp" "$_lsore_prev"
            return 0
        fi
        # The resume boot was not confirmed by module_status: judge it now from
        # the boot-loop guard and the self-mount record that boot left.
        _lsore_completed=$(sed -n 's/^completedBootId=//p' "$_lsore_module/config/boot-loop-guard.conf" 2>/dev/null | head -n1 | tr -d '\r\n')
        _lsore_mount=$(sed -n 's/^state=//p' "$_lsore_module/config/self-mount.conf" 2>/dev/null | head -n1 | tr -d '\r\n')
        if [ "$_lsore_completed" = "$_lsore_apply_boot" ] && luoshu_system_ota_mount_ok "$_lsore_mount"; then
            if luoshu_system_ota_resume_mark_applied "$_lsore_module" boot-completed "$_lsore_apply_boot"; then
                return 1
            fi
            # Cleanup failed: stay apply-ready, but do not hold (XML is back).
            return 1
        fi
        if [ "$_lsore_completed" = "$_lsore_apply_boot" ]; then
            luoshu_system_ota_resume_mark_failed "$_lsore_module" "mount-${_lsore_mount:-unknown}" "$_lsore_apply_boot"
        else
            luoshu_system_ota_resume_mark_failed "$_lsore_module" boot-not-completed "$_lsore_apply_boot"
        fi
        luoshu_system_ota_hold_xml "$_lsore_module" "$_lsore_boot" "$_lsore_fp" "$_lsore_prev"
        return 0
    fi

    # pending / rescan-trusted. A newer apply on this ROM ends the hold: the
    # existing release keeps the newer payload XML over the held copy.
    if luoshu_system_ota_held_present "$_lsore_module" && luoshu_system_ota_payload_has_xml "$_lsore_module"; then
        luoshu_system_ota_resume_mark_applied "$_lsore_module" user-reapply "$_lsore_boot" >/dev/null 2>&1 || true
        return 1
    fi
    if [ "$(luoshu_system_ota_generation_identity "$_lsore_module")" != \
         "$(luoshu_system_ota_resume_get "$_lsore_module" identity)" ]; then
        luoshu_system_ota_resume_mark_applied "$_lsore_module" user-reapply "$_lsore_boot" >/dev/null 2>&1 || true
        return 1
    fi
    if luoshu_system_ota_resume_advance "$_lsore_module" "$_lsore_fp"; then
        luoshu_system_ota_resume_set "$_lsore_module" apply-ready \
            "trustedBootId=$(luoshu_system_ota_resume_get "$_lsore_module" trustedBootId)" \
            "readyDigest=$(luoshu_system_ota_resume_get "$_lsore_module" readyDigest)" \
            "applyBootId=$_lsore_boot" || {
                luoshu_system_ota_hold_xml "$_lsore_module" "$_lsore_boot" "$_lsore_fp" "$_lsore_prev"
                return 0
            }
        luoshu_system_ota_resume_log "$_lsore_module" '本次开机恢复系统更新前暂停的 XML 覆盖'
        return 1
    fi
    luoshu_system_ota_hold_xml "$_lsore_module" "$_lsore_boot" "$_lsore_fp" "$_lsore_prev"
    luoshu_system_ota_resume_log "$_lsore_module" "继续暂停 XML 覆盖与 /data/fonts 动态视图（状态 $(luoshu_system_ota_resume_get "$_lsore_module" state)），字体文件槽照常挂载"
    return 0
}

# luoshu_system_ota_resume_post MODDIR ACTIVE_FONT MOUNT_STATE
# After boot completed (module_status.sh): confirm a resume boot, or move a
# pending record forward so the next early boot can resume directly.
luoshu_system_ota_resume_post() {
    _lsorp_module="$1"
    _lsorp_state=$(luoshu_system_ota_resume_get "$_lsorp_module" state) || return 0
    _lsorp_fp=$(luoshu_system_build_prop ro.build.fingerprint)
    [ -n "$_lsorp_fp" ] || return 0
    [ "$(luoshu_system_ota_resume_get "$_lsorp_module" fingerprint)" = "$_lsorp_fp" ] || return 0
    _lsorp_boot=$(luoshu_system_ota_current_boot)
    case "$_lsorp_state" in
        apply-ready)
            [ -n "$_lsorp_boot" ] && \
                [ "$(luoshu_system_ota_resume_get "$_lsorp_module" applyBootId)" = "$_lsorp_boot" ] || return 0
            if [ "${2:-default}" = default ]; then
                luoshu_system_ota_resume_mark_applied "$_lsorp_module" default-font "$_lsorp_boot"
            elif luoshu_system_ota_mount_ok "$3"; then
                luoshu_system_ota_resume_mark_applied "$_lsorp_module" mounted "$_lsorp_boot"
            elif [ "$3" = failed ]; then
                luoshu_system_ota_resume_mark_failed "$_lsorp_module" mount-failed "$_lsorp_boot"
            fi
            ;;
        pending|rescan-trusted)
            [ "${2:-default}" != default ] || return 0
            luoshu_system_ota_resume_advance "$_lsorp_module" "$_lsorp_fp" >/dev/null 2>&1 || true
            ;;
    esac
    return 0
}

# One-line status for diagnostics and tests.
luoshu_system_ota_resume_status() {
    _lsorst_state=$(luoshu_system_ota_resume_get "$1" state) || {
        printf 'state=none\n'
        return 0
    }
    printf 'state=%s\nfingerprint=%s\napplyFailedReason=%s\n' "$_lsorst_state" \
        "$(luoshu_system_ota_resume_get "$1" fingerprint)" \
        "$(luoshu_system_ota_resume_get "$1" applyFailedReason)"
}
