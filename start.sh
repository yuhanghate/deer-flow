#!/usr/bin/env bash
#
# 后台启动 DeerFlow（nginx 对外监听 2026）。
# 用法: ./start.sh
# 日志: logs/{langgraph,gateway,frontend,nginx}.log
# 停止: ./stop.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$REPO_ROOT"

exec make dev-daemon
