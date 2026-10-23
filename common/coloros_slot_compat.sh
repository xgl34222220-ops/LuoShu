#!/system/bin/sh
# ColorOS / OxygenOS font slot compatibility mode (opt-in, default off).
#
# The normal ColorOS route (coloros_global.sh) only overlays font files under
# /system, /system_ext and /product. OPlus keeps its selectable system font
# ("flip font") as entries in a /data directory (see coloros_flipfont.sh);
# /system/fonts/SysFont-*.ttf point there. Once Settings or the Theme Store
# re-points those entries outside /system/fonts, the overlay can no longer
# reach English/digit text drawn through them.
#
# When config/coloros_slot_compat.conf contains an exact "enabled=1" line,
# this mode additionally writes the active LuoShu font into those OPlus slots:
#   * only entries named OplusOSUI-* / ColorOSUI-* / SysFont-* / SysSans-* /
#     OplusSans-* that already exist (no new nodes);
#   * clock, monospace, icon, emoji, symbol, serif, italic and script-specific
#     slots are never touched (same deny tokens as common/font_inventory.py);
#   * only entries the overlay cannot reach (coloros_flipfont.sh state
#     "external" or "file") or entries this mode wrote earlier;
#   * every original entry (link target or file copy) is recorded first in a
#     store outside the module directory, so module updates keep it;
#   * any failure restores every recorded entry and leaves the mode inactive.
# With the switch off, on the system default font, on a non-ColorOS ROM, or on
# uninstall, recorded entries are put back and nothing else is written.
#
#   coloros_slot_compat.sh sync     apply or restore according to config/state
#   coloros_slot_compat.sh restore  put every recorded entry back
#   coloros_slot_compat.sh status   key=value lines for the App
#   coloros_slot_compat.sh boot     wait for boot completion, then sync
set +e

_lcsc_init() {
    LCSC_MODULE="${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
    LCSC_CONF="${LUOSHU_COLOROS_SLOT_COMPAT_CONF:-$LCSC_MODULE/config/coloros_slot_compat.conf}"
    LCSC_STORE="${LUOSHU_COLOROS_SLOT_COMPAT_STORE:-/data/adb/luoshu/coloros-slot-compat}"
    LCSC_MANIFEST="$LCSC_STORE/manifest.v1"
    LCSC_ACTIVE_CONF="${LUOSHU_ACTIVE_FONT_CONF:-$LCSC_MODULE/config/active_font.conf}"
    LCSC_OVERLAY="${LUOSHU_COLOROS_SLOT_COMPAT_OVERLAY:-$LCSC_MODULE/system/fonts}"
    LCSC_LOG="${LUOSHU_COLOROS_SLOT_COMPAT_LOG:-$LCSC_MODULE/logs/coloros_slot_compat.log}"
    if [ -f "$LCSC_MODULE/common/coloros_flipfont.sh" ]; then
        . "$LCSC_MODULE/common/coloros_flipfont.sh"
    elif [ -f "${0%/*}/coloros_flipfont.sh" ]; then
        . "${0%/*}/coloros_flipfont.sh"
    fi
    type _lcf_init >/dev/null 2>&1 && _lcf_init
}

_lcsc_log() {
    mkdir -p "${LCSC_LOG%/*}" 2>/dev/null || return 0
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$*" >> "$LCSC_LOG" 2>/dev/null || true
}

# Exact enabled=1 (last line wins); anything else, or no file, is off.
luoshu_coloros_slot_compat_enabled() {
    [ -n "$LCSC_CONF" ] || _lcsc_init
    [ -f "$LCSC_CONF" ] || return 1
    _lcsce_value=$(tr -d '\r' < "$LCSC_CONF" 2>/dev/null | sed -n 's/^enabled=\([01]\)$/\1/p' | tail -n 1)
    [ "$_lcsce_value" = 1 ]
}

_lcsc_is_coloros() {
    case "${LUOSHU_COLOROS_SLOT_COMPAT_FORCE_ROM:-}" in
        coloros) return 0 ;;
        other) return 1 ;;
    esac
    [ "${IS_COLOROS:-}" = true ] && return 0
    [ -n "$(getprop ro.build.version.oplusrom 2>/dev/null)$(getprop ro.build.version.opporom 2>/dev/null)$(getprop ro.oxygen.version 2>/dev/null)" ]
}

