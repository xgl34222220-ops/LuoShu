#!/bin/sh
# Label decisions only: chcon is mocked; no host security labels are changed.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
r=$(mktemp -d)
trap 'rm -rf "$r"' EXIT
mkdir -p "$r/stock/sub" "$r/copy/sub"
printf original > "$r/stock/existing.xml"
printf selected > "$r/copy/existing.xml"
printf generated > "$r/copy/sub/new.ttf"
printf 'f|existing.xml\nd|sub\nf|sub/new.ttf\n' > "$r/inventory"
chmod 0666 "$r/copy/existing.xml" "$r/copy/sub/new.ttf"
. "$ROOT/common/mount_self_backend.sh"
set -eu
_luoshu_selinux_active() { return 0; }
_luoshu_file_context() {
    case "$1" in
      "$r/stock/existing.xml") echo u:object_r:font_config:s0 ;;
      "$r/stock/sub") echo u:object_r:vendor_font:s0 ;;
      "$r/stock") echo u:object_r:system_file:s0 ;;
      *) awk -F'|' -v p="$1" '$1==p{value=$2}END{if(value=="")exit 1;print value}' "$r/labels" ;;
    esac
}
_luoshu_set_file_context() { printf '%s|%s\n' "$2" "$1" >> "$r/labels"; }
_luoshu_restore_memory_labels "$r/copy" "$r/stock" "$r/inventory"
test "$(_luoshu_file_context "$r/copy/existing.xml")" = u:object_r:font_config:s0
test "$(_luoshu_file_context "$r/copy/sub/new.ttf")" = u:object_r:vendor_font:s0
test "$(stat -c %a "$r/copy/sub/new.ttf")" = 644
test "$(stat -c %a "$r/copy/sub")" = 755
test "$(cat "$r/stock/existing.xml")" = original
! grep -F "$r/stock|" "$r/labels"
# Denied relabel or mismatched readback cannot be published as success.
_luoshu_set_file_context() { return 1; }
if _luoshu_restore_memory_labels "$r/copy" "$r/stock" "$r/inventory"; then exit 1; fi
_luoshu_set_file_context() { :; }
: > "$r/labels"
if _luoshu_restore_memory_labels "$r/copy" "$r/stock" "$r/inventory"; then exit 1; fi
# Missing originals cannot manufacture a guessed context.
if _luoshu_stock_label_reference "$r/missing" new.ttf; then exit 1; fi
ln -s "$r/stock/existing.xml" "$r/stock/alias.xml"
if _luoshu_stock_label_reference "$r/stock" alias.xml; then exit 1; fi
_luoshu_selinux_active() { return 2; }
if _luoshu_restore_memory_labels "$r/copy" "$r/stock" "$r/inventory"; then exit 1; fi
# The config layer explicitly disables relabel, even on an enforcing host.
_luoshu_selinux_active() { return 0; }
_luoshu_set_file_context() { printf changed >> "$r/labels"; }
: > "$r/labels"
_luoshu_restore_memory_labels "$r/copy" "$r/stock" "$r/inventory" 0
test ! -s "$r/labels"
printf 'memory_layer_context_test: PASS (mock-only exact/ancestor contexts, modes, denial and readback)\n'
