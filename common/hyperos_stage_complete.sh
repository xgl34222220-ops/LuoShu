#!/system/bin/sh
# Complete a staged LuoShu payload with the same HyperOS physical UI targets used by
# the current mapper. This helper never writes the live payload; callers pass an
# isolated next-boot/staging root.
set +e

PAYLOAD_ROOT="${1:-${LUOSHU_HYPEROS_STAGE_ROOT:-}}"
[ -n "$PAYLOAD_ROOT" ] || exit 2

REALMOD="${LUOSHU_REAL_MODDIR:-}"
if [ -z "$REALMOD" ]; then
    _self_dir=$(CDPATH= cd -- "${0%/*}" 2>/dev/null && pwd)
    REALMOD=$(CDPATH= cd -- "$_self_dir/.." 2>/dev/null && pwd)
fi
[ -f "$REALMOD/module.prop" ] || exit 2

MODULE_DIR="$REALMOD"
MODDIR="$REALMOD"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
export MODULE_DIR MODDIR USER_FONTS_DIR

[ -f "$REALMOD/common/util_functions.sh" ] && . "$REALMOD/common/util_functions.sh"
[ -f "$REALMOD/common/rom_adapters.sh" ] && . "$REALMOD/common/rom_adapters.sh"
[ -f "$REALMOD/common/hyperos_global.sh" ] && . "$REALMOD/common/hyperos_global.sh"

type _hyperos_core_files >/dev/null 2>&1 || exit 2
type _hyperos_weight_files >/dev/null 2>&1 || exit 2
type _hyperos_upright_ui_files >/dev/null 2>&1 || exit 2
type _hyperos_clock_ui_files >/dev/null 2>&1 || exit 2

stage_font_dir="$PAYLOAD_ROOT/system/fonts"
[ -d "$stage_font_dir" ] || exit 1

# v3.3.6 used one compact line contract for HyperOS physical slots instead of
# feeding each user's raw hhea/OS2 metrics directly to SystemUI and app controls.
# That release is already device-proven to have substantially less vertical drift.
# Reuse the exact old ratios here, but cache once per distinct source font. A fixed
# composite maps the same source into every 100-900 slot; keying this cache by weight
# rewrote the same large CJK font nine times and turned a seconds-level switch into
# several minutes.
hyperos_336_source_key() {
    _source="$1"
    _contract_key="${2:-main}"
    _identity=$(stat -c '%d:%i:%s:%Y' "$_source" 2>/dev/null)
    [ -n "$_identity" ] || _identity=$(toybox stat -c '%d:%i:%s:%Y' "$_source" 2>/dev/null)
    [ -n "$_identity" ] || _identity="$_source:$(wc -c <"$_source" 2>/dev/null | tr -d '[:space:]')"
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s|%s' "$_identity" "$_contract_key" | sha256sum | awk '{print substr($1,1,20)}'
    elif command -v toybox >/dev/null 2>&1; then
        printf '%s|%s' "$_identity" "$_contract_key" | toybox sha256sum | awk '{print substr($1,1,20)}'
    else
        printf '%s|%s' "$_identity" "$_contract_key" | cksum | awk '{print $1}'
    fi
}

# Resolve every physical slot against the device inventory once.  App processes such
# as QQ and Coolapk commonly open Roboto/GoogleSans slots directly, while SystemUI
# uses MiSans/clock slots.  A main-slot-only contract therefore fixes the status bar
# but leaves application baselines unchanged.  The compact key deduplicates slots
# with identical metrics, so a 145-slot ROM still normalizes only a few distinct
# contracts instead of serializing the CJK composite 145 times.
CONTRACT_MAP="$stage_font_dir/.luoshu-font-store/hyperos-slot-contracts.tsv"
build_contract_map() {
    _inventory="$REALMOD/config/device_font_inventory.json"
    _pyroot="$REALMOD/common/python"
    _python="$_pyroot/bin/luoshu-python"
    [ -x "$_python" ] && [ -s "$_inventory" ] || return 1
    mkdir -p "${CONTRACT_MAP%/*}" 2>/dev/null || return 1
    PYTHONHOME="$_pyroot" \
    PYTHONPATH="$REALMOD/common:$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" - "$_inventory" >"${CONTRACT_MAP}.tmp.$$" <<'PY_CONTRACTS'
import hashlib
import json
import sys

try:
    data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
except Exception:
    raise SystemExit(1)
if data.get("schema") != "device-font-inventory-v1" or data.get("state") != "ready":
    raise SystemExit(1)
for path, slot in sorted((data.get("slots") or {}).items()):
    try:
        metrics = slot["metrics"]
        upem = int(metrics["upem"])
        ascent = int(metrics["hhea"]["ascent"])
        descent = int(metrics["hhea"]["descent"])
        if upem <= 0 or ascent <= 0 or descent >= 0:
            continue
    except (KeyError, TypeError, ValueError):
        continue
    raw = f"{upem}:{ascent}:{descent}"
    key = hashlib.sha256(raw.encode()).hexdigest()[:16]
    print(f"{path}\t{key}")
PY_CONTRACTS
    _rc=$?
    if [ "$_rc" -eq 0 ] && [ -s "${CONTRACT_MAP}.tmp.$$" ]; then
        mv -f "${CONTRACT_MAP}.tmp.$$" "$CONTRACT_MAP" 2>/dev/null || return 1
        return 0
    fi
    rm -f "${CONTRACT_MAP}.tmp.$$" 2>/dev/null || true
    return 1
}

