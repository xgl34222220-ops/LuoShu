from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def load(path):
    return (ROOT / path).read_text(encoding='utf-8')

def save(path, text):
    (ROOT / path).write_text(text, encoding='utf-8')

def replace_once(path, old, new):
    text = load(path)
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{path}: expected exactly one match, found {n}')
    save(path, text.replace(old, new, 1))

def insert_before_once(path, marker, block):
    text = load(path)
    n = text.count(marker)
    if n != 1:
        raise SystemExit(f'{path}: marker expected exactly once, found {n}')
    save(path, text.replace(marker, block + marker, 1))

# Discover actual OEM font XML names on every configured partition.
replace_once('common/font_config_partitions.sh', '''_luoshu_font_config_specs() {
    _lfcp_names="$(_luoshu_font_config_xml_names)"
    while IFS='|' read -r _lfcp_key _lfcp_real_etc _lfcp_overlay; do
        [ -n "$_lfcp_key" ] && [ -n "$_lfcp_real_etc" ] && [ -n "$_lfcp_overlay" ] || continue
        # shellcheck disable=SC2086
        _luoshu_font_config_emit_partition "$_lfcp_key" "$_lfcp_real_etc" "$_lfcp_overlay" $_lfcp_names
    done <<EOF_LUOSHU_PARTITIONS
$(_luoshu_font_config_partition_rows)
EOF_LUOSHU_PARTITIONS
}
''', '''_luoshu_font_config_specs() {
    _lfcp_names="$(_luoshu_font_config_xml_names)"
    while IFS='|' read -r _lfcp_key _lfcp_real_etc _lfcp_overlay; do
        [ -n "$_lfcp_key" ] && [ -n "$_lfcp_real_etc" ] && [ -n "$_lfcp_overlay" ] || continue
        # Keep the curated list as a stable baseline, then discover vendor-specific font XML that
        # actually exists on this ROM. Unknown OEM names must not silently escape the no-hook path.
        _lfcp_all="$_lfcp_names"
        for _lfcp_found in \
            "$_lfcp_real_etc"/*font*.xml \
            "$_lfcp_real_etc"/*Font*.xml \
            "$_lfcp_real_etc"/*FONT*.xml; do
            [ -f "$_lfcp_found" ] || continue
            _lfcp_base="${_lfcp_found##*/}"
            case " $_lfcp_all " in
                *" $_lfcp_base "*) continue ;;
            esac
            _lfcp_all="$_lfcp_all $_lfcp_base"
        done
        # shellcheck disable=SC2086
        _luoshu_font_config_emit_partition "$_lfcp_key" "$_lfcp_real_etc" "$_lfcp_overlay" $_lfcp_all
    done <<EOF_LUOSHU_PARTITIONS
$(_luoshu_font_config_partition_rows)
EOF_LUOSHU_PARTITIONS
}
''')

