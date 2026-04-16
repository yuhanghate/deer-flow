#!/usr/bin/env bash
#
# 在本地以公网入口端口 8100 启动 DeerFlow（nginx 对外监听 8100）。
# 用法: ./start.sh   或   bash start.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$REPO_ROOT"

export PORT=8100
exec make dev
