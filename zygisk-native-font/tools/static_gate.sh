#!/bin/sh
# Static gate for the built module libraries.
#   static_gate.sh READELF BUILD_ROOT
# * the .so exports exactly one defined dynamic symbol: zygisk_module_entry
# * DT_NEEDED is a subset of {libc, libdl, liblog, libm, libandroid}
# * no inline-hook library is linked or embedded
set -eu
readelf="$1"
build_root="$2"
allowed_needed=' libc.so libdl.so liblog.so libm.so libandroid.so '
status=0
for so in "$build_root"/*/libluoshu_native_font.so; do
  echo "== $so ($(stat -c %s "$so") bytes)"
  exports="$("$readelf" -W --dyn-syms "$so" | awk '$5=="GLOBAL"||$5=="WEAK" {if ($7!="UND") print $8}' | sed 's/@.*//' | sort -u)"
  echo "exports: $(echo "$exports" | tr '\n' ' ')"
  if [ "$exports" != "zygisk_module_entry" ]; then
    echo "::error::$so must export only zygisk_module_entry" >&2
    status=1
  fi
  needed="$("$readelf" -W -d "$so" | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p')"
  echo "needed: $(echo "$needed" | tr '\n' ' ')"
  for lib in $needed; do
    case "$allowed_needed" in
      *" $lib "*) ;;
      *) echo "::error::$so links unexpected $lib" >&2; status=1 ;;
    esac
  done
  if strings -a "$so" | grep -E -i -q 'shadowhook|dobby|bytehook|xhook|substrate'; then
    echo "::error::$so embeds a hook library" >&2
    status=1
  fi
done
exit "$status"
