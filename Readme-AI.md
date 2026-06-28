# WW3Tool  文档

## 1. 项目定位

![](public/resource/README-media/截屏2026-06-18%2011.02.07.png)

WW3Tool 是围绕 **WAVEWATCH III**（海浪数值模式）构建的 **预处理与运行辅助工具**。它不替代 WW3 本身的可执行程序（ww3_grid、ww3_prnc、ww3_shel 等），而是负责：

- 强迫场文件的校验、修复与合并（纬度排序、变量重命名、时间轴修复）
- 网格生成（结构化矩形 / 三角形非结构化 / SMC 三种类型）
- 自动配置 WW3 所需的全套 namelist 文件（ww3_grid.nml、ww3_prnc.nml、ww3_shel.nml、ww3_ounf.nml、ww3_multi.nml 等）
- 生成 Slurm 提交脚本（server.sh）和本地运行脚本（local.sh）
- 通过 SSH 将工作目录上传到 HPC 服务器、提交 Slurm 作业、监控任务状态、下载结果
- 后处理绘图（波高填色图、方向谱、Jason-3 卫星验证、NDBC 浮标匹配等）

WW3Tool 完全由 Python 组成（其他语言的代码是网格生成器 meshgen 的代码），支持 Windows / Linux / macOS，UI 支持中英文双语。



## 2. 快速开始

run.py 是唯一入口，通过命令行参数区分三种模式：

```sh
python3 run.py                    # GUI（图形界面）
python3 run.py shell              # 交互式终端（REPL，可反复执行各步骤）
python3 run.py <子命令> [workdir]  # 无界面 CLI（一条命令一个步骤，适合脚本与 AI 调用）
```

三种模式共享同一套业务逻辑（src/workflows/application/），差别仅在交互层。


### 2.1 GUI 

![](public/resource/README-media/截屏2026-06-18%2011.02.07.png)

```bash
python3 run.py  
```



### 2.2 交互式终端

```sh
python3 run.py shell              # 交互式终端
```

![](public/resource/README-media/截屏2026-06-18%2011.07.11.png)




### 2.3 无界面 CLI 

```sh
python3 run.py <子命令> [workdir]  # 无界面 CLI（一条命令一个步骤，适合脚本与 AI 调用）
```

CLI 的"一条命令一个步骤、无需人工交互"特性天然适合 AI Agent 调用，命令包括：

| 类别   | 子命令                                                             | 说明                   |
| ---- | --------------------------------------------------------------- | -------------------- |
| 配置管理 | workdir <path>                                                | 创建或加载工作目录            |
|      | validate [workdir]                                            | 校验 params.yml        |
|      | config [workdir]                                              | 打印配置摘要               |
|      | print-params [workdir]                                        | 输出 params.yml 原文     |
| 预处理  | prepare-forcing [workdir]                                     | 准备强迫场（Step 1）        |
|      | merge-forcing <in1.nc> [...] -o <out.nc>                      | 独立工具：校验并合并强迫场 NetCDF |
|      | generate-grid [workdir]                                       | 生成网格（Step 2）         |
|      | recommend-grid [workdir] [--coarse\|--fine]                   | 按区域范围推荐网格间距          |
|      | recommend-cfl [workdir] [--mode safe\|fast\|faster] [--factor X] | 按 CFL 公式推荐时间步长       |
|      | prepare-ww3 [workdir]                                         | 仅生成 WW3 namelist     |
|      | run-workflow [workdir]                                        | 完整预处理流程              |
|      | local-run [workdir]                                           | 执行 local.sh          |
| 远程运维 | connect-test [workdir]                                        | 测试 SSH 连接            |
|      | ssh [workdir]                                                 | 打开交互式 SSH 终端         |
|      | slurm-idle [workdir]                                          | 查看 Slurm 空闲 CPU      |
|      | confirm-slurm [workdir]                                       | 写 server.sh          |
|      | upload [workdir] --confirm                                    | 上传工作目录到远程            |
|      | submit [workdir]                                              | 提交 server.sh         |
|      | check-status [workdir]                                        | 检查远程任务状态             |
|      | queue-status [workdir]                                        | 查看 SLURM 队列          |
|      | download-results [workdir] [--nested]                         | 下载远程结果               |
|      | download-log [workdir]                                        | 下载远程日志               |
|      | clear-remote [workdir] --confirm                              | 清空远程目录               |
|      | cancel-job [workdir] <job_id>                                 | 取消 SLURM 任务          |
|      | ntfy-watch [workdir]                                          | 注入常驻 ntfy 监听         |
|      | ntfy-watch-job [workdir] <job_id>                             | 为指定任务注入一次性 ntfy 监听   |
| 后处理  | plot-wave-maps [workdir] [--contour]                          | 波高填色图                |
|      | plot-spectrum [workdir] [--mode ...] [--station N]            | 方向谱图                 |
|      | plot-jason3 / plot-jason3-swh / download-jason3 [workdir] | Jason-3 相关           |
|      | plot-ndbc [workdir]                                           | NDBC 浮标匹配            |
|      | download-ndbc [workdir]                                       | 下载 NDBC 浮标观测数据       |
| 辅助   | print-example                                                 | 输出示例 params.yml      |



## 3. 工作目录结构

工作目录是一整个 WW3 算例的运行沙盒。GUI、Shell、CLI 打开工作目录时，首先读取这里的 `params.yml`；除 Step 1 会扫描标准化后的 `wind.nc`、`current.nc`、`level.nc`、`ice.nc` 来回显强迫场按钮外，其它表单状态不从 namelist、脚本或结果文件反推。

一个普通单层算例常见结构如下：

