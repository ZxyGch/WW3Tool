# WW3Tool — AI 参考文档

本文档面向 AI Agent 与开发者，旨在清晰说明 WW3Tool 的整体逻辑、代码组织与工作流。不包含图片，纯文字描述。

---

## 1. 项目定位

WW3Tool 是围绕 **WAVEWATCH III**（海浪数值模式）构建的 **预处理与运行辅助工具**。它不替代 WW3 本身的可执行程序（`ww3_grid`、`ww3_prnc`、`ww3_shel` 等），而是负责：

- 强迫场文件的校验、修复与合并（纬度排序、变量重命名、时间轴修复）
- 网格生成（结构化矩形 / 三角形非结构化 / SMC 三种类型）
- 自动配置 WW3 所需的全套 namelist 文件（`ww3_grid.nml`、`ww3_prnc.nml`、`ww3_shel.nml`、`ww3_ounf.nml`、`ww3_multi.nml` 等）
- 生成 Slurm 提交脚本（`server.sh`）和本地运行脚本（`local.sh`）
- 通过 SSH 将工作目录上传到 HPC 服务器、提交 Slurm 作业、监控任务状态、下载结果
- 后处理绘图（波高填色图、方向谱、Jason-3 卫星验证、NDBC 浮标匹配等）

WW3Tool 几乎完全由 Python 组成（保留 gridgen 的原始 Matlab 代码），支持 Windows / Linux / macOS，UI 支持中英文双语。

---

## 2. 三种入口模式

`run.py` 是唯一入口，通过命令行参数区分三种模式：

```sh
python3 run.py                    # GUI（PyQt6 图形界面，默认）
python3 run.py shell              # 交互式终端（REPL，可反复执行各步骤）
python3 run.py <子命令> [workdir]  # 无界面 CLI（一条命令一个步骤，适合脚本与 AI 调用）
```

三种模式共享同一套业务逻辑（`src/workflows/application/`），差别仅在交互层。

### 2.1 无界面 CLI 的自动化适配

CLI 的"一条命令一个步骤、无需人工交互"特性天然适合 AI Agent 调用。每个子命令读取工作目录的 `params.yml` 后执行、打印日志到 stdout、通过退出码反馈成功/失败。主要子命令包括：

| 类别 | 子命令 | 说明 |
|------|--------|------|
| 配置管理 | `workdir <path>` | 创建或加载工作目录 |
| | `validate [workdir]` | 校验 params.yml |
| | `config [workdir]` | 打印配置摘要 |
| | `print-params [workdir]` | 输出 params.yml 原文 |
| 预处理 | `prepare-forcing [workdir]` | 准备强迫场（Step 1） |
| | `merge-forcing <in1.nc> [...] -o <out.nc>` | 独立工具：校验并合并强迫场 NetCDF |
| | `generate-grid [workdir]` | 生成网格（Step 2） |
| | `recommend-grid [--coarse\|--fine]` | 按区域范围推荐网格间距 |
| | `recommend-cfl` | 按 CFL 公式推荐时间步长 |
| | `prepare-ww3 [workdir]` | 仅生成 WW3 namelist |
| | `run-workflow [workdir]` | 完整预处理流程 |
| | `local-run [workdir]` | 执行 local.sh |
| 远程运维 | `connect-test` | 测试 SSH 连接 |
| | `ssh` | 打开交互式 SSH 终端 |
| | `slurm-idle` | 查看 Slurm 空闲 CPU |
| | `confirm-slurm [--full\|--half]` | 写 server.sh |
| | `upload --confirm` | 上传工作目录到远程 |
| | `submit` | 提交 server.sh |
| | `check-status` | 检查远程任务状态 |
| | `queue-status` | 查看 SLURM 队列 |
| | `download-results [--nested]` | 下载远程结果 |
| | `download-log` | 下载远程日志 |
| | `clear-remote --confirm` | 清空远程目录 |
| | `cancel-job <job_id>` | 取消 SLURM 任务 |
| | `ntfy-watch` | 注入常驻 ntfy 监听 |
| | `ntfy-watch-job <job_id>` | 为指定任务注入一次性 ntfy 监听 |
| 后处理 | `plot-wave-maps [--contour]` | 波高填色图 |
| | `plot-spectrum [--mode ...] [--station N]` | 方向谱图 |
| | `plot-jason3` / `plot-jason3-swh` / `download-jason3` | Jason-3 相关 |
| | `plot-ndbc [--download]` | NDBC 浮标匹配 |
| 辅助 | `print-example` | 输出示例 params.yml |

