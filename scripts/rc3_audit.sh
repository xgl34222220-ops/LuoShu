#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

# App-only 仓库不能继续保留可运行的 WebUI 前端或准备脚本。
[ ! -d "$ROOT/webroot" ] || {
  echo 'obsolete WebUI source directory still exists: webroot/' >&2
  exit 85
}
[ ! -e "$ROOT/scripts/prepare_webui.sh" ] || {
  echo 'obsolete WebUI build script still exists: scripts/prepare_webui.sh' >&2
  exit 85
}

# 运行时脚本不得创建或依赖 webroot，也不得重新暴露热刷新入口。
RUNTIME_FILES="$ROOT/customize.sh $ROOT/post-fs-data.sh $ROOT/service.sh $ROOT/action.sh $ROOT/common/font_manager.sh $ROOT/common/app_bridge.sh $ROOT/common/luoshu_cli.sh"
HITS=$(grep -InE 'webroot|restart_ui|sync_preview_fonts|重启界面|刷新字体缓存|回滚上一字体' $RUNTIME_FILES 2>/dev/null || true)
if [ -n "$HITS" ]; then
  echo '=== App-only forbidden runtime inventory ===' >&2
  printf '%s\n' "$HITS" >&2
  exit 86
fi
# 安装脚本可以单向删除旧 previous_font.conf，但字体管理器不能再读取或生成它。
! grep -q 'previous_font\.conf' "$ROOT/common/font_manager.sh"

# 已废弃的 Emoji、稳定性自救和旧桥接负载不得重新出现。
PATTERN='USER_EMOJI_DIR|/sdcard/LuoShu/emoji/|emojiSection|emojiCurrent|emojiList|openEmojiFolder|moreOpenEmoji|sync_emoji_preview|importedEmoji|find_emoji_file|switch_emoji|emoji_switch|emoji_status|emoji_list|stability\.(js|css)|common/stability\.sh|fonts_xml_template|common/play_font_bridge\.sh|common/wechat_xweb_bridge\.sh'
HITS=$(grep -RInE --exclude-dir=python --exclude-dir=dist --exclude='*.pyc' "$PATTERN" \
  "$ROOT/common" "$ROOT/config" "$ROOT/service.sh" "$ROOT/uninstall.sh" "$ROOT/module.prop" \
  "$ROOT/README.md" "$ROOT/README.txt" "$ROOT/CHANGELOG.md" 2>/dev/null || true)
if [ -n "$HITS" ]; then
  echo '=== Forbidden legacy feature inventory ===' >&2
  printf '%s\n' "$HITS" >&2
  exit 87
fi

for FILE in common/stability.sh common/fonts_xml_template.sh common/play_font_bridge.sh common/wechat_xweb_bridge.sh config/active_emoji.conf; do
  [ ! -e "$ROOT/$FILE" ] || { echo "obsolete file still exists: $FILE" >&2; exit 88; }
done

# 允许后端导入过滤器识别彩色/图标字体，但禁止模块内出现可挂载的彩色表情负载。
find "$ROOT/system" -type f -iname '*emoji*' -print -quit 2>/dev/null | grep -q . && {
  echo 'colored emoji payload exists under system/' >&2
  exit 89
} || true

# 当前构建和工作流只允许单包模式。
! grep -RIn 'LUOSHU_VARIANT' "$ROOT/scripts" "$ROOT/.github/workflows" >/dev/null 2>&1
! grep -q '^webroot=' "$ROOT/module.prop"
grep -q 'native_font_index.json' "$ROOT/common/font_manager.sh"
grep -q 'native_font_index.json' "$ROOT/service.sh"
