#!/bin/sh
# A function defined in several files is resolved purely by source order, and the last definition
# silently wins. That has already cost a whole feature: a third definition of
# font_config_enable_for_payload shadowed the two that actually generated the no-hook XML overlay,
# so the module fell back to file-slot mapping on every device without any error being reported.
#
# Overriding is a legitimate technique here (later layers deliberately replace earlier ones), so this
# guard does not forbid it. It pins the current set: adding a new duplicate, or a new file that
# redefines an existing function, fails until the intent is recorded in the allowlist below.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='重复函数定义'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

# Every function that is intentionally overridden by a later-loaded layer, with the reason.
cat > "$TMP/allow" <<'ALLOW'
_copy_as_inventory
_device_font_inventory_target
_dfpr_anchor_lines
_dfpr_prepare_dynamic_state
_font_anchor
_luoshu_config_weight_source
_luoshu_font_config_exec
_luoshu_font_config_specs
_luoshu_magic_mount_present
_luoshu_mountify_present
_luoshu_overlay_mount_dir
_luoshu_self_visible_root
_luoshu_visible_path
_verify_font_copy
apply_font_by_rom
axis_value
clean_spec
clear_managed_text_fonts
config_json
copy_as_coloros
copy_as_hyperos
current_boot_id
device_font_dynamic_mount_apply
device_font_payload_build_install
device_font_payload_clear
fail_json
find_best_source
font_config_disable
font_config_enable_for_payload
font_config_mark_boot_success
font_config_prepare_payload_weights
font_validate_global
get_all_coloros_files
get_all_coloros_names
get_all_hyperos_files
import_copy_unique
import_detect_family
import_is_italic_name
import_probe_metadata
import_weight_label
json_escape
luoshu_copy_tree_bounded
luoshu_current_boot_id
luoshu_detect_mount_engine
luoshu_dynamic_targets_apply
luoshu_font_lock_acquire
luoshu_font_lock_active
luoshu_font_lock_pid
luoshu_font_lock_reap_stale
luoshu_font_lock_release
luoshu_font_validate_global_cached
luoshu_hybrid_backend
luoshu_magic_mount_ensure_partitions
luoshu_mount_backend
luoshu_mount_preflight
luoshu_mount_verify_active
luoshu_mountify_module_selected
luoshu_mountify_value
luoshu_payload_build_manifest
luoshu_payload_quarantine
luoshu_payload_transaction_abort
luoshu_payload_transaction_begin
luoshu_payload_transaction_commit
luoshu_payload_transaction_rollback
luoshu_payload_validate_current
luoshu_payload_validate_manifest_fast
luoshu_payload_validate_manifest_full
luoshu_self_mount_ensure
luoshu_used_partitions
luoshu_write_mount_probe
luoshu_write_mount_probes
precheck_mix
prune_composite_cache
python_run
read_prop
read_value
recover_task
role_weight
run_instance
safe_weight
start_mix
status_json
update_task
worker
write_task
ALLOW

: > "$TMP/defs"
for f in "$ROOT"/common/*.sh "$ROOT"/*.sh; do
    [ -f "$f" ] || continue
    grep -o '^[a-zA-Z_][a-zA-Z0-9_]*()' "$f" 2>/dev/null | tr -d '()' | while IFS= read -r fn; do
        printf '%s\n' "$fn" >> "$TMP/defs"
    done
done

sort "$TMP/defs" | uniq -d | sort > "$TMP/dupes"
sort "$TMP/allow" > "$TMP/allow-sorted"

comm -23 "$TMP/dupes" "$TMP/allow-sorted" > "$TMP/unexpected"
if [ -s "$TMP/unexpected" ]; then
    printf '以下函数在多个文件中重复定义，但不在允许清单里：\n' >&2
    while IFS= read -r fn; do
        printf '  %s  ->  %s\n' "$fn" \
            "$(grep -l "^${fn}()" "$ROOT"/common/*.sh "$ROOT"/*.sh 2>/dev/null | sed "s|$ROOT/||" | tr '\n' ' ')" >&2
    done < "$TMP/unexpected"
    printf '如果这是有意的分层覆盖，请把函数名加入本测试的允许清单并说明原因。\n' >&2
    fail "$(wc -l < "$TMP/unexpected" | tr -d '[:space:]') 个未登记的重复定义"
fi

# The allowlist must not rot: an entry that is no longer duplicated should be removed.
comm -13 "$TMP/dupes" "$TMP/allow-sorted" > "$TMP/stale"
if [ -s "$TMP/stale" ]; then
    printf '允许清单里这些函数已经不再重复定义，请删除条目：\n' >&2
    sed 's/^/  /' "$TMP/stale" >&2
    fail "$(wc -l < "$TMP/stale" | tr -d '[:space:]') 个过期的允许条目"
fi

printf 'Duplicate shell function guard passed (%s 个已登记的分层覆盖).\n' \
    "$(wc -l < "$TMP/dupes" | tr -d '[:space:]')"