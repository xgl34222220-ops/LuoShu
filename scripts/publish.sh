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

sh scripts/check.sh
sh scripts/build.sh

VERSION=$(sed -n 's/^version=//p' module.prop | head -n 1)
git add -A
if git diff --cached --quiet; then
  echo "没有需要提交的变更。"
  exit 0
fi

git commit -m "release: ${VERSION}"
git push origin HEAD:main

echo "源码已推送。GitHub Actions 将自动构建并发布 ${VERSION}。"
