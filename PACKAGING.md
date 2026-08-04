# WW3Tool 封装指南

把 WW3Tool 封装成多种形态，让日常使用和 AI 客户端调用都像 `mysql` / `git`
一样简单：

| 形态 | 入口 | 适合谁 |
| --- | --- | --- |
| CLI 全局命令 | `ww3tool`（安装后任意目录可用） | 人（终端）与脚本 |
| MCP server | 34 个 `ww3tool_*` tools + `list_commands`（stdio） | Claude / Cursor 等 AI 客户端 |

所有形态都复用仓库根的 `run.py` 统一入口，venv 引导、依赖检查、语言切换
完全一致，**不需要改动任何现有代码**（打包形态下仅需 `WW3TOOL_ROOT` 指向资源）。

---

## 一、安装方式

### 1. 一键脚本（推荐给其他人）

```bash
curl -fsSL https://raw.githubusercontent.com/ZxyGch/WW3Tool/master/remote-install.sh | bash
```

自动完成：浅克隆仓库到 `~/.ww3tool` → 把 `ww3tool` 命令软链到 PATH
（优先 `~/.local/bin`，其次 `/usr/local/bin`）→ 首次运行自动建 venv 装依赖。
可覆盖：`WW3TOOL_REPO_URL`、`WW3TOOL_INSTALL_DIR`、`WW3TOOL_BIN_DIR`。

### 2. pip install

```bash
pip install git+https://github.com/ZxyGch/WW3Tool.git
# 或发布到 PyPI / 内网源后：pip install ww3tool
# 需要桌面 GUI 时：pip install "ww3tool[gui]"
```

安装后 `ww3tool` 命令直接可用。**注意**：pip 只装 Python 代码；网格生成
（`meshgen/`）、翻译、`params.yml` 模板等仓库资源需要指向一个仓库目录：

```bash
export WW3TOOL_ROOT=/path/to/WW3Tool   # 指向 clone 的仓库根
ww3tool workdir my_workdir
```

不设置 `WW3TOOL_ROOT` 时，`workdir` 等需要模板的命令会报缺模板错误
（其余轻量命令正常）。仓库形态（源码里直接跑 `python3 run.py`）无需设置。

### 3. Homebrew

已发布 tap：`ZxyGch/homebrew-ww3tool`，直接使用：

```bash
brew tap ZxyGch/ww3tool && brew trust zxygch/ww3tool && brew install ww3tool
# 或一步到位（自动 tap，首次仍需 trust）：brew install ZxyGch/ww3tool
```

> Homebrew 6+ 对第三方 tap 默认不信任，首次使用需 `brew trust`（一次性）。

也可不发布直接本地装：`brew install ./Formula/ww3tool.rb`

formula 会把运行所需资源（meshgen / public / params.yml 模板）连同代码
一起装进 Cellar，命令链接到 `/opt/homebrew/bin/ww3tool`，**无需**
`WW3TOOL_ROOT`。巨型目录（`WW3/`、`WW3-6.07.1/`、`workSpace/`）不随包分发。

### 4. 已 clone 仓库的场景

```bash
./install.sh   # 把仓库内 ww3tool 软链到 PATH（可 --prefix 指定目录）
```

### 各方式对比

| 方式 | 命令 | 需 clone 仓库 | 资源(meshgen等) | WW3TOOL_ROOT |
| --- | --- | --- | --- | --- |
| curl \| bash | 一条命令 | 自动（~/.ww3tool） | 随仓库 | 不需要 |
| pip | 一条命令 | 需手动 clone | 不包含 | 需要 |
| brew | tap + trust + install | 自动（Cellar） | 随包 | 不需要 |
| install.sh | 一条命令 | 已 clone | 随仓库 | 不需要 |

> **通用要求**：Python 3.9+（curl/pip 方式使用系统 `python3`；brew 方式使用
> Homebrew 的 `python@3.12`）。首次运行会自动建 venv 装依赖，需几分钟与网络。

---

## 二、使用（CLI 命令）

```bash
ww3tool --help                          # 命令参考
ww3tool shell workdir/example           # 交互式 REPL
ww3tool workdir my_workdir              # 从模板创建工作目录
ww3tool run-workflow my_workdir         # 完整预处理
ww3tool validate my_workdir             # 校验配置
ww3tool local-run my_workdir            # 本地跑 WW3
ww3tool upload --confirm my_workdir     # 上传到远程
```

所有子命令与 `python3 run.py` 完全等价，从任何目录调用均可。

---

## 三、MCP server

把 CLI 子命令暴露为 MCP tools（工具名 `ww3tool_<子命令>`，如
`ww3tool_run_workflow`、`ww3tool_plot_wave_maps`）。工具与参数 schema
**运行时从 `build_parser()` 自动提取**，CLI 增加命令后 MCP 自动同步。
交互式命令 `ssh` 不通过 MCP 提供，仅 CLI 使用。

