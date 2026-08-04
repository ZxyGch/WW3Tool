#!/usr/bin/env bash
# WW3Tool one-line installer (self-contained; safe to pipe from a raw URL).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ZxyGch/WW3Tool/master/public/packaging/remote-install.sh | bash
#
# Optional environment overrides:
#   WW3TOOL_REPO_URL    Repo git URL (default: https://github.com/ZxyGch/WW3Tool.git)
#   WW3TOOL_INSTALL_DIR Install directory (default: $HOME/.ww3tool)
#   WW3TOOL_BIN_DIR     Directory for the ww3tool command symlink
#                       (default: auto-pick ~/.local/bin or /usr/local/bin)
#
# What it does: shallow-clones the repo into the install directory and symlinks
# the bundled ww3tool entry script into PATH. On first run, run.py creates a
# virtual environment and installs dependencies automatically.
set -euo pipefail

# Repo URL (override with WW3TOOL_REPO_URL).
REPO_URL="${WW3TOOL_REPO_URL:-https://github.com/ZxyGch/WW3Tool.git}"
INSTALL_DIR="${WW3TOOL_INSTALL_DIR:-$HOME/.ww3tool}"
BIN_DIR="${WW3TOOL_BIN_DIR:-}"
echo "==> WW3Tool installer"
echo "    repo:    $REPO_URL"
echo "    install: $INSTALL_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "Error: 'git' is required (preinstalled on macOS; on Linux: sudo apt install git, etc.)" >&2
  exit 1
fi

if [ -e "$INSTALL_DIR" ] && [ ! -d "$INSTALL_DIR/.git" ]; then
  echo "Error: $INSTALL_DIR exists but is not a WW3Tool repo (missing .git)." >&2
  echo "       Remove it or set WW3TOOL_INSTALL_DIR to another directory." >&2
  exit 1
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  echo "==> Cloning repository (shallow)..."
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
else
  echo "==> Updating existing installation..."
  if ! git -C "$INSTALL_DIR" pull --ff-only; then
    echo "Warning: update failed (local changes?). Please handle $INSTALL_DIR manually." >&2
  fi
fi

if [ ! -x "$INSTALL_DIR/public/packaging/ww3tool" ]; then
  echo "Error: executable 'ww3tool' entry script not found in the repository" >&2
  exit 1
fi

# Pick the directory for the command symlink.
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
ln -sf "$INSTALL_DIR/public/packaging/ww3tool" "$BIN_DIR/ww3tool"

echo "==> Done."
echo "    command: $BIN_DIR/ww3tool"
echo "    First run creates a virtual environment and installs dependencies (a few minutes)."
if ! echo "$PATH" | tr ':' '\n' | grep -qxF "$BIN_DIR" >/dev/null 2>&1; then
  echo "    Note: $BIN_DIR is not in PATH. Run: export PATH=\"$BIN_DIR:\$PATH\""
fi
echo "    Verify: ww3tool --help"
