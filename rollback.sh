#!/usr/bin/env bash
# NTK 登录加装包 · 回滚
# 用法：在 Piik 源码目录运行 bash rollback.sh
# 会把最近一次 .natsuko-backup/<时间戳>/ 里的文件还原回去，并删除注入的 account.ts / callback.html
set -euo pipefail

ROOT="$(pwd)"
BASES="$ROOT/.natsuko-backup"

if [[ ! -d "$BASES" ]]; then
  echo "找不到备份目录 $BASES，无需回滚。" >&2
  exit 1
fi

LATEST="$(ls -1d "$BASES"/* 2>/dev/null | sort | tail -1 || true)"
if [[ -z "$LATEST" ]]; then
  echo "备份目录为空，无需回滚。" >&2
  exit 1
fi

echo "==> 从备份还原：$LATEST"
cp -a "$LATEST/." "$ROOT/"

# 移除加装包新增的文件（仅当它们确实是本包生成的）
rm -f "$ROOT/src/client/lib/account.ts"
rm -f "$ROOT/public/auth/callback.html"
rmdir "$ROOT/public/auth" 2>/dev/null || true

echo "==> 已回滚。重新 npm run build 并重启服务即可。"
