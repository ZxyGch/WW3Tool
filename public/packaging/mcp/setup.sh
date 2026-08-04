#!/usr/bin/env bash
# 初始化 WW3Tool MCP server 的专用虚拟环境（安装 mcp SDK）。
# 同事 clone 仓库后，运行一次即可：
#   ./public/packaging/mcp/setup.sh
# 可用环境变量 MCP_PYTHON 指定 Python（默认 python3.12，需 >= 3.10）。
set -euo pipefail
MCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${MCP_PYTHON:-python3.12}"

if [ ! -x "$MCP_DIR/.venv/bin/python" ]; then
  echo "[setup] 创建 $MCP_DIR/.venv（$PY）..."
  "$PY" -m venv "$MCP_DIR/.venv"
fi

"$MCP_DIR/.venv/bin/python" -m pip install --quiet --upgrade pip
"$MCP_DIR/.venv/bin/python" -m pip install --quiet "mcp>=1.9,<2"
"$MCP_DIR/.venv/bin/python" -c "from mcp.server.fastmcp import FastMCP; print('[setup] mcp SDK OK')"
echo "[setup] 完成。MCP server: $MCP_DIR/ww3tool_mcp.py"