slot_contract_key() {
    [ -s "$CONTRACT_MAP" ] || return 1
    awk -F '\t' -v wanted="$1" '$1 == wanted { print $2; exit }' "$CONTRACT_MAP" 2>/dev/null
}

build_contract_map >/dev/null 2>&1 || true

hyperos_336_compact_anchor() {
    _source="$1"
    _target_slot="${2:-}"
    _contract_key="${3:-main}"
    _strict_contract="${4:-false}"
    [ -s "$_source" ] || return 1
    _store="$stage_font_dir/.luoshu-font-store"
    _source_key=$(hyperos_336_source_key "$_source" "$_contract_key")
    [ -n "$_source_key" ] || return 1
    _output="$_store/hyperos-336-source-${_source_key}.font"
    if [ -s "$_output" ]; then
        printf '%s\n' "$_output"
        return 0
    fi

    _pyroot="$REALMOD/common/python"
    _python="$_pyroot/bin/luoshu-python"
    [ -x "$_python" ] && [ -f "$REALMOD/common/font_metrics_normalize.py" ] || return 1
    mkdir -p "$_store" 2>/dev/null || return 1
    rm -f "$_output" 2>/dev/null || true

    PYTHONHOME="$_pyroot" \
    PYTHONPATH="$REALMOD/common:$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" - "$_source" "$_output" \
            "$REALMOD/config/device_font_inventory.json" "$_target_slot" "$_strict_contract" <<'PY_COMPACT' >/dev/null 2>&1
import sys
from pathlib import Path
import font_metrics_normalize as metrics

# Exact HyperOS compact line contract used by LuoShu v3.3.6.
metrics.TYPO_ASCENDER_RATIO = 0.98
metrics.TYPO_DESCENDER_RATIO = 0.30
metrics.WIN_ASCENT_CAP_RATIO = 0.98
metrics.WIN_DESCENT_CAP_RATIO = 0.35
metrics.HHEA_ASCENT_CAP_RATIO = 0.98
metrics.HHEA_DESCENT_CAP_RATIO = 0.30
metrics._outline_extremes = lambda font: None
inventory = Path(sys.argv[3])
target_slot = sys.argv[4] or None
strict_contract = sys.argv[5].lower() == "true"
metrics.normalize_path(
    Path(sys.argv[1]),
    Path(sys.argv[2]),
    inventory=inventory,
    target_slot=target_slot,
    strict_contract=strict_contract,
)
PY_COMPACT
    _rc=$?
    if [ "$_rc" -eq 0 ] && [ -s "$_output" ]; then
        chmod 0644 "$_output" 2>/dev/null || true
        printf '%s\n' "$_output"
        return 0
    fi
    rm -f "$_output" 2>/dev/null || true
    return 1
}

