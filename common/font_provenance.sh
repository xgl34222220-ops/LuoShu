#!/system/bin/sh
# Stable provenance for active-font reuse and composite caches.
# This file hashes only source/config/code inputs; it never touches live mounts.
set +e

_luoshu_provenance_module() {
    if [ -n "${LUOSHU_REAL_MODDIR:-}" ] && [ -d "${LUOSHU_REAL_MODDIR:-}" ]; then
        printf '%s\n' "${LUOSHU_REAL_MODDIR%/}"
    else
        printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    fi
}

luoshu_provenance_hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum 2>/dev/null | awk '{print $1}'
    elif command -v toybox >/dev/null 2>&1; then
        toybox sha256sum 2>/dev/null | awk '{print $1}'
    elif command -v cksum >/dev/null 2>&1; then
        cksum 2>/dev/null | awk '{print $1 "-" $2}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox cksum 2>/dev/null | awk '{print $1 "-" $2}'
    else
        return 1
    fi
}

luoshu_provenance_hash_file() {
    _lphf_file="$1"
    [ -f "$_lphf_file" ] || return 1
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$_lphf_file" 2>/dev/null | awk '{print $1}'
    elif command -v toybox >/dev/null 2>&1; then
        toybox sha256sum "$_lphf_file" 2>/dev/null | awk '{print $1}'
    elif command -v cksum >/dev/null 2>&1; then
        cksum "$_lphf_file" 2>/dev/null | awk '{print $1 "-" $2}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox cksum "$_lphf_file" 2>/dev/null | awk '{print $1 "-" $2}'
    else
        return 1
    fi
}

_luoshu_provenance_size() {
    if command -v stat >/dev/null 2>&1; then
        stat -c '%s' "$1" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%s' "$1" 2>/dev/null && return 0
    fi
    wc -c < "$1" 2>/dev/null | tr -d '[:space:]'
}

_luoshu_provenance_checksum_files() (
    [ "$#" -gt 0 ] || return 1
    {
        for _lpcf_file in "$@"; do
            [ -f "$_lpcf_file" ] || return 1
            _lpcf_hash=$(luoshu_provenance_hash_file "$_lpcf_file") || return 1
            _lpcf_size=$(_luoshu_provenance_size "$_lpcf_file")
            case "$_lpcf_size" in ''|*[!0-9]*) return 1 ;; esac
            printf '%s|%s|%s\n' "$_lpcf_file" "$_lpcf_size" "$_lpcf_hash"
        done
    } | luoshu_provenance_hash_stream
)

luoshu_provenance_inventory_identity() (
    _lpi_module="$(_luoshu_provenance_module)"
    set --
    for _lpi_file in "$_lpi_module/config/device_font_inventory.json" \
                     "$_lpi_module/config/device_font_partitions.conf" \
                     "$_lpi_module/config/device_font_roots.conf"; do
        [ ! -f "$_lpi_file" ] || set -- "$@" "$_lpi_file"
    done
    if [ "$#" -eq 0 ]; then
        printf 'no-inventory\n'
        return 0
    fi
    _luoshu_provenance_checksum_files "$@"
)

luoshu_provenance_engine_identity() (
    _lpe_module="$(_luoshu_provenance_module)"
    LC_ALL=C; export LC_ALL
    set --
    for _lpe_file in "$_lpe_module"/common/*.sh "$_lpe_module"/common/*.py                      "$_lpe_module"/common/legacy_v14_4/*.sh "$_lpe_module"/common/legacy_v14_4/*.py                      "$_lpe_module"/common/python/lib/python*/site-packages/fontTools/__init__.py; do
        [ ! -f "$_lpe_file" ] || set -- "$@" "$_lpe_file"
    done
    [ "$#" -gt 0 ] || return 1
    _luoshu_provenance_checksum_files "$@"
)

luoshu_provenance_source_signature() {
    _lpss_file="$1"
    [ -f "$_lpss_file" ] || return 1
    _lpss_size=$(_luoshu_provenance_size "$_lpss_file")
    case "$_lpss_size" in ''|*[!0-9]*) return 1 ;; esac
    _lpss_hash=$(luoshu_provenance_hash_file "$_lpss_file") || return 1
    {
        printf 'source-v1\n'
        printf '%s\n' "$_lpss_size"
        printf '%s\n' "$_lpss_hash"
    } | luoshu_provenance_hash_stream
}

