#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-device-plan)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
PUBLIC="$TMP/public"
CALLS="$TMP/calls.log"
mkdir -p "$MODULE/common" "$MODULE/config" "$PUBLIC/fonts"
cp "$ROOT/common/font_library_cache.sh" "$MODULE/common/font_library_cache.sh"

cat > "$MODULE/common/device_font_template.sh" <<EOF
#!/bin/sh
printf 'template:%s\n' "\${1:-}" >> "$CALLS"
mkdir -p "$MODULE/config"
printf '{"schema":"device-font-template-v1"}\n' > "$MODULE/config/device-font-template.json"
EOF
cat > "$MODULE/common/device_font_slot_plan.sh" <<EOF
#!/bin/sh
printf 'plan:%s|%s|%s\n' "\${1:-}" "\${2:-}" "\${3:-}" >> "$CALLS"
EOF
chmod 0755 "$MODULE/common"/*.sh

printf 'Alpha\n' > "$MODULE/config/active_font.conf"
printf 'fixture-font\n' > "$PUBLIC/fonts/Alpha-Regular.ttf"

# 指纹查询必须是纯读取，不能在开机服务中隐式启动规划进程。
MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_library_cache.sh" value >/dev/null
sleep 0.1
test ! -e "$CALLS"

MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_library_cache.sh" prepare-plan >/dev/null
grep -q '^template:ensure$' "$CALLS"
grep -Fq "plan:build|$PUBLIC/fonts/Alpha-Regular.ttf|Alpha" "$CALLS"

: > "$CALLS"
printf 'default\n' > "$MODULE/config/active_font.conf"
MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_library_cache.sh" value >/dev/null
sleep 0.1
test ! -s "$CALLS"

MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_library_cache.sh" prepare-plan >/dev/null
grep -q '^template:ensure$' "$CALLS"
grep -q '^plan:clear||$' "$CALLS"

echo 'Device font slot-plan runtime handoff test passed.'
