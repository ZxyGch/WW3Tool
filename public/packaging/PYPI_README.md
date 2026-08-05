# WW3Tool

**WAVEWATCH III 工作流工具包** —— 围绕 WAVEWATCH III（第三代海浪数值模式）的
预处理与运行辅助工具。纯 Python 编写，支持 Windows / Linux / macOS，
提供 CLI / 交互式 Shell / 桌面 GUI / MCP server 四种使用方式，界面中英双语。

## 这是什么

WW3Tool **不替代** WW3 可执行文件（`ww3_grid`、`ww3_prnc`、`ww3_shel` 等），
而是把这些流程串起来、自动化：

- **强迫场预处理**：风场 NetCDF 文件的校验 / 修复 / 合并（纬度排序、变量重命名、时间轴修正）
- **网格生成**：结构化矩形网格（任意深度双向嵌套）/ 非结构化三角网格 / SMC 网格
- **自动配置**：生成 WW3 全套 namelist（`ww3_grid.nml`、`ww3_prnc.nml`、`ww3_shel.nml`、
  `ww3_ounf.nml`、`ww3_multi.nml` 等），支持 v6.07.1 与 v7.14
- **运行脚本**：自动生成正确调用 `ww3_grid` / `ww3_prnc` / `ww3_shel` 的脚本
- **HPC 对接**：SSH 上传工作目录到超算、配置 Slurm、提交作业、监控状态、下载结果
- **后处理绘图**：波高填色图、方向谱、Jason-3 卫星验证、NDBC 浮标匹配

## 安装

一条指令，所有平台相同（macOS / Linux / Windows）：

```bash
pip install ww3tool
```

需要桌面图形界面（GUI）：

```bash
pip install "ww3tool[gui]"
```

> 要求：Python 3.9+。安装后 `ww3tool` 命令直接可用，无需额外配置。

## 快速开始

```bash
ww3tool --help              # 查看全部命令
ww3tool workdir my_run      # 从内置模板创建工作目录并进入
ww3tool config              # 查看 / 修改配置（风场路径、网格参数等）
ww3tool print-params        # 打印当前工作目录的参数
```

`workdir` 会从内置模板生成 `params.yml`；编辑该文件配置风场 / 网格 / 计算参数后，
再执行对应子命令生成网格、namelist 与运行脚本。

## 桌面图形界面（GUI）

```bash
ww3tool          # 无参数默认启动桌面（需先安装 GUI 扩展）
# 或显式：ww3tool desktop
```

## 交互式命令行（shell）

```bash
ww3tool shell
```

支持 Tab 补全与历史记录，与 GUI 共用同一套配置。

## MCP server（供 AI 客户端调用）

仓库提供 MCP server（34 个 `ww3tool_*` 工具 + `list_commands`，stdio 传输），
可直接接入 Claude / Cursor 等 AI 客户端。配置方法见 GitHub 仓库
`public/packaging/mcp/` 目录下的说明与示例配置。

## 相关链接

- GitHub 仓库（完整文档、网格生成器源码、示例）：https://github.com/ZxyGch/WW3Tool
- 安装 / 发布 / MCP 详细说明：仓库内 `public/packaging/PACKAGING.md`
