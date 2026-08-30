# WW3Tool

**WAVEWATCH III workflow toolkit** · **WAVEWATCH III 工作流工具包**

A pure-Python preprocessing & run-assist toolkit around WAVEWATCH III (third-generation ocean wave model). Works on Windows / Linux / macOS. Provides CLI / interactive Shell / Desktop GUI / MCP server. Bilingual UI (Chinese / English).

---

## English

### What it does

WW3Tool does **not** replace the WW3 executables (`ww3_grid`, `ww3_prnc`, `ww3_shel`, ...). It automates and chains them:

- **Forcing preprocessing**: validate / fix / merge wind & current NetCDF forcing files (latitude sorting, variable renaming, time-axis repair).
- **Mesh generation**: structured rectilinear meshes (arbitrary-depth two-way nesting), unstructured triangular meshes, and SMC meshes.
- **Automatic namelists**: generate the full WW3 namelist set for v6.07.1 and v7.14 (`ww3_grid.nml`, `ww3_prnc.nml`, `ww3_shel.nml`, `ww3_ounf.nml`, `ww3_multi.nml`, ...).
- **Run scripts**: generate scripts that correctly invoke `ww3_grid` / `ww3_prnc` / `ww3_shel`.
- **HPC integration**: SSH upload of the workdir to clusters, Slurm configuration, job submission / monitoring / result download.
- **Post-processing**: wave-height maps, directional spectra, Jason-3 satellite validation, NDBC buoy matching.

### Install

One command on every platform (macOS / Linux / Windows):

```bash
pip install ww3tool            # CLI + shell
pip install "ww3tool[gui]"     # …plus the desktop GUI
```

The GUI dependencies are optional so that a plain install works on machines
that have no Qt wheels — an HPC compute node, for instance, where only the CLI
is wanted. Running `ww3tool --gui` installs them on demand when a display is
available.

Requires Python 3.9+. The `ww3tool` command is ready right after install.

### Quick start

```bash
ww3tool --help              # list all commands
ww3tool workdir my_run      # create a workdir from the built-in template
ww3tool config              # view / edit the configuration
ww3tool print-params        # print the current params.yml
```

> ### ⚠️ You MUST configure `params.yml` first
>
> `workdir` creates `params.yml` from the built-in template. **Edit it before running anything**: set the wind/current forcing paths, mesh region and resolution, time steps, and output settings — then run the corresponding subcommand to generate the mesh, namelists, and run scripts. WW3Tool cannot know your case until `params.yml` is configured.

### Desktop GUI

```bash
ww3tool --gui    # launch the desktop GUI (installs its deps on demand)
ww3tool          # no argument prints the help
```

### Calling it from an AI agent or a script

All 37 subcommands speak JSON. With `--json`, stdout carries exactly one
object, so nothing has to be parsed out of prose:

```bash
ww3tool --json generate-grid /path/to/workdir
```

```json
{
  "command": "generate-grid", "status": "ok", "exit_code": 0, "seconds": 618.8,
  "data": {"dx": 0.5, "dy": 0.5, "grid": {"nx": "720", "closure": "SMPL"}},
  "outputs": ["…/grid.bot", "…/grid.mask_nobound", "…/grid.obst"],
  "messages": ["… the human-readable log, kept as lines …"]
}
```

- `status` / `exit_code` / `outputs` are always there — no grepping to find out
  whether a run worked or where its files went.
- Failures put the reason **and the next step** in the object:
  `{"error": {"message": "…", "hints": ["run `ww3tool schema --json` …"]}}`
- `ww3tool --json schema` describes every `params.yml` field: path, type, valid
  values, defaults, and notes where the layout is not obvious.
- `ww3tool --json validate --stage grid` checks only what that step needs, so a
  mistake is caught in a second rather than after a ten-minute run.

- `--progress stderr` (or a file path) streams NDJSON events while a long run
  is in flight — one object per line, so a ten-minute grid can be followed
  instead of waited out. stdout still carries only the final object.

Without `--json` the output is unchanged.

### Interactive shell

```bash
ww3tool shell
```

Tab completion and history; shares the same configuration as the GUI.

### MCP server (for AI clients)

The repo ships an MCP server (34 `ww3tool_*` tools + `list_commands`, stdio transport) for Claude / Cursor and other AI clients. See `public/packaging/mcp/` in the GitHub repo.

### Links

- GitHub (full docs, mesh generators, examples): https://github.com/ZxyGch/WW3Tool
- Packaging / MCP details: `public/packaging/PACKAGING.md` in the repo