---

## 3. 项目结构

```
WW3Tool/
├── run.py                  # 唯一入口：依赖检查 → 语言切换 → 分发到 GUI / Shell / CLI
├── params.yml              # 算例参数模板（勿直接运行；用 workdir 创建副本后编辑）
├── public/                 # 全局资源
│   ├── languages/          #   zh_CN.json / en_US.json 翻译文件
│   ├── ww3/                #   WW3 namelist 模板（ww3_shel.nml, ww3_prnc.nml 等）
│   ├── scripts/            #   远程脚本（ww3_ntfy_watch.sh 等）
│   └── forcing/            #   示例强迫场文件（测试用）
├── meshgen/                # 网格生成器
│   ├── structured_generator/  # 结构化矩形网格（含 pygridgen）
│   ├── unst_generator/        # JIGSAW 非结构化网格
│   ├── smc_generator/         # SMC 网格
│   ├── reference_data/        # 水深/海岸线数据（GEBCO, ETOPO 等，约 6.5GB）
│   └── cache/                 # 网格缓存（按参数 hash 索引）
├── workSpace/              # 默认工作目录根；每个子文件夹是一个独立算例
└── src/
    ├── desktop/            # PyQt6 图形界面层
    │   ├── windows/        #   主窗口（preprocessing_window.py）、设置窗口
    │   ├── steps/          #   各步骤面板（ww3_panel, server_connect_panel 等）
    │   ├── view_models/    #   视图模型（remote.py, pipeline.py 等）
    │   └── components/     #   可复用 UI 组件
    └── workflows/          # 核心业务逻辑（DDD 风格分层）
        ├── interfaces/     #   入口适配器：command_line.py, interactive_cli.py, workdir_setup.py
        ├── application/    #   用例层：configuration.py, preprocessing_workflow.py, remote_ops.py, slurm_ops.py, forcing_merge.py 等
        ├── domain/         #   领域模型：config_models.py, forcing_fields.py, grid_spacing_recommendation.py 等
        ├── infrastructure/ #   基础设施：adapters/, forcing/, remote/, plot/, ww3/ 等
        └── support/        #   工具类：日志、异常等
```

GUI 模式和 Shell 模式最终都调用 `src/workflows/application/` 中的用例函数。

---

## 4. 配置系统：params.yml

`params.yml` 是描述一次算例全部参数的核心载体。根目录的 `params.yml` 只是模板；实际运行前须用 `workdir` 命令创建独立工作目录，再编辑该目录下的 `params.yml`。

### 4.1 段落结构

| 段落 | 内容 |
|------|------|
| `presets` | 可复用的命名列表：`output_scheme`（谱分区输出方案）、`server_st`（服务器 WW3 可执行文件路径）、`local_st`（本地 WW3 路径）、`structured_bathymetry` / `smc_bathymetry`（水深数据集）、`coastline_precision`（海岸线精度）、`file_split`（输出文件分割策略） |
| `paths` | 本地路径：MATLAB、GRIDGEN、WW3BIN、reference_data、JASON 数据等 |
| `forcing` | 强迫场源文件路径及处理方式（风/流/水位/海冰） |
| `grid` | 网格类型（structured / unstructured / smc）、经纬度范围、分辨率、嵌套设置 |
| `calc` | 计算模式（region / spectral_point / track） |
| `ww3` | 时间范围、计算/输出精度、输出方案、文件分割 |
| `ww3_grid` | 谱离散参数（XFR, FREQ1, NK, NTH）和时间步（DTMAX, DTXY, DTKTH, DTMIN） |
| `slurm` | SSH 连接信息、CPU 分区、核数、节点数、`server_st`（ST 版本） |
| `plot` | 绘图开关与参数（波高图、谱图、Jason-3、NDBC） |

### 4.2 配置加载流程

1. `configuration.py` 的 `load_pipeline_config(params_path, validation_stage)` 读取 YAML
2. 解析为 `PipelineConfig` 数据类（`config_models.py`），包含 `ForcingConfig`、`GridConfig`、`CalcConfig`、`WW3Config`、`SlurmConfig`、`PlotConfig` 等子结构
3. 根据 `validation_stage`（`forcing` / `grid` / `full` / `plot`）执行不同严格程度的校验
4. 交叉验证：例如 `slurm.server_st` 必须存在于 `presets.server_st` 中

### 4.3 GUI Override 机制

