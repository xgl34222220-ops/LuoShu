#!/system/bin/sh
# Shared composite byte/implementation proof. Callers provide hash_file/hash_text
# and COMPOSITE_RUNNER; policy, generation, ownership and validation stay local.

composite_validate_output() (
    # Used only when no real guarded generator ran: same-source copies and
    # legacy entries without a receipt. Proven warm entries need no glyph read.
    [ -s "$1" ] && [ ! -L "$1" ] || return 1
    MODDIR="$MODDIR" sh "$COMPOSITE_RUNNER" --validate-output "$1"
)

composite_validate_cached_output() {
    font_validate "$1" text && composite_validate_output "$1" >/dev/null
}

composite_cache_identity() (
    if command -v sha256sum >/dev/null 2>&1; then
        _cci_records=$(sha256sum "$MODDIR/common/composite_font.py" "$MODDIR/common/composite_layout.py" "$COMPOSITE_RUNNER" 2>/dev/null) || return 1
    elif command -v toybox >/dev/null 2>&1; then
        _cci_records=$(toybox sha256sum "$MODDIR/common/composite_font.py" "$MODDIR/common/composite_layout.py" "$COMPOSITE_RUNNER" 2>/dev/null) || return 1
    else
        _cci_engine=$(hash_file "$MODDIR/common/composite_font.py")
        _cci_layout=$(hash_file "$MODDIR/common/composite_layout.py")
        _cci_runner=$(hash_file "$COMPOSITE_RUNNER")
        [ -n "$_cci_engine" ] && [ -n "$_cci_layout" ] && [ -n "$_cci_runner" ] || return 1
        printf '%s\000%s\000%s' "$_cci_engine" "$_cci_layout" "$_cci_runner" | hash_text
        return $?
    fi
    # Hash the three contents in order; do not make their path names identity.
    printf '%s\n' "$_cci_records" | while IFS= read -r _cci_line; do
        printf '%s\000' "${_cci_line%% *}"
    done | hash_text
)

composite_receipt_matches() (
    # Parse only our fixed, complete record with Shell builtins. A receipt is
    # evidence for exact payload bytes, never permission to trust a filename.
    [ -f "$1" ] && [ ! -L "$1" ] || return 1
    {
        IFS= read -r _crm_schema && IFS= read -r _crm_payload &&
        IFS= read -r _crm_engine && IFS= read -r _crm_validator &&
        ! IFS= read -r _crm_extra
    } <"$1" || return 1
    [ "$_crm_schema" = "schema=${5:-auto-composite-receipt-v1}" ] &&
    [ "$_crm_payload" = "payloadDigest=$2" ] &&
    [ "$_crm_engine" = "engineIdentity=$3" ] &&
    [ "$_crm_validator" = "validatorIdentity=$4" ]
)

write_composite_receipt() (
    _wcr_target="$1"; _wcr_tmp="$2"
    {
        printf 'schema=%s\npayloadDigest=%s\n' "${6:-auto-composite-receipt-v1}" "$3"
        printf 'engineIdentity=%s\nvalidatorIdentity=%s\n' "$4" "$5"
    } >"$_wcr_tmp" && chmod 0644 "$_wcr_tmp" && mv -f "$_wcr_tmp" "$_wcr_target"
)

# App fine-tuning for imported Latin/digits (英数大小 / 英数上下位置), whole
# percent, carried by the mix request environment. 0/0 keeps the automatic
# layout and the historical cache key; any other value is part of the key.
composite_tune_clamp() {
    _ctc_value="$1"; _ctc_digits="${1#-}"
    case "$_ctc_digits" in ''|*[!0-9]*) printf '0\n'; return 0 ;; esac
    _ctc_digits=${_ctc_digits#"${_ctc_digits%%[!0]*}"}
    [ -n "$_ctc_digits" ] || _ctc_digits=0
    [ "${#_ctc_digits}" -le 3 ] || _ctc_digits=999
    [ "$_ctc_digits" -le "$2" ] || _ctc_digits="$2"
    case "$_ctc_value" in -*) [ "$_ctc_digits" = 0 ] || _ctc_digits="-$_ctc_digits" ;; esac
    printf '%s\n' "$_ctc_digits"
}

composite_tune_load() {
    COMPOSITE_TUNE_SIZE=$(composite_tune_clamp "${LUOSHU_MIX_LATIN_SIZE:-0}" 15)
    COMPOSITE_TUNE_OFFSET=$(composite_tune_clamp "${LUOSHU_MIX_LATIN_OFFSET:-0}" 10)
}

composite_tune_key_suffix() {
    [ "${COMPOSITE_TUNE_SIZE:-0}" = 0 ] && [ "${COMPOSITE_TUNE_OFFSET:-0}" = 0 ] && return 0
    printf -- '-latin-tune-size=%s-offset=%s' "$COMPOSITE_TUNE_SIZE" "$COMPOSITE_TUNE_OFFSET"
}
