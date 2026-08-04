# WW3Tool Homebrew formula
#
# 本地测试：
#   brew install --HEAD ./ww3tool.rb
# 发布 tap 后：
#   brew tap ZxyGch/ww3tool && brew trust zxygch/ww3tool && brew install ww3tool
#
# 正式发布策略：每次发版在主仓库打新 tag（v0.1.0、v0.1.1...），
# 然后把本文件的 url / sha256 更新为对应 tag tarball。
#   curl -sL <tarball-url> | shasum -a 256
# 注意：仓库结构 v0.1.2 起将入口脚本收敛到 public/packaging/（见下），
# v0.1.1 及之前的 tag 中 ww3tool 位于仓库根；本公式按新结构编写，
# 发布 v0.1.2 时同步更新 tap（homebrew-ww3tool）即可。
# 注意：formula 只分发运行所需资源（meshgen/public/params.yml/src），
# WW3 计算内核与超大目录（WW3/、WW3-6.07.1/、workSpace/）不打包。
class Ww3tool < Formula
  desc "WW3Tool - WAVEWATCH III workflow toolkit (CLI / Shell REPL / Desktop GUI / MCP server)"
  homepage "https://github.com/ZxyGch/WW3Tool"
  url "https://github.com/ZxyGch/WW3Tool/archive/refs/tags/v0.1.1.tar.gz"
  sha256 "52b6d03363bc2d0dcd5545c0faeda650044f2eb84b3fb5502eee27dbeb39760c"
  version "0.1.1"
  head "https://github.com/ZxyGch/WW3Tool.git", branch: "master"

  depends_on "python@3.12"

  def install
    # GitHub archive 解压出 <repo>-<version>/ 顶层目录；Homebrew 的 buildpath
    # 可能是 staging 根或该子目录。显式定位项目目录，避免依赖 cwd。
    proj = buildpath/"WW3Tool-#{version}"
    proj = buildpath unless (proj/"setup.py").exist?
    # 保留运行所需的仓库资源；libexec 即仓库根（ww3tool 脚本据此定位资源）。
    # 入口脚本位于 public/packaging/ww3tool（public/ 整体拷入，packaging 自动包含）。
    libexec.install Dir[proj/"meshgen", proj/"public", proj/"src", proj/"params.yml",
                        proj/"run.py", proj/"public/packaging/ww3tool",
                        proj/"pyproject.toml", proj/"setup.py"]
    python = Formula["python@3.12"].opt_bin/"python3.12"
    system python, "-m", "venv", libexec/".venv"
    vpy = libexec/".venv/bin/python"
    system vpy, "-m", "pip", "install", "--upgrade", "pip"
    # 显式切到 libexec 再安装（libexec 内含 setup.py/pyproject.toml），
    # 规避任何 cwd 不确定性；一次性装齐全部依赖（含 GUI extra），
    # 与 pip 安装方式一致，装完 CLI/GUI 开箱即用；run.py 首次运行仍保留
    # 自动补装核心依赖作为兜底。
    Dir.chdir(libexec) do
      system vpy, "-m", "pip", "install", ".[gui]"
    end
    # 移除 pip 生成的 console script，统一使用 libexec/ww3tool 入口
    # （其会通过 run.py 引导到 libexec/.venv 中的 Python）。
    FileUtils.rm_f libexec/".venv/bin/ww3tool"
    bin.install_symlink libexec/"ww3tool"
  end

  test do
    system bin/"ww3tool", "--help"
  end
end