```text
work_dir_name/
├── params.yml                         # 该算例的唯一权威配置；GUI 表单恢复以它为准
├── run.log                            # local.sh / server.sh 追加写入的运行日志
├── local.sh                           # 本地运行脚本，由 public/scripts/local.sh 复制并按算例修正
├── server.sh                          # 服务器 Slurm 运行脚本，由 public/scripts/server.sh 复制并按算例修正
├── success / fail                     # 空标记文件，表示最近一次运行成功或失败
│
├── wind.nc                            # 标准化后的风场强迫，通常来自 Step 1
├── current.nc                         # 标准化后的流场强迫，可选
├── level.nc                           # 标准化后的水位强迫，可选
├── ice.nc                             # 标准化后的海冰强迫，可选
│
├── grid.bot                           # 水深网格，Step 2 生成或导入
├── grid.obst                          # 阻塞网格，结构化网格常见
├── grid.meta                          # WW3Tool 记录的网格元信息
├── mod_def.ww3                        # ww3_grid 生成的 WW3 网格定义文件
│
├── ww3_grid.nml                       # 网格与谱参数 namelist
├── ww3_prnc.nml                       # 强迫场预处理 namelist
├── ww3_shel.nml                       # 主计算 namelist
├── ww3_ounf.nml                       # 场输出 namelist
├── ww3_ounp.nml                       # 点位谱输出 namelist
├── ww3_trnc.nml                       # 轨迹输出 namelist，如启用航迹
├── namelists.nml                      # 部分 WW3 版本使用的合并 namelist
│
├── points.list                        # 定点谱输出点位，由 params.yml 的 calc.points 生成
├── track_i.ww3                        # 航迹输入文件，由 params.yml 的 calc.track_points 生成
│
├── wind.ww3 / current.ww3 / level.ww3 # ww3_prnc 产生的 WW3 二进制强迫文件
├── out_grd.ww3                        # ww3_shel 产生的场输出中间文件
├── out_pnt.ww3                        # ww3_shel 产生的点位谱中间文件
├── track_o.ww3                        # ww3_shel 产生的航迹输出中间文件
├── restart*.ww3                       # 重启动文件，如启用 restart
│
├── ww3.YYYY.nc                        # 场输出 NetCDF，通常由 ww3_ounf 产生
├── ww3.YYYY_spec.nc                   # 点位谱 NetCDF，通常由 ww3_ounp 产生
├── ww3.YYYY_trck.nc                   # 航迹 NetCDF，通常由 ww3_trnc 产生
└── photo/                             # GUI 或后处理保存的图片目录，如有
```

嵌套网格算例会在根目录保留总控文件，并为每一层生成独立目录：

```text
work_dir_name/
├── params.yml
├── ww3_multi.nml                      # 多网格耦合主控 namelist
├── local.sh / server.sh / run.log
├── wind.nc / current.nc / level.nc    # 根目录保留标准化强迫场源文件
├── level0/
│   ├── grid.bot / grid.obst / grid.meta
│   ├── ww3_grid.nml / ww3_prnc.nml / ww3_shel.nml / ww3_ounf.nml
│   ├── mod_def.ww3
│   ├── out_grd.ww3 / out_pnt.ww3
│   └── ww3.YYYY.nc / ww3.YYYY_spec.nc
├── level1/
│   └── ...
└── levelN/
    └── ...
```

关键约定：

1. `params.yml` 是唯一权威配置。打开已有工作目录时，第三步计算模式和点位只读取 `calc.mode`、`calc.points`、`calc.track_points`；即使目录里已经存在 `points.list` 或 `track_i.ww3`，也不会据此自动切换模式。
2. `ww3_*.nml`、`local.sh`、`server.sh` 是由当前参数生成的执行文件，不作为 GUI 反填配置的来源。修改参数后应重新确认参数或重新生成脚本。
3. `run.log` 必须追加写入，不应在重新执行 `local.sh` 或 `server.sh` 时清空旧日志。
4. `*.nc`、`*.ww3`、图片、视频、Slurm 输出和临时下载文件都属于运行产物，默认不要提交到 Git。
5. 大规模工作目录默认放在外置盘 `/Volumes/Zxy's Disk/WW3Tool_workSpace/`；仓库内 `workSpace/` 只适合少量测试或历史算例。




## 4. 配置系统：params.yml

params.yml 是描述一次计算任务的全部参数。

比如我现在想要对 110E ~ 130E，10N~30N 的区域进行海浪模拟，使用 2025 年 1 月 3 号到   2025 年 1 月 5 号的 ERA5 再分析风场数据做强迫场，这次模拟就可以认为是一个计算任务，常用的 WW3 NML 配置参数都会在 params.yml 中设置。

ww3_grid.nml 常用的数值积分参数

```swift
&SPECTRUM_NML
	SPECTRUM%XFR   = 1.1
	SPECTRUM%FREQ1 = 0.04118
	SPECTRUM%NK    = 32
	SPECTRUM%NTH   = 24
/

&TIMESTEPS_NML
	TIMESTEPS%DTMAX = 900
	TIMESTEPS%DTXY = 320
	TIMESTEPS%DTKTH = 300
	TIMESTEPS%DTMIN = 15
/
```

在 params.yml 描述为

```swift
ww3_grid:
	SPECTRUM%XFR: 1.1
	SPECTRUM%FREQ1: 0.04118
	SPECTRUM%NK: 32
	SPECTRUM%NTH: 24
	TIMESTEPS%DTMAX: 900
	TIMESTEPS%DTXY: 320
	TIMESTEPS%DTKTH: 300
	TIMESTEPS%DTMIN: 15
```

根目录的 params.yml (即 WW3Tool/params.yml) 只是模板，用于提供默认参数；实际的运行时候，我们会创建独立的工作目录，再编辑该目录下的 params.yml。

工作目录中的 params.yml 描述了一次计算任务的全部参数。

GUI 模式下，你填写的表单，程序会先在内存中保存参数，然后把根 params.yml 复制覆盖当前工作目录 yml 然后覆盖相应的参数，这么做是为了始终保持工作目录的 params.yml 和根 params.yml  的结构一致。

每次打开工作目录，GUI 程序会自动读取 params.yml ，恢复表单，让你能方便的知道当前工作目录的配置。

而在 Shell 和 CLI 模式下，你需要手动修改工作目录的 params.yml ，然后使用 Shell 和 CLI  的指令执行。



### 校验 params.yml

每次执行指令都会自动校验一遍 params.yml ，检查是否存在格式问题。

在 Shell 和 CLI 模式下，有一个专门的指令用于校验 params.yml 。

```sh
python run.py validate [work_dir_name] 
```

 
### 路径验证

执行每个步骤的功能的时候，例如 

