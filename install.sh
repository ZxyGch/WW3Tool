#!/usr/bin/env bash
# 把 WW3Tool 安装为全局命令 `ww3tool`（类似 mysql / git）。
#
# 用法：
#   ./install.sh               自动选择安装目录并安装
#   ./install.sh --prefix DIR  安装到指定目录（优先于自动探测）
#   ./install.sh --uninstall   移除已安装的链接
#   ./install.sh --check       只显示将安装到哪里，不做修改
#
# 自动探测顺序：
#   1. $WW3TOOL_PREFIX 环境变量
#   2. ~/.local/bin（若在 PATH 中或可写）
#   3. /usr/local/bin（若可写）
#   4. 否则提示使用 sudo ./install.sh --prefix /usr/local/bin
#
# 安装后即可在任何目录执行：ww3tool shell / ww3tool run-workflow ...
# 卸载：./install.sh --uninstall
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINK_NAME="ww3tool"
UNINSTALL=0
CHECK_ONLY=0
PREFIX=""

while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) UNINSTALL=1; shift ;;
    --check) CHECK_ONLY=1; shift ;;
    --prefix)
      if [ $# -lt 2 ]; then
        echo "用法：--prefix 需要跟随目录参数，如：./install.sh --prefix /usr/local/bin" >&2
        exit 2
      fi
      PREFIX="$2"
      shift 2
      ;;
    --prefix=*) PREFIX="${1#--prefix=}"; shift ;;
    *)
      echo "未知参数：$1" >&2
      echo "用法：./install.sh [--prefix DIR | --uninstall | --check]" >&2
      exit 2
      ;;
  esac
done

choose_dir() {
  if [ -n "${WW3TOOL_PREFIX:-}" ]; then
    echo "${WW3TOOL_PREFIX%/}"
    return
  fi
  local home_bin="$HOME/.local/bin"
  if [ -d "$home_bin" ] || echo "$PATH" | tr ':' '\n' | grep -qxF "$home_bin" >/dev/null 2>&1; then
    echo "$home_bin"
    return
  fi
  if [ -w "/usr/local/bin" ]; then
    echo "/usr/local/bin"
    return
  fi
  echo ""
}

uninstall() {
  local target="${PREFIX:-$(choose_dir)}"
  if [ -z "$target" ]; then
    echo "未找到安装目录（--uninstall 请配合 --prefix 或安装时使用的目录）" >&2
    exit 1
  fi
  local link="$target/$LINK_NAME"
  if [ -L "$link" ]; then
    rm "$link"
    echo "已移除：$link"
  elif [ -e "$link" ]; then
    echo "警告：$link 存在但不是符号链接，未删除（请手动检查）" >&2
    exit 1
  else
    echo "$link 不存在，无需卸载。"
  fi
}

if [ "$UNINSTALL" = "1" ]; then
  uninstall
  exit 0
fi

target="${PREFIX:-$(choose_dir)}"
if [ -z "$target" ]; then
  echo "没有可写的系统目录。请选择以下任一方式：" >&2
  echo "  1) sudo ./install.sh --prefix /usr/local/bin" >&2
  echo "  2) mkdir -p ~/.local/bin && ./install.sh --prefix ~/.local/bin（并确保 ~/.local/bin 在 PATH 中）" >&2
  exit 1
fi

mkdir -p "$target"
link="$target/$LINK_NAME"

if [ "$CHECK_ONLY" = "1" ]; then
  echo "将安装到：$link"
  echo "指向：$SCRIPT_DIR/$LINK_NAME"
  exit 0
fi

if [ -e "$link" ] && [ ! -L "$link" ]; then
  echo "错误：$link 已存在且不是符号链接，拒绝覆盖。请手动处理。" >&2
  exit 1
fi

ln -sf "$SCRIPT_DIR/$LINK_NAME" "$link"
echo "已安装：$link"
echo "现在可以在任意目录执行：ww3tool --help"
if ! echo "$PATH" | tr ':' '\n' | grep -qxF "$target" >/dev/null 2>&1; then
  echo "提示：$target 不在 PATH 中，如需全局使用请把它加入 PATH。"
fi