# >>> LUOSHU_SLOT_COMPAT_DENY (font_inventory.GENERIC_DENY_FILE_TOKENS + GENERIC_DENY_STYLE_TOKENS;
# scripts/coloros_slot_compat_test.sh checks every inventory token is listed here)
_lcsc_deny_tokens() {
    printf '%s\n' 'emoji icon symbol math music serif mono monospace clock dingbat barcode qrcode materialicons notocoloremoji adlam arabic hebrew thai devanagari bengali tamil telugu malayalam gujarati gurmukhi kannada khmer lao tibetan myanmar sinhala ethiopic georgian armenian japanese korean hangul hiragana katakana odia oriya cjkjp cjkkr italic oblique'
}
# <<< LUOSHU_SLOT_COMPAT_DENY

# OPlus proprietary UI slot names; clock/mono/icon and script slots are excluded.
luoshu_coloros_slot_compat_slot_ok() {
    case "$1" in
        OplusOSUI-*.ttf|OplusOSUI-*.otf|ColorOSUI-*.ttf|ColorOSUI-*.otf|SysFont-*.ttf|SysFont-*.otf|\
        SysSans-*.ttf|SysSans-*.otf|OplusSans-*.ttf|OplusSans-*.otf) ;;
        *) return 1 ;;
    esac
    _lcsso_lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    for _lcsso_token in $(_lcsc_deny_tokens); do
        case "$_lcsso_lower" in *"$_lcsso_token"*) return 1 ;; esac
    done
    return 0
}

_lcsc_role() {
    _lcsr_lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lcsr_lower" in
        *extrabold*|*extra-bold*) printf 'extrabold\n' ;;
        *semibold*|*semi-bold*|*demibold*) printf 'semibold\n' ;;
        *extralight*|*extra-light*|*xthin*) printf 'extralight\n' ;;
        *medium*) printf 'medium\n' ;;
        *black*|*heavy*) printf 'black\n' ;;
        *bold*) printf 'bold\n' ;;
        *light*) printf 'light\n' ;;
        *thin*) printf 'thin\n' ;;
        *) printf 'regular\n' ;;
    esac
}

# Single-face sfnt only (00010000 / OTTO / true); a .ttf slot must not get a collection.
_lcsc_font_ok() {
    [ -s "$1" ] || return 1
    _lcsfo_magic=$(dd if="$1" bs=4 count=1 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')
    case "$_lcsfo_magic" in 00010000|4f54544f|74727565) return 0 ;; esac
    return 1
}

# Font from the active LuoShu payload for this slot: same-named overlay file,
# then the weight anchor, then the regular anchor / core aliases.
_lcsc_source_for() {
    _lcssf_role=$(_lcsc_role "$1")
    for _lcssf_path in \
        "$LCSC_OVERLAY/$1" \
        "$LCSC_OVERLAY/.luoshu-font-store/${_lcssf_role}.font" \
        "$LCSC_OVERLAY/.luoshu-font-store/regular.font" \
        "$LCSC_OVERLAY/SysFont-Regular.ttf" \
        "$LCSC_OVERLAY/SysSans-En-Regular.ttf" \
        "$LCSC_OVERLAY/Roboto-Regular.ttf"; do
        _lcsc_font_ok "$_lcssf_path" && { printf '%s\n' "$_lcssf_path"; return 0; }
    done
    return 1
}

_lcsc_recorded() {
    [ -f "$LCSC_MANIFEST" ] && awk -F'|' -v n="$1" '$1 == n { found = 1 } END { exit found ? 0 : 1 }' "$LCSC_MANIFEST"
}

_lcsc_stat_owner() { stat -c '%u:%g' "$1" 2>/dev/null; }
_lcsc_stat_mode() { stat -c '%a' "$1" 2>/dev/null; }
_lcsc_stat_context() {
    _lcssc=$(stat -c '%C' "$1" 2>/dev/null)
    case "$_lcssc" in ''|'?') return 1 ;; esac
    printf '%s\n' "$_lcssc"
}