GUI 面板的值通过 `ww3_overrides()` 和 `slurm_overrides()` 方法返回字典，由 `pipeline.py` 合并写入 `params.yml` 对应段落，再重新加载配置。这保证了 GUI 编辑和 YAML 文件始终保持同步。

---

## 5. 端到端工作流

一次完整流程的典型链路：

```
强迫场 NetCDF
  → [Step 1 强迫场准备] 校验、修复、复制/移动到工作目录
  → [Step 2 网格生成] 调用 meshgen 生成网格文件
  → [Step 3 计算模式] 选择 region / spectral_point / track
  → [Step 4 WW3 配置] 生成全套 namelist 和脚本
  → [运行] 本地执行 local.sh 或 上传到服务器执行 server.sh / Slurm
  → WW3 模式输出 (ww3.YYYY.nc 等)
  → [后处理] 波高图、谱图、卫星/浮标验证
```

### 5.1 Step 1 — 强迫场准备

`application/forcing_preparation.py` + `infrastructure/forcing/`

- 扫描用户选择的 NetCDF 文件
- 检测并修复纬度方向（ERA5 默认递减 → 自动翻转为递增）
- 自动重命名变量（CFSR 的 `wndewd`/`wndnwd` → `u10`/`v10`）
- 修复 Copernicus 数据的时间标签
- 复制到工作目录并统一命名：`wind.nc`、`current.nc`、`level.nc`、`ice.nc`
- 如果一个文件包含多种强迫场，命名为 `current_level.nc` 等

独立工具 `merge-forcing` 可脱离工作目录，直接校验并合并多个强迫场 NetCDF（按时间拼接 + 变量合并），支持 `--time-range` 和 `--bbox` 裁剪。

### 5.2 Step 2 — 网格生成

`application/grid_preparation.py` + `meshgen/`

三种网格类型：

**结构化矩形网格**（`structured_generator/`）
- 调用 `pygridgen` 生成 `grid.bot`（水深）、`grid.obst`（障碍物）、`grid.mask_nobound`（陆海掩膜）、`grid.meta`（网格描述）
- 支持最多两层嵌套网格（coarse 外网格 + fine 内网格），使用 Two-way nesting，收缩系数默认 1.1x
- 嵌套模式下在工作目录创建 `coarse/` 和 `fine/` 子目录

**三角形非结构化网格**（`unst_generator/`）
- 基于 JIGSAW 生成，支持深水尺度、近岸尺度、浅水波长加密、水深梯度等参数

**SMC 网格**（`smc_generator/`）
- 基于 SMCGTools 生成

所有网格生成结果自动缓存到 `meshgen/cache/`，以参数 hash 为 key，避免重复计算。

工具 `recommend-grid [--coarse|--fine]` 可根据经纬度范围和网格类型自动推荐网格间距。

### 5.3 Step 3 — 计算模式

`domain/config_models.py` 中 `CalcConfig.mode` 字段：

- `region`：标准区域计算，输出 `ww3.YYYY.nc`（通过 `ww3_ounf`）
- `spectral_point`：在工作目录生成 `points.list`（经度 纬度 点名称），输出 `ww3.YYYY_spec.nc`（通过 `ww3_ounp`），同时开启 `namelists.nml` 中的 `E3D=1`
- `track`：生成 `track_i.ww3`（含时间列），输出 `ww3.YYYY_trck.nc`（通过 `ww3_trnc`）

打开工作目录时，程序会自动检测 `points.list` 或 `track_i.ww3` 并切换对应模式。

### 5.4 Step 4 — WW3 配置（namelist 与脚本生成）

`infrastructure/adapters/ww3_namelist_adapter.py` + `infrastructure/ww3/`

这是最核心的步骤，执行顺序：

1. 从 `public/ww3/` 复制模板文件到工作目录
2. 同步 `grid.meta` 中的网格参数到 `ww3_grid.nml`
3. 根据 `presets.output_scheme` 修改 `ww3_shel.nml` 和 `ww3_ounf.nml` 的谱分区输出
4. 更新 `server.sh`：Slurm 作业名、CPU 分区、核数、节点数、ST 路径
5. 设置 `ww3_ounf.nml` 的输出时间和间隔
6. 设置 `ww3_shel.nml` 的计算域起止时间和时间步长
7. 修改 `ww3_prnc.nml` 的强迫场时间范围
8. 为每种非风强迫场生成独立的 `ww3_prnc_*.nml`（每个只能启用一个 `FORCING%FIELD%`）
9. 更新 `ww3_shel.nml` 的 `INPUT%FORCING%*` 开关
10. 航迹模式下生成 `track_i.ww3`，添加 `DATE%TRACK`
11. 谱点模式下修改 `namelists.nml` 的 `E3D`，生成 `points.list`
12. 嵌套网格模式额外生成 `ww3_multi.nml`，处理内外网格的资源分配

