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
# A real same-directory ROM font alias supplies the terminal file's label.
printf font > "$r/stock/Roboto-Regular.ttf"
ln -s Roboto-Regular.ttf "$r/stock/DroidSans.ttf"
ln -s DroidSans.ttf "$r/stock/DroidSans-Bold.ttf"
printf selected > "$r/copy/DroidSans.ttf"
printf selected > "$r/copy/DroidSans-Bold.ttf"
printf 'f|DroidSans.ttf\nf|DroidSans-Bold.ttf\n' > "$r/alias-inventory"
printf '%s|%s\n' "$r/stock/Roboto-Regular.ttf" u:object_r:system_font:s0 >> "$r/labels"
test "$(_luoshu_stock_label_reference "$r/stock" DroidSans.ttf)" = "$r/stock/Roboto-Regular.ttf"
test "$(_luoshu_stock_label_reference "$r/stock" DroidSans-Bold.ttf)" = "$r/stock/Roboto-Regular.ttf"
_luoshu_restore_memory_labels "$r/copy" "$r/stock" "$r/alias-inventory"
test "$(_luoshu_file_context "$r/copy/DroidSans.ttf")" = u:object_r:system_font:s0
test "$(_luoshu_file_context "$r/copy/DroidSans-Bold.ttf")" = u:object_r:system_font:s0
test "$(readlink "$r/stock/DroidSans.ttf")" = Roboto-Regular.ttf
test "$(cat "$r/stock/Roboto-Regular.ttf")" = font
# Loops, dangling names, directory aliases and any path-bearing hop stay blocked.
ln -s cycle-b "$r/stock/cycle-a"; ln -s cycle-a "$r/stock/cycle-b"
ln -s missing.ttf "$r/stock/dangling.ttf"
ln -s sub "$r/stock/directory.ttf"
ln -s ../stock/Roboto-Regular.ttf "$r/stock/escape-return.ttf"
ln -s sub/new.ttf "$r/stock/path.ttf"
for rel in cycle-a dangling.ttf directory.ttf escape-return.ttf path.ttf ../stock/Roboto-Regular.ttf ./Roboto-Regular.ttf; do
    if _luoshu_stock_label_reference "$r/stock" "$rel"; then echo "unsafe label reference accepted: $rel" >&2; exit 1; fi
done
ln -s "$r/stock/sub" "$r/stock/parent-link"
if _luoshu_stock_label_reference "$r/stock" parent-link/new.ttf; then exit 1; fi
# A source payload symlink is never legalized by accepting a stock alias.
ln -s existing.xml "$r/copy/forbidden.ttf"
if _luoshu_memory_tree_inventory "$r/copy" "$r/bad-inventory"; then exit 1; fi
rm "$r/copy/forbidden.ttf"
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

# Only the explicitly approved synthetic API36 system XML scope can opt in.
mkdir "$r/config-copy" "$r/config-stock"
printf original > "$r/config-stock/font_fallback.xml"
printf xml > "$r/config-copy/font_fallback.xml"
getprop() { case "$1" in ro.kernel.qemu) echo 1 ;; ro.build.version.sdk) echo 36 ;; esac; }
getenforce() { echo Enforcing; }
id() { echo 0; }
if _luoshu_config_copy_labels_allowed "$r/config-copy" system-etc "$r/config-stock"; then exit 1; fi
LUOSHU_XML_COPY_LABEL_TEST_APPROVED=true
_luoshu_config_copy_labels_allowed "$r/config-copy" system-etc "$r/config-stock"
if _luoshu_config_copy_labels_allowed "$r/config-copy" vendor-etc "$r/config-stock"; then exit 1; fi
printf other > "$r/config-copy/unrelated.xml"
if _luoshu_config_copy_labels_allowed "$r/config-copy" system-etc "$r/config-stock"; then exit 1; fi
rm "$r/config-copy/unrelated.xml"
getenforce() { echo Permissive; }
if _luoshu_config_copy_labels_allowed "$r/config-copy" system-etc "$r/config-stock"; then exit 1; fi
getenforce() { echo Enforcing; }
rm "$r/config-stock/font_fallback.xml"
if _luoshu_config_copy_labels_allowed "$r/config-copy" system-etc "$r/config-stock"; then exit 1; fi
printf 'memory_layer_context_test: PASS (mock-only exact/ancestor contexts, modes, denial and readback)\n'
