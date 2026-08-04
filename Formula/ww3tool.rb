# WW3Tool Homebrew formula
#
# 本地测试（需要真实 URL 后才能通过）：
#   brew install --HEAD ./Formula/ww3tool.rb
# 或发布 tap 后：
#   brew tap ZxyGch/ww3tool
#   brew install ww3tool
#
# 正式发布（打 tag）后替换：
#   1. url 从 refs/heads/master 改为 refs/tags/v0.1.0
#   2. 重新计算 sha256（curl -sL <tarball-url> | shasum -a 256）
# 注意：formula 只分发运行所需资源（meshgen/public/params.yml/src），
# WW3 计算内核与超大目录（WW3/、WW3-6.07.1/、workSpace/）不打包。
class Ww3tool < Formula
  desc "WW3Tool - WAVEWATCH III workflow toolkit (CLI / Shell REPL / Desktop GUI / MCP server)"
  homepage "https://github.com/ZxyGch/WW3Tool"
  url "https://github.com/ZxyGch/WW3Tool/archive/refs/heads/master.tar.gz"
  sha256 "498fb68a8125b3c302c8a85fa918249a4e9e2b1356b6d360a35984f7e77b5435"
  version "0.1.0"
  head "https://github.com/ZxyGch/WW3Tool.git", branch: "master"

  depends_on "python@3.12"

  def install
    # 保留运行所需的仓库资源；libexec 即仓库根（ww3tool 脚本据此定位资源）。
    libexec.install Dir["meshgen", "public", "src", "params.yml",
                        "run.py", "ww3tool", "pyproject.toml", "setup.py"]
    python = Formula["python@3.12"].opt_bin/"python3.12"
    system python, "-m", "venv", libexec/".venv"
    vpy = libexec/".venv/bin/python"
    system vpy, "-m", "pip", "install", "--upgrade", "pip"
    # --no-deps：轻量依赖由 run.py 首次运行时自动补装，
    # 避免 formula 构建期拉取全部重依赖（cartopy 等）。
    system vpy, "-m", "pip", "install", "--no-deps", "."
    # 移除 pip 生成的 console script，统一使用 libexec/ww3tool 入口
    # （其会通过 run.py 引导到 libexec/.venv 中的 Python）。
    FileUtils.rm_f libexec/".venv/bin/ww3tool"
    bin.install_symlink libexec/"ww3tool"
  end

  test do
    system bin/"ww3tool", "--help"
  end
end
