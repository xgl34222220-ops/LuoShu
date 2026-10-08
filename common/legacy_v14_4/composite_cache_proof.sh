#!/system/bin/sh
# Shared composite byte/implementation proof. Callers provide hash_file/hash_text
# and COMPOSITE_RUNNER; policy, generation, ownership and validation stay local.

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