# XML generation needs the complete master family, while partition-local failures are fail-open.
replace_once('common/font_config_runtime.sh', '''    font_config_capture_original || return 1
    mkdir -p "$_lfc_stage" 2>/dev/null || return 1

    _lfc_changed=0
''', '''    font_config_capture_original || return 1

    # Weight availability is a global invariant. Never publish XML that references a half-built
    # family merely because one partition happens to be writable.
    for _lfc_prefix in LuoShu LuoShuMono; do
        for _lfc_weight in 100 200 300 400 500 600 700 800 900; do
            [ -s "$_lfc_module/system/fonts/${_lfc_prefix}-${_lfc_weight}.ttf" ] || {
                _luoshu_font_config_disable_base
                return 1
            }
        done
    done

    mkdir -p "$_lfc_stage" 2>/dev/null || return 1

    _lfc_changed=0
''')
replace_once('common/font_config_runtime.sh', '''        if _luoshu_font_config_exec "$_lfc_tool" --input "$_lfc_input" --output "$_lfc_output" \\
            --font-prefix LuoShu --mono-font-prefix LuoShuMono --font-dir "$_lfc_fonts" >/dev/null 2>&1 && \\
            [ -s "$_lfc_output" ] && _luoshu_font_config_validate "$_lfc_output" "$_lfc_fonts"; then
            _lfc_changed=$((_lfc_changed + 1))
        else
            rm -f "$_lfc_output" 2>/dev/null || true
        fi
''', '''        if _luoshu_font_config_exec "$_lfc_tool" --input "$_lfc_input" --output "$_lfc_output" \\
            --font-prefix LuoShu --mono-font-prefix LuoShuMono --font-dir "$_lfc_fonts" >/dev/null 2>&1 && \\
            [ -s "$_lfc_output" ] && _luoshu_font_config_validate "$_lfc_output" "$_lfc_fonts"; then
            _lfc_changed=$((_lfc_changed + 1))
        else
            _lfc_failed=$((_lfc_failed + 1))
            rm -f "$_lfc_output" 2>/dev/null || true
        fi
''')
replace_once('common/font_config_runtime.sh', '''    if [ "$_lfc_changed" -eq 0 ] || [ "$_lfc_failed" -gt 0 ]; then
        rm -rf "$_lfc_stage" 2>/dev/null || true
        _luoshu_font_config_disable_base
        return 1
    fi

    # Commit only after every generated document and every referenced font has validated.
''', '''    if [ "$_lfc_changed" -eq 0 ]; then
        rm -rf "$_lfc_stage" 2>/dev/null || true
        _luoshu_font_config_disable_base
        return 1
    fi
    [ "$_lfc_failed" -eq 0 ] || _luoshu_font_config_log WARN \\
        "部分分区未能生成字体别名，已按通过校验的可用分区提交 XML 覆盖：ok=$_lfc_changed failed=$_lfc_failed"

    # Commit only independently generated documents whose referenced aliases already validated.
''')

