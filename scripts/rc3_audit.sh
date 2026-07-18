#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

# 功能/UI/公开路径禁止出现；安装脚本中用于删除旧状态的最小清理代码不在此扫描范围。
PATTERN='USER_EMOJI_DIR|/sdcard/LuoShu/emoji/|emojiSection|emojiCurrent|emojiList|openEmojiFolder|moreOpenEmoji|sync_emoji_preview|importedEmoji|find_emoji_file|switch_emoji|emoji_switch|emoji_status|emoji_list|stability\.(js|css)|common/stability\.sh|fonts_xml_template|common/play_font_bridge\.sh|common/wechat_xweb_bridge\.sh'
HITS=$(grep -RInE --exclude-dir=python --exclude-dir=dist --exclude='*.pyc' "$PATTERN" \
  "$ROOT/common" "$ROOT/config" "$ROOT/webroot" \
  "$ROOT/service.sh" "$ROOT/uninstall.sh" "$ROOT/module.prop" \
  "$ROOT/README.md" "$ROOT/README.txt" "$ROOT/CHANGELOG.md" 2>/dev/null || true)
if [ -n "$HITS" ]; then
  echo '=== RC3 forbidden feature inventory ===' >&2
  printf '%s\n' "$HITS" >&2
  exit 86
fi

# WebUI 不再保留隐藏页面、死样式、兼容桩或相关文案。
UI_HITS=$(grep -RInEi --exclude='*.map' 'emoji|stability' "$ROOT/webroot" 2>/dev/null || true)
if [ -n "$UI_HITS" ]; then
  echo '=== RC3 WebUI legacy inventory ===' >&2
  printf '%s\n' "$UI_HITS" >&2
  exit 85
fi

for FILE in common/stability.sh webroot/stability.js webroot/stability.css common/fonts_xml_template.sh common/play_font_bridge.sh common/wechat_xweb_bridge.sh config/active_emoji.conf; do
  [ ! -e "$ROOT/$FILE" ] || { echo "obsolete file still exists: $FILE" >&2; exit 87; }
done

# 允许后端导入过滤器识别彩色/图标字体，但禁止模块内出现可挂载的彩色表情负载。
find "$ROOT/system" -type f -iname '*emoji*' -print -quit 2>/dev/null | grep -q . && {
  echo 'colored emoji payload exists under system/' >&2
  exit 88
} || true