### 1. 初始化（新环境只需一次）

```bash
./mcp/setup.sh        # 创建 mcp/.venv（Python 3.12）并安装 mcp SDK
```

### 2. 通用 stdio 配置

任意支持 MCP 的客户端，注册一个 stdio server，`command` 指向
`launch.sh` 即可（内容见 `mcp/config.example.json`）：

```json
{
  "mcpServers": {
    "ww3tool": {
      "command": "/绝对路径/WW3Tool/mcp/launch.sh",
      "args": []
    }
  }
}
```

把 `/绝对路径/WW3Tool` 换成实际仓库路径。各客户端放置位置：

- **Claude Desktop**：`~/Library/Application Support/Claude/claude_desktop_config.json` 的 `mcpServers` 字段
- **Cursor**：项目根 `.cursor/mcp.json`（或用 `cursor mcp add` 命令添加）
- **VS Code / Copilot**、**Cherry Studio** 等：在各自的 MCP 设置里按同样格式添加

### 3. 工具清单（35 个）

- `list_commands`：列出全部命令及用途（帮助 LLM 选工具）
- `ww3tool_workdir / validate / config / print_params`：配置管理
- `ww3tool_prepare_forcing / generate_grid / prepare_ww3 / recommend_cfl /
  recommend_grid / run_workflow / local_run / merge_forcing`：预处理
- `ww3tool_plot_wave_maps / plot_spectrum / plot_jason3 / plot_jason3_swh /
  download_jason3 / plot_ndbc / download_ndbc`：后处理与绘图
- `ww3tool_connect_test / slurm_idle / confirm_slurm / upload /
  submit / check_status / queue_status / download_results / download_log /
  clear_remote / cancel_job / ntfy_watch / ntfy_watch_job / list_files`：远程运维
  （`ssh` 为交互式命令，仅 CLI 使用）

### 4. 使用约定（重要）

- **工作目录**：多数工具带 `workdir` 参数（含 `params.yml` 的目录）。
  建议总是显式传入；省略时使用 server 进程启动时的当前目录，结果不可预期。
- **退出码**：每个工具返回
  `[exit code N] --- stdout --- ... --- stderr --- ...`，
  LLM 应依据 `exit code` 判断成败（0 成功；1 运行异常；2 配置错误；
  3 破坏性操作缺 `--confirm`）。
- **破坏性操作**：`upload`、`clear_remote` 等工具保留了 CLI 的 `confirm`
  布尔参数，必须显式传 `True` 才会执行。
- **长任务**：`local_run`、`submit`、`download_results` 等可能运行很久。
  工具内建 1 小时超时（超时返回 exit code 124），客户端超时也请放宽
  （或改用 CLI 执行这类任务）。

### 5. 冒烟测试

```bash
mcp/.venv/bin/python mcp/tests/smoke_test.py
```

会真实走一遍 `initialize → tools/list → tools/call`（含创建一个临时
工作目录并执行 `ww3tool_config` / `ww3tool_validate`）。

---

## 四、发布清单（把"给其他人用"变成现实）

仓库已指向 https://github.com/ZxyGch/WW3Tool（默认分支 `master`），并已发布
`v0.1.0` tag；Homebrew tap（`ZxyGch/homebrew-ww3tool`）的 formula 已指向该 tag
并填入真实 `sha256`。**以后每次发版：**

1. **打 tag 并推送**（tag 是稳定锚点，日常 push 不影响已发布的 formula）：
   ```bash
   git tag v0.1.1 && git push origin v0.1.1
   curl -sL https://github.com/ZxyGch/WW3Tool/archive/refs/tags/v0.1.1.tar.gz | shasum -a 256
   ```
2. **更新 tap 仓库** `ZxyGch/homebrew-ww3tool` 的 `ww3tool.rb`：
   把 `url` 换成新 tag、`sha256` 换成新值，推送。
3. **可选**：发布到 PyPI（`pip install ww3tool`）。

---

## 五、常见问题

- **`ww3tool` 提示 command not found**：确认安装目录在 PATH 中，
  或手动 `export PATH="$HOME/.local/bin:$PATH"`。
- **pip 安装后 `workdir` 报缺模板**：设置 `export WW3TOOL_ROOT=/path/to/WW3Tool`。
- **MCP 客户端连不上**：先跑冒烟测试确认 server 正常；再检查配置里的
  `command` 是否为**绝对路径**且 `launch.sh` 有执行权限。
- **MCP 调用报 `Dependency check failed`**：项目 `.venv` 依赖不全，
  用 `python3 run.py --help` 触发一次自动安装即可。
- **`pip install .` 生成 build/、*.egg-info/**：构建产物，已加入 `.gitignore`。