# Foreground cache-miss policy. De-duplicate source scans and distinguish true XML from slot-only
# success so a false positive never suppresses the background aligned cache.
insert_before_once('common/device_font_payload_policy.sh', 'font_config_enable_for_payload() {\n', '''# A foreground switch must remain bounded. Static sources can be linked cheaply; a variable source
# would require real instancing for nine weights and therefore stays on the background cache path.
_dfpp_xml_prepare_is_cheap() {
    type _luoshu_config_weight_source >/dev/null 2>&1 || return 1
    type is_variable_font >/dev/null 2>&1 || return 0
    _dfpp_seen='|'
    for _dfpp_w in 100 200 300 400 500 600 700 800 900; do
        _dfpp_src=$(_luoshu_config_weight_source "$_dfpp_w" 2>/dev/null)
        [ -n "$_dfpp_src" ] || return 1
        case "$_dfpp_seen" in *"|$_dfpp_src|"*) continue ;; esac
        _dfpp_seen="${_dfpp_seen}${_dfpp_src}|"
        if is_variable_font "$_dfpp_src"; then
            _device_font_policy_log "字重来源为可变字体，前台跳过 XML 家族覆盖以免长时间卡顿：$_dfpp_src"
            return 1
        fi
    done
    return 0
}

# font_config_generate can succeed with dynamic file aliases only. That fallback is useful, but it
# is not proof of XML coverage and must not cancel the background device-aligned cache build.
_dfpp_xml_overlay_active() {
    _dfpp_module="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    _dfpp_config="${CONFIG_DIR:-$_dfpp_module/config}"
    _dfpp_state="$_dfpp_config/font-config-overlay.conf"
    [ -s "$_dfpp_state" ] || return 1
    grep -qx 'mode=enabled' "$_dfpp_state" 2>/dev/null || return 1
    _dfpp_expected=$(sed -n 's/^configs=//p' "$_dfpp_state" 2>/dev/null | head -n1)
    case "$_dfpp_expected" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_dfpp_expected" -gt 0 ] || return 1
    type _luoshu_font_config_specs >/dev/null 2>&1 || return 1
    _dfpp_seen_xml=0
    while IFS='|' read -r _dfpp_key _dfpp_real _dfpp_overlay _dfpp_fonts; do
        [ -s "$_dfpp_overlay" ] || continue
        grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\\.ttf' "$_dfpp_overlay" 2>/dev/null || continue
        if type _luoshu_font_config_validate >/dev/null 2>&1; then
            _luoshu_font_config_validate "$_dfpp_overlay" "$_dfpp_fonts" || return 1
        fi
        _dfpp_seen_xml=$((_dfpp_seen_xml + 1))
    done <<EOF_DFPP_XML
$(_luoshu_font_config_specs)
EOF_DFPP_XML
    [ "$_dfpp_seen_xml" -eq "$_dfpp_expected" ]
}

''')
replace_once('common/device_font_payload_policy.sh', '''    # Keep the physical ROM aliases prepared by the quick mapper and remove only stale v2/XML state.
    _dfpp_preserve="${LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE:-0}"
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE=1
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE
    if type font_config_disable >/dev/null 2>&1; then
        font_config_disable >/dev/null 2>&1 || true
    fi
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE="$_dfpp_preserve"
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE

    # Scheduling is metadata-only. The expensive builder runs after the foreground transaction.
    if type device_font_cache_schedule >/dev/null 2>&1; then
        device_font_cache_schedule "$_dfpp_family" >/dev/null 2>&1 || true
    fi
    [ "${IS_COLOROS:-false}" != true ] || LUOSHU_COLOROS_TARGETS_MAPPED=1
    export LUOSHU_COLOROS_TARGETS_MAPPED
    LUOSHU_DEVICE_PAYLOAD_RESULT='slot-only'
    _device_font_policy_log "前台已完成常量时间物理槽映射；后台对齐缓存按条件安排：$_dfpp_family"
    return 0
''', '''    # A device-cache miss is not a reason to abandon the no-hook XML family overlay. Keep OEM
    # quick-map aliases intact while trying the bounded static path.
    _dfpp_preserve="${LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE:-0}"
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE=1
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE

    _dfpp_xml=0
    if type font_config_prepare_payload_weights >/dev/null 2>&1 && \\
       type font_config_generate >/dev/null 2>&1 && \\
       _dfpp_xml_prepare_is_cheap; then
        if font_config_prepare_payload_weights; then
            if font_config_generate "$_dfpp_family"; then
                if _dfpp_xml_overlay_active; then
                    _dfpp_xml=1
                else
                    _device_font_policy_log "字体配置返回成功但未提交有效 XML，继续安排后台设备对齐缓存：$_dfpp_family"
                fi
            else
                _device_font_policy_log "XML 家族覆盖生成失败，回退物理槽映射：$_dfpp_family"
            fi
        else
            _device_font_policy_log "九档静态字体准备失败，跳过 XML 家族覆盖：$_dfpp_family"
        fi
    fi

    if [ "$_dfpp_xml" -ne 1 ] && type font_config_disable >/dev/null 2>&1; then
        font_config_disable >/dev/null 2>&1 || true
    fi
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE="$_dfpp_preserve"
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE

    [ "${IS_COLOROS:-false}" != true ] || LUOSHU_COLOROS_TARGETS_MAPPED=1
    export LUOSHU_COLOROS_TARGETS_MAPPED

    if [ "$_dfpp_xml" -eq 1 ]; then
        LUOSHU_DEVICE_PAYLOAD_RESULT='legacy'
        _device_font_policy_log "已启用无 Hook XML 家族覆盖（含等宽），未安排重复的后台对齐缓存：$_dfpp_family"
        return 0
    fi

    # Scheduling is metadata-only. The expensive builder runs after the foreground transaction.
    if type device_font_cache_schedule >/dev/null 2>&1; then
        device_font_cache_schedule "$_dfpp_family" >/dev/null 2>&1 || true
    fi
    LUOSHU_DEVICE_PAYLOAD_RESULT='slot-only'
    _device_font_policy_log "前台保留物理槽映射；后台对齐缓存按条件安排：$_dfpp_family"
    return 0
''')