```swift
python3 run.py prepare-forcing [work_dir_name]
```

都会自动校验带有路径的参数有效性，比如 

```swift
paths:
	matlab_path: /Applications/MATLAB_R2024a.app/bin/matlab
	jason_path: /Users/zxy/ocean/Paper/WW3Tool/jason3
	ndbc_path: null 
	jason3_download_url: https://www.ncei.noaa.gov/data/oceans/jason3/
```

如果发现某个参数为空或者路径不存在，那么会自动填写为 WW3Tool/ndbc ，WW3Tool/jason 等等类似的，在程序内部都有相关的规定默认的路径是什么。




## 5. 内部实现逻辑

一次完整流程的典型链路：

```
→ [创建或加载工作目录]  自动复制根 params.yml 到工作目录
→ [Step 1 强迫场准备] 校验、修复、复制/移动强迫场数据到工作目录
→ [Step 2 网格生成] 调用 meshgen 生成网格文件
→ [Step 3 计算模式] 选择 区域计算 / 二维谱点计算 / 航迹计算
→ [Step 4 WW3 配置] 配置 nml 文件参数
→ [Step 5 连接服务器] SSH 连接、配置 Slurm 参数、选择服务器 WW3 版本
→ [Step 6 上传与运行] 上传工作目录、提交到 Slurm 作业系统
→ [Step 7 最终] WW3 模式输出结果 (ww3.*.nc 等)
```

```mermaid
flowchart LR
  A[强迫场 NetCDF] --> B[Step 1 强迫场准备]
  B --> C[Step 2 网格生成]
  C --> D[Step 3 计算模式
  区域 / 谱点 / 航迹]
  D --> E[Step 4 WW3 配置 
  namelist / 脚本]
  E --> F{运行方式}
  F -->|本地| G[local.sh]
  F -->|服务器| H[上传 + server.sh / Slurm]
  G --> I[WW3 模式输出 ww3.2025.nc 等]
  H --> I
  I --> J[后处理绘图
  波高图 / 谱图 / 检验等]
```
我会在接下来的章节中，详细的和你说明每一步具体在做什么，让你放心的使用这个软件



### 5.1 创建工作目录

> 工作目录是什么？
> 
> 想象一个场景：我们现在想要对 110E ~ 130E，10N~30N 的区域进行海浪模拟，先使用 gridgen 生成了网格文件，然后下载了 2025 年 1 月 3 号到   2025 年 1 月 5 号的 ERA5 再分析风场数据做强迫场，配置了相关的 WW3 NML 文件，这一大堆文件都需要一个存放的位置：工作目录。

创建工作目录的 CLI  指令：

```sh
python3 run.py workdir [work_dir_name]    # 创建并加载工作目录，默认在 WW3Tool/workSpace 内创建
```

![](public/resource/README-media/截屏2026-06-18%2013.02.46.png)

创建工作目录时，程序会自动执行以下操作：

1. 在 WW3Tool/workSpace/ 下创建新文件夹，默认名称为当前时间戳（如 2026-06-17_19-37-01）

2. 将根目录 params.yml 原样复制到工作目录

3. 对工作目录 params.yml 执行：替换工作目录路径、清空强迫场文件路径、清空日期范围和 remote_dir ，这是防止每次自动恢复主页表单值的时候错误使用了根  params.yml  的值

4. 读取 params.yml 填充 UI 的默认值。



#### yml 对应参数

```swift
workdir:
	path: /Users/zxy/ocean/Paper/WW3Tool/workSpace/new
	default_workspace: /Volumes/Zxy's Disk/WW3Tool_workSpace/
```

path 是工作目录的路径

default_workspace 是新建工作目录默认的存放路径

```sh
python run.py workdir [work_dir_name]
```

这条指令中 work_dir_name 可以是一个绝对路径，也可以是一个名字，如果对应的目录不存在则会自动创建一个工作目录，自动复制根目录的 params.yml 到新工作目录，并替换工作目录的  params.yml 的 workdir.path 为工作目录路径。



#### 根目录校验

为了防止忘记创建工作目录就直接使用 Shell 或 CLI 指令，我加了一个校验当前目录是否是 WW3Tool 根目录，这样就不会误用根目录 params.yml 或忘记创建工作目录.

在 CLI 模式中，尝试不指定工作目录：

```bash
python3 run.py prepare-forcing 
    
---------------------------------------------------------------

Using project virtual environment: /Users/zxy/ocean/Paper/WW3Tool/.venv
Dependency check passed.
Parameter error: Cannot use the repository root params.yml directly (it is a template file).
Please create or load a working directory first:
  python3 run.py workdir my_workdir
```

在 shll 模式下不使用 workdir 指令，你是无法进行任何操作的。

```sh
ww3>  config  
⚠ No configuration loaded. Use 'workdir <path>' first.
ww3> queue-status
⚠ No configuration loaded. Use 'workdir <path>' first.
```



### 5.2 Step 1 — 强迫场准备

```sh
python3 run.py prepare-forcing [work_dir_name]    # 准备强迫场
```

第一步对所有导入的强迫场（风场、流场、水位场、冰场）文件进行标准化处理。


#### 判断强迫场类型

检测 NetCDF 内部变量名来判断强迫场类型：

- **风场**：存在 u10/v10、wndewd/wndnwd、uwnd/vwnd 任一对（大小写均匹配）
- **流场**：存在 uo/vo
- **水位场**：存在 zos
- **冰场**：存在 siconc


#### 强迫场标准化处理

1. 自动识别各类命名变体（如 wndewd/wndnwd → u10/v10，uo/vo 、zos 、siconc 保持），统一输出为标准变量名，并设置对应的 units、level 等属性

这是为了方便在第四步不需要根据强迫场变量名修改 ww3_prnc.nml

2. 坐标变量统一命名为 longitude / latitude / time（不论源文件用的是 lon / lat / valid_time 还是其他变体），同步重命名维度和引用该维度的所有变量 (原因同上)

3. 重命名为标准名字：wind.nc、current.nc、level.nc、ice.nc (原因同上)

4. 纬度从大到小排列时自动翻转为从小到大（避免 WW3 6.07.1 的 ww3_prnc 在规则经纬网下触发 EXTCDE(32)）