# Record the original entry once: name|link|target or name|file|owner|mode|context.
_lcsc_record() {
    _lcsr_name="$1"
    _lcsc_recorded "$_lcsr_name" && return 0
    _lcsr_path="$LCF_DIR/$_lcsr_name"
    mkdir -p "$LCSC_STORE/originals" 2>/dev/null || return 1
    chmod 0700 "$LCSC_STORE" 2>/dev/null || true
    if [ -L "$_lcsr_path" ]; then
        _lcsr_target=$(readlink "$_lcsr_path" 2>/dev/null)
        [ -n "$_lcsr_target" ] || return 1
        printf '%s|link|%s\n' "$_lcsr_name" "$_lcsr_target" >> "$LCSC_MANIFEST" || return 1
    elif [ -f "$_lcsr_path" ]; then
        cp -f "$_lcsr_path" "$LCSC_STORE/originals/$_lcsr_name.tmp" 2>/dev/null || return 1
        cmp -s "$_lcsr_path" "$LCSC_STORE/originals/$_lcsr_name.tmp" || return 1
        mv -f "$LCSC_STORE/originals/$_lcsr_name.tmp" "$LCSC_STORE/originals/$_lcsr_name" || return 1
        printf '%s|file|%s|%s|%s\n' "$_lcsr_name" "$(_lcsc_stat_owner "$_lcsr_path")" \
            "$(_lcsc_stat_mode "$_lcsr_path")" "$(_lcsc_stat_context "$_lcsr_path")" >> "$LCSC_MANIFEST" || return 1
    else
        return 1
    fi
    return 0
}

# Write src over slot atomically; the temp file is created inside the slot
# directory so it inherits that directory's label, then takes the original
# file's owner/mode/label when the original was a regular file.
_lcsc_write_slot() {
    _lcsw_name="$1"
    _lcsw_src="$2"
    _lcsw_path="$LCF_DIR/$_lcsw_name"
    _lcsw_tmp="$LCF_DIR/.luoshu-slot.$_lcsw_name.$$"
    _lcsw_owner=$(_lcsc_stat_owner "$LCF_DIR")
    _lcsw_mode=644
    _lcsw_context=''
    if [ -f "$LCSC_MANIFEST" ]; then
        _lcsw_row=$(awk -F'|' -v n="$_lcsw_name" '$1 == n && $2 == "file" { print; exit }' "$LCSC_MANIFEST")
        if [ -n "$_lcsw_row" ]; then
            _lcsw_owner=$(printf '%s' "$_lcsw_row" | cut -d'|' -f3)
            _lcsw_mode=$(printf '%s' "$_lcsw_row" | cut -d'|' -f4)
            _lcsw_context=$(printf '%s' "$_lcsw_row" | cut -d'|' -f5)
        fi
    fi
    rm -f "$_lcsw_tmp" 2>/dev/null
    cp -f "$_lcsw_src" "$_lcsw_tmp" 2>/dev/null || { rm -f "$_lcsw_tmp"; return 1; }
    [ -z "$_lcsw_owner" ] || chown "$_lcsw_owner" "$_lcsw_tmp" 2>/dev/null || true
    chmod "${_lcsw_mode:-644}" "$_lcsw_tmp" 2>/dev/null || chmod 0644 "$_lcsw_tmp" 2>/dev/null || true
    [ -z "$_lcsw_context" ] || chcon "$_lcsw_context" "$_lcsw_tmp" 2>/dev/null || true
    mv -f "$_lcsw_tmp" "$_lcsw_path" 2>/dev/null || { rm -f "$_lcsw_tmp"; return 1; }
    [ -f "$_lcsw_path" ] && [ ! -L "$_lcsw_path" ] && cmp -s "$_lcsw_src" "$_lcsw_path"
}