old_guard = '''    if [ "$_ldt_scan_failed" -gt 0 ] || [ "$_ldt_mapped" -ne "$_ldt_targets" ]; then
        while IFS='|' read -r _ldt_rel _ldt_rest; do rm -f "$_ldt_module/$_ldt_rel" 2>/dev/null || true; done < "$_ldt_manifest_tmp"
        rm -f "$_ldt_manifest_tmp" "$_ldt_coverage_tmp" 2>/dev/null || true
        _luoshu_safety_log ERROR "动态字体目标映射失败：targets=$_ldt_targets mapped=$_ldt_mapped scanFailed=$_ldt_scan_failed"
        return 1
    fi
'''
new_guard = '''    # Unmapped targets keep their stock font. Zero useful mappings is a hard failure; non-zero partial
    # coverage is committed and reported honestly instead of collapsing an unfamiliar ROM to zero.
    if [ "$_ldt_mapped" -eq 0 ]; then
        while IFS='|' read -r _ldt_rel _ldt_rest; do rm -f "$_ldt_module/$_ldt_rel" 2>/dev/null || true; done < "$_ldt_manifest_tmp"
        rm -f "$_ldt_manifest_tmp" "$_ldt_coverage_tmp" 2>/dev/null || true
        _luoshu_safety_log ERROR "动态字体目标映射失败：targets=$_ldt_targets mapped=0 scanFailed=$_ldt_scan_failed"
        return 1
    fi
    if [ "$_ldt_mapped" -eq "$_ldt_targets" ] && [ "$_ldt_scan_failed" -eq 0 ]; then
        _ldt_coverage_status=full
    else
        _ldt_coverage_status=partial
        _luoshu_safety_log WARN "部分字体目标未能映射，未映射项保留原厂字体：targets=$_ldt_targets mapped=$_ldt_mapped scanFailed=$_ldt_scan_failed"
    fi
'''
old_write = '''    {
        printf 'configs=%s\\n' "$_ldt_configs"
        printf 'targets=%s\\n' "$_ldt_targets"
        printf 'mapped=%s\\n' "$_ldt_mapped"
        printf 'time=%s\\n' "$(date +%s)"
    } > "$_ldt_coverage_tmp" 2>/dev/null || return 1
'''
new_write = '''    {
        printf 'configs=%s\\n' "$_ldt_configs"
        printf 'discovered=%s\\n' "$_ldt_targets"
        printf 'targets=%s\\n' "$_ldt_targets"
        printf 'mapped=%s\\n' "$_ldt_mapped"
        printf 'status=%s\\n' "$_ldt_coverage_status"
        printf 'scanFailed=%s\\n' "$_ldt_scan_failed"
        printf 'time=%s\\n' "$(date +%s)"
    } > "$_ldt_coverage_tmp" 2>/dev/null || return 1
'''
for p in ('common/font_safety.sh', 'common/font_finalize_hotfix.sh'):
    replace_once(p, old_guard, new_guard)
    replace_once(p, old_write, new_write)

replace_once('common/font_safety.sh', '''    # A ROM may expose UI file slots without a safely rewritable named family. Keep only a complete
    # dynamic mapping; partial mappings are rejected above.
    [ "$_lfg_dynamic" -eq 0 ] && return 0
''', '''    # A ROM may expose UI file slots without a safely rewritable named family. Keep any validated
    # non-zero dynamic mapping; unmapped targets remain on the stock font and are reported as partial.
    [ "$_lfg_dynamic" -eq 0 ] && return 0
''')
for p in ('common/font_safety.sh', 'common/font_finalize_hotfix.sh'):
    replace_once(p, '''    [ "$_ldt_targets" -gt 0 ] || return 2
    _luoshu_safety_log INFO "已按设备真实 XML 完整映射 $_ldt_mapped 个 UI 字体目标"
    return 0
''', '''    [ "$_ldt_targets" -gt 0 ] || return 2
    if [ "$_ldt_coverage_status" = full ]; then
        _luoshu_safety_log INFO "已按设备真实 XML 完整映射 $_ldt_mapped/$_ldt_targets 个 UI 字体目标"
    else
        _luoshu_safety_log WARN "已按设备真实 XML 部分映射 $_ldt_mapped/$_ldt_targets 个 UI 字体目标"
    fi
    return 0
''')