#### 多场文件自动关联

如果一个 NetCDF 文件同时包含多种强迫场（如流场+水位场），程序会检测所有存在的场类型，把转换后的强迫场进行自动关联处理，即 current_level.nc、wind_current_level_ice.nc，同时 GUI 多个强迫场槽位指向同一个文件。

自动关联在 params.yml 中定义为 forcing.auto_associate，为 true 的时候开启。


#### 工作目录扫描

打开工作目录时，会自动检测是否存在已经标准化处理过的强迫场文件，GUI 模式下会自动填充选择强迫场的对应按钮。







### 5.3 Step 2 — 网格生成

```sh
python3 run.py generate-grid  [work_dir_name]                 # 生成网格
python3 run.py recommend-grid [work_dir_name] --coarse        # 使用推荐网格间距
```

关于网格生成器 WW3Tool/meshgen，他们的详细说明可以查看 meshgen/README.md ，这里不再赘述。

在生成网格前，我们需要下载水深数据、海岸边界数据 reference_data，我已经把下载功能集成到 WW3Tool 了，你只需点击生成网格就会自动提示你下载。

每次网格生成的文件都会自动缓存到 meshgen/cache/，以参数 hash 为 key，避免重复计算。

我们生成的网格文件最终会被 WAVEWATCH III 编译出来的程序：ww3_grid 处理。


#### 网格 yml 参数

```yml
# ────────────────────────────────────────────────────────────────────
# Grid generation settings (structured / SMC / unstructured).
#   mesh_type – grid topology: 'structured' | 'smc' | 'unstructured'.
#   grid_type – 'normal' (single domain) or 'nested' (multi-level
#               refinement: level0 coarsest … levelN finest).
#   gridgen_version – grid generator back-end ('Python' or 'MATLAB').
#   reference_data_path – path to bathymetry / coastline data bundle;
#                          null = auto-detect from project defaults.
#   structured.nested.levels – ordered list (coarse → fine); each level
#               has dx/dy and lon/lat bounds. nested_contraction_coefficient
#               is a GUI helper for auto-shrinking bounds between levels.
#   lon       – [west, east] longitude bounds of the main domain (deg).
#   lat       – [south, north] latitude bounds of the main domain (deg).
# ────────────────────────────────────────────────────────────────────
grid:
  mesh_type: structured
  grid_type: normal
  gridgen_version: Python
  reference_data_path: /Users/zxy/ocean/Paper/WW3Tool/meshgen/reference_data
  lon:
  - 110.0
  - 130.0
  lat:
  - 10.0
  - 30.0
```



#### 结构化矩形网格

由 pygridgen（gridgen）在规则经纬度上生成矩形格点。grid_type: normal 时只生成一层，产物直接落在工作目录根；grid_type: nested 时按层生成多套网格，见下文。



##### 嵌套网格

嵌套用于「外圈粗、内圈细」的多分辨率模拟：外层覆盖大尺度背景，内层在感兴趣区域加密。WW3Tool 采用 WW3 的 ww3_multi 路线，一次积分驱动多层网格（见 §5.5.7、嵌套网格设计与问题分析.md）。

配置要点：

| 项 | 说明 |
|----|------|
| grid.grid_type | 设为 nested 启用嵌套；normal 为单层 |
| grid.structured.nested.levels | 从粗到细的有序列表，levels[0] 为最粗层 level0，levels[-1] 为最细层 levelN；支持 2～99 层 |
| 每层字段 | dx、dy（度）、lon、lat（该层矩形范围） |
| nested_contraction_coefficient | GUI「套娃」辅助：按系数向中心收缩上一层的范围、并减半 dx/dy，自动填下一层；也可在 yml 里逐层手写 |
| 校验 | 细层 dx/dy 须小于粗层；第 k 层地理范围须完全落在第 k−1 层之内 |

生成与目录约定：

- generate-grid 对每一层独立调用 gridgen，输出到 level0/、level1/、…、levelN/（不再使用旧的 coarse/、fine/ 命名）。
- 各层各有 grid.bot、grid.obst、grid.meta 等；强迫场 NetCDF 仍放在工作目录根，各层 prnc 用 ../wind.nc 引用。
- 根目录一份 ww3_multi.nml；谱点模式时 points.list 也在根目录，谱点须落在最细层网格内。

CLI 示例（两层嵌套）：

```sh
python3 run.py workdir nested_demo
# params.yml:
#   grid.grid_type: nested
#   grid.structured.nested.levels: [ level0 粗, level1 细 ]
python3 run.py generate-grid nested_demo
python3 run.py recommend-cfl nested_demo    # 逐层按 CFL 算时间步
python3 run.py prepare-ww3 nested_demo
python3 run.py local-run nested_demo
```

嵌套算例仍处演进中；若 run.log 出现 OUTPUT POINT OUT OF GRID、NBI=0 AND RANK > 1 等，请对照 嵌套网格设计与问题分析.md 检查层间范围、点位与 ww3_multi.nml 配置。



##### yml 参数

单层（grid_type: normal）时 levels 只保留一项即可；嵌套时至少两项。

```yml
# Structured grid options:
#   bathymetry       – bathymetry dataset name (see presets.structured_bathymetry).
#   coastline_precision – GSHHG coastline detail level (full/high/inter/low/coarse).
#   min_dist         – minimum distance filter between adjacent grid points (km).
#   cut_off          – land-sea mask cut-off: 0 = keep all sea points.
#   lim_bathy        – depth-based cell inclusion threshold (fraction of cell wet).
#   lim_val          – masking threshold for cell classification (0–1).
#   split_lim        – split-cell limit: 0 = disabled.
#   lake_tol         – minimum lake area (cells) to keep; smaller lakes are filled.
#   nested.levels    – coarse → fine; level0 = levels[0], finest = levels[-1].
#   nested.nested_contraction_coefficient – GUI shrink ratio between levels (≥ 1).
structured:
  nested:
    nested_contraction_coefficient: 1.3
    levels:
    - dx: 0.05
      dy: 0.05
      lon: [110.0, 130.0]
      lat: [10.0, 30.0]
    - dx: 0.025
      dy: 0.025
      lon: [115.0, 125.0]
      lat: [15.0, 25.0]
  bathymetry: GEBCO
  coastline_precision: full
  min_dist: 20
  cut_off: 0
  lim_bathy: 0.4
  lim_val: 0.5
  split_lim: 0
  lake_tol: 50
```



