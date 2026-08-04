# WW3Tool 封装指南

把 WW3Tool 封装成两种形态，让日常使用和 AI 客户端调用都像 `mysql` / `git`
一样简单：

| 形态 | 入口 | 适合谁 |
| --- | --- | --- |
| CLI 全局命令 | `ww3tool`（安装后任意目录可用） | 人（终端）与脚本 |
| MCP server | 36 个 `ww3tool_*` tools（stdio） | Claude / Cursor 等 AI 客户端 |

两种形态都复用仓库根的 `run.py` 统一入口，venv 引导、依赖检查、语言切换
完全一致，**不需要改动任何现有代码**。

---

## 一、CLI 全局命令（类似 `mysql xxx`）

### 安装

```bash
cd WW3Tool
./install.sh            # 自动探测：~/.local/bin（在 PATH 中时）→ /usr/local/bin
./install.sh --prefix /usr/local/bin   # 或指定目录（该目录需要 sudo 时加 sudo）
```

> `install.sh` 只是把仓库内的 `ww3tool` 脚本软链到 PATH 目录，不改动仓库、
> 不复制文件。卸载：`./install.sh --uninstall`。

### 使用

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

### 给其他人用

同事拿到仓库后（git clone 或拷贝）只需：

```bash
./install.sh          # 获得全局 ww3tool 命令
```

`run.py` 首次运行会自动创建/复用项目 `.venv` 并安装依赖。

---

## 二、MCP server

把 CLI 子命令暴露为 MCP tools（工具名 `ww3tool_<子命令>`，
如 `ww3tool_run_workflow`、`ww3tool_plot_wave_maps`）。工具与参数 schema
**运行时从 `build_parser()` 自动提取**，CLI 增加命令后 MCP 自动同步，无重复维护。
交互式命令 `ssh`（打开 SSH 终端）不通过 MCP 提供，仅 CLI 使用。

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

## 三、常见问题

- **`ww3tool` 提示 command not found**：确认 `install.sh` 的安装目录在 PATH 中，
  或手动 `export PATH="$HOME/.local/bin:$PATH"`。
- **MCP 客户端连不上**：先跑冒烟测试确认 server 正常；再检查配置里的
  `command` 是否为**绝对路径**且 `launch.sh` 有执行权限。
- **MCP 调用报 `Dependency check failed`**：项目 `.venv` 依赖不全，
  用 `python3 run.py --help` 触发一次自动安装即可。