_luoshu_provenance_detect_family() {
    if type detect_font_family >/dev/null 2>&1; then
        detect_font_family "$1"
        return
    fi
    _lpdf_result="${1%.*}"
    for _lpdf_suffix in Regular ExtraBold UltraBold ExtraLight UltraLight Bold Light Medium SemiBold Thin Black Heavy Italic Oblique Condensed Extended                         regular extrabold ultrabold extralight ultralight bold light medium semibold thin black heavy italic oblique condensed extended                         常规 粗体 细体 中等 半粗 极细 特粗 重 斜体 轻; do
        case "$_lpdf_result" in *-"$_lpdf_suffix") _lpdf_result="${_lpdf_result%-$_lpdf_suffix}" ;; esac
    done
    while true; do
        case "$_lpdf_result" in " ") _lpdf_result="" ;; *[[:space:]]) _lpdf_result="${_lpdf_result%?}" ;; *-) _lpdf_result="${_lpdf_result%-}" ;; *_) _lpdf_result="${_lpdf_result%_}" ;; *) break ;; esac
    done
    printf '%s\n' "$_lpdf_result"
}

luoshu_provenance_family_signature() (
    _lpfs_family="$1"
    _lpfs_root="${2:-${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts}"
    [ -n "$_lpfs_family" ] || return 1
    _lpfs_count=0
    _lpfs_rows=''
    LC_ALL=C; export LC_ALL
    for _lpfs_file in "$_lpfs_root"/*.ttf "$_lpfs_root"/*.otf "$_lpfs_root"/*.ttc                       "$_lpfs_root"/*.TTF "$_lpfs_root"/*.OTF "$_lpfs_root"/*.TTC; do
        [ -f "$_lpfs_file" ] || continue
        [ "$(_luoshu_provenance_detect_family "${_lpfs_file##*/}")" = "$_lpfs_family" ] || continue
        _lpfs_sig=$(luoshu_provenance_source_signature "$_lpfs_file") || return 1
        _lpfs_rows="${_lpfs_rows}${_lpfs_file##*/}|${_lpfs_sig}
"
        _lpfs_count=$((_lpfs_count + 1))
    done
    [ "$_lpfs_count" -gt 0 ] || return 1
    {
        printf 'family-v1|%s|%s\n' "$_lpfs_family" "$_lpfs_count"
        printf '%s' "$_lpfs_rows"
    } | luoshu_provenance_hash_stream
)

luoshu_provenance_direct_proof() {
    _lpdp_source="$1"
    _lpdp_label="$2"
    _lpdp_source_sig=$(luoshu_provenance_source_signature "$_lpdp_source") || return 1
    _lpdp_inventory=$(luoshu_provenance_inventory_identity) || return 1
    _lpdp_engine=$(luoshu_provenance_engine_identity) || return 1
    {
        printf 'direct-proof-v1\n'
        printf '%s\n' "$_lpdp_label"
        printf '%s\n' "$_lpdp_source_sig"
        printf '%s\n' "$_lpdp_inventory"
        printf '%s\n' "$_lpdp_engine"
    } | luoshu_provenance_hash_stream
}

luoshu_provenance_mix_proof() {
    _lpmp_cjk="$1"; _lpmp_latin="$2"; _lpmp_digit="$3"
    _lpmp_cjk_axes="$4"; _lpmp_latin_axes="$5"; _lpmp_digit_axes="$6"
    _lpmp_cjk_mode="$7"; _lpmp_latin_mode="$8"; _lpmp_digit_mode="$9"
    shift 9
    _lpmp_root="${1:-${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts}"
    _lpmp_cjk_sig=$(luoshu_provenance_family_signature "$_lpmp_cjk" "$_lpmp_root") || return 1
    _lpmp_latin_sig=$(luoshu_provenance_family_signature "$_lpmp_latin" "$_lpmp_root") || return 1
    _lpmp_digit_sig=$(luoshu_provenance_family_signature "$_lpmp_digit" "$_lpmp_root") || return 1
    _lpmp_inventory=$(luoshu_provenance_inventory_identity) || return 1
    _lpmp_engine=$(luoshu_provenance_engine_identity) || return 1
    {
        printf 'mix-proof-v1\n'
        printf '%s|%s|%s\n' "$_lpmp_cjk" "$_lpmp_latin" "$_lpmp_digit"
        printf '%s|%s|%s\n' "$_lpmp_cjk_axes" "$_lpmp_latin_axes" "$_lpmp_digit_axes"
        printf '%s|%s|%s\n' "$_lpmp_cjk_mode" "$_lpmp_latin_mode" "$_lpmp_digit_mode"
        printf '%s|%s|%s\n' "$_lpmp_cjk_sig" "$_lpmp_latin_sig" "$_lpmp_digit_sig"
        printf '%s\n%s\n' "$_lpmp_inventory" "$_lpmp_engine"
    } | luoshu_provenance_hash_stream
}
