#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ ! -d .git ]; then
  echo "请先将源码解压到 LuoShu Git 仓库根目录，再运行此脚本。" >&2
  exit 1
fi

REMOTE=$(git remote get-url origin 2>/dev/null || true)
case "$REMOTE" in
  *xgl34222220-ops/LuoShu*) ;;
  *)
    echo "当前目录不是 xgl34222220-ops/LuoShu 仓库：$REMOTE" >&2
    exit 1
    ;;
esac

APP_APK="${LUOSHU_APP_APK:-}"
[ -n "$APP_APK" ] && [ -s "$APP_APK" ] || {
  echo '本地候选构建需要 LUOSHU_APP_APK 指向已签名的正式 APK。' >&2
  echo '推荐直接使用 GitHub Actions 的 Publish signed release 工作流。' >&2
  exit 65
}

sh scripts/check.sh
LUOSHU_APP_APK="$APP_APK" \
LUOSHU_APP_PACKAGE="${LUOSHU_APP_PACKAGE:-}" \
LUOSHU_APP_VERSION_CODE="${LUOSHU_APP_VERSION_CODE:-}" \
  sh scripts/build.sh

VERSION=$(sed -n 's/^version=//p' module.prop | head -n 1)
sh scripts/pre_release_readiness.sh --target "$VERSION" --enforce

echo "本地候选 ${VERSION} 已构建并通过预发行门禁。"
echo '为防止绕过 PR、固定签名和真机矩阵，本脚本不会直接推送 main 或创建 Release。'
echo '请通过 Publish signed release 工作流发布；稳定版还会强制检查真机证据。'
