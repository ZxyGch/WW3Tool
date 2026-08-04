#!/usr/bin/env bash
# 启动 WW3Tool MCP server（stdio）。
# MCP 客户端的 command 指向本脚本即可，无需关心 venv 细节。
set -euo pipefail
MCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$MCP_DIR/.venv/bin/python" "$MCP_DIR/ww3tool_mcp.py" "$@"