pick_anchor() {
    _name="$1"
    _target_slot="${2:-}"
    _contract_key="${3:-main}"
    _strict_contract="${4:-false}"
    _weight=400
    if type _hyperos_file_weight >/dev/null 2>&1; then
        _weight=$(_hyperos_file_weight "$_name")
    else
        case "$_name" in
            100.ttf) _weight=100 ;; 200.ttf) _weight=200 ;; 300.ttf) _weight=300 ;;
            500.ttf) _weight=500 ;; 600.ttf) _weight=600 ;; 700.ttf) _weight=700 ;;
            800.ttf) _weight=800 ;; 900.ttf) _weight=900 ;; *) _weight=400 ;;
        esac
    fi
    _raw=''
    for _candidate in \
        "$stage_font_dir/LuoShu-${_weight}.ttf" \
        "$stage_font_dir/.luoshu-font-store/wght-${_weight}.font" \
        "$stage_font_dir/.luoshu-font-store/compact-wght-${_weight}.font" \
        "$stage_font_dir/.luoshu-font-store/mix-composite.font" \
        "$stage_font_dir/.luoshu-font-store/regular.font" \
        "$stage_font_dir/.luoshu-font-store/compact-regular.font" \
        "$stage_font_dir/400.ttf" \
        "$stage_font_dir/MiSansVF.ttf" \
        "$stage_font_dir/Roboto-Regular.ttf"; do
        [ -s "$_candidate" ] || continue
        _raw="$_candidate"
        break
    done
    if [ -z "$_raw" ]; then
        _raw=$(find "$stage_font_dir" -maxdepth 2 -type f \( -iname '*.ttf' -o -iname '*.otf' \) -print -quit 2>/dev/null)
    fi
    [ -s "$_raw" ] || return 1

    _compact=$(hyperos_336_compact_anchor "$_raw" "$_target_slot" "$_contract_key" "$_strict_contract" 2>/dev/null || true)
    if [ -s "$_compact" ]; then
        printf '%s\n' "$_compact"
    else
        # Never make font switching fail merely because normalization failed on an
        # unusual font. The old raw physical mapping remains the safety fallback.
        printf '%s\n' "$_raw"
    fi
}

link_font() {
    _source="$1"
    _dest="$2"
    [ -s "$_source" ] || return 1
    mkdir -p "${_dest%/*}" 2>/dev/null || return 1
    rm -f "$_dest" 2>/dev/null || true
    ln "$_source" "$_dest" 2>/dev/null || cp -f "$_source" "$_dest" 2>/dev/null || return 1
    chmod 0644 "$_dest" 2>/dev/null || true
    return 0
}

all_targets() {
    {
        _hyperos_core_files
        _hyperos_weight_files
        _hyperos_upright_ui_files
        _hyperos_clock_ui_files
    } | tr ' ' '\n' | awk 'NF && !seen[$0]++'
}

mapped=0
while IFS= read -r _file; do
    [ -n "$_file" ] || continue
    while IFS='|' read -r _part _real_root; do
        [ -e "$_real_root/$_file" ] || continue
        _logical_slot="$_real_root/$_file"
        _target_slot=''
        _contract_key='main'
        _strict_contract=false
        _slot_key=$(slot_contract_key "$_logical_slot" 2>/dev/null || true)
        if [ -n "$_slot_key" ]; then
            _target_slot="$_logical_slot"
            _contract_key="slot-$_slot_key"
        fi
        case "$_file" in
            Mitype*Clock*|MiClock*|MiSans*Clock*|AndroidClock*|Clockopia.ttf)
                _strict_contract=true
                ;;
        esac
        _anchor=$(pick_anchor "$_file" "$_target_slot" "$_contract_key" "$_strict_contract")
        [ -s "$_anchor" ] || continue
        _dest="$PAYLOAD_ROOT/$_part/fonts/$_file"
        if link_font "$_anchor" "$_dest"; then
            mapped=$((mapped + 1))
        fi
    done <<'EOF_PARTS'
system|/system/fonts
system_ext|/system_ext/fonts
product|/product/fonts
mi_ext|/mi_ext/fonts
vendor|/vendor/fonts
odm|/odm/fonts
oem|/oem/fonts
my_product|/my_product/fonts
hw_product|/hw_product/fonts
cust|/cust/fonts
EOF_PARTS
done <<EOF_TARGETS
$(all_targets)
EOF_TARGETS

# HyperOS itself always carries MiSansVF in /system/fonts. Keep a deterministic core
# fallback for test environments where the stock root is not mounted.
if [ ! -s "$PAYLOAD_ROOT/system/fonts/MiSansVF.ttf" ]; then
    _anchor=$(pick_anchor MiSansVF.ttf '')
    [ ! -s "$_anchor" ] || { link_font "$_anchor" "$PAYLOAD_ROOT/system/fonts/MiSansVF.ttf" && mapped=$((mapped + 1)); }
fi

printf 'mapped=%s\n' "$mapped"
[ "$mapped" -gt 0 ] 2>/dev/null