##### 网格可视化

![](public/resource/README-media/grid_bathymetry.png)

![](public/resource/README-media/grid_obstruction_x.png)

![](public/resource/README-media/grid_obstruction_y.png)

![](public/resource/README-media/grid_structure.png)



##### 网格文件

单层时，结构化矩形网格由 gridgen 在工作目录根生成 grid.obst、grid.bot、grid.mask_nobound、grid.meta。嵌套时每一层 levelK/ 下各有同样一套文件。

```sh
grid.bot
  - 格式：ASCII 文本文件
  - 内容：网格水深数据(来)
  - 单位：来(实际值 = 文件值 / 1000)
  - 尺寸：Ny × Nx
grid.mask_nobound
  - 格式：ASCII 文本文件
  - 内容：陆海掩膜
  - 值：0 = 陆地，1 = 海洋
  - 尺寸：Ny × Nx
grid.obst
  - 格式：ASCII 文本文件
  - 内容：x 和 y 方向的障碍物值
  - 单位：0-1 之间的比例(实际值 = 文件值 / 100)
  - 尺寸：Ny × Nx(x 方向)，Ny × Nx(y 方向)
grid.meta (实际上是 ww3_grid.nml，用于同步一些配置)
  - 格式：ASCII 文本文件
  - 内容：供 WAVEWATCH III `ww3_grid` 使用的网格描述
  - 包含：网格尺寸、分辨率、范围等信息
```



#### 三角形非结构化网格

基于 JIGSAW 生成，支持深水尺度、近岸尺度、浅水波长加密、水深梯度等参数


##### yml 参数

```yaml
# Unstructured (triangular) grid spacing parameters:
# hmax – maximum element spacing in deep water (km).
# hmin – minimum allowed spacing everywhere (km).
# hshr – target spacing near shorelines (km).
# nwav – number of wavelengths per element for resolution.
# dhdx – rate of spacing change with depth gradient.
# deep_ocean_threshold_m – depth (m) above which hmax applies.
# margin_deg – buffer margin around domain boundary (degrees).
# edge_segments – number of segments along coastlines.
# options.data – optional mask / exclusion file.
# options.command_line_args – extra JIGSAW CLI flags.
# options.regional – stereographic projection centre (stereo_lon/lat).

unstructured:
	hmax: 100
	hmin: 2
	hshr: 20
	nwav: 400
	dhdx: 0.05
	deep_ocean_threshold_m: 4000
	margin_deg: 1
	edge_segments: 64
	options:
	data:
	mask_file: ''
	command_line_args:
	black_sea: 3
	regional:
	stereo_lon: 120.0
	stereo_lat: 20.0
```


##### 网格文件

| 文件                    | 说明                                                                            |
| --------------------- | ----------------------------------------------------------------------------- |
| grid_cell.dat         | SMC 内部单元                                                                      |
| grid_boundary.dat     | 仅当 grid.global 为 false 且 boundary.generate_boundary_cells 为 true 时生成开边界带。 |
| grid_arctic_cells.dat | 仅当 grid.global 为 **true** 且 **grid.arctic** 为 **true** 时生成北极单元。           |
| grid_subtr.dat        | WW3 SMCG 子网格阻障文件（create_grid.py 写 **全零** = 无阻挡）。                            |
| grid.json             | 网格生成配置                                                                        |



##### 网格可视化

![](public/resource/README-media/grid_unst_bathymetry.png)

![](public/resource/README-media/grid_unst_structure.png)



#### SMC 网格

基于 SMCGTools 生成


##### yml 参数

```yml
# SMC (Spherical Multi-Cell) grid options:
#   bathymetry       – dataset name (see presets.smc_bathymetry).
#   bathy_convention – 'elevation' (positive up) or 'depth' (positive down).
#   n_levels         – number of cell-size refinement levels.
#   wlevel           – water-level reference index.
#   depmin           – minimum depth below which cells are excluded (m).
#   dshalw           – shallow-water depth threshold for extra refinement (m).
#   generate_boundary_cells – whether to create open-boundary ghost cells.
#   msea             – minimum cell count across straits.
#   options.input    – low-level input pre-processing (auto-flip, tolerances).
#   options.grid     – grid identity & projection (global, arctic, origin).
#   options.output   – output file naming and formatting.
smc:
  bathymetry: ETOPO2
  bathy_convention: elevation
  n_levels: 2
  wlevel: 0
  depmin: 0
  dshalw: -150
  generate_boundary_cells: true
  msea: 1
  options:
    input:
      auto_flip_lat: true
      auto_flip_lon: true
      coord_spacing_rtol: 0.001
      coord_spacing_atol: 1.0e-08
      nan_fill_value: 1000.0
    grid:
      name: grid
      global: false
      arctic: false
      glb_arc_lat: 84.4
      origin:
        lon0: 0.0
        lat0: -90.0
    output:
      file_prefix: ''
```


##### 网格可视化

![](public/resource/README-media/grid_smc_bathymetry.png)

![](public/resource/README-media/grid_smc_structure.png)





### 5.4 Step 3 — 计算模式

计算模式决定 WW3 算一整片海域、只算若干固定点位，还是沿一条移动轨迹算。在 params.yml 的 calc.mode 里设置，GUI 上第三步选择；没有单独的 CLI 子命令，会在 prepare-ww3 或 run-workflow 时自动读取。

| 模式 | calc.mode | 你会在工作目录看到 | 最终常见产物 |
|------|-------------|-------------------|--------------|
| 区域尺度计算 | region | 无额外列表文件 | ww3.2025.nc 等场输出 |
| 谱空间逐点计算 | spectral_point | points.list | ww3.2025_spec.nc 等谱点输出 |
| 航迹模式 | track | track_i.ww3 | ww3.2025_trck.nc 等航迹输出 |

典型用法：先在 GUI 或 params.yml 里设好 calc.mode 和点位，再跑第四步。例如区域算例：