# All three final validators must understand partial coverage; the bridge is loaded last in production.
old_validate = '''    _lpv_targets=$(sed -n 's/^targets=//p' "$_lpv_config/font-target-coverage.conf" 2>/dev/null | head -n1)
    _lpv_mapped=$(sed -n 's/^mapped=//p' "$_lpv_config/font-target-coverage.conf" 2>/dev/null | head -n1)
    case "$_lpv_targets" in ''|*[!0-9]*) _lpv_targets=0 ;; esac
    case "$_lpv_mapped" in ''|*[!0-9]*) _lpv_mapped=0 ;; esac
    [ "$_lpv_targets" -eq "$_lpv_mapped" ] || return 1
'''
new_validate = '''    _lpv_coverage="$_lpv_config/font-target-coverage.conf"
    if [ -f "$_lpv_coverage" ]; then
        _lpv_targets=$(sed -n 's/^targets=//p' "$_lpv_coverage" 2>/dev/null | head -n1)
        _lpv_mapped=$(sed -n 's/^mapped=//p' "$_lpv_coverage" 2>/dev/null | head -n1)
        _lpv_status=$(sed -n 's/^status=//p' "$_lpv_coverage" 2>/dev/null | head -n1)
        case "$_lpv_targets" in ''|*[!0-9]*) return 1 ;; esac
        case "$_lpv_mapped" in ''|*[!0-9]*) return 1 ;; esac
        [ "$_lpv_mapped" -le "$_lpv_targets" ] || return 1
        case "$_lpv_status" in
            full) [ "$_lpv_mapped" -eq "$_lpv_targets" ] || return 1 ;;
            partial) [ "$_lpv_mapped" -gt 0 ] && [ "$_lpv_mapped" -lt "$_lpv_targets" ] || return 1 ;;
            '') [ "$_lpv_targets" -eq 0 ] || [ "$_lpv_mapped" -gt 0 ] || return 1 ;;
            *) return 1 ;;
        esac
        _lpv_manifest="$_lpv_config/font-target-aliases.conf"
        _lpv_manifest_count=$(awk 'NF { n++ } END { print n+0 }' "$_lpv_manifest" 2>/dev/null)
        case "$_lpv_manifest_count" in ''|*[!0-9]*) return 1 ;; esac
        [ "$_lpv_manifest_count" -eq "$_lpv_mapped" ] || return 1
        while IFS='|' read -r _lpv_rel _lpv_key _lpv_weight _lpv_family; do
            [ -n "$_lpv_rel" ] || continue
            case "$_lpv_rel" in */fonts/*.ttf|*/fonts/*.otf|*/fonts/*.ttc) ;; *) return 1 ;; esac
            [ -f "$_lpv_module/$_lpv_rel" ] || return 1
            if type _luoshu_fast_font_ok >/dev/null 2>&1; then
                _luoshu_fast_font_ok "$_lpv_module/$_lpv_rel" || return 1
            fi
        done < "$_lpv_manifest"
    fi
'''
for p in ('common/font_safety.sh', 'common/font_finalize_hotfix.sh', 'common/device_font_payload_bridge.sh'):
    replace_once(p, old_validate, new_validate)

# Restore bridge-test errexit after sourced common scripts and exercise real-vs-false XML success.
replace_once('scripts/device_font_payload_bridge_test.sh', '''LEGACY_RC=0
CALLS="$TMP/calls"
''', '''LEGACY_RC=0
LEGACY_REAL_XML=0
CALLS="$TMP/calls"
''')
replace_once('scripts/device_font_payload_bridge_test.sh', '''font_config_generate() { record legacy; return "$LEGACY_RC"; }
''', '''font_config_generate() { record legacy; return "$LEGACY_RC"; }
device_font_cache_schedule() { record schedule; return 0; }
_luoshu_config_weight_source() { printf '%s\\n' "$TMP/source.ttf"; }
is_variable_font() { [ "${VARIABLE_SOURCE:-0}" = 1 ]; }
''')
replace_once('scripts/device_font_payload_bridge_test.sh', '''. "$ROOT/common/device_font_payload_bridge.sh"

# OriginOS and Flyme must never fall through to the generic adapter after the bridge loads.
''', '''. "$ROOT/common/device_font_payload_bridge.sh"
set -eu

# OriginOS and Flyme must never fall through to the generic adapter after the bridge loads.
''')
replace_once('scripts/device_font_payload_bridge_test.sh', '''# The foreground policy is loaded after the bridge in production. On a cache miss it must
# finish with the physical ROM mapping and must never enter the 18-file weight preparation
# or legacy XML generator that made a simple switch take minutes.
. "$ROOT/common/device_font_payload_policy.sh"
ROM=originos
rm -f "$MODULE/config/device-font-engine.conf"
: > "$CALLS"
apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture
grep -qx originos "$CALLS"
! grep -qx generic "$CALLS"
! grep -qx prepare "$CALLS"
! grep -qx legacy "$CALLS"
grep -qx device-clear "$CALLS"
grep -qx dynamic-clear "$CALLS"
grep -qx base-clear "$CALLS"
! grep -qx oem-clear "$CALLS"
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = slot-only
''', '''# The foreground policy is loaded after the bridge in production. Static cache misses may try XML,
# but only a real committed overlay suppresses the background aligned-cache builder.
. "$ROOT/common/device_font_payload_policy.sh"
set -eu
_dfpp_xml_overlay_active() { [ "$LEGACY_REAL_XML" = 1 ]; }
ROM=originos
rm -f "$MODULE/config/device-font-engine.conf"
VARIABLE_SOURCE=0
DEVICE_RC=2

LEGACY_RC=0
LEGACY_REAL_XML=1
: > "$CALLS"
font_config_enable_for_payload Fixture
grep -qx prepare "$CALLS"
grep -qx legacy "$CALLS"
! grep -qx schedule "$CALLS"
! grep -qx base-clear "$CALLS"
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = legacy

# Wrapper-level success without an actual XML file must still schedule the aligned cache.
LEGACY_RC=0
LEGACY_REAL_XML=0
: > "$CALLS"
font_config_enable_for_payload Fixture
grep -qx prepare "$CALLS"
grep -qx legacy "$CALLS"
grep -qx schedule "$CALLS"
grep -qx base-clear "$CALLS"
! grep -qx oem-clear "$CALLS"
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = slot-only

LEGACY_RC=1
LEGACY_REAL_XML=0
: > "$CALLS"
font_config_enable_for_payload Fixture
grep -qx prepare "$CALLS"
grep -qx legacy "$CALLS"
grep -qx schedule "$CALLS"
grep -qx base-clear "$CALLS"
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = slot-only

# Variable sources stay off the foreground XML path.
VARIABLE_SOURCE=1
LEGACY_RC=0
: > "$CALLS"
font_config_enable_for_payload Fixture
! grep -qx prepare "$CALLS"
! grep -qx legacy "$CALLS"
grep -qx schedule "$CALLS"
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = slot-only
VARIABLE_SOURCE=0
LEGACY_RC=0
''')

