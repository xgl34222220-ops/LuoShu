#!/system/bin/sh
# Coverage remediation for the physical-safe next-boot payload.
#
# This helper never touches the live .luoshu-payload. It receives an isolated
# stage, joins it with the validated device inventory, fills only missing safe
# TTF/OTF UI slots, and records intentional preserves so Coverage does not offer
# the same impossible repair after every reboot.
set +e

MODDIR="${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
STAGE="${1:-}"
MODE="${2:-direct}"
FAMILY="${3:-}"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
INVENTORY="$MODDIR/config/device_font_inventory.json"
INVENTORY_TOOL="$MODDIR/common/font_inventory.py"
NORMALIZER="$MODDIR/common/font_metrics_normalize.py"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
LOG_FILE="$MODDIR/logs/fontswitch.log"
PLAN="${LUOSHU_COVERAGE_PLAN:-}"
PLAN_ENABLED=false

log_line() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    printf '[%s] [COVERAGE-REMEDIATE] %s\n'         "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*"         >> "$LOG_FILE" 2>/dev/null || true
}

json_error() {
    printf '{"status":"error","message":"%s"}\n'         "$(printf '%s' "$*" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  ')"
}

case "$STAGE" in
    "$MODDIR"/.luoshu-payload-stage.*|"$MODDIR"/.luoshu-mix-stage|"$MODDIR"/.luoshu-payload-next) ;;
    *) json_error '补齐目标不是受信任的下一启动暂存负载'; exit 1 ;;
esac
[ "$STAGE" != "$MODDIR/.luoshu-payload" ] || {
    json_error '拒绝直接修改当前启动字体负载'
    exit 1
}
[ -d "$STAGE" ] || {
    json_error '下一启动字体暂存负载不存在'
    exit 1
}
[ -s "$INVENTORY" ] && [ -f "$INVENTORY_TOOL" ] && [ -f "$NORMALIZER" ] && [ -x "$PYBIN" ] || {
    json_error '本机字体扫描清单或解析器不可用'
    exit 1
}