```sh
python3 run.py workdir 2026_shanghai_region
# 编辑 workSpace/2026_shanghai_region/params.yml → calc.mode: region
python3 run.py run-workflow 2026_shanghai_region
```

谱点算例在 params.yml 里设 calc.mode: spectral_point，并在 calc.points 里写好经纬度；第四步会生成 points.list：

```sh
python3 run.py workdir 2026_shanghai_points
python3 run.py prepare-ww3 2026_shanghai_points
```

打开工作目录时，GUI 只根据 params.yml 的 calc 段恢复第三步：calc.mode 决定区域 / 谱点 / 航迹模式，calc.points 和 calc.track_points 决定表格点位。已有的 points.list 或 track_i.ww3 只视为第四步/运行后生成的文件，或手动点击第三步导入按钮时的输入来源；不会在打开工作目录时自动反推模式或覆盖 yml 中的点位。

谱点模式需要若干 (经度, 纬度, 名称)；航迹模式还要每个点的时间。第四步会把这些列表写进 namelist，并启用相应的后处理（ww3_ounp / ww3_trnc）。



### 5.5 Step 4 — WW3 配置

```sh
python3 run.py prepare-ww3 work_dir_name      # 只做到第四步：生成 nml 和运行脚本
python3 run.py run-workflow work_dir_name     # Step 1～4 一次跑完
```

完整预处理示例（假设工作目录里已有 wind.nc 和网格）：

```sh
python3 run.py workdir new
python3 run.py prepare-forcing new
python3 run.py generate-grid new
python3 run.py prepare-ww3 new
```

或一条命令做完 Step 1～4：

```sh
python3 run.py run-workflow new
```

> 第四步在做什么？
>
> 前三步已经把风场、网格、计算模式准备好了。第四步根据工作目录里的 params.yml，把 WW3 需要的一整套 namelist 和 local.sh / server.sh 配好。  
> 原则很简单：只在模板文件里改和本次算例有关的字段，其余保持 public/{version}_nml/ 模板原样，方便你对照官方示例排错。

下面按你在日志里常见到的阶段说明程序背后做了什么。



#### 5.5.1 复制模板与写运行脚本

日志里会出现类似「已复制 N 个 NML 模板」「已更新 server.sh」：

- 从 public/6.07_nml/ 或 public/7.14_nml/（由 ww3.version 决定）复制 ww3_grid.nml、ww3_prnc.nml、ww3_shel.nml、ww3_ounf.nml 等到工作目录（嵌套时还会复制 ww3_multi.nml）。
- 同时写入 local.sh（本机跑）和 server.sh（服务器 Slurm 跑）。两个脚本的计算流程相同；差别见 §5.5.8。

仅刷新 nml 和脚本、不重复做 Step 1～2 时：

```sh
python3 run.py prepare-ww3 new
```



#### 5.5.2 把网格写进 ww3_grid.nml

日志：已成功同步 grid.meta 参数到 ww3_grid.nml 或各 【levelN】 下的同类信息。

Step 2 生成的 grid.meta 本质是 ww3_grid.nml 的精简版（格点数 NX/NY、分辨率、范围、水深/障碍物文件名等）。第四步把这些数抄回对应层的 ww3_grid.nml，保证 WW3 读到的网格和 gridgen 生成的一致。

嵌套算例需先完成网格生成再配置 WW3：

```sh
python3 run.py generate-grid nested_case
python3 run.py prepare-ww3 nested_case
```



#### 5.5.3 按 CFL 推荐时间步（自动配置时间步）

GUI 点「自动配置时间步」，或 CLI / Shell 执行 recommend-cfl，会按 CFL 稳定性给出 TIMESTEPS%DTXY、DTMAX、DTKTH、DTMIN 的建议，并写入 params.yml 的 ww3_grid 段；确认第四步时再写进各层 ww3_grid.nml。

```sh
python3 run.py recommend-cfl new                         # 默认 safe，CFL 系数 0.9
python3 run.py recommend-cfl new --mode fast             # 更激进，CFL 系数 1.05
python3 run.py recommend-cfl new --mode faster           # 最激进内置档，CFL 系数 1.15
python3 run.py recommend-cfl new --factor 1.2            # 手动指定 CFL 系数，自动上限 1.25
python3 run.py prepare-ww3 new
```

WW3 官方在 ww3_grid.nml 注释里的思路是：波浪在网格上传播时，一个时间步内波群走过的距离不能超过一个网格间距。记：

- \(\Delta x\)：网格最小间距（米）。结构化/SMC 由 dx、dy 和纬度换算；非结构用 hmin（km）直接当最细尺度。
- \(f_1\)：谱最低频率 SPECTRUM%FREQ1（Hz）。
- 深水近似下，最低频波的群速度 \(C_g \approx g / (4\pi f_1)\)（\(g=9.8\,\mathrm{m/s^2}\)）。

则 CFL 时间尺度：

\[
T_{\mathrm{cfl}} = \frac{\Delta x}{C_g} = \frac{\Delta x \cdot f_1 \cdot 4\pi}{g}
\]

WW3Tool 在此基础上取整数秒，并级联得到：

| 模式 | CFL 系数 | 说明 |
|------|----------|------|
| safe | 0.90 | 默认保守设置 |
| fast | 1.05 | 更激进，减少步数，适合已有经验的复跑 |
| faster | 1.15 | 最激进内置档，需关注稳定性 |
| --factor X | 自定义，最高 1.25 | 直接指定 CFL 乘子 |

| 参数 | 含义 | 推荐关系 |
|------|------|----------|
| DTXY | 空间传播时间步 | \(\approx \mathrm{CFL系数} \times T_{\mathrm{cfl}}\) |
| DTMAX | 积分主时间步上限 | \(\approx 3 \times \mathrm{DTXY}\) |
| DTKTH | 谱源汇时间步 | 无强流时 \(\approx \mathrm{DTMAX}/2\)；有强流时更细 |
| DTMIN | 最小时间步 | 默认 15 s，一般不动 |

嵌套网格时每一层 dx/dy 不同，会逐层重算 CFL：细网格间距小 → DTXY 更小 → 同样模拟时长内步数更多，计算更重。这和 ww3_multi.nml 里进程分配有关（见 5.5.7）。