# Extend transactional XML runtime tests.
runtime_path = 'scripts/font_config_runtime_test.sh'
runtime = load(runtime_path)
marker = "printf 'Font configuration runtime tests passed.\\n'\n"
if runtime.count(marker) != 1:
    raise SystemExit(f'{runtime_path}: final marker mismatch')
extra = r'''

mk_weights() {
    mkdir -p "$MOD/system/fonts"
    for _prefix in LuoShu LuoShuMono; do
        for _weight in 100 200 300 400 500 600 700 800 900; do
            dd if=/dev/zero of="$MOD/system/fonts/${_prefix}-${_weight}.ttf" bs=2048 count=1 2>/dev/null
            chmod 0644 "$MOD/system/fonts/${_prefix}-${_weight}.ttf"
        done
    done
}
font_config_disable
mk_weights
cat > "$PRODUCT_ETC/hihonor_magic_fonts.xml" <<'XML'
<familyset>
  <family name="honor-sans"><font weight="400">HonorSans-Regular.ttf</font></family>
  <family name="honor-icons"><font weight="400">HonorIcons.ttf</font></family>
</familyset>
XML
cat > "$PRODUCT_ETC/ACME_FONT_CONFIG.xml" <<'XML'
<familyset>
  <family name="acme-sans"><font weight="500">AcmeSans-Medium.ttf</font></family>
</familyset>
XML
font_config_generate DemoFamily
test -s "$MOD/product/etc/hihonor_magic_fonts.xml"
grep -q 'LuoShu-400.ttf' "$MOD/product/etc/hihonor_magic_fonts.xml"
grep -q 'HonorIcons.ttf' "$MOD/product/etc/hihonor_magic_fonts.xml"
test -s "$MOD/product/etc/ACME_FONT_CONFIG.xml"
grep -q 'LuoShu-500.ttf' "$MOD/product/etc/ACME_FONT_CONFIG.xml"
test "$(_luoshu_font_config_specs | sort | uniq -d | wc -l)" -eq 0

# One unusable overlay partition does not veto validated XML from the others.
font_config_disable
mk_weights
rm -rf "$MOD/odm"
: > "$MOD/odm"
font_config_generate DemoFamily
test -s "$MOD/system/etc/fonts.xml"
grep -q 'LuoShu-400.ttf' "$MOD/system/etc/fonts.xml"
test -s "$MOD/product/etc/mi_fonts_customization.xml"
test ! -e "$MOD/odm/etc/fonts_customization.xml"
rm -f "$MOD/odm"

# Missing master weights are a global XML failure.
font_config_disable
mk_weights
rm -f "$MOD/system/fonts/LuoShuMono-500.ttf"
if _luoshu_font_config_generate_base DemoFamily; then
    echo 'XML overlay unexpectedly generated without a complete nine-weight set' >&2
    exit 1
fi
test ! -e "$MOD/system/etc/fonts.xml"
test ! -e "$MOD/product/etc/mi_fonts_customization.xml"
test ! -e "$MOD/product/etc/hihonor_magic_fonts.xml"
test ! -e "$MOD/product/etc/ACME_FONT_CONFIG.xml"
'''
save(runtime_path, runtime.replace(marker, extra + "\n" + marker, 1))