嵌套网格的特殊处理：
- 使用 `ww3_multi.nml` 替代 `ww3_shel.nml` 作为主控
- 内外网格分别处理，各自生成独立的 namelist
- 强迫场文件使用 `../wind.nc` 引用共享，避免双倍存储

### 5.5 运行

**本地运行**：执行工作目录下的 `local.sh`，调用本地安装的 WW3 可执行文件。

**服务器运行**：
1. 通过 SSH（`paramiko`）连接远程 HPC
2. 上传工作目录到服务器指定路径
3. 在登录节点执行 `server.sh`（通过 `sbatch` 提交 Slurm 作业）
4. 服务器端生成 `success.log`（成功）、`fail.log`（失败）或 `run.log`（运行中）
5. 通过 `check-status` 检测完成状态，`download-results` 下载结果

### 5.6 ntfy 通知系统

通过 `ntfy.sh` 服务实现 Slurm 作业完成通知：

- **全局监听**（`ntfy-watch`）：在登录节点注入常驻 bash 脚本 `ww3_ntfy_watch.sh`，通过 `nohup`/`disown` 后台运行，定期扫描 `squeue`/`sacct`，当任何作业完成时发送 ntfy 通知。Topic 由用户名+工作目录名+SHA1 摘要生成（如 `zxy-myproject-a1b2c3d4e5`）。
- **单任务监听**（`ntfy-watch-job <job_id>`）：注入一次性监听，监控指定作业。使用独立 topic（基础 topic + `-job-{job_id}` 后缀），避免与全局监听混在同一频道。
- GUI 中的"常驻 ntfy 监听"按钮具备智能判断：检查远端是否已有监听进程在运行，没有则注入，有则发送测试通知。

---

## 6. 代码架构

采用类 DDD（领域驱动设计）分层：

### interfaces/ — 入口适配器

- `command_line.py`：非交互 CLI，argparse 解析子命令 → 加载配置 → 调用 application 层用例
- `interactive_cli.py`：交互式 REPL（cmd.Cmd），支持 Tab 补全、历史翻阅、分组帮助
- `workdir_setup.py`：工作目录创建/加载逻辑

### application/ — 用例层（Use Cases）

无框架依赖的纯业务逻辑，接收配置对象，返回结果对象：

- `configuration.py`：YAML 解析 → `PipelineConfig`，含校验与交叉验证
- `preprocessing_workflow.py`：编排 Step 1~4 的完整流程
- `forcing_preparation.py` / `forcing_merge.py`：强迫场处理
- `grid_preparation.py`：网格生成调度
- `remote_ops.py`：SSH 远程操作（上传、提交、下载、ntfy 注入等）
- `slurm_ops.py`：Slurm 资源查询与确认
- `local_run.py`：本地运行
- `plot_wave_maps.py` / `plot_spectrum.py` / `match_jason3.py` / `match_ndbc.py`：后处理绘图与验证

### domain/ — 领域模型

- `config_models.py`：`PipelineConfig` 及各子结构的数据类定义
- `forcing_fields.py`：强迫场变量映射与元数据
- `grid_spacing_recommendation.py`：网格间距推荐算法（按区域跨度匹配档位）
- `timestep_recommendation.py`：CFL 时间步推荐
- `parameter_catalog.py`：参数目录

### infrastructure/ — 基础设施

- `adapters/ww3_namelist_adapter.py`：WW3 namelist 生成与修改的核心逻辑
- `forcing/`：强迫场文件服务（NetCDF 读写、变量修复、文件扫描）
- `remote/ssh_client.py`：paramiko SSH 封装（`exec_command`、`upload_matching_files`）
- `plot/`：matplotlib 绘图实现
- `ww3/`：server.sh / local.sh 脚本生成
- `runtime_config.py`：运行时全局状态（语言、路径等）

### desktop/ — PyQt6 图形界面

- `windows/preprocessing_window.py`：主窗口（约 2400 行），编排各步骤面板
- `steps/`：各步骤的 UI 面板（`ww3_panel.py`、`server_connect_panel.py` 等）
- `view_models/`：视图模型，作为 UI 与 application 层之间的桥接
  - `remote.py`：封装远程操作的异步调用
  - `pipeline.py`：配置加载/保存、GUI override 合并