若网格很粗或 FREQ1 很小，算出的步长会偏大；若仍不稳定，应减小 dx/dy 或略减小推荐系数，而不是盲目加大 DTMAX。



#### 5.5.4 时间与输出步长

日志：已更新 ww3_shel.nml：DOMAIN%START=… / 已更新 ww3_ounf.nml：FIELD%TIMESTART=…

来自 params.yml 的 ww3.start_date、ww3.end_date、ww3.output_step（输出间隔，秒）：

- 计算时间窗写进 ww3_shel.nml（或嵌套时的 ww3_multi.nml）的 DOMAIN%START/STOP 和 DATE%FIELD 等。
- NetCDF 场输出间隔写进 ww3_ounf.nml 的 FIELD%TIMESTRIDE。
- 强迫场预处理 ww3_prnc.nml 的时间窗与计算一致，避免多读无关时段。

CLI 下直接改 params.yml 后重新生成 nml 即可，例如：

```sh
# params.yml 片段示例
# ww3:
#   start_date: "20250103"
#   end_date: "20250105"
#   output_step: "3600"
python3 run.py prepare-ww3 new
```

GUI 上「从 wind.nc 读取时间范围」只读风场文件头里的起止时间填回表单，不会从旧 nml 反填界面。



#### 5.5.5 谱分区输出方案

日志：已修改 ww3_shel，ww3_ounf 的谱分区输出方案

在设置页配置的 presets.output_scheme（如 standard、minimal）是一组变量缩写列表（HS、DIR、FP…）。第四步把同一份列表写入 ww3_shel.nml 的 TYPE%FIELD%LIST 和 ww3_ounf.nml 的 FIELD%LIST。嵌套时还会同步到 ww3_multi.nml 的 ALLTYPE%FIELD%LIST。

```sh
# params.yml 片段示例
# ww3:
#   output_scheme: standard
python3 run.py prepare-ww3 new
```

方案名只存在 params.yml 里，不会从已有 shel 反推回 GUI。



#### 5.5.6 强迫场开关与多套 prnc

日志：已修改 ww3_shel.nml：更新 INPUT%FORCING%*；运行阶段日志里会出现 Running ww3_prnc (wind)、Running ww3_prnc (current) 等。

Step 1 放了哪些 wind.nc、current.nc 等，shel/multi 里对应强迫开关就为 T，否则为 F。ww3_prnc 一次只能处理一种强迫场，因此除风场外每种场有独立的 ww3_prnc_current.nml 等；local.sh / server.sh 会轮流改名为 ww3_prnc.nml 再执行（见 §5.5.8）。

只有风场时，预处理链通常是：

```sh
python3 run.py prepare-forcing new
python3 run.py prepare-ww3 new
python3 run.py local-run new
```



#### 5.5.7 嵌套网格（level0 … levelN）

> 嵌套网格仍在演进中，使用前请阅读 嵌套网格设计与问题分析.md。

日志结构大致是：

```
======================================================================
🔄 【工作目录】开始处理公共文件...     ← server.sh、ww3_multi.nml、points.list 等
======================================================================
🔄 【level0】开始处理网格...           ← 最粗层
======================================================================
🔄 【level1】…
======================================================================
🔄 【level2】…                        ← 最细层
```

嵌套算例 CLI 示例：

```sh
python3 run.py workdir nested_demo
# params.yml → grid.grid_type: nested，并配置 structured.nested.levels
python3 run.py prepare-forcing nested_demo
python3 run.py generate-grid nested_demo
python3 run.py recommend-cfl nested_demo
python3 run.py prepare-ww3 nested_demo
python3 run.py local-run nested_demo
```

要点：

- 工作目录根下放 ww3_multi.nml 和 points.list（谱点模式）；各层 level0/、level1/… 各有自己的 ww3_grid.nml、mod_def 等。
- ww3_multi.nml 里每个 MODEL(i)%NAME 对应一层（如 level2），并设置嵌套层级 RANK_ID 与 MPI 资源区间 COMM_FRAC。
- 强迫场 NetCDF 通常放在根目录，各层 prnc 用 ../wind.nc 引用。
- 谱点列表在根目录一份即可。默认 UNIPTS=F 时，谱点 raw 文件跟最细层 MODEL%NAME 走（如 out_pnt.level2）。

DOMAIN%FLGHG1/FLGHG2 控制双向嵌套掩膜；若未正确配置或层间几何不匹配，运行日志里可能出现 NBI=0 AND RANK > 1、OUTPUT POINT OUT OF GRID 等 WW3 警告。



#### 5.5.8 local.sh 与 server.sh 在算什么

两个脚本都是按固定顺序调用 WW3 官方可执行文件；任一步失败就停止，并在工作目录留下空文件 fail（成功则 success）。全程追加写入 run.log。

本机跑：

```sh
python3 run.py local-run new
# 或进入工作目录
cd workSpace/new && bash local.sh
# 指定 MPI 进程数
WW3_MPI_NPROCS=8 python3 run.py local-run new
```

服务器跑（先上传、再提交）：

```sh
python3 run.py upload --confirm new
python3 run.py submit new
python3 run.py check-status new
python3 run.py download-log new
```

公共前半段（每层或单层都要做）：

1. ww3_grid — 读 grid.bot / grid.meta 等，生成 mod_def.ww3。
2. ww3_prnc — 把 NetCDF 强迫场插值到波浪网格，得到 wind.ww3 等（多种强迫场则 wind → current → level → ice 依次跑）。
3. ww3_strt — 初始场或冷启动。

普通网格（grid_type: normal）：

4. mpirun ww3_shel（失败会尝试单进程 ww3_shel）— 主积分，生成 out_grd.ww3 等。
5. 按 params.yml 的 calc.mode 决定后处理：spectral_point → 生成 points.list 并运行 ww3_ounp；track → 生成 track_i.ww3 并运行 ww3_trnc。
6. ww3_ounf — 把 out_grd.ww3 转成 ww3.YYYY.nc。

嵌套网格（grid_type: nested）：