# Focused partial-coverage regression test.
partial_test = r'''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/config/font-config-source/system" "$MOD/system/fonts"
dd if=/dev/zero of="$MOD/system/fonts/LuoShu-400.ttf" bs=2048 count=1 2>/dev/null
MODULE_DIR="$MOD"; MODDIR="$MOD"; CONFIG_DIR="$MOD/config"
export MODULE_DIR MODDIR CONFIG_DIR
. "$ROOT/common/font_safety.sh"
set -eu
_luoshu_font_config_specs() {
    printf 'system/fonts.xml|%s|%s|%s\\n' "$TMP/real-fonts.xml" "$MOD/system/etc/fonts.xml" "$MOD/system/fonts"
}
font_config_capture_original() { :; }
_luoshu_font_config_exec() {
    printf '%s\\n' 'Good.ttf|400|sans-serif' 'Bad.ttf|400|sans-serif'
}
_luoshu_safety_log() { :; }
ln() { case "$2" in *Bad.ttf) return 1 ;; esac; command ln "$@"; }
cp() { case "$2" in *Bad.ttf) return 1 ;; esac; command cp "$@"; }
luoshu_dynamic_targets_apply
test -s "$MOD/config/font-target-coverage.conf"
grep -qx 'discovered=2' "$MOD/config/font-target-coverage.conf"
grep -qx 'targets=2' "$MOD/config/font-target-coverage.conf"
grep -qx 'mapped=1' "$MOD/config/font-target-coverage.conf"
grep -qx 'status=partial' "$MOD/config/font-target-coverage.conf"
test "$(wc -l < "$MOD/config/font-target-aliases.conf" | tr -d ' ')" -eq 1
test -s "$MOD/system/fonts/Good.ttf"
test ! -e "$MOD/system/fonts/Bad.ttf"
rm -f "$MOD/system/fonts/LuoShu-400.ttf"
if luoshu_dynamic_targets_apply; then
    echo 'zero dynamic mappings unexpectedly succeeded' >&2
    exit 1
fi
test ! -e "$MOD/config/font-target-coverage.conf"
printf 'Generic XML partial coverage tests passed.\\n'
'''
partial = ROOT / 'scripts/generic_xml_partial_coverage_test.sh'
partial.write_text(partial_test, encoding='utf-8')
partial.chmod(0o755)

# Wire the regression into both dedicated and broad CI gates.
replace_once('.github/workflows/no-hook-font-engine.yml', '''      - scripts/font_config_runtime_test.sh
      - scripts/font_config_weights_test.sh
''', '''      - scripts/font_config_runtime_test.sh
      - scripts/generic_xml_partial_coverage_test.sh
      - scripts/font_config_weights_test.sh
''')
replace_once('.github/workflows/no-hook-font-engine.yml', '''      - name: Run payload transaction and boot guard tests
        run: sh -x scripts/font_safety_test.sh
''', '''      - name: Run payload transaction and boot guard tests
        run: |
          sh -x scripts/font_safety_test.sh
          sh -x scripts/generic_xml_partial_coverage_test.sh
''')
replace_once('scripts/check.sh', '''sh "$ROOT/scripts/font_config_transaction_rollback_test.sh"
sh "$ROOT/scripts/font_switch_performance_test.sh"
''', '''sh "$ROOT/scripts/font_config_transaction_rollback_test.sh"
sh "$ROOT/scripts/generic_xml_partial_coverage_test.sh"
sh "$ROOT/scripts/font_switch_performance_test.sh"
''')

print('Generic XML overlay refinement applied successfully.')
