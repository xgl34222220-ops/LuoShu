#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PATTERN='NotoColorEmoji|active_emoji|emoji_switch|emoji_status|emoji_list|emoji_task|emoji_reboot|USER_EMOJI_DIR|/sdcard/LuoShu/emoji/|emojiSection|emojiCurrent|emojiList|openEmojiFolder|moreOpenEmoji|sync_emoji_preview|importedEmoji|find_emoji_file|switch_emoji|stability\.(js|css)|common/stability\.sh|fonts_xml_template|common/play_font_bridge\.sh|common/wechat_xweb_bridge\.sh'
HITS=$(grep -RInE --exclude-dir=python --exclude-dir=dist --exclude='*.pyc' "$PATTERN" "$ROOT/common" "$ROOT/config" "$ROOT/webroot" "$ROOT/scripts" "$ROOT/customize.sh" "$ROOT/post-fs-data.sh" "$ROOT/service.sh" "$ROOT/uninstall.sh" "$ROOT/module.prop" "$ROOT/README.md" "$ROOT/README.txt" "$ROOT/CHANGELOG.md" 2>/dev/null || true)
if [ -n "$HITS" ]; then
  echo '=== RC3 legacy inventory ===' >&2
  printf '%s\n' "$HITS" >&2
  exit 86
fi
for FILE in common/stability.sh webroot/stability.js webroot/stability.css common/fonts_xml_template.sh common/play_font_bridge.sh common/wechat_xweb_bridge.sh config/active_emoji.conf; do
  [ ! -e "$ROOT/$FILE" ] || { echo "obsolete file still exists: $FILE" >&2; exit 87; }
done