1. 对每个 level* 重复 grid + prnc + strt。
2. 把各层 mod_def.ww3、wind.ww3 等搬到工作目录根，改名为 mod_def.level0、wind.level1… 供 ww3_multi 识别。
3. mpirun ww3_multi — 多网格积分（替代单层 ww3_shel）。
4. 把 out_grd.levelN、out_pnt.levelN 等移回最细层 levelN/，再跑 ww3_ounp / ww3_trnc / ww3_ounf。

local.sh 与 server.sh 的差别：

| | local.sh | server.sh |
|---|----------|-----------|
| 触发 | 本机 bash local.sh 或 local-run | 登录节点 sbatch server.sh 或 submit |
| 核数 | WW3_MPI_NPROCS，否则本机逻辑 CPU 数 | #SBATCH -n 与脚本内 MPI_NPROCS |
| 日志 | 终端 + run.log（tee） | 主要写入 run.log |
| WW3 路径 | 本机 PATH 里的 WW3 | export PATH=… 指向服务器编译版本 |

第四步改 nml，脚本按顺序调程序；run.log 里 Running ww3_grid、Running mpirun ww3_shel 等分隔线对应当前步骤。



### 5.6 连接服务器与 Slurm

```sh
python3 run.py connect-test work_dir_name    # 测试 SSH
python3 run.py slurm-idle work_dir_name      # 看集群空闲核数
python3 run.py queue-status work_dir_name    # 看作业队列
python3 run.py confirm-slurm work_dir_name   # 按 params.yml 刷新 server.sh
python3 run.py ssh work_dir_name             # 打开交互式 SSH 终端
```

示例：

```sh
python3 run.py connect-test hpc_case
python3 run.py slurm-idle hpc_case
python3 run.py confirm-slurm hpc_case
```

在 GUI 第五步，你需要先连上 HPC，确认分区、核数、节点数和 WW3 版本（slurm.server_st）。这些值在 params.yml 里；「确认 Slurm 配置」会写进 server.sh 顶部的 #SBATCH 和 MPI_NPROCS。nml 管物理参数，server.sh 管申请多少核、用哪套可执行文件。



### 5.7 上传与运行

```sh
python3 run.py upload --confirm work_dir_name   # 上传整个工作目录
python3 run.py submit work_dir_name             # 在服务器提交 server.sh
python3 run.py check-status work_dir_name       # 看 success / fail 标记
python3 run.py download-results work_dir_name   # 拉回结果
python3 run.py download-results work_dir_name --nested   # 嵌套：只拉最细层
python3 run.py download-log work_dir_name       # 拉回 run.log
python3 run.py cancel-job work_dir_name 12345   # 取消作业
python3 run.py clear-remote --confirm work_dir_name
python3 run.py local-run work_dir_name          # 本机跑 local.sh
```

服务器完整链路示例：

```sh
python3 run.py run-workflow hpc_case
python3 run.py confirm-slurm hpc_case
python3 run.py upload --confirm hpc_case
python3 run.py submit hpc_case
python3 run.py check-status hpc_case
python3 run.py download-log hpc_case
python3 run.py download-results hpc_case
```

本机调试（不连服务器）：

```sh
python3 run.py run-workflow local_test
python3 run.py local-run local_test
```

嵌套算例下载结果时，一般只关心最细层 levelN/ 里的 ww3.*.nc。



### 5.8 ntfy 通知（可选）

```sh
python3 run.py ntfy-watch work_dir_name
python3 run.py ntfy-watch-job work_dir_name 12345
```

示例：提交作业后挂一次性监听（12345 换成 squeue 里的 JobID）：

```sh
python3 run.py submit hpc_case
python3 run.py ntfy-watch-job hpc_case 12345
```

作业在服务器上跑得久时，可在登录节点轮询 Slurm，任务结束往手机推 ntfy 通知。



### 5.9 后处理绘图

```sh
python3 run.py plot-wave-maps work_dir_name
python3 run.py plot-wave-maps work_dir_name --contour
python3 run.py plot-spectrum work_dir_name
python3 run.py plot-spectrum work_dir_name --station 0
python3 run.py plot-jason3 work_dir_name
python3 run.py plot-jason3-swh work_dir_name
python3 run.py download-jason3 work_dir_name
python3 run.py plot-ndbc work_dir_name
python3 run.py download-ndbc work_dir_name
```

算例跑完后：

```sh
python3 run.py download-results new
python3 run.py plot-wave-maps new
python3 run.py plot-spectrum new --mode polar
```

Step 7 用工作目录里已有的 ww3.*.nc、points.list 等做填色图、方向谱、与 Jason-3 / NDBC 对比，不参与 WW3 积分本身。



## 7. 工作目录结构

一个典型工作目录（如 workSpace/work_dir_name/）包含：

```
work_dir_name/
├── params.yml              # 该算例的参数（GUI 状态以它为准）
├── wind.nc                 # 风场（Step 1）
├── current.nc / level.nc / ice.nc   # 其他强迫场（如有）
├── grid.bot / grid.obst / grid.meta # 网格（Step 2，单层时）
├── level0/ … levelN/       # 嵌套各层（如有）
├── ww3_grid.nml …          # WW3 namelist（Step 4）
├── ww3_multi.nml           # 嵌套主控（如有）
├── server.sh / local.sh    # 运行脚本
├── points.list / track_i.ww3        # 谱点 / 航迹（如有）
├── run.log                 # 运行日志（local.sh 或 server.sh 产生）
├── success 或 fail         # 空标记文件，表示成败
└── ww3.2025.nc 等          # 后处理产物（ww3_ounf / ounp / trnc）
```

打开工作目录时，程序只从 params.yml 恢复表单；另外会扫描是否已有 wind.nc 等标准强迫场文件名来填充 Step 1。第三步计算模式和点位只读取 params.yml 的 calc.mode、calc.points、calc.track_points；即使工作目录里已经存在 points.list 或 track_i.ww3，也不会自动切换模式或导入点位。嵌套时根据 params.yml 的 grid.grid_type 和 nested levels 恢复网格设置。不会从 ww3_shel.nml 或 server.sh 反填时间、谱分区或 Slurm 参数。

载入已有算例：

```sh
python3 run.py workdir /path/to/existing_case
python3 run.py config existing_case
python3 run.py validate existing_case
```