---

## 7. 工作目录结构

一个典型工作目录（如 `workSpace/my_case/`）包含：

```
my_case/
├── params.yml              # 该算例的参数配置
├── wind.nc                 # 风场（Step 1 产生）
├── current.nc              # 流场（如有）
├── level.nc                # 水位场（如有）
├── ice.nc                  # 海冰场（如有）
├── grid.bot                # 网格水深（Step 2 产生）
├── grid.obst               # 网格障碍物
├── grid.mask_nobound       # 陆海掩膜
├── grid.meta               # 网格描述（实为 ww3_grid.nml 的子集）
├── ww3_grid.nml            # WW3 网格 namelist（Step 4 产生）
├── ww3_prnc.nml            # 强迫场预处理 namelist
├── ww3_prnc_current.nml    # 流场强迫场 namelist（如有）
├── ww3_prnc_level.nml      # 水位场 namelist（如有）
├── ww3_shel.nml            # WW3 主运行 namelist
├── ww3_ounf.nml            # 场输出 namelist
├── ww3_ounp.nml            # 谱点输出 namelist（如有）
├── ww3_trnc.nml            # 航迹输出 namelist（如有）
├── ww3_multi.nml           # 嵌套网格主控 namelist（如有）
├── namelists.nml           # 嵌套网格辅助配置（如有）
├── server.sh               # Slurm 提交脚本
├── local.sh                # 本地运行脚本
├── points.list             # 谱点坐标列表（如有）
├── track_i.ww3             # 航迹坐标列表（如有）
├── coarse/                 # 外网格文件（嵌套模式）
└── fine/                   # 内网格文件（嵌套模式）
```

打开工作目录时，程序自动扫描已有文件来恢复状态：检测强迫场文件名自动填充、检测 `coarse`/`fine` 切换嵌套模式、检测 `points.list` 或 `track_i.ww3` 切换计算模式、从 `server.sh` 读取 Slurm 参数等。

---

## 8. 翻译系统

所有用户可见文本使用 `tr(key, default)` 函数：

- `key`：翻译键（如 `"icli_help_merge_forcing"`）
- `default`：默认文本（通常为英文）

运行时根据 `--lang` 参数（默认 `zh_CN`）从 `public/languages/zh_CN.json` 或 `en_US.json` 查找对应翻译。若键不存在则返回 default。

翻译文件约 2300+ 行，覆盖 GUI 标签、CLI 帮助、日志消息、错误提示等。

---

## 9. 远程操作

`application/remote_ops.py` 封装了所有通过 SSH 与远程 HPC 交互的用例：

- 使用 `paramiko` 作为 SSH 客户端（`infrastructure/remote/ssh_client.py`）
- `exec_command` 使用 `get_pty=True` 以获取完整 shell 环境
- 文件上传通过 `upload_matching_files` 实现，自动处理 Windows `\r\n` → Unix `\n` 转换
- 远程脚本（如 `ww3_ntfy_watch.sh`）通过 `nohup ... & echo $! > pid_file; disown` 模式启动后台进程，避免 SSH 断开时收到 SIGHUP

ntfy 监听脚本 `ww3_ntfy_watch.sh`（约 350 行）的关键机制：
- 通过 `squeue` + `sacct` 监控 Slurm 作业状态变化
- 使用 `curl` 发送 ntfy.sh 通知，含重试与超时
- 维护状态目录 `.ntfy_watch_state_{mode}/` 记录已知作业状态
- 对已完成但首次发现的作业（UNKNOWN_DONE），设置宽限期避免误报

---

## 10. 关键设计模式

**配置驱动**：所有行为由 `params.yml` 驱动，GUI 编辑通过 override 机制写回 YAML，CLI 直接读取 YAML。

**Override 合并**：GUI 面板的 `ww3_overrides()` / `slurm_overrides()` 返回字典，由 pipeline 合并到 YAML 对应段落后保存，再重新加载整个配置。这避免了部分更新导致的状态不一致。

**缓存机制**：网格生成结果按参数 hash 缓存，相同参数的重复生成直接使用缓存。

**向后兼容**：配置解析保留对旧字段名的兼容（如 `ww3.st` 作为 `slurm.server_st` 的 fallback），避免升级时破坏已有配置。

**分层解耦**：interfaces → application → domain ← infrastructure，业务逻辑不依赖具体框架，GUI 和 CLI 仅是不同的入口适配器。
