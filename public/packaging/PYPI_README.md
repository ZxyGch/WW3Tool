# WW3Tool

**WAVEWATCH III workflow toolkit** · **WAVEWATCH III 工作流工具包**

A pure-Python preprocessing & run-assist toolkit around WAVEWATCH III
(third-generation ocean wave model). Works on Windows / Linux / macOS with
CLI / interactive Shell / Desktop GUI / MCP server, bilingual UI (zh / en).

围绕 WAVEWATCH III（第三代海浪数值模式）的预处理与运行辅助工具。
纯 Python 编写，支持 Windows / Linux / macOS，提供 CLI / 交互式 Shell /
桌面 GUI / MCP server 四种使用方式，界面中英双语。

## What it does · 这是什么

WW3Tool does **not** replace the WW3 executables (`ww3_grid`, `ww3_prnc`,
`ww3_shel`, ...); it automates and chains them:

WW3Tool **不替代** WW3 可执行文件（`ww3_grid`、`ww3_prnc`、`ww3_shel` 等），
而是把这些流程串起来、自动化：

- **Forcing preprocessing 强迫场预处理**: validate / fix / merge wind NetCDF
  (latitude sorting, variable renaming, time-axis repair) · 风场 NetCDF 的校验 / 修复 / 合并（纬度排序、变量重命名、时间轴修正）
- **Mesh generation 网格生成**: structured rectilinear (arbitrary-depth
  two-way nesting) / unstructured triangular / SMC meshes ·
  结构化矩形网格（任意深度双向嵌套）/ 非结构化三角网格 / SMC 网格
- **Automatic namelists 自动配置**: full WW3 namelist set for v6.07.1 &
  v7.14 (`ww3_grid.nml`, `ww3_prnc.nml`, `ww3_shel.nml`, `ww3_ounf.nml`, `ww3_multi.nml`, ...) · 生成 WW3 全套 namelist
- **Run scripts 运行脚本**: correct invocations of `ww3_grid` / `ww3_prnc` /
  `ww3_shel` · 自动生成正确调用 WW3 程序的脚本
- **HPC integration HPC 对接**: SSH upload to clusters, Slurm config, job
  submit / monitor / download · SSH 上传工作目录到超算、配置 Slurm、提交作业、监控状态、下载结果
- **Post-processing 后处理绘图**: wave-height maps, directional spectra,
  Jason-3 satellite validation, NDBC buoy matching · 波高填色图、方向谱、Jason-3 卫星验证、NDBC 浮标匹配

## Install · 安装

One command on every platform (macOS / Linux / Windows) — GUI included,
no extra extra to install:

一条指令，所有平台相同（macOS / Linux / Windows），GUI 依赖已内置，
无需额外安装：

```bash
pip install ww3tool
```

> Requires Python 3.9+. The `ww3tool` command is ready right after install.
>
> 要求 Python 3.9+，安装后 `ww3tool` 命令直接可用。

## Quick start · 快速开始

```bash
ww3tool --help              # list all commands · 查看全部命令
ww3tool workdir my_run      # create a workdir from the built-in template · 从内置模板创建工作目录并进入
ww3tool config              # view / edit the configuration · 查看 / 修改配置
ww3tool print-params        # print the current params.yml · 打印当前参数
```

### ⚠️ You MUST configure `params.yml` first · ⚠️ 必须配置 `params.yml`

`workdir` creates `params.yml` from the built-in template. **Edit it before
running anything**: set the wind/current forcing paths, mesh region and
resolution, time steps, and output settings — then run the corresponding
subcommand to generate the mesh, namelists, and run scripts. WW3Tool will not
know your case until `params.yml` is configured.

`workdir` 会从内置模板生成 `params.yml`。**运行前必须编辑它**：配置风场 /
流场路径、网格区域与分辨率、时间步长、输出设置，再执行对应子命令生成网格、
namelist 与运行脚本。不配置 `params.yml`，工具无法知道你的算例是什么。

## Desktop GUI · 桌面图形界面

```bash
ww3tool          # no argument launches the desktop GUI · 无参数默认启动桌面
```

## Interactive shell · 交互式命令行

```bash
ww3tool shell
```

Tab completion and history; shares the same configuration as the GUI.
支持 Tab 补全与历史记录，与 GUI 共用同一套配置。

## MCP server（for AI clients · 供 AI 客户端调用）

The repo ships an MCP server (34 `ww3tool_*` tools + `list_commands`, stdio)
for Claude / Cursor etc. See `public/packaging/mcp/` in the GitHub repo.

仓库提供 MCP server（34 个 `ww3tool_*` 工具 + `list_commands`，stdio 传输），
可直接接入 Claude / Cursor 等 AI 客户端。配置方法见 GitHub 仓库
`public/packaging/mcp/` 目录。

## Links · 相关链接

- GitHub (full docs, mesh generators, examples · 完整文档、网格生成器源码、示例): https://github.com/ZxyGch/WW3Tool
- Packaging / MCP details · 安装 / 发布 / MCP 详细说明: `public/packaging/PACKAGING.md` in the repo