if [ -n "$PLAN" ]; then
    case "$PLAN" in
        "$MODDIR"/config/*) ;;
        *) json_error '字体补齐计划路径不受信任'; exit 1 ;;
    esac
    [ -s "$PLAN" ] || {
        json_error '字体补齐计划为空或不存在'
        exit 1
    }
    awk '
        $0 !~ /^\// || $0 ~ /\/\.\.?\// || $0 ~ /\/\// { bad=1 }
        seen[$0]++ { bad=1 }
        END { exit bad }
    ' "$PLAN" || {
        json_error '字体补齐计划包含无效或重复槽位'
        exit 1
    }
    PLAN_ENABLED=true
fi

LEGACY_UTIL="$MODDIR/common/legacy_v14_4/util_functions.sh"
MODERN_MAPPER="$MODDIR/common/rom_adapters.sh"
MODULE_DIR="$MODDIR"
export MODULE_DIR USER_FONTS_DIR LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
[ -f "$LEGACY_UTIL" ] && . "$LEGACY_UTIL" >/dev/null 2>&1 || true
# Only reuse the modern mapper's metric-normalized _font_anchor helper here.
# No apply/mount entry point is called from this remediation process.
[ -f "$MODERN_MAPPER" ] && . "$MODERN_MAPPER" >/dev/null 2>&1 || true

TMP_ROWS="$MODDIR/config/.coverage-remediate-rows.$"
BATCH="$MODDIR/config/.coverage-remediate-batch.$"
PRESERVED="$STAGE/.luoshu-coverage-preserved.tsv"
PRESERVED_TMP="${PRESERVED}.tmp.$$"
SUMMARY="$STAGE/.luoshu-coverage-remediation.conf"
SUMMARY_TMP="${SUMMARY}.tmp.$$"
trap 'rm -f "$TMP_ROWS" "$BATCH" "$PRESERVED_TMP" "$SUMMARY_TMP" 2>/dev/null || true' EXIT HUP INT TERM

PYTHONHOME="$PYROOT" PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"     "$PYBIN" "$INVENTORY_TOOL" --list --output "$INVENTORY" > "$TMP_ROWS" 2>> "$LOG_FILE"
_rc=$?
if [ "$_rc" -ne 0 ] || [ ! -s "$TMP_ROWS" ]; then
    json_error '无法读取已验证的本机字体槽位清单'
    exit 1
fi
awk -F '\t' 'NF != 7 || $1 !~ /^\// || $2 == "" { bad=1 } END { exit bad }' "$TMP_ROWS" || {
    json_error '本机字体槽位清单行格式异常'
    exit 1
}

STORE="$STAGE/system/fonts/.luoshu-font-store"
REGULAR="$STORE/regular.font"
MIX="$STORE/mix-composite.font"
case "$MODE" in
    direct)
        [ -s "$REGULAR" ] || {
            json_error '当前字体暂存负载缺少 Regular 源锚点'
            exit 1
        }
        _exact_weights=''
        if [ -n "$FAMILY" ] && type scan_family_weights >/dev/null 2>&1; then
            _exact_weights="$(scan_family_weights "$FAMILY" 2>/dev/null)"
        fi
        ;;
    mix)
        [ -s "$MIX" ] || {
            json_error '复合字体暂存负载缺少组合源锚点'
            exit 1
        }
        ;;
    *)
        json_error '未知字体覆盖补齐模式'
        exit 1
        ;;
esac

role_for_weight() {
    case "$1" in
        100) printf 'thin\n' ;;
        200) printf 'extralight\n' ;;
        300|350) printf 'light\n' ;;
        500) printf 'medium\n' ;;
        600) printf 'semibold\n' ;;
        700) printf 'bold\n' ;;
        800) printf 'extrabold\n' ;;
        900) printf 'black\n' ;;
        *) printf 'regular\n' ;;
    esac
}

has_exact_role() {
    _wanted="$1"
    case ",${_exact_weights:-}," in
        *",$_wanted,"*) return 0 ;;
        *) return 1 ;;
    esac
}

has_variable_source() {
    case ",${_exact_weights:-}," in
        *",variable,"*) return 0 ;;
        *) return 1 ;;
    esac
}

record_preserved() {
    _path="$1"; _reason="$2"
    printf '%s\t%s\n' "$_path" "$_reason" >> "$PRESERVED_TMP" 2>/dev/null || return 1
    _preserved=$((_preserved + 1))
    return 0
}

font_size_ok() {
    _file="$1"
    _size=$(stat -c '%s' "$_file" 2>/dev/null)
    case "$_size" in ''|*[!0-9]*) _size=$(wc -c < "$_file" 2>/dev/null | tr -d '[:space:]') ;; esac
    case "$_size" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_size" -ge 1024 ] 2>/dev/null
}

: > "$PRESERVED_TMP" 2>/dev/null || {
    json_error '无法创建补齐保护清单'
    exit 1
}
: > "$BATCH" 2>/dev/null || {
    json_error '无法创建逐槽度量补齐任务'
    exit 1
}

_added=0
_planned=0
_existing=0
_rewritten=0
_requested=0
_matched=0
_preserved=0
_failed=0
_seen=0
if [ "$PLAN_ENABLED" = true ]; then
    _requested=$(grep -c '^/' "$PLAN" 2>/dev/null || true)
    case "$_requested" in ''|*[!0-9]*) _requested=0 ;; esac
fi
_tab=$(printf '\t')
while IFS="$_tab" read -r _logical _name _partition _format _weight _style _source; do
    [ -n "$_logical" ] && [ -n "$_name" ] || continue
    _seen=$((_seen + 1))
    case "$_logical" in
        /*) ;;
        *) _failed=$((_failed + 1)); continue ;;
    esac
    case "/${_logical#/}/" in *"/../"*|*"/./"*|*"//"*) _failed=$((_failed + 1)); continue ;; esac
    _rel=${_logical#/}
    _target="$STAGE/$_rel"
    case "$_target" in "$STAGE"/*) ;; *) _failed=$((_failed + 1)); continue ;; esac

    _requested_slot=false
    if [ "$PLAN_ENABLED" = true ]; then
        if grep -Fqx "$_logical" "$PLAN" 2>/dev/null; then
            _requested_slot=true
            _matched=$((_matched + 1))
        elif [ -s "$_target" ]; then
            _existing=$((_existing + 1))
            continue
        fi
        # The plan is a mandatory rewrite set, not an allow-list for the final
        # payload. Composite staging intentionally removes the previous text tree;
        # every other safe inventory slot that is now missing must be backfilled
        # too, otherwise "repair one red slot" can silently delete good coverage.
    elif [ -s "$_target" ]; then
        # Legacy/no-plan callers keep the historical "fill only missing" behavior.
        _existing=$((_existing + 1))
        continue
    fi

    _format_upper=$(printf '%s' "$_format" | tr '[:lower:]' '[:upper:]')
    case "$_format_upper" in
        TTF|OTF) ;;
        TTC|OTC)
            record_preserved "$_logical" 'preserved-collection' || _failed=$((_failed + 1))
            continue
            ;;
        *)
            record_preserved "$_logical" 'unsupported-font-container' || _failed=$((_failed + 1))
            continue
            ;;
    esac

    _style_lower=$(printf '%s' "${_style:-normal}" | tr '[:upper:]' '[:lower:]')
    case "$_style_lower" in
        ''|normal|regular) ;;
        *)
            record_preserved "$_logical" "preserved-style-${_style_lower}" || _failed=$((_failed + 1))
            continue
            ;;
    esac

    case "${_weight:-400}" in ''|*[!0-9]*) _weight=400 ;; esac

    if [ "$MODE" = mix ]; then
        _anchor="$MIX"
    elif [ "$_weight" -eq 400 ] 2>/dev/null; then
        _anchor="$REGULAR"
    else
        _role=$(role_for_weight "$_weight")
        if has_exact_role "$_role" || has_variable_source; then
            # The remediation plan forces rewrites, but a newly rebuilt stage
            # still needs every safe missing weight restored from a real source.
            _anchor="$STORE/${_role}.font"
            if [ ! -s "$_anchor" ] && type get_weight_file >/dev/null 2>&1 && type _font_anchor >/dev/null 2>&1; then
                _role_source="$(get_weight_file "$FAMILY" "$_role" 2>/dev/null)"
                if [ -s "$_role_source" ]; then
                    _anchor="$(_font_anchor "$_role_source" "$STAGE/system/fonts" "$_role" 2>/dev/null)"
                fi
            fi
            # A variable family is itself a real multi-weight source. If a role
            # anchor could not be materialized separately, normalize from the
            # variable Regular anchor rather than falsely protecting the slot.
            if [ ! -s "$_anchor" ] && has_variable_source; then
                _anchor="$REGULAR"
            fi
            if [ ! -s "$_anchor" ]; then
                record_preserved "$_logical" "missing-real-source-weight-${_weight}" || _failed=$((_failed + 1))
                continue
            fi
        else
            record_preserved "$_logical" "missing-real-source-weight-${_weight}" || _failed=$((_failed + 1))
            continue
        fi
    fi

    mkdir -p "${_target%/*}" 2>/dev/null || {
        _failed=$((_failed + 1))
        continue
    }
    if [ "$_requested_slot" = true ] && [ -s "$_target" ]; then
        _rewritten=$((_rewritten + 1))
    fi
    rm -f "$_target" 2>/dev/null || true
    # One embedded-Python process normalizes every new target against that exact
    # stock inventory slot. This preserves per-slot hhea/OS/2 metrics and avoids
    # both HyperOS vertical drift and one Python cold start per font file.
    printf '%s\t%s\t\t%s\n' "$_anchor" "$_target" "$_logical" >> "$BATCH" 2>/dev/null || {
        _failed=$((_failed + 1))
        continue
    }
    _planned=$((_planned + 1))
done < "$TMP_ROWS"

if [ "$PLAN_ENABLED" = true ] && [ "$_matched" -ne "$_requested" ] 2>/dev/null; then
    _failed=$((_failed + 1))
    log_line "补齐计划与当前 inventory 不一致：requested=$_requested matched=$_matched"
fi

if [ "$_failed" -eq 0 ] && [ "$_planned" -gt 0 ]; then
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$NORMALIZER" --batch "$BATCH" --inventory "$INVENTORY" \
        >> "$LOG_FILE" 2>&1
    _batch_rc=$?
    if [ "$_batch_rc" -ne 0 ]; then
        _failed=$((_failed + 1))
    fi

    while IFS="$_tab" read -r _batch_source _batch_target _batch_mono _batch_slot; do
        [ -n "$_batch_target" ] || continue
        if [ "$_batch_rc" -eq 0 ] && font_size_ok "$_batch_target"; then
            _added=$((_added + 1))
        else
            rm -f "$_batch_target" 2>/dev/null || true
            [ "$_batch_rc" -ne 0 ] || _failed=$((_failed + 1))
        fi
    done < "$BATCH"
fi

if [ "$_failed" -ne 0 ]; then
    # A batch failure must never leave a partially normalized next-boot tree.
    while IFS="$_tab" read -r _batch_source _batch_target _batch_mono _batch_slot; do
        [ -z "$_batch_target" ] || rm -f "$_batch_target" 2>/dev/null || true
    done < "$BATCH"
    _added=0
    log_line "补齐失败：seen=$_seen requested=$_requested matched=$_matched planned=$_planned rewritten=$_rewritten added=$_added existing=$_existing preserved=$_preserved failed=$_failed"
    json_error "字体覆盖补齐有 $_failed 个槽位写入失败，已拒绝提交半成品"
    exit 1
fi

if [ -s "$PRESERVED_TMP" ]; then
    mv -f "$PRESERVED_TMP" "$PRESERVED" 2>/dev/null || {
        json_error '无法提交字体覆盖保护清单'
        exit 1
    }
    chmod 0644 "$PRESERVED" 2>/dev/null || true
else
    rm -f "$PRESERVED" "$PRESERVED_TMP" 2>/dev/null || true
fi

{
    printf 'schema=physical-coverage-remediation-v1\n'
    printf 'mode=%s\n' "$MODE"
    printf 'font=%s\n' "$FAMILY"
    printf 'inventory=%s\n' "$_seen"
    printf 'requested=%s\n' "$_requested"
    printf 'matched=%s\n' "$_matched"
    printf 'planned=%s\n' "$_planned"
    printf 'rewritten=%s\n' "$_rewritten"
    printf 'added=%s\n' "$_added"
    printf 'existing=%s\n' "$_existing"
    printf 'preserved=%s\n' "$_preserved"
    printf 'failed=0\n'
    printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
} > "$SUMMARY_TMP" 2>/dev/null || {
    json_error '无法保存字体覆盖补齐摘要'
    exit 1
}
mv -f "$SUMMARY_TMP" "$SUMMARY" 2>/dev/null || {
    json_error '无法提交字体覆盖补齐摘要'
    exit 1
}
chmod 0644 "$SUMMARY" 2>/dev/null || true

log_line "补齐完成：mode=$MODE font=$FAMILY seen=$_seen requested=$_requested matched=$_matched planned=$_planned rewritten=$_rewritten added=$_added existing=$_existing preserved=$_preserved"
printf '{"status":"ok","data":{"mode":"%s","font":"%s","inventory":%s,"requested":%s,"matched":%s,"planned":%s,"rewritten":%s,"added":%s,"existing":%s,"preserved":%s}}\n' \
    "$MODE" "$(printf '%s' "$FAMILY" | sed 's/\\/\\\\/g; s/"/\\"/g')" \
    "$_seen" "$_requested" "$_matched" "$_planned" "$_rewritten" "$_added" "$_existing" "$_preserved"
exit 0
