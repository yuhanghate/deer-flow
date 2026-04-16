#!/usr/bin/env bash
#
# 停止由 make dev / make dev-daemon / ./start.sh 拉起的 DeerFlow 相关进程。
# 需与 start.sh 中 PORT 一致，否则 nginx 监听端口可能无法被 _kill_port 清理。
# 用法: ./stop.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$REPO_ROOT"

export PORT=8100
exec make stop