luoshu_coloros_slot_compat_restore() {
    [ -n "$LCSC_STORE" ] || _lcsc_init
    [ -f "$LCSC_MANIFEST" ] || { rm -rf "$LCSC_STORE/originals" 2>/dev/null; return 0; }
    _lcsrs_failed=0
    _lcsrs_count=0
    _lcsrs_keep="$LCSC_MANIFEST.keep.$$"
    : > "$_lcsrs_keep" 2>/dev/null
    while IFS='|' read -r _lcsrs_name _lcsrs_kind _lcsrs_a _lcsrs_b _lcsrs_c; do
        [ -n "$_lcsrs_name" ] || continue
        case "$_lcsrs_name" in */*|.*) continue ;; esac
        _lcsrs_path="$LCF_DIR/$_lcsrs_name"
        _lcsrs_ok=1
        if [ ! -d "$LCF_DIR" ]; then
            _lcsrs_ok=1
        elif [ "$_lcsrs_kind" = link ]; then
            rm -f "$_lcsrs_path" 2>/dev/null
            ln -s "$_lcsrs_a" "$_lcsrs_path" 2>/dev/null || _lcsrs_ok=0
            [ "$(readlink "$_lcsrs_path" 2>/dev/null)" = "$_lcsrs_a" ] || _lcsrs_ok=0
        elif [ "$_lcsrs_kind" = file ] && [ -f "$LCSC_STORE/originals/$_lcsrs_name" ]; then
            _lcsrs_tmp="$LCF_DIR/.luoshu-restore.$_lcsrs_name.$$"
            if cp -f "$LCSC_STORE/originals/$_lcsrs_name" "$_lcsrs_tmp" 2>/dev/null; then
                [ -z "$_lcsrs_a" ] || chown "$_lcsrs_a" "$_lcsrs_tmp" 2>/dev/null || true
                [ -z "$_lcsrs_b" ] || chmod "$_lcsrs_b" "$_lcsrs_tmp" 2>/dev/null || true
                [ -z "$_lcsrs_c" ] || chcon "$_lcsrs_c" "$_lcsrs_tmp" 2>/dev/null || true
                mv -f "$_lcsrs_tmp" "$_lcsrs_path" 2>/dev/null || _lcsrs_ok=0
            else
                _lcsrs_ok=0
            fi
            rm -f "$_lcsrs_tmp" 2>/dev/null
            cmp -s "$LCSC_STORE/originals/$_lcsrs_name" "$_lcsrs_path" || _lcsrs_ok=0
        fi
        if [ "$_lcsrs_ok" = 1 ]; then
            _lcsrs_count=$((_lcsrs_count + 1))
            rm -f "$LCSC_STORE/originals/$_lcsrs_name" 2>/dev/null
        else
            _lcsrs_failed=$((_lcsrs_failed + 1))
            printf '%s|%s|%s|%s|%s\n' "$_lcsrs_name" "$_lcsrs_kind" "$_lcsrs_a" "$_lcsrs_b" "$_lcsrs_c" >> "$_lcsrs_keep"
        fi
    done < "$LCSC_MANIFEST"
    if [ "$_lcsrs_failed" -eq 0 ]; then
        rm -f "$LCSC_MANIFEST" "$_lcsrs_keep" 2>/dev/null
        rm -rf "$LCSC_STORE/originals" 2>/dev/null
        rmdir "$LCSC_STORE" 2>/dev/null
        [ "$_lcsrs_count" -eq 0 ] || _lcsc_log "restored $_lcsrs_count OPlus slot(s)"
        return 0
    fi
    # Keep only the entries that still need restoring so a later sync retries them.
    mv -f "$_lcsrs_keep" "$LCSC_MANIFEST" 2>/dev/null
    _lcsc_log "restore incomplete: $_lcsrs_failed slot(s) kept for retry"
    return 1
}

_lcsc_active_font() {
    _lcsaf=$(sed -n '1p' "$LCSC_ACTIVE_CONF" 2>/dev/null | tr -d '\r\n')
    printf '%s\n' "${_lcsaf:-default}"
}

# Candidate slot names: proprietary, not protected, and either unreachable by
# the overlay (external/file) or written by this mode earlier.
luoshu_coloros_slot_compat_candidates() {
    [ -n "$LCSC_STORE" ] || _lcsc_init
    [ -d "$LCF_DIR" ] || return 0
    for _lcscd_path in "$LCF_DIR"/*; do
        [ -e "$_lcscd_path" ] || [ -L "$_lcscd_path" ] || continue
        _lcscd_name=${_lcscd_path##*/}
        luoshu_coloros_slot_compat_slot_ok "$_lcscd_name" || continue
        if _lcsc_recorded "$_lcscd_name"; then
            printf '%s\n' "$_lcscd_name"
            continue
        fi
        _lcscd_row=$(_lcf_classify "$_lcscd_path") || continue
        case "${_lcscd_row%%|*}" in external|file) printf '%s\n' "$_lcscd_name" ;; esac
    done
}