---

## 中文

### 这是什么

WW3Tool **不替代** WW3 可执行文件（`ww3_grid`、`ww3_prnc`、`ww3_shel` 等），而是把这些流程串起来、自动化：

- **强迫场预处理**：风场 / 流场 NetCDF 强迫文件的校验、修复与合并（纬度排序、变量重命名、时间轴修正）。
- **网格生成**：结构化矩形网格（任意深度双向嵌套）、非结构化三角网格、SMC 网格。
- **自动配置**：为 v6.07.1 与 v7.14 生成 WW3 全套 namelist（`ww3_grid.nml`、`ww3_prnc.nml`、`ww3_shel.nml`、`ww3_ounf.nml`、`ww3_multi.nml` 等）。
- **运行脚本**：自动生成正确调用 `ww3_grid` / `ww3_prnc` / `ww3_shel` 的脚本。
- **HPC 对接**：SSH 上传工作目录到超算、配置 Slurm、提交作业、监控状态、下载结果。
- **后处理绘图**：波高填色图、方向谱、Jason-3 卫星验证、NDBC 浮标匹配。

### 安装

一条指令，所有平台相同（macOS / Linux / Windows）：

```bash
pip install ww3tool            # 命令行 + 交互式 shell
pip install "ww3tool[gui]"     # 额外装上桌面图形界面
```

GUI 依赖单列为可选项，这样在拿不到 Qt wheel 的机器上（例如只需要命令行的
HPC 计算节点）也能正常安装。有图形环境时运行 `ww3tool --gui` 会按需补装。

要求 Python 3.9+，安装后 `ww3tool` 命令直接可用。

### 快速开始

```bash
ww3tool --help              # 查看全部命令
ww3tool workdir my_run      # 从内置模板创建工作目录并进入
ww3tool config              # 查看 / 修改配置
ww3tool print-params        # 打印当前参数
```

> ### ⚠️ 必须配置 `params.yml`
>
> `workdir` 会从内置模板生成 `params.yml`。**运行前必须编辑它**：配置风场 / 流场路径、网格区域与分辨率、时间步长、输出设置，再执行对应子命令生成网格、namelist 与运行脚本。不配置 `params.yml`，工具无法知道你的算例是什么。

### 桌面图形界面（GUI）

```bash
ww3tool --gui    # 启动桌面端（依赖按需补装）
ww3tool          # 无参数显示帮助
```

### 用 AI 或脚本调用

37 条子命令全部支持 JSON。加 `--json` 后 stdout 上只有一个对象，不需要从
散文里往外抠：

```bash
ww3tool --json generate-grid /path/to/workdir
```

```json
{
  "command": "generate-grid", "status": "ok", "exit_code": 0, "seconds": 618.8,
  "data": {"dx": 0.5, "dy": 0.5, "grid": {"nx": "720", "closure": "SMPL"}},
  "outputs": ["…/grid.bot", "…/grid.mask_nobound", "…/grid.obst"],
  "messages": ["… 原本给人看的日志，按行保留 …"]
}
```

- `status` / `exit_code` / `outputs`一定存在——不必再 grep 关键词判断成败或
  猜产出在哪。
- 失败时把原因**和下一步**一起放进对象：
  `{"error": {"message": "…", "hints": ["run `ww3tool schema --json` …"]}}`
- `ww3tool --json schema` 描述 `params.yml` 每个字段：路径、类型、合法值、
  默认值，结构不直观的还有附注。
- `ww3tool --json validate --stage grid` 只校验该步需要的部分，配错一秒就
  发现，不用等十分钟的网格跑完。

- `--progress stderr`（或给个文件路径）在长任务运行期间逐行输出 NDJSON 事件，
  每行一个独立对象——十几分钟的网格可以边跑边看，不必干等。stdout 上仍然只有
  最终那个对象。

不加 `--json` 时输出与以往完全一致。

### 交互式命令行（shell）

```bash
ww3tool shell
```

支持 Tab 补全与历史记录，与 GUI 共用同一套配置。

### MCP server（供 AI 客户端调用）

仓库提供 MCP server（34 个 `ww3tool_*` 工具 + `list_commands`，stdio 传输），可直接接入 Claude / Cursor 等 AI 客户端。配置方法见 GitHub 仓库 `public/packaging/mcp/` 目录。

### 相关链接

- GitHub 仓库（完整文档、网格生成器源码、示例）：https://github.com/ZxyGch/WW3Tool
- 安装 / 发布 / MCP 详细说明：仓库内 `public/packaging/PACKAGING.md`
