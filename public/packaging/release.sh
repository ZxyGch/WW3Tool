#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# WW3Tool 一键打包上传 PyPI
#
# 用法:
#   ./public/packaging/release.sh            # 完整流程:检测版本 → 构建 → 校验 → 上传
#   ./public/packaging/release.sh --build    # 只构建 + twine check,不上传
#   ./public/packaging/release.sh --upload   # 跳过构建,直接上传 dist/ 现有产物
#
# 前置要求:
#   - ~/.pypirc 已配置 PyPI 凭据(或 TWINE_USERNAME / TWINE_PASSWORD 环境变量)
#   - 发布新版本前先在 pyproject.toml 改 version
#
# [EN] One-shot build & upload to PyPI.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

# 项目根(脚本位于 public/packaging/ 下,向上两级)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# 选一个可用的 Python(优先新版)
PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "❌ 未找到 python3,请先安装 Python 3.9+" >&2
    exit 1
fi
echo "🔧 使用 Python: $($PY --version 2>&1)"

MODE="${1:-full}"

# 版本号(来自 pyproject.toml)
VERSION="$(grep -m1 '^version = ' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/')"
if [ -z "$VERSION" ]; then
    echo "❌ 无法从 pyproject.toml 读取版本号" >&2
    exit 1
fi
echo "📦 版本: $VERSION"

# 检查 PyPI 上是否已存在该版本(已存在则拒绝,避免 400)
check_version() {
    local exists
    exists="$($PY - <<EOF 2>/dev/null || echo no
import json, urllib.request
try:
    d = json.load(urllib.request.urlopen("https://pypi.org/pypi/ww3tool/json", timeout=15))
    print("yes" if "$VERSION" in d.get("releases", {}) else "no")
except Exception:
    print("no")
EOF
)"
    if [ "$exists" = "yes" ]; then
        echo "❌ 版本 $VERSION 已在 PyPI 发布。若需更新描述/代码,请先在 pyproject.toml 升版本号。" >&2
        exit 1
    fi
}

# 确保 setuptools / twine 可用
ensure_tools() {
    "$PY" -m pip install -q --upgrade setuptools twine 2>/dev/null || \
        "$PY" -m pip install -q --user --upgrade setuptools twine 2>/dev/null || true
}

build() {
    echo "🏗️  构建 wheel + sdist ..."
    rm -rf build dist
    "$PY" -m pip wheel . -w dist --no-deps >/tmp/ww3tool_build.log 2>&1 || {
        echo "❌ wheel 构建失败:" >&2
        tail -20 /tmp/ww3tool_build.log >&2
        exit 1
    }
    "$PY" -c "import run; print(run.build_sdist('dist'))" >/dev/null 2>&1 || {
        echo "❌ sdist 构建失败" >&2
        exit 1
    }
    echo "✅ 产物:"
    ls -la dist/
}

check() {
    echo "🔍 twine check ..."
    "$PY" -m twine check dist/* || {
        echo "❌ twine check 未通过" >&2
        exit 1
    }
    echo "✅ 校验通过"
}

upload() {
    echo "🚀 上传 PyPI ..."
    # 网络代理可能抖动断连:逐文件上传,失败自动重试(最多 6 次)
    for f in dist/*; do
        local ok=0
        for i in 1 2 3 4 5 6; do
            if "$PY" -m twine upload "$f" >/tmp/ww3tool_upload.log 2>&1; then
                ok=1
                break
            fi
            echo "  上传 $(basename "$f") 第 ${i} 次失败,10 秒后重试 ..." >&2
            sleep 10
        done
        if [ "$ok" != "1" ]; then
            echo "❌ 上传失败: $(basename "$f")" >&2
            tail -5 /tmp/ww3tool_upload.log >&2
            exit 1
        fi
        echo "  ✅ $(basename "$f")"
    done
    echo "✅ 上传完成: https://pypi.org/project/ww3tool/$VERSION/"
}

case "$MODE" in
    --build)
        ensure_tools
        check_version
        build
        check
        ;;
    --upload)
        [ -n "$(ls dist/* 2>/dev/null)" ] || { echo "❌ dist/ 为空,请先 --build" >&2; exit 1; }
        ensure_tools
        upload
        ;;
    *)
        ensure_tools
        check_version
        build
        check
        upload
        ;;
esac

echo "🎉 完成: ww3tool $VERSION 已发布"