luoshu_coloros_slot_compat_apply() {
    [ -n "$LCSC_STORE" ] || _lcsc_init
    [ -d "$LCF_DIR" ] && [ ! -L "$LCF_DIR" ] || { _lcsc_log "skip: flip directory absent"; return 0; }
    _lcsa_names=$(luoshu_coloros_slot_compat_candidates)
    [ -n "$_lcsa_names" ] || { _lcsc_log "skip: no OPlus slot outside /system/fonts"; return 0; }
    _lcsa_written=0
    for _lcsa_name in $_lcsa_names; do
        _lcsa_src=$(_lcsc_source_for "$_lcsa_name") || {
            _lcsc_log "fail: no usable payload font for $_lcsa_name; rolling back"
            luoshu_coloros_slot_compat_restore
            return 1
        }
        if _lcsc_recorded "$_lcsa_name" && [ -f "$LCF_DIR/$_lcsa_name" ] && [ ! -L "$LCF_DIR/$_lcsa_name" ] && \
           cmp -s "$_lcsa_src" "$LCF_DIR/$_lcsa_name"; then
            _lcsa_written=$((_lcsa_written + 1))
            continue
        fi
        if ! _lcsc_record "$_lcsa_name" || ! _lcsc_write_slot "$_lcsa_name" "$_lcsa_src"; then
            _lcsc_log "fail: could not write $_lcsa_name; rolling back"
            luoshu_coloros_slot_compat_restore
            return 1
        fi
        _lcsa_written=$((_lcsa_written + 1))
    done
    _lcsc_log "applied: $_lcsa_written OPlus slot(s)"
    return 0
}

luoshu_coloros_slot_compat_sync() {
    _lcsc_init
    if luoshu_coloros_slot_compat_enabled && _lcsc_is_coloros && [ "$(_lcsc_active_font)" != default ]; then
        luoshu_coloros_slot_compat_apply
        return $?
    fi
    luoshu_coloros_slot_compat_restore
}

luoshu_coloros_slot_compat_status() {
    _lcsc_init
    _lcsst_enabled=false
    luoshu_coloros_slot_compat_enabled && _lcsst_enabled=true
    _lcsst_rom=false
    _lcsc_is_coloros && _lcsst_rom=true
    _lcsst_slots=0
    [ -f "$LCSC_MANIFEST" ] && _lcsst_slots=$(awk -F'|' 'NF >= 2 { n++ } END { print n + 0 }' "$LCSC_MANIFEST")
    printf 'enabled=%s\n' "$_lcsst_enabled"
    printf 'coloros=%s\n' "$_lcsst_rom"
    printf 'writtenSlots=%s\n' "$_lcsst_slots"
}

if [ "${0##*/}" = coloros_slot_compat.sh ]; then
    case "${1:-status}" in
        sync) luoshu_coloros_slot_compat_sync ;;
        restore) _lcsc_init; luoshu_coloros_slot_compat_restore ;;
        status) luoshu_coloros_slot_compat_status ;;
        boot)
            _lcsc_wait=0
            while [ "$(getprop sys.boot_completed 2>/dev/null)" != 1 ] && [ "$_lcsc_wait" -lt 150 ]; do
                sleep 2
                _lcsc_wait=$((_lcsc_wait + 1))
            done
            luoshu_coloros_slot_compat_sync
            ;;
        *) echo 'usage: coloros_slot_compat.sh sync|restore|status|boot' >&2; exit 2 ;;
    esac
fi
