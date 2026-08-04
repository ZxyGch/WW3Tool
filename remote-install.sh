#!/usr/bin/env bash
# WW3Tool 一键安装脚本（远程安装，自包含 —— 从 raw URL 获取后直接执行）。
#
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/<YOUR-ORG>/WW3Tool/main/remote-install.sh | bash
#
# 可覆盖的环境变量：
#   WW3TOOL_REPO_URL    仓库 git 地址（默认 https://github.com/<YOUR-ORG>/WW3Tool.git）
#   WW3TOOL_INSTALL_DIR 安装目录（默认 $HOME/.ww3tool）
#   WW3TOOL_BIN_DIR     命令链接目录（默认自动选择 ~/.local/bin 或 /usr/local/bin）
#
# 安装内容：浅克隆仓库到安装目录，并把仓库内的 ww3tool 入口软链到 PATH。
# 首次运行 ww3tool 时，run.py 会自动创建虚拟环境并安装依赖。
set -euo pipefail

# 发布前把下面的 <YOUR-ORG> 替换为真实组织/用户（README 有说明）。
REPO_URL="${WW3TOOL_REPO_URL:-https://github.com/<YOUR-ORG>/WW3Tool.git}"
INSTALL_DIR="${WW3TOOL_INSTALL_DIR:-$HOME/.ww3tool}"
BIN_DIR="${WW3TOOL_BIN_DIR:-}"

echo "==> WW3Tool 一键安装"
echo "    仓库:   $REPO_URL"
echo "    安装到: $INSTALL_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "错误: 需要 git 命令（macOS 自带；Linux: sudo apt install git 等）" >&2
  exit 1
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  echo "==> 克隆仓库（浅克隆）..."
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
else
  echo "==> 更新已有安装..."
  git -C "$INSTALL_DIR" pull --ff-only
fi

if [ ! -x "$INSTALL_DIR/ww3tool" ]; then
  echo "错误: 仓库中未找到可执行的 ww3tool 入口脚本" >&2
  exit 1
fi

# 选择命令链接目录
if [ -z "$BIN_DIR" ]; then
  if [ -d "$HOME/.local/bin" ] || echo "$PATH" | tr ':' '\n' | grep -qxF "$HOME/.local/bin" >/dev/null 2>&1; then
    BIN_DIR="$HOME/.local/bin"
  elif [ -w "/usr/local/bin" ]; then
    BIN_DIR="/usr/local/bin"
  else
    BIN_DIR="$HOME/.local/bin"
  fi
fi
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/ww3tool" "$BIN_DIR/ww3tool"

echo "==> 完成。"
echo "    命令: $BIN_DIR/ww3tool"
echo "    首次运行 ww3tool 会自动创建虚拟环境并安装依赖（需几分钟）。"
if ! echo "$PATH" | tr ':' '\n' | grep -qxF "$BIN_DIR" >/dev/null 2>&1; then
  echo "    提示: $BIN_DIR 不在 PATH 中，请先执行: export PATH=\"$BIN_DIR:\$PATH\""
fi
echo "    验证: ww3tool --help"
