# WW3Tool  文档

## 1. 项目定位



WW3Tool 是围绕 **WAVEWATCH III**（海浪数值模式）构建的 **预处理与运行辅助工具**。它不替代 WW3 本身的可执行程序（ww3_grid、ww3_prnc、ww3_shel 等），而是负责：

- 强迫场文件的校验、修复与合并（纬度排序、变量重命名、时间轴修复）
- 网格生成（结构化矩形网格（支持任意层数的 Two-Way Nesting ） / 三角形非结构化网格 / SMC 网格三种类型）
- 自动配置 WW3 所需的全套 namelist 文件，支持 v6.07.1 和 v7.14 （ww3_grid.nml、ww3_prnc.nml、ww3_shel.nml、ww3_ounf.nml、ww3_multi.nml 等）
- 针对不同配置的运行脚本，正确的执行 ww3_grid、ww3_prnc、ww3_shel 等等
- 通过 SSH 将工作目录上传到 HPC 服务器、配置 Slurm 参数，提交 Slurm 作业、监控任务状态、下载结果
- 后处理绘图（波高填色图、方向谱、Jason-3 卫星验证、NDBC 浮标匹配等）

WW3Tool 完全由 Python 组成（其他语言的代码是网格生成器 meshgen 的代码），支持 Windows / Linux / macOS，UI 支持中英文双语。

我是上海海洋大学的一名海洋科学研究生，由于我本科不是海洋科学，对 WAVEWATCH III 了解并不多，因此如果你对 WW3Tool 有什么建议，请联系我： atomgoto@gmail.com 

另外如果 WW3Tool 对你有帮助，请给我一颗 🌟 ！ 🥳 


## 2. 快速开始

run.py 是唯一入口，通过命令行参数区分三种模式：

```sh
python3 run.py                    # GUI（图形界面）
python3 run.py shell              # 交互式终端（REPL，可反复执行各步骤）
python3 run.py <子命令> [workdir]  # 无界面 CLI（一条命令一个步骤，适合脚本与 AI 调用）
```

三种模式共享同一套业务逻辑（src/workflows/application/），差别仅在交互层。


### 2.1 GUI

![](public/resource/README-media/截屏2026-06-28%2009.57.44.png)

```bash
python3 run.py
```

这是我们最常用的模式



### 2.2 交互式终端

```sh
python3 run.py shell              # 交互式终端
```

![](public/resource/README-media/截屏2026-06-18%2011.07.11.png)

这个模式更适合远程在服务器使用


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
| 预处理  | generate-grid [workdir]                                       | 生成网格（Step 1）        |
|      | merge-forcing <in1.nc> [...] -o <out.nc>                      | 独立工具：校验并合并强迫场 NetCDF |
|      | prepare-forcing [workdir]                                     | 准备强迫场（Step 2）        |
|      | recommend-grid [workdir] [--coarse\|--fine]                   | 按区域范围推荐网格间距          |
|      | recommend-cfl [workdir] [--mode safe\|fast\|faster] [--factor X] | 按 CFL 公式推荐时间步长       |
|      | prepare-ww3 [workdir]                                         | 仅生成 WW3 namelist     |
|      | run-workflow [workdir]                                        | 完整预处理流程              |
|      | local-run [workdir]                                           | 执行 local.sh          |
| 远程运维 | connect-test [workdir]                                        | 测试 SSH 连接            |
|      | ssh [workdir]                                                 | 打开交互式 SSH 终端         |
|      | slurm-idle [workdir]                                          | 查看 Slurm 空闲分区      |
|      | confirm-slurm [workdir]                                       | 写 server.sh          |
|      | upload [workdir] --confirm                                    | 上传工作目录到远程            |
|      | submit [workdir]                                              | 提交 server.sh         |
|      | check-status [workdir]                                        | 检查远程任务状态             |
|      | queue-status [workdir]                                        | 查看 SLURM 队列          |
|      | download-results [workdir]                                    | 下载远程结果；嵌套网格自动下载最细层 |
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

注意：几乎所有的 CLI 指令都是必须指定工作目录的，没有工作目录是不允许执行的。





## 3. 工作目录

> 工作目录是什么？
>
> 想象一个场景：我们现在想要对 110E ~ 130E，10N~30N 的区域进行海浪模拟，先使用 gridgen 生成了网格文件，然后下载了 2025 年 1 月 3 号到   2025 年 1 月 5 号的 ERA5 再分析风场数据做强迫场，配置了相关的 WW3 NML 文件，这一大堆文件都需要一个存放的位置：工作目录。

一个普通单层算例常见结构如下：

```text
work_dir_name/
├── params.yml                         # 该算例的唯一权威配置；GUI 表单恢复以它为准
├── run.log                            # local.sh / server.sh 追加写入的运行日志
├── local.sh                           # 本地运行脚本，由 public/scripts/local.sh 复制并按算例修正
├── server.sh                          # 服务器 Slurm 运行脚本，由 public/scripts/server.sh 复制并按算例修正
├── success / fail                     # 空标记文件，表示最近一次运行成功或失败
│
├── wind.nc                            # 标准化后的风场强迫，通常来自 Step 2
├── current.nc                         # 标准化后的流场强迫，可选
├── level.nc                           # 标准化后的水位强迫，可选
├── ice.nc                             # 标准化后的海冰强迫，可选
│
├── grid.bot                           # 水深网格，Step 1 生成或导入
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
→ [Step 1 网格生成] 调用 meshgen 生成网格文件
→ [Step 2 强迫场准备] 校验、修复、复制/移动强迫场数据到工作目录
→ [Step 3 计算模式] 选择 区域计算 / 二维谱点计算 / 轨迹计算
→ [Step 4 WW3 配置] 配置 nml 文件参数
→ [Step 5 连接服务器] SSH 连接、配置 Slurm 参数、选择服务器 WW3 版本
→ [Step 6 上传与运行] 上传工作目录、提交到 Slurm 作业系统
→ [Step 7 最终] WW3 模式输出结果 (ww3.*.nc 等)
```

```mermaid
flowchart LR
  A[网格参数 / 水深 / 海岸线] --> B[Step 1 网格生成]
  B --> C[Step 2 强迫场准备]
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

各步骤的 CLI 指令示例不单独集中罗列，统一放在每节的 `yml 对应参数` 或 `params.yml 参数` 小节里，方便一边看参数一边执行对应命令。

我会在接下来的章节中，详细的和你说明每一步具体在做什么，让你放心的使用这个软件



### 5.1 创建工作目录

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
	default_workspace: /public/home/weiyl001/user/gongchuheng/WorkSpace/ShangHai/
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



### 5.2 Step 1 — 网格生成

第一步负责根据 `params.yml` 的 `grid` 段生成 WW3 网格文件。它只负责“把经纬度范围、水深、海岸线、网格类型变成 WW3 可读取的网格输入”，不运行 `ww3_grid`；真正把网格编译成 `mod_def.ww3` 是 Step 4 / 运行脚本中的 `ww3_grid` 完成的。

![](public/resource/README-media/截屏2026-06-28%2010.50.13.png)


#### GUI 操作逻辑

主页 Step 1 当前是“设置网格参数、预览范围、然后生成网格”：

关于底层网格生成器 `WW3Tool/meshgen`，详细说明见 `meshgen/README.md`。这里只写 GUI / CLI 使用时最常改、最容易误解的部分。




![](public/resource/README-media/截屏2026-06-28%2011.09.59.png)


1. 选择网格类型：普通网格 / 嵌套网格，以及矩形网格 / SMC 网格 / 非结构网格。
2. 填写主网格范围。界面统一显示为 `纬度`、`经度` 两行，每行两个输入框；对应 yml 中的 `grid.lat: [south, north]` 和 `grid.lon: [west, east]`。
3. 矩形网格需要填写 `DX/DY`；SMC 和非结构网格会隐藏 `DX/DY`，改用各自的参数卡片。
4. 点击“推荐网格间距”可按当前范围和网格类型写入一组保守起步参数。
5. 点击“查看地图”可预览当前网格范围。嵌套网格会显示各层矩形范围，便于检查细层是否完全落在粗层内部。
6. 点击“生成网格”后，程序调用 `meshgen` 生成对应文件，并写入工作目录。

如果生成网格前缺少水深数据、海岸线数据 `reference_data`，GUI 会提示下载。生成结果会按参数 hash 缓存在 `meshgen/cache/`，同一组参数重复生成时会优先复用缓存。

#### reference_data

reference_data 数据包内含 gebco、etopo1/2 及海岸边界等文件，它们是网格生成的必要数据，如果没有 reference_data，将无法生成网格文件。

如果 WW3Tool/meshgen/reference_data 没有找到这些数据文件，那么在第一步生成网格时会弹出一个下载窗口

![](public/resource/README-media/截屏2026-06-29%2017.01.09.png)

点击下载按钮：程序会从自动从 [GitHub Release](https://github.com/ZxyGch/WW3Tool/releases/tag/data) 下载（大约 6.5GB）不需要你手动执行。




#### 网格类型

| 类型     | 适合场景                        | 主要产物                                                   |
| ------ | --------------------------- | ------------------------------------------------------ |
| 矩形网格   | 区域规则、调试、批量事件模拟；目前最稳妥        | `grid.bot`、`grid.obst`、`grid.mask_nobound`、`grid.meta` |
| 矩形嵌套   | 外圈粗、内圈细；关注局部海域又需要远场传播       | `level0/` 至 `levelN/` 各自一套网格文件                         |
| SMC 网格 | 全球或大区域多分辨率格点，需配套 SMC 版本 WW3 | `grid_cell.dat`、`grid_subtr.dat` 等                     |
| 非结构网格  | 复杂岸线、局部高分辨率三角网格             | `grid.ww3`、`unstructured_grid.json`                    |


#### 精度调整

最简单的增大精度方法不是扩大经纬度范围，而是减小控制网格尺度的参数。网格变细后，格点数、计算量和输出文件都会明显增加；每次调整后建议重新执行 `recommend-cfl` 或在 Step 4 重新自动推荐时间步。

| 网格 | 建议优先调整的参数 | 最简单的增大精度方法 | 注意 |
| --- | --- | --- | --- |
| 矩形网格 | `structured.nested.levels[0].dx`、`dy`；GUI 中的 `DX/DY` | 把 `dx/dy` 同比例减小，例如 `0.05 → 0.025` | 经纬两个方向都减半时，水平格点数约变为 4 倍；`DTXY` 通常也要变小 |
| 矩形嵌套 | 最细层 `levels[-1].dx/dy`、最细层 `lon/lat`；必要时增加一层 | 保持外层不变，只把最细层 `dx/dy` 减小，或新增一个更小范围的细层 | 细层必须完全落在上一层内部；谱点要落在最细层内 |
| SMC 网格 | `smc.n_levels`、`smc.dshalw`、`smc.depmin`、`smc.msea` | 增大 `n_levels`，让浅水和近岸区域允许更细单元 | 需要 SMC 版本 WW3；加密范围受水深阈值影响，不能只看 `n_levels` |
| 非结构网格 | `unstructured.hmin`、`hshr`、`hmax`、`nwav`、`dhdx`、`edge_segments` | 先减小 `hmin/hshr`，让近岸和目标区域更细 | `hmin` 是最小尺度，过小会让三角形数量和生成时间快速增加 |

常用经验：

1. 矩形网格最直接：改小 `DX/DY`。
2. 嵌套网格最省算力：只加密最内层，不动外层。
3. SMC 网格优先调 `n_levels` 和浅水阈值。
4. 非结构网格优先调 `hmin/hshr`，其次再调 `hmax/nwav/dhdx`。
5. `coastline_precision` 主要影响海岸线细节，不等价于整体网格分辨率。


#### 网格 yml 参数

对应 params.yml 与 CLI：

```sh
python3 run.py generate-grid  [work_dir_name]                 # 生成网格
python3 run.py recommend-grid [work_dir_name] --coarse        # 使用推荐网格间距
```

```yaml
# ────────────────────────────────────────────────────────────────────
# 网格生成配置（矩形 / SMC / 非结构）。
#   mesh_type – 网格拓扑：'structured' | 'smc' | 'unstructured'。
#   grid_type – 'normal' 表示单层网格；'nested' 表示嵌套网格（仅矩形网格）。
#   gridgen_version – 网格生成后端：'Python' 或 'MATLAB'。
#   reference_data_path – 水深 / 海岸线数据目录；
#                         null 表示按项目默认路径自动查找。
#   lon       – 主网格经度范围 [west, east]，单位：度。
#   lat       – 主网格纬度范围 [south, north]，单位：度。
#   structured.nested.levels – grid_type=nested 时的嵌套层级，从粗到细。
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

关键字段：

| 字段 | 含义 |
| --- | --- |
| `grid.mesh_type` | 网格拓扑：`structured`、`smc`、`unstructured` |
| `grid.grid_type` | 仅矩形网格使用：`normal` 单层，`nested` 嵌套 |
| `grid.lon` | 主网格经度范围 `[west, east]` |
| `grid.lat` | 主网格纬度范围 `[south, north]` |
| `grid.reference_data_path` | 水深/海岸线数据目录；为空时按项目默认路径自动查找 |
| `grid.structured.nested.levels` | 嵌套网格各层，从粗到细；`level0` 是最外层，`levelN` 是最细层 |

#### 结构化矩形网格

由 pygridgen / gridgen 在规则经纬度上生成矩形格点。`grid_type: normal` 时只生成一层，产物直接落在工作目录根；`grid_type: nested` 时按层生成多套网格，见下文。



##### 嵌套网格

![](public/resource/README-media/截屏2026-06-28%2012.46.43.png)
![](public/resource/README-media/截屏2026-06-28%2012.53.13.png)

嵌套用于「外圈粗、内圈细」的多分辨率模拟：外层覆盖大尺度背景，内层在感兴趣区域加密。WW3Tool 采用 WW3 的 ww3_multi 路线，一次积分驱动多层网格（见 §5.5.8、嵌套网格设计与问题分析.md）。

配置要点：

| 项 | 说明 |
|----|------|
| grid.grid_type | 设为 nested 启用嵌套；normal 为单层 |
| grid.structured.nested.levels | 从粗到细的有序列表，levels[0] 为最粗层 level0，levels[-1] 为最细层 levelN；支持 2～99 层 |
| 每层字段 | dx、dy（度）、lon、lat（该层矩形范围） |
| nested_contraction_coefficient | GUI「套娃」辅助：按系数向中心收缩上一层的范围、并减半 dx/dy，自动填下一层；也可在 yml 里逐层手写 |
| 校验 | 细层 dx/dy 须小于粗层；第 k 层地理范围须完全落在第 k−1 层之内 |

生成与目录约定：

- generate-grid 对每一层独立调用 gridgen，输出到 level0/、level1/、…、levelN/。

![](public/resource/README-media/截屏2026-06-28%2014.03.55.png)

- 各层各有 grid.bot、grid.obst、grid.meta 等；强迫场 NetCDF 仍放在工作目录根，各层 prnc 用 ../wind.nc 引用。

- 根目录一份 ww3_multi.nml；谱点模式时 points.list 也在根目录，谱点须落在最细层网格内。

嵌套算例仍处演进中；若 run.log 出现 OUTPUT POINT OUT OF GRID、NBI=0 AND RANK > 1 等，请对照 嵌套网格设计与问题分析.md 检查层间范围、点位与 ww3_multi.nml 配置。



##### yml 参数

单层（grid_type: normal）时 levels 只保留一项即可；嵌套时至少两项。

对应 params.yml 与 CLI：

```sh
python3 run.py workdir nested_demo
# params.yml:
#   grid.grid_type: nested
#   grid.structured.nested.levels: [ level0 粗, level1 细 ]
python3 run.py generate-grid nested_demo
python3 run.py recommend-cfl nested_demo    # 按 level0 格距估算一组时间步写 params（逐层以 Step 4 为准）
python3 run.py prepare-ww3 nested_demo
python3 run.py local-run nested_demo
```

```yml
# 矩形网格参数：
#   bathymetry       – 水深数据集名称（见 presets.structured_bathymetry）。
#   coastline_precision – GSHHG 海岸线精度（full/high/inter/low/coarse）。
#   min_dist         – 相邻网格点的最小距离过滤阈值，单位：km。
#   cut_off          – 陆海掩膜截断阈值；0 表示保留所有海点。
#   lim_bathy        – 基于水深的格点保留阈值，表示单元内湿点比例。
#   lim_val          – 格点分类的掩膜阈值，范围 0–1。
#   split_lim        – 分裂单元阈值；0 表示禁用。
#   lake_tol         – 保留湖泊的最小面积（以格点数计）；更小湖泊会被填充。
#   nested.levels    – 嵌套层级，从粗到细；level0 = levels[0]，最细层 = levels[-1]。
#   nested.nested_contraction_coefficient – GUI 自动套娃时的层间范围收缩系数（≥ 1）。
structured:
  nested:
    nested_contraction_coefficient: 1.3
    levels:
    - dx: 0.05
      dy: 0.05
      lon:
      - 100.0
      - 130.0
      lat:
      - 10.0
      - 30.0
    - dx: 0.025
      dy: 0.025
      lon:
      - 103.4615
      - 126.5385
      lat:
      - 12.3077
      - 27.6923
    - dx: 0.0125
      dy: 0.0125
      lon:
      - 106.1242
      - 123.8758
      lat:
      - 14.0828
      - 25.9172
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

单层时，结构化矩形网格由 gridgen 在工作目录根生成 `grid.obst`、`grid.bot`、`grid.mask_nobound`、`grid.meta`。嵌套时每一层 `levelK/` 下各有同样一套文件。

| 文件 | 说明 |
| --- | --- |
| `grid.bot` | 水深网格，ASCII 文本，尺寸通常为 `Ny × Nx`；后续写入 `ww3_grid.nml` 的 bottom 输入 |
| `grid.mask_nobound` | 陆海掩膜，`0 = 陆地`，`1 = 海洋` |
| `grid.obst` | x/y 方向阻塞率，供 WW3 obstruction 输入使用 |
| `grid.meta` | WW3Tool 记录的网格元信息，包含范围、分辨率、格点数等；Step 4 会据此同步 namelist |



#### 三角形非结构化网格

基于 JIGSAW / NOAA `unst_msh_gen` 生成三角网格，支持深水尺度、近岸尺度、浅水波长加密、水深梯度等参数。非结构网格不使用 `DX/DY`，核心控制量是 `hmax/hmin/hshr`。



##### yml 参数

```yaml
# 非结构（三角形）网格间距参数：
# hmax – 深水区最大单元间距，单位：km。
# hmin – 全域允许的最小单元间距，单位：km。
# hshr – 近岸目标间距，单位：km。
# nwav – 每个单元解析的波长数量。
# dhdx – 随水深梯度变化的网格间距变化率。
# deep_ocean_threshold_m – 深水阈值，水深大于该值时使用 hmax，单位：m。
# margin_deg – 区域边界外扩缓冲，单位：度。
# edge_segments – 海岸线边界分段数量。
# options.data – 可选的掩膜 / 排除区域文件。
# options.command_line_args – 额外传给 JIGSAW 的 CLI 参数。
# options.regional – 区域投影中心（stereo_lon / stereo_lat）。

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

| 文件 | 说明 |
| --- | --- |
| `grid.ww3` | 非结构网格主文件，供 WW3 非结构网格流程使用 |
| `unstructured_grid.json` | 本次生成时解析后的配置，便于复现和缓存定位 |

非结构网格缓存位于 `meshgen/cache/unst/<hash>/`。如果命中缓存，会直接把 `grid.ww3` 复制到工作目录。



##### 网格可视化

![](public/resource/README-media/grid_unst_bathymetry.png)

![](public/resource/README-media/grid_unst_structure.png)



#### SMC 网格

基于 SMCGTools 生成。SMC 网格需要使用支持 SMC 的 WW3 可执行文件和对应 namelist 模板；如果只是普通区域模拟，不建议默认选择 SMC。


##### yml 参数

```yml
# SMC（Spherical Multi-Cell）网格参数：
#   bathymetry       – 水深数据集名称（见 presets.smc_bathymetry）。
#   bathy_convention – 水深数据约定：'elevation' 表示向上为正，'depth' 表示向下为正。
#   n_levels         – 单元尺度加密层数。
#   wlevel           – 水位参考索引。
#   depmin           – 最小水深阈值，浅于该值的单元会被剔除，单位：m。
#   dshalw           – 浅水额外加密的水深阈值，单位：m。
#   generate_boundary_cells – 是否生成开边界虚拟单元。
#   msea             – 海峡中保留的最小单元数。
#   options.input    – 底层输入预处理参数（自动翻转、容差等）。
#   options.grid     – 网格身份与投影参数（全球、北极、原点等）。
#   options.output   – 输出文件命名与格式化参数。
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





### 5.3 Step 2 — 强迫场准备

![](public/resource/README-media/截屏2026-06-28%2011.09.59.png)

Step 2 负责把外部 NetCDF 强迫场导入工作目录，并统一成 WW3Tool 后续步骤能够直接识别的标准文件。支持四类场：风场、流场、水位场、海冰场。

#### GUI 操作逻辑

主页 Step 2 的推荐操作顺序：

1. 点击风场、流场、水位场、海冰场按钮选择 NetCDF 文件。

2. 选择某个文件后，右侧日志会立即显示该文件信息，包括变量、时间范围、经纬度范围等；这一步只读取信息，不会复制、剪切或裁剪文件。

![](public/resource/README-media/截屏2026-06-28%2013.19.18.png)


3. 如果要按范围裁剪，先编辑时间、纬度、经度范围，然后点击"确认裁剪并导入"。时间格式为 `YYYYMMDD`，空间范围为经纬度数值。
4. 如果不裁剪，点击"直接导入，不进行裁剪"。此时会完整复制或剪切原文件到工作目录，再做标准化。

导入模式：

- `复制`：保留原始文件，把处理后的文件写入工作目录。
- `剪切`：导入完成后移走或删除原始文件。裁剪导入时，源文件不会被原样移动到工作目录，而是先生成裁剪后的工作目录文件；成功后再删除源文件。

几个辅助按钮的含义：

- `查看地图`：根据当前 Step 2 的经纬度范围生成区域预览图。
- `查看地图`：显示最多四个强迫场的空间范围，用于检查风、流、水位、海冰覆盖区是否一致。
- `查看所有场文件信息`：把当前已选择的所有强迫场文件信息一次性写入日志。
- 每个强迫场选择按钮右侧的 `×`：清除当前选择；如果指向的是工作目录中已转换的标准强迫场文件，会提示是否删除该文件，并同步清除引用它的场。


#### params.yml 参数

Step 2 相关配置位于 `forcing` 段：

对应 params.yml 与 CLI：

```sh
python3 run.py prepare-forcing [work_dir_name]    # 准备强迫场
```

```yaml
forcing:
  wind: null
  current: null
  level: null
  ice: null
  process_mode: copy        # copy 或 move
  crop_time_range: []       # [start_YYYYMMDD, end_YYYYMMDD]，为空表示不裁剪
  crop_bbox: []             # [west, east, south, north]，为空表示不裁剪
  auto_associate: true      # 一个文件含多个场时，是否自动关联到多个槽位
```

设置页面里的“强迫场配置”提供默认导入方式和自动关联开关。主页打开工作目录时会读取这些默认值；实际导入时仍以主页当前选择和按钮操作为准。


#### 判断强迫场类型

程序检测 NetCDF 内部变量名来判断强迫场类型：

- **风场**：存在 u10/v10、wndewd/wndnwd、uwnd/vwnd 任一对（大小写均匹配）
- **流场**：存在 uo/vo
- **水位场**：存在 zos
- **冰场**：存在 siconc


#### 强迫场标准化处理

```swift
🔄 Rewriting time metadata to WW3-readable char attributes (units + calendar)

✅ Forcing field normalized and saved to: /User/WW3Tool/workSpace/2026-06-29_16-57-02/wind.nc
```

确认导入后，程序会对目标文件执行标准化：

1. 自动识别各类命名变体，例如 `wndewd/wndnwd`、`uwnd/vwnd` 转为风场标准变量，`uo/vo`、`zos`、`siconc` 转为对应强迫场变量。
2. 坐标变量统一命名为 `longitude`、`latitude`、`time`，同时同步维度名和引用这些维度的变量。
3. 输出文件按场类型命名。单场通常为 `wind.nc`、`current.nc`、`level.nc`、`ice.nc`；一个文件包含多种场且开启自动关联时，可能输出 `current_level.nc`、`wind_current_level_ice.nc` 等组合文件。
4. 纬度从大到小时会自动翻转为从小到大，避免 WW3 6.07.1 的 `ww3_prnc` 在规则经纬网下触发 `EXTCDE(32)`。
5. 标准化后的文件供 Step 4 自动生成 `ww3_prnc.nml` 使用，因此后续不需要再根据原始变量名手动改 namelist。


#### 多场文件自动关联

如果一个 NetCDF 文件同时包含多种强迫场，例如流场和水位场在同一个文件里，且 `forcing.auto_associate: true`，程序会检测文件中所有存在的场类型，并把同一个标准化后的文件路径关联到多个 GUI 槽位。

例如：

- 文件同时含 `uo/vo` 和 `zos`，导入后可保存为 `current_level.nc`，GUI 的流场和水位场都指向这个文件。
- 文件同时含风、流、水位、海冰，导入后可保存为 `wind_current_level_ice.nc`，四个槽位都指向同一个文件。

如果关闭自动关联，用户在哪个槽位选择文件，就只按该槽位导入。

#### 工作目录扫描

打开工作目录时，会自动检测是否存在已经标准化处理过的强迫场文件，并在 GUI 中回填对应按钮。扫描主要依据标准文件名和组合文件名，例如 `wind.nc`、`current.nc`、`level.nc`、`ice.nc`、`current_level.nc`、`wind_current_level_ice.nc`。

扫描只负责恢复 Step 1 的网格参数显示；真正生成网格仍然需要用户点击“生成网格”。







### 5.4 Step 3 — 计算模式

计算模式决定 WW3 算一整片海域、只算若干固定点位，还是沿一条移动轨迹算。在 params.yml 的 calc.mode 里设置，GUI 上第三步选择；没有单独的 CLI 子命令，会在 prepare-ww3 或 run-workflow 时自动读取。

![](public/resource/README-media/截屏2026-06-28%2013.03.46.png)

![](public/resource/README-media/截屏2026-06-28%2014.09.11.png)


| 模式      | `calc.mode`      | 适合场景               | 工作目录文件        | 最终常见产物                   |
| ------- | ---------------- | ------------------ | ------------- | ------------------------ |
| 区域尺度计算  | `region`         | 要输出整片网格的波高、周期、方向等场 | 无额外列表文件       | `ww3.YYYY.nc` 等场输出       |
| 二维谱点计算 | `spectral_point` | 验证点的二维谱            | `points.list` | `ww3.YYYY_spec.nc` 等谱点输出 |
| 轨迹计算    | `track`          | 沿船舶、浮标、台风路径等移动轨迹取值 | `track_i.ww3` | `ww3.YYYY_trck.nc` 等航迹输出 |

如果你不了解，用区域尺度计算就行了，这是最常用的。


#### params.yml 参数

Step 3 相关配置位于 `calc` 段。GUI 第三步修改模式、点位或航迹点后，会写回工作目录的 `params.yml`；第四步 `prepare-ww3` 会读取这里的设置，生成 `points.list` 或 `track_i.ww3`。

对应 params.yml 与 CLI：

```sh
# Step 3 没有单独 CLI 子命令；改好 calc 段后执行第四步
python3 run.py prepare-ww3 [work_dir_name]

# 或在完整预处理时自动读取 calc 段
python3 run.py run-workflow [work_dir_name]
```

```yaml
calc:
  mode: spectral_point     # region | spectral_point | track
  points:
  - lon: 114.225
    lat: 15.4798
    name: '0'
  - lon: 115.519
    lat: 20.6623
    name: '1'
  track_points: []
```

使用注意：

1. `region` 模式不需要填写 `points` 或 `track_points`。
2. `spectral_point` 模式至少需要一个点；第四步会据此生成 `points.list`。
3. `track` 模式需要航迹点；第四步会据此生成 `track_i.ww3`。





### 5.5 Step 4 — WW3 配置

> 第四步在做什么？
>
> 前三步已经把风场、网格、计算模式准备好了。第四步根据工作目录里的 params.yml，把 WW3 需要的一整套 namelist 配好。
>
原则很简单：只在模板文件里改和本次算例有关的字段，其余保持 public/nml/ 模板原样，方便你对照官方示例排错。

![](public/resource/README-media/截屏2026-06-28%2016.34.00.png)



#### 5.5.3 按 CFL 推荐时间步

```log
📐 CFL-based timesteps: DXY≈5230 m, Tcfl≈252 s → DTXY=226, DTMAX=678, DTKTH=339, DTMIN=15
```

第四步的「自动配置时间步」会按 CFL 稳定性给出数值积分时间步长的建议，点击确认参数后会写进 ww3_grid.nml。

```swift
✅ Spectral parameters and time steps have been written to ww3_grid.nml:
  SPECTRUM%XFR    = 1.1
  SPECTRUM%FREQ1  = 0.0375
  SPECTRUM%NK     = 35
  SPECTRUM%NTH    = 36

  TIMESTEPS%DTMAX = 678
  TIMESTEPS%DTXY  = 226
  TIMESTEPS%DTKTH = 339
  TIMESTEPS%DTMIN = 15
```

自动配置时间步对应的 CLI 指令：

```sh
# 写入 params.yml 的 ww3_grid.parameters.TIMESTEPS%*
python3 run.py recommend-cfl new                         # 默认 safe，CFL 系数 0.9
python3 run.py recommend-cfl new --mode fast             # 更激进，CFL 系数 1.05
python3 run.py recommend-cfl new --mode faster           # 最激进内置档，CFL 系数 1.15
python3 run.py recommend-cfl new --factor 1.2            # 手动指定 CFL 系数，自动上限 1.25
python3 run.py prepare-ww3 new
```



##### CFL 推荐步长的计算方式

WW3 官方在 ww3_grid.nml 注释里的思路是：波浪在网格上传播时，一个时间步内波群走过的距离不能超过一个网格间距。记：

- $\Delta x$：网格最小间距（米）。结构化/SMC 由 dx、dy 和纬度换算；非结构用 hmin（km）直接当最细尺度。
- $f_1$：谱最低频率 SPECTRUM%FREQ1（Hz）。
- 深水近似下，最低频波的群速度 $C_g \approx g / (4\pi f_1)$（$g=9.8\,\mathrm{m/s^2}$）。

则 CFL 时间尺度：


$$
T_{\mathrm{cfl}} = \frac{\Delta x}{C_g} = \frac{\Delta x \cdot f_1 \cdot 4\pi}{g}
$$

WW3Tool 在此基础上取整数秒，并级联得到：

| 模式 | CFL 系数 | 说明 |
|------|----------|------|
| safe | 0.90 | 默认保守设置 |
| fast | 1.05 | 更激进，减少步数，适合已有经验的复跑 |
| faster | 1.15 | 最激进内置档，需关注稳定性 |
| --factor X | 自定义，最高 1.25 | 直接指定 CFL 乘子 |

| 参数 | 含义 | 推荐关系 |
|------|------|----------|
| DTXY | 空间传播时间步 | $\approx \mathrm{CFL 系数} \times T_{\mathrm{cfl}}$ |
| DTMAX | 积分主时间步上限 | $\approx 3 \times \mathrm{DTXY}$ |
| DTKTH | 谱源汇时间步 | 无强流时 $\approx \mathrm{DTMAX}/2$；有强流时更细 |
| DTMIN | 最小时间步 | 默认 15 s，一般不动 |

简单理解：

- `DTXY` 控制波在空间网格上的传播步长，是 CFL 稳定性最直接相关的参数；网格越细，它通常越小。
- `DTMAX` 是 WW3 主积分允许使用的最大时间步，通常随 `DTXY` 成比例放大。
- `DTKTH` 控制谱空间方向/波数相关过程的更新时间步；有强流、强折射或复杂地形时应更保守。
- `DTMIN` 是自适应源项积分的最小步长下限，一般不作为提高精度的首要调节项。

嵌套网格时每一层 dx/dy 不同，会逐层重算 CFL：细网格间距小 → DTXY 更小 → 同样模拟时长内步数更多，计算更重。这和 ww3_multi.nml 里进程分配有关（见 5.5.7）。

若网格很粗或 FREQ1 很小，算出的步长会偏大；若仍不稳定，应减小 dx/dy 或略减小推荐系数，而不是盲目加大 DTMAX。




#### 5.5.1 复制模板与写运行脚本

```log
✅ Copied server.sh, local.sh to the current work directory
✅ Copied 8 NML template files to current work directory
```

- 从 public/6.07_nml/ 或 public/7.14_nml/（根据你的 NML Version 选择）复制 ww3_grid.nml、ww3_prnc.nml、ww3_shel.nml、ww3_ounf.nml 等到工作目录。

- 从 public/scripts/ 复制  local.sh 和 server.sh。算例具体怎么一步步跑起来，见 §5.5.9。

他们决定了 WW3 的程序（例如 ww3_grid、ww3_shel）执行流程， local.sh 是在本地运行的脚本， server.sh 是在 Slurm 运行的脚本。


#### 5.5.2 把网格写进 ww3_grid.nml

Step 1 生成的网格文件需要 Step 4  配置 `ww3_grid.nml` 的网格相关的参数才能让 WW3 能正确读取。不同网格类型写法不一样：

```log
✅ Successfully synced grid.meta parameters to ww3_grid.nml:
  GRID%TYPE  = 'RECT'
  GRID%COORD = 'SPHE'
  GRID%CLOS  = 'NONE'

  RECT%NX    = 401
  RECT%NY    = 401
  RECT%SX    = 0.050000000000
  RECT%SY    = 0.050000000000
  RECT%X0    = 110.0000
  RECT%Y0    = 10.0000
  DEPTH%SF   = 0.001000
  OBST%SF    = 0.010000
```

```log
✅ Unstructured mesh: updated ww3_grid.nml and namelists.nml (&RECT_NML, &DEPTH_NML, &MASK_NML, &OBST_NML blocks commented with !):
  GRID%TYPE     = 'UNST'
  UNST%FILENAME = 'grid.ww3'

  FLAGTR        = 0
```

```log
✅ SMC mesh: updated ww3_grid.nml (template &DEPTH_NML, &MASK_NML, &OBST_NML commented with !; appended &DEPTH_NML DEPTH%SF):
  GRID%TYPE          = 'RECT'

  RECT%NX            = 570
  RECT%NY            = 598
  RECT%SX            = 0.033332824707
  RECT%SY            = 0.033332824707
  RECT%X0            = 109.9983
  RECT%Y0            = 9.9985
  RECT%SF            = 1.00
  RECT%SF0           = 1.00
  SMC%MCELS%FILENAME = 'grid_cell.dat'
  SMC%ISIDE%FILENAME = 'grid_iside.dat'
  SMC%JSIDE%FILENAME = 'grid_jside.dat'
  SMC%SUBTR%FILENAME = 'grid_subtr.dat'
  SMC%BUNDY%FILENAME = 'grid_bundy.dat'
  DEPTH%SF           = -1.0
✅ Updated namelists.nml:
  NBISMC = 341 (grid_bundy.dat)
  LvSMC  = 2
```

矩形网格主要是“把范围、分辨率、水深文件写进去”；非结构网格主要是“告诉 WW3 直接读 `grid.ww3`”；SMC 网格则是“写入包络矩形 + SMC cell/side/boundary 文件”。这三类都由第四步自动完成。




#### 5.5.4 时间与输出步长

```log
✅ Updated ww3_ounp.nml:
  POINT%TIMESTART  = '20250103 000000'
  POINT%TIMESTRIDE = '3600'
  POINT%TIMESPLIT  = 0
✅ Updated ww3_ounf.nml:
  FIELD%TIMESTART  = '20250103 000000'
  FIELD%TIMESTRIDE = '3600'
  FIELD%TIMESPLIT  = 0
✅ Updated ww3_shel.nml:
  DOMAIN%START            = '20250103 000000'
  DOMAIN%STOP             = '20250105 235959'
  OUTPUT%FIELD%TIMESTART  = '20250103 000000'
  OUTPUT%FIELD%TIMESTRIDE = '3600'
  DATE%FIELD              = '20250103 000000' '3600' '20250105 235959'
  DATE%RESTART%START      = '20250103 000000'
  DATE%RESTART%STOP       = '20250105 235959'

  TYPE%POINT%FILE         = 'points.list'
  DATE%POINT              = '20250103 000000' '3600' '20250105 235959'
  DATE%BOUNDARY           = '20250103 000000' '86400' '20250105 235959'
✅ Modified ww3_prnc.nml:
  FORCING%TIMESTART = '20250103 000000'
  FORCING%TIMESTOP  = '20250105 235959'
```

对应的 yml 参数：

```yaml
ww3:
  start_date: "20250103"
  end_date: "20250105"
  output_step: "3600"   # 输出间隔，秒
```

这些时间字段不是重复配置，而是分别给 WW3 的不同程序使用：

| 写入位置                                          | 作用                                                               |
| --------------------------------------------- | ---------------------------------------------------------------- |
| `ww3_shel.nml` 的 `DOMAIN%START/STOP`          | 控制主模式积分从什么时候开始、什么时候结束，是整个模拟的总时间窗                                 |
| `ww3_shel.nml` 的 `DATE%FIELD`                 | 控制场输出在主积分过程中什么时候写出、按多长间隔写出，步长越小，`out_grd.ww3` 和后续 `ww3.*.nc` 越大。 |
| `ww3_ounf.nml` 的 `FIELD%TIMESTART/TIMESTRIDE` | 控制 `ww3_ounf` 从中间文件导出 NetCDF 场结果的起始时间和输出间隔                       |
| `ww3_ounp.nml` 的 `POINT%TIMESTART/TIMESTRIDE` | 二维谱点计算时，控制谱点 NetCDF 的导出起始时间和输出间隔                                 |
| `ww3_prnc.nml` 的 `FORCING%TIMESTART/TIMESTOP` | 控制强迫场预处理读取哪一段时间，通常应覆盖主积分时间窗                                      |


#### 5.5.5 启动方式与热启动

第四步「时间设置」下方可以选择**冷启动**或**热启动**。新算例一律选冷启动；只有工作目录里已经有一次（或多次）算完留下的 `restart*.ww3`，才需要热启动。

**冷启动**走完整流程：`ww3_strt` 生成初始海浪场 → `ww3_shel` 从你在第四步填的**起始日期**开始积分。

**热启动**跳过 `ww3_strt`，直接拿上一次算出的海浪状态接着往后积。适合任务拆段、服务器中断后续算、或先 spin-up 再正式模拟。

##### 第四步界面上有什么

| 界面项 | 冷启动 | 热启动 + 自动最新 | 热启动 + 手动 |
| --- | --- | --- | --- |
| 启动方式 | 冷启动 | 热启动 | 热启动 |
| Restart 日期 | 灰掉 | 显示「自动最新」 | 填 `YYYYMMDD` 或 `YYYYMMDD HHMMSS` |
| Restart 文件 | 灰掉 | 灰掉 | 可选填 `restart036.ww3` 等 |
| 起始日期 | 可编辑 | **只读**（仍表示整段模拟的日历起点） | 只读 |
| 结束日期 | 可编辑 | 可编辑 | 可编辑 |

点「确认参数」后，工具会把你的选择写进工作目录的 `params.yml`，并按 §5.5.4 把**起始日期、结束日期、输出步长**同步进各 nml。其中 `ww3_shel.nml` 里：

- `DOMAIN%START` / `DOMAIN%STOP`：整段模拟的起止（此时 `START` = 起始日期 00:00:00）
- `DATE%FIELD` 等：场输出的起止与间隔（间隔 = 第四步的**输出步长**）
- `DATE%RESTART`：冷启动时**每隔多久写一个 restart 文件**（起点 = 起始日期，步长 = 输出步长）

强迫场时间（`ww3_prnc.nml` 的 `FORCING%TIMESTART/TIMESTOP`）同样按起始/结束日期写入，须覆盖你要积分的整段日历。



##### 真正开算时发生什么（自动最新）

本机点「本地运行」，或服务器上传后点「提交计算任务」，工作目录里的 `local.sh` / `server.sh` 会**最先**处理热启动，然后才跑 `ww3_grid`。对普通网格，顺序是：

1. **找 checkpoint**  
   先在工作目录找带时间戳的文件，如 `20250104.120000.restart.ww3`（v7.14 ）。  
   若没有，再找编号最大的 `restart071.ww3` 这类文件（v6.07.1 ）。此时时刻不能从文件名读，工具会根据 `ww3_shel.nml` 里**第四步已写好**的 `DATE%RESTART` 日程反推，例如起点 `20250103 000000`、步长 `3600`、文件 `restart071.ww3` → 对应 `20250105 230000`。

2. **复制为 `restart.ww3`**  
   `ww3_shel` 只认这个名字的初始场文件。

3. **改 `ww3_shel.nml` 的积分起点**  
   把 `DOMAIN%START`、`DATE%FIELD` 等**输出相关**起始时刻改成上一步算出的 checkpoint 时刻。  
   **`DATE%RESTART` 不改**——它仍描述「每隔多久写下一个 restart」，与冷启动时第四步设的一致。

4. **跳过 `ww3_strt`，直接跑 `ww3_shel`**  
   从 checkpoint 时刻积到 `DOMAIN%STOP`（结束日期 23:59:59）。

`run.log` 里通常能看到：

```log
✅ Auto Latest restart: restart071.ww3 -> restart.ww3 (20250105 230000)
⏭️ Restart mode: skip ww3_strt, start from 20250105 230000
```

##### 手动指定 checkpoint（不用自动最新）

关掉「自动最新」后，须填 **Restart 日期**；**Restart 文件**可选。

工具按这个顺序找文件：

1. 若填了 Restart 文件（如 `restart036.ww3`）→ 直接用；
2. 否则按 Restart 日期找 `YYYYMMDD.HHMMSS.restart.ww3`；
3. 再否则按 `DATE%RESTART` 日程反查 `restartNNN.ww3`（时刻须正好落在日程格点上）。

只填日期 `20250104` 会当作 `20250104 000000`。

##### 工作目录里会出现哪些 restart 文件

| 样子                                  | 怎么来的                              | 时刻怎么知道                          |
| ----------------------------------- | --------------------------------- | ------------------------------- |
| `restart001.ww3`、`restart002.ww3` … | 6.07 冷启动/积分时按 `DATE%RESTART` 间隔写出 | 用 `DATE%RESTART` 起点 + 编号 × 步长推算 |
| `20250104.120000.restart.ww3`       | 7.14 开启 `DATE%RESTART2` 时写出       | 文件名里自带                          |

**`restart.ww3`** 不是第四次写出物，而是**每次开算前**从某个 checkpoint 复制来的「本次要用的初始场」。冷启动时由 `ww3_strt` 生成；热启动时由运行脚本从 checkpoint 复制。

若多次热启动后，较早的 `restartNNN.ww3` 可能被覆盖，编号与内嵌时刻会对不上，`ww3_shel` 会报 `CONFLICTING TIMES`。这时应改用手动指定 Restart 文件，或换用带时间戳的 checkpoint。

##### 嵌套网格

嵌套算例每层目录 `level0/`、`level1/` … 各自有 restart；热启动时各层须同一时刻。自动最新在嵌套模式下**只认带时间戳的 checkpoint**（如 `20250104.120000.restart.level2`），暂不支持用 `restartNNN.ww3` 反推。改的是根目录 `ww3_multi.nml` 里的积分起点，而不是各层 `ww3_shel.nml`。

##### 使用注意

- checkpoint 须与当前网格、谱参数、WW3 版本一致，否则读不进去。
- 第四步的**起始日期**在热启动时仍表示「这一段模拟从日历哪天算起」、强迫场从哪天读；**真正从哪一刻接着积**由 checkpoint 决定，并在开算时写进 `DOMAIN%START`。




#### 5.5.6 谱分区输出方案

![](public/resource/README-media/截屏2026-06-28%2019.03.05.png)

在设置页可以配置谱分区输出方案，你可以在这里新增、修改、删除方案。

```log
✅ Modified spectral partition output scheme in ww3_shel and ww3_ounf:
  TYPE%FIELD%LIST = 'HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS EF'
  FIELD%LIST      = 'HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS EF'
```

第四步谱分区输出方案写入 ww3_shel.nml 和 ww3_ounf.nml 。嵌套时还会同步到 ww3_multi.nml 的 ALLTYPE%FIELD%LIST。

对应的 yml 参数：

```swift
ww3:
  output_scheme:
    use: with_spectrum
    standard: HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS
    with_spectrum: HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS EF
```



#### 5.5.7 强迫场开关与多套 prnc

![](public/resource/README-media/截屏2026-06-28%2019.06.49.png)

当第二步导入了多个强迫场，那么在第四步会显示可选的强迫场多选，其中风场是必选的，其他强迫场可以选择是否使用。

在确认参数时，会根据强迫场生成不同的 ww3_prnc.nml

```log
✅ Copied and modified ww3_prnc_current.nml:
  FORCING%FIELD%CURRENTS = T
  FILE%FILENAME          = 'current_level.nc'
  FILE%VAR(1)            = 'uo'
  FILE%VAR(2)            = 'vo'
✅ Copied and modified ww3_prnc_level.nml:
  FORCING%FIELD%WATER_LEVELS = T
  FILE%FILENAME              = 'current_level.nc'
  FILE%VAR(1)                = 'zos'
```

默认的  ww3_prnc.nml 是处理风场的，由于 ww3_prnc 一次只能处理一个 nml ，因此我们复制了风场的   ww3_prnc.nml ，然后修改其中的变量，最终在 ww3_prnc 运行的时候我们还会更改 nml 的名字以满足 ww3_prnc  的要求，这会在 local.sh 或者 server.sh 中自动完成。



#### 5.5.8 嵌套网格

![](public/resource/README-media/截屏2026-06-28%2019.21.54.png)


如果当前是嵌套网格，那么 WW3Tool  会在工作目录根下放 ww3_multi.nml 和 points.list（谱点模式）；各层 level0/、level1/… 各有自己的 ww3_grid.nml、mod_def 等。

![](public/resource/README-media/截屏2026-06-28%2022.40.04.png)


##### ww3_multi.nml

```nml
&INPUT_GRID_NML
  INPUT(1)%NAME                  = 'wind'
  INPUT(1)%FORCING%WINDS         = T

  INPUT(2)%NAME                  = 'current'
  INPUT(2)%FORCING%CURRENTS      = T

  INPUT(3)%NAME                  = 'level'
  INPUT(3)%FORCING%WATER_LEVELS  = T

  INPUT(4)%NAME                  = 'ice'
  INPUT(4)%FORCING%ICE_CONC      = F

  INPUT(5)%NAME                  = 'ice1'
  INPUT(5)%FORCING%ICE_PARAM1    = F
/

&MODEL_GRID_NML

  MODEL(1)%NAME                  = 'level0'
  MODEL(1)%FORCING%WINDS         = 'native'
  MODEL(1)%FORCING%CURRENTS      = 'native'
  MODEL(1)%FORCING%WATER_LEVELS  = 'native'
  MODEL(1)%FORCING%ICE_CONC      = 'no'
  MODEL(1)%FORCING%ICE_PARAM1    = 'no'
  MODEL(1)%RESOURCE              = 1 1 0.00 0.08 F

  MODEL(2)%NAME                  = 'level1'
  MODEL(2)%FORCING%WINDS         = 'native'
  MODEL(2)%FORCING%CURRENTS      = 'native'
  MODEL(2)%FORCING%WATER_LEVELS  = 'native'
  MODEL(2)%FORCING%ICE_CONC      = 'no'
  MODEL(2)%FORCING%ICE_PARAM1    = 'no'
  MODEL(2)%RESOURCE              = 2 1 0.08 0.24 F

  MODEL(3)%NAME                  = 'level2'
  MODEL(3)%FORCING%WINDS         = 'native'
  MODEL(3)%FORCING%CURRENTS      = 'native'
  MODEL(3)%FORCING%WATER_LEVELS  = 'native'
  MODEL(3)%FORCING%ICE_CONC      = 'no'
  MODEL(3)%FORCING%ICE_PARAM1    = 'no'
  MODEL(3)%RESOURCE              = 3 1 0.24 1.00 F
/
```

`ww3_multi.nml` 把各嵌套层串成一次 `mpirun ww3_multi` 积分。`MODEL_GRID_NML` 里每个 `MODEL(i)%NAME` 对应一层目录（如 `level2`），并经由 `MODEL(i)%RESOURCE` 声明该层在嵌套与 MPI 并行中的角色。

`MODEL(i)%RESOURCE` 写成一行五个字段，等价于 ：

| 字段           | 含义                                                                                                       |
| ------------ | -------------------------------------------------------------------------------------------------------- |
| `RANK_ID`    | **嵌套层级序号**：`level0`（最粗）= 1，向细层递增。。                                                                       |
| `GROUP_ID`   | MPI 进程组号；WW3Tool 默认各层均为 `1`（同一通信域内跑 multi-grid）。                                                         |
| `COMM_FRAC`  | **进程份额区间** `[下界, 上界]`，取值 0–1，各层区间首尾相接且覆盖全体 MPI 进程。例如总进程 48、`0.24 1.00` 表示最细层约占用 24%–100% 的进程（约 37–48 个）。 |
| `BOUND_FLAG` | 是否输出该层供细层嵌套用的边界文件 `nest.<NAME>`；WW3Tool 默认 `F`。                                                          |

WW3Tool 在 Step 4 会按各层 `ww3_grid.nml` 中的格点数（`RECT%NX × NY`）和传播步 `TIMESTEPS%DTXY` 估算相对计算量 `点数 / DTXY`，再自动写入 `COMM_FRAC`。




##### 同强迫场

强迫场文件放在根目录，各层 ww3_prnc.nml 用 ../wind.nc 引用。

```log
✅ Modified ww3_prnc.nml:
  FORCING%FIELD%WINDS = T
  FILE%FILENAME       = '../wind.nc'
  FILE%VAR(1)         = 'u10'
  FILE%VAR(2)         = 'v10'

✅ Copied and modified ww3_prnc_current.nml:
  FORCING%FIELD%CURRENTS = T
  FILE%FILENAME          = '../current_level.nc'
  FILE%VAR(1)            = 'uo'
  FILE%VAR(2)            = 'vo'

✅ Copied and modified ww3_prnc_level.nml:
  FORCING%FIELD%WATER_LEVELS = T
  FILE%FILENAME              = '../current_level.nc'
  FILE%VAR(1)                = 'zos'
```



##### 二维谱点计算

```
&DOMAIN_NML
  DOMAIN%NRINP  = 0
  DOMAIN%NRGRD  = 3
  DOMAIN%UNIPTS = F
  DOMAIN%FLGHG1 = T
  DOMAIN%FLGHG2 = T
  DOMAIN%START  = '20250103 000000'
  DOMAIN%STOP   = '20250105 235959'
/

&OUTPUT_TYPE_NML
  ALLTYPE%FIELD%LIST     = 'HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS EF'
  ALLTYPE%POINT%FILE     = 'points.list'
  ALLTYPE%POINT%NAME     = 'level2'
/
```

WW3Tool 采用 `DOMAIN%UNIPTS = F`（不合并各层谱点 raw）。

`points.list` 只在工作目录根目录生成一份，谱点坐标须落在最细层 `levelN` 网格内。`ww3_multi` 积分后，有效谱点 raw 为根目录的 `out_pnt.<最细层 MODEL%NAME>`（三层嵌套例：`out_pnt.level2`）；

`local.sh` / `server.sh` 会将其移入 `levelN/out_pnt.ww3`，再于最细层目录执行 `ww3_ounp` 导出 NetCDF。粗层不单独维护谱点列表，也不使用 `UNIPTS = T` 的统一点输出路径。



##### 各层自动 CFL 时间步

嵌套各层的 `dx` / `dy` 不同（`level0` 最粗、`levelN` 最细），**传播时间步不能共用一套**：CFL 要求 `DTXY ∝ Δx`，若细层仍用粗层的 `DTXY`，细网格会数值不稳定。

Step 4 在嵌套模式下对 **每一层** `level0/`、`level1/`、… 依次处理时，会在写入该层 `ww3_grid.nml` 的谱参数与 `grid.meta` 同步之后，**自动**调用 CFL 重算（`TIMESTEPS%DTXY`、`DTMAX`、`DTKTH`、`DTMIN`），写回**该层目录**下的 `ww3_grid.nml`

```log
✅ Recomputed CFL timesteps: DTXY=189, DTMAX=567, DTKTH=284 (bathy Cg=24.9m/s)
```




#### 5.5.9 local.sh 与 server.sh：算例是怎么跑起来的

第四步点「确认参数」时，工具会把 `public/scripts/` 里的 `local.sh`、`server.sh` 复制到工作目录。它们不是 WW3 本身，而是**按固定顺序调用** `ww3_grid`、`ww3_prnc`、`ww3_shel` 等程序的壳脚本；所有屏幕输出追加进同目录的 `run.log`。某一步失败就停，并在目录里放一个空的 `fail` 文件；全部跑完则放 `success`。

本机调试走 `local.sh`（Step 6「本地运行」或 `python3 run.py local-run`）；上服务器走 `server.sh`（先上传，再 Step 6「提交计算任务」或 `python3 run.py submit`）。**两边调用的 WW3 步骤完全一样**，差别只是在哪里跑、用几核、PATH 指向哪套编译版本（见文末对比）。

脚本启动时会读工作目录里的 `params.yml`：里面的**网格类型**决定走普通网格还是嵌套分支；**启动方式**（冷/热）决定要不要先处理 restart、要不要跑 `ww3_strt`。这些值都是第四步写进去的，脚本不会自己猜。

##### 普通网格：从点运行到出 NetCDF

下面是一条**冷启动**的完整链路。热启动只是在最前面多几步、并跳过 `ww3_strt`，其余相同。

**0. 热启动预处理（仅热启动）**  
若第四步选了热启动，脚本在一切之前先：在工作目录找最新 checkpoint → 复制为 `restart.ww3` → 把 `ww3_shel.nml` 里积分/输出的起始时刻改成 checkpoint 时刻（详见 §5.5.5）。冷启动跳过此步。

**1. `ww3_grid`**  
读 `ww3_grid.nml`（第四步根据 Step 1 网格写入）和 `grid.bot` 等，生成 `mod_def.ww3`。后面所有步骤都依赖它。

**2. `ww3_prnc`（可能有多次）**  
读 `ww3_prnc.nml` 及第二步导入的 NetCDF 强迫场，生成 `wind.ww3` 等二进制强迫。WW3 一次只处理一种强迫，所以若第四步勾了流场、水位等，脚本会临时改名 nml，按 **风 → 流 → 水位 → 海冰** 顺序逐个跑（见 §5.5.7 日志）。

**3. `ww3_strt`（仅冷启动）**  
生成初始海浪谱，写出 `restart.ww3`。热启动时目录里已有上一步复制好的 `restart.ww3`，日志里会出现 `skip ww3_strt`。

**4. `ww3_shel`（主积分）**  
读 `mod_def.ww3`、强迫文件、`restart.ww3`、`ww3_shel.nml`，从 `DOMAIN%START` 积到 `DOMAIN%STOP`，写出 `out_grd.ww3` 等中间结果；并按 `DATE%RESTART` 间隔继续写出 `restartNNN.ww3` 供下次热启动。  
脚本优先 `mpirun` 并行；若本机 MPI 报错，会自动再试一次单进程 `ww3_shel`。

**5. 导出（按需）**  
- 有 `points.list`（二维谱点，第四步生成）→ `ww3_ounp` → `ww3.*_spec.nc`  
- 有 `track_i.ww3`（轨迹模式）→ `ww3_trnc`  
- 最后几乎总会跑 `ww3_ounf`，把 `out_grd.ww3` 转成 `ww3.YYYY.nc` 场结果  

**6. `success`**  
表示整条链路跑通。

```text
[热启动] 找 checkpoint → restart.ww3 → 改 ww3_shel.nml 起点
    ↓
ww3_grid → ww3_prnc（×N 种强迫）→ ww3_strt 或跳过
    ↓
mpirun ww3_shel
    ↓
ww3_ounp? → ww3_trnc? → ww3_ounf
    ↓
success
```

##### 嵌套网格：多一层目录结构

嵌套算例没有单独的根目录 `ww3_shel`，而是：

1. 对 **每一层** `level0/`（最粗）… `levelN/`（最细）分别跑 `ww3_grid` → `ww3_prnc` → `ww3_strt`（热启动则各层跳过 strt）；  
2. 把各层的 `mod_def.ww3`、`restart.ww3`、`wind.ww3` 等搬到根目录，改名为 `mod_def.level0`、`restart.level0` … 供 `ww3_multi` 使用；  
3. 在根目录 `mpirun ww3_multi`（读第四步写好的 `ww3_multi.nml`）做一次多层耦合积分；  
4. 把最细层 `levelN` 的 `out_grd.*`、`out_pnt.*` 移回该层目录，在那里跑 `ww3_ounp` / `ww3_trnc` / `ww3_ounf`。

强迫场 NetCDF 放在根目录，各层 `ww3_prnc.nml` 用 `../wind.nc` 引用（§5.5.8）。

##### local.sh 和 server.sh 有什么不同

对你而言，**算哪几步是一样的**；不同在于「在哪儿、用谁的 CPU、日志打到哪里」：

| | 本机 `local.sh` | 服务器 `server.sh` |
| --- | --- | --- |
| 怎么启动 | Step 6 本地运行 | 上传后 Step 6 提交；脚本若不在 Slurm 作业里会先 `sbatch` 自己 |
| 用几核 | 默认本机全部逻辑核；终端可设 `WW3_MPI_NPROCS=8` | 与第五步「确认 Slurm 配置」写入的核数一致 |
| WW3 程序从哪来 | 第四步选的**本机 ST**，走系统 PATH | 第五步把**服务器 ST** 路径写进脚本头部 `export PATH=...` |
| 日志 | 终端可见，同时写入 `run.log` | 只写入服务器上的 `run.log`，需 `download-log` 拉回 |
| 跑完怎么知道 | 看目录里 `success` / `fail` | 同上；`check-status` 查远程这两个文件 |

**提交前 checklist：** 第四步已确认参数（namelist 和脚本是最新的）→ `upload --confirm` 同步到服务器 → 第五步已确认 Slurm（`server.sh` 头信息与队列匹配）→ 再 submit。`submit` **不会**重新生成 nml，也**不会**自动上传。

##### 出错了怎么查

打开工作目录的 `run.log`，搜 `Running` 分隔线，最后一条通常是失败步骤，例如 `Running ww3_prnc`、`Running mpirun ww3_shel`。

热启动问题多在**最前面**：搜 `Auto Latest restart`、`Restart file`、`skip ww3_strt`。若 `ww3_shel` 报 `CONFLICTING TIMES`，说明复制的 `restart.ww3` 内嵌时刻与 `ww3_shel.nml` 的 `DOMAIN%START` 不一致，见 §5.5.5「手动指定 checkpoint」。

本机快速试跑：

```sh
python3 run.py local-run <工作目录名>
```

服务器标准流程：

```sh
python3 run.py upload --confirm <工作目录名>
python3 run.py submit <工作目录名>
python3 run.py check-status <工作目录名>
python3 run.py download-log <工作目录名>
```


### 5.6 Step5 —  Slurm 配置

#### 服务器配置

你需要先配置服务器的连接方式才能连接服务器， WW3Tool 提供了三种 SSH 方式。

![](public/resource/README-media/截屏2026-06-28%2020.48.27.png)

其中服务器路径是用于默认存储上传的工作目录位置。

三种 SSH 模式的区别：

SSH 配置名称模式使用 `server.ssh_config_host`，适合本机已经在 `~/.ssh/config` 配好 Host 别名的情况，也是推荐方式。程序连接时直接使用这个 Host 别名，`host/user/password/key_file` 可以为空。

```yaml
server:
  ssh_config_host: SHOU
  host: null
  port: 22
  user: null
  password: null
  key_file: null
  default_remote_dir: /public/home/weiyl001/user/gongchuheng/
  remote_dir: ''
```

密码登录模式使用 `server.host`、`server.port`、`server.user`、`server.password`，适合临时服务器或没有私钥时使用。它配置最直观，但密码不适合长期写在配置文件里。

```yaml
server:
  ssh_config_host: ''
  host: <server-host>
  port: 22
  user: <server-user>
  password: <server-password>
  key_file: null
  default_remote_dir: /public/home/weiyl001/user/gongchuheng/
  remote_dir: ''
```

![](public/resource/README-media/截屏2026-06-29%2010.24.45.png)


私钥文件登录模式使用 `server.host`、`server.port`、`server.user`、`server.key_file`，适合固定服务器和自动化运行。`key_file` 指向本机 SSH 私钥路径；如果同时有 `password`，连接逻辑会优先尝试可用私钥。

```yaml
server:
  ssh_config_host: ''
  host: <server-host>
  port: 22
  user: <server-user>
  password: null
  key_file: /Users/<name>/.ssh/id_rsa
  default_remote_dir: /public/home/weiyl001/user/gongchuheng/
  remote_dir: ''
```

![](public/resource/README-media/截屏2026-06-29%2010.25.12.png)

优先级上，只要填写了 `server.ssh_config_host`，连接时会先解析 `~/.ssh/config`，再补充 `params.yml` 中显式填写的密码或私钥字段。




#### 任务列表与空闲资源列表

这些列表的作用不用多说，当然是为了更好的利用计算资源了。

![](public/resource/README-media/截屏2026-06-28%2021.03.35.png)

GUI 连接服务器后会自动轮询任务列表和空闲资源，背后用的是 Slurm 自带指令。

任务列表显示作业 ID、分区、任务名、状态、运行时间、节点数、核心数和原因/节点。GUI 使用的服务器指令是：

```sh
squeue -o '%i %P %j %T %M %D %C %R' -h
```

对应 CLI：

```sh
python3 run.py queue-status
```

空闲资源列表按节点读取状态、CPU 分配情况、分区和内存，再解析出空闲节点、空闲核心和可用分区。GUI 使用的服务器指令是：

```sh
sinfo -h -N -o '%N|%T|%c|%C|%P|%m|%e'
```

对应 CLI：

```sh
python3 run.py slurm-idle <workdir>
```

注意：`queue-status` 的 CLI 输出使用 `squeue -l`，适合快速看完整队列文本；主页任务列表为了做成卡片，会使用更固定的 `squeue -o ...` 格式。



#### Slurm 配置

下面关于 Slurm 的配置只是提供一个默认值，在主页第五步连接服务器后可以自行修改。

![](public/resource/README-media/截屏2026-06-28%2020.48.51.png)

```log
✅ Updated server.sh:
  #SBATCH -J    = 2026-06-28_21-10-11
  #SBATCH -p    = CPU6240R
  #SBATCH -n    = 48
  #SBATCH -N    = 1
  #SBATCH --mem = 360G
  #SBATCH -w    = -
  #SBATCH --time = -
  MPI_NPROCS    = 48
  ST            = ST2
  export PATH   = /public/home/weiyl001/software/wavewatch3/model/exe
```

在第五步我们有自动解析服务器分区的功能，设置页面的服务器分区只是提供一个兜底的默认值，只有在无法正确解析服务器分区列表的情况下，才会使用。

如果解析的服务器分区列表包含这个默认值，那么会默认使用该分区。

第五步的 Slurm 参数会写回工作目录的 `params.yml`，点击“确认 Slurm 配置”或执行 `confirm-slurm` 后，会刷新 `server.sh` 顶部的 `#SBATCH` 行和 `MPI_NPROCS`：

- `slurm.job_name`：作业名，写入 `#SBATCH -J`。为空时使用工作目录名。
- `slurm.partition`：分区，写入 `#SBATCH -p`。GUI 连接服务器后会从 `sinfo` 解析分区列表。
- `slurm.nodes`：节点数，写入 `#SBATCH -N`。
- `slurm.cores`：总核心数，写入 `#SBATCH -n` 和脚本内 `MPI_NPROCS`。
- `slurm.nodelist`：指定节点，非必填；多个节点用空格填写，例如 `node01 node02`，写入 `#SBATCH -w node01,node02`。为空时不限制节点。
- `slurm.time`：最长运行时间，非必填；写入 `#SBATCH --time`，可用 Slurm 原生格式，例如 `2-00:00:00` 或 `48:00:00`。为空时保留模板脚本中的默认值。
- `slurm.mem`：内存，非必填；写入 `#SBATCH --mem=`。GUI 会根据空闲资源给出建议值，也可以手动清空或修改。
- `slurm.server_st.use`：服务器 WW3 版本，写入 `export PATH=...:$PATH`，决定服务器运行时使用哪一套 WW3 可执行程序。

这里的 `nodes` 和 `cores` 需要互相匹配。例如申请 `nodes: 2`、`cores: 96` 通常表示 2 个节点合计 96 核；如果还指定 `nodelist: node01 node02`，那么 Slurm 会尽量把任务投到这两个节点上。是否一定能分配成功取决于服务器当前空闲资源和分区策略。



#### CLI 总例子

Step5 只负责连接服务器、查看资源、确认 Slurm 参数并刷新 `server.sh`，不负责上传和提交。上传与提交放在 Step6。

对应 params.yml 与 CLI：

```yaml
server:
  # 优先使用 ~/.ssh/config 里的 Host 别名；使用它时 host/user/password/key_file 可以为空
  ssh_config_host: SHOU
  host: null
  port: 22
  user: null
  password: null
  key_file: null

  # 上传时使用的远程工作根目录；remote_dir 通常由程序按工作目录名自动生成
  default_remote_dir: /public/home/weiyl001/user/gongchuheng/
  remote_dir: ''

slurm:
  # job_name 为空时默认使用工作目录名
  job_name: null
  partition: CPU6240R
  nodes: 1
  cores: 48
  nodelist: null        # 非必填；多个节点用空格分开，如 "node01 node02"
  time: null            # 非必填；如 "2-00:00:00" 或 "48:00:00"
  mem: 190G

  # server_st.use 是当前选中的服务器 WW3 版本
  server_st:
    use: ST2
    ST2: /public/home/weiyl001/software/wavewatch3/model/exe
    ST4: /public/home/weiyl001/software2/ww4/model/exe
```

```sh
# 1. 测试 SSH 是否能连通
python3 run.py connect-test hpc_case

# 2. 查看服务器空闲分区和核心
python3 run.py slurm-idle hpc_case

# 3. 写入/刷新 server.sh 顶部的 #SBATCH、MPI_NPROCS 和 ST 路径
python3 run.py confirm-slurm hpc_case

# 4. 可选：查看当前用户队列
python3 run.py queue-status
```

如果只是改 `slurm.partition`、`slurm.nodes`、`slurm.cores`、`slurm.nodelist`、`slurm.time`、`slurm.mem` 或 `slurm.server_st.use`，不需要重新执行 Step1～Step4，直接重新运行 `confirm-slurm` 即可。



#### ST 版本管理

ST 版本是服务器 WW3 编译的不同源项的地址，在第五步确认 Slurm 参数的时候会自动把这个地址写入 server.sh

```sh
#wavewatch3--ST2
export PATH=/public/home/weiyl001/software/wavewatch3/model/exe:$PATH
```

![](public/resource/README-media/截屏2026-06-28%2020.51.34.png)

对应的 params.yml 参数

```yaml
slurm:
  server_st:
    use: ST2
    ST2: /public/home/weiyl001/software/wavewatch3/model/exe
    ST4: /public/home/weiyl001/software2/ww4/model/exe
    ST6: /public/home/weiyl001/software2/ww6/model/exe
    ST6A: /public/home/weiyl001/software2/ww6a/model/exe
    7.14 ST2: /public/home/weiyl001/software/ww3_714/WW3-develop/install_ST2/bin
    7.14 ST4: /public/home/weiyl001/software/ww3_714/WW3-develop/install_ST4/bin
    7.14 ST6: /public/home/weiyl001/software/ww3_714/WW3-develop/install_ST6/bin
```


#### ntfy 通知



作业在服务器上跑得久时，可在登录节点轮询 Slurm，任务结束往手机推 ntfy 通知。

常驻监听绑定到 `server.default_remote_dir`（远程工作根目录），pid/日志/状态文件存放在根目录下，与具体算例 workdir 解耦；清理单个算例目录不会影响 watcher。

对应 params.yml 与 CLI：

```sh
python3 run.py ntfy-watch work_dir_name
python3 run.py ntfy-watch-job work_dir_name 12345

# 提交作业后挂一次性监听（12345 换成 squeue 里的 JobID）
python3 run.py submit hpc_case
python3 run.py ntfy-watch-job hpc_case 12345
```




### 5.7 Step6  — 上传与运行

![](public/resource/README-media/截屏2026-06-29%2011.15.31.png)

这些 GUI 按钮的功能如下：

`服务器路径` 输入框用于指定远程工作目录，也就是上传、提交、下载都要操作的服务器目录。如果留空，程序通常会根据 `server.default_remote_dir` 和本地工作目录名自动拼接。

`查看文件列表` 会列出当前服务器路径下的文件，用来确认工作目录是否已经上传、结果文件和日志是否存在。

`清空文件夹` 会删除远程工作目录里的文件和子目录，但保留目录本身。这是危险操作，通常只在远程目录混乱、需要重新上传完整工作目录时使用。

`上传工作目录文件夹到服务器` 会把当前本地工作目录完整上传到服务器路径，包括强迫场文件、namelist、脚本和辅助文件。正式提交前通常使用这个按钮。

`上传非强迫场文件到服务器` 只上传脚本、namelist、配置和其他非强迫场文件，适合已经上传过大型强迫场、这次只改了参数或脚本的情况，可以避免重复传大文件。

`提交计算任务` 会在服务器工作目录执行 `server.sh`，通常会提交 Slurm 作业。它不会重新生成 namelist，也不会自动重新上传文件；因此提交前要先完成前面步骤，并确认服务器目录里的文件是最新的。

`查看任务队列` 会查询 Slurm 队列，显示当前作业是否在排队、运行或失败。主页连接服务器后也会自动刷新任务列表，这个按钮用于手动刷新。

`检查是否已完成` 会检查远程工作目录里的 `success` / `fail` 标记，判断 `server.sh` 是否完整跑完。它不是实时队列状态；如果没有标记，可能是作业还在排队、正在运行，或者脚本尚未启动。

`下载结果文件到本地` 会下载远程的 `ww3*.nc` 结果。普通网格从远程工作目录根目录下载；嵌套网格会自动下载最细层 `levelN/` 里的结果。

`下载 log 文件` 会下载远程 `run.log`  诊断文件。排错时通常先下载日志，再决定是否修改参数、重新上传或重新提交。

`执行` 会把输入框里的命令发送到远程服务器执行，适合临时查看目录、手动运行 `squeue`、`tail run.log` 等操作。这个按钮权限很大，输入命令前要确认当前服务器路径和命令内容。



#### 推荐执行顺序 

对应的 CLI 指令

```sh
python3 run.py upload --confirm work_dir_name   # 上传整个工作目录
python3 run.py submit work_dir_name             # 在服务器提交 server.sh
python3 run.py check-status work_dir_name       # 看 success / fail 标记
python3 run.py download-results work_dir_name   # 拉回结果；嵌套网格自动拉最细层 levelN
python3 run.py download-log work_dir_name       # 拉回 run.log
python3 run.py cancel-job work_dir_name 12345   # 取消作业
python3 run.py clear-remote --confirm work_dir_name
python3 run.py local-run work_dir_name          # 本机跑 local.sh
```



#### 服务器工作目录

```yaml
server:
  ssh_config_host: ''
  host: <server-host>
  port: 22
  user: <server-user>
  password: null
  key_file: /Users/<name>/.ssh/id_rsa
  default_remote_dir: /public/home/weiyl001/user/gongchuheng/
  remote_dir: ''
```

default_remote_dir 是提供一个服务器默认存放工作目录的地址，如果你不指定 remote_dir ，那么程序会自动拼接 default_remote_dir 和工作目录名为 remote_dir。

如果你填写了 remote_dir ，那么会使用你指定的地址。








### 5.9 后处理绘图

![](public/resource/README-media/截屏2026-06-29%2015.31.50.png)



Step 7 用工作目录里已有的 `ww3*.nc`、`ww3*_spec.nc`、`points.list`、风场文件和外部观测数据做可视化与验证，不参与 WW3 积分本身。也就是说，后处理绘图只读已有结果，不会重新计算波浪场；如果结果文件缺失，先回到下载结果或运行日志排查。


#### 各绘图的目的

`波高图` 用于查看 WW3 场输出的空间分布，重点看显著波高、传播范围、近岸衰减和高值中心位置。它适合回答“这一时刻哪里浪最大、涌浪是否已经到达目标海域、结果场有没有明显异常”。

`等高线图` 用于把波高梯度和空间结构看得更清楚。相比填色图，它更适合检查锋面式梯度、岛屿/陆架附近的快速变化，以及不同时间片之间高值区边界的移动。

`风涌浪图` 用于把波浪场与风场方向放在同一张图上判断关系。它主要帮助区分本地风浪和远场涌浪：如果波浪传播方向与局地风向不一致，通常说明涌浪成分更明显；如果两者高度一致，则要警惕本地风强迫主导。

`波高视频` 用于连续查看一次事件从生成、传播到衰减的时间演变。它比单张图更适合判断到达时间、传播路径是否连续、边界处是否有突变，以及模型结果是否存在不自然的跳变。

`风场图` 用于单独检查输入风场或事件期风向。当前箭头统一大小和长度，只表达方向，不表达风速大小；它适合判断远场天气系统的旋转结构、风向带和强迫方向是否与波浪传播解释一致。

`二维谱图` 用于查看点位输出的方向-频率能量分布。它比普通波高图更适合判断“某个站点在某一时刻的能量来自哪个方向、哪个频段”，也可以用最大值归一化模式比较不同站点或不同时刻的谱形，而不是只比较绝对能量大小。

`显示在地图上` 用于查看二维谱点位的空间位置，避免选错站点或把谱点解释到错误海域。做多点谱输出时，建议先看地图，再生成选中站点的谱图。

`Jason-3 卫星观测图` 用于查看卫星轨道上的实测 SWH 分布，先确认卫星过境时间和空间范围是否覆盖算例事件。它是拟合前的观测侧检查。

`Jason-3 拟合图` 用于把 WW3 场输出插值到 Jason-3 轨道附近，与卫星高度计 SWH 对比。它主要检验模型在开放海域或轨道覆盖区域的波高量级、相位和空间变化是否可信。

`NDBC 浮标站点图` 用于查看可用浮标位置，判断浮标是否靠近模拟区域、事件路径或目标海域。它帮助决定是否值得下载某些浮标数据做验证。

`NDBC 拟合图` 用于把 WW3 输出与浮标时间序列对比。它更适合检验固定点的到达时间、峰值偏差、持续时间和衰减过程；如果关注近岸站点，NDBC 往往比卫星轨道更直观。



#### CLI 指令

常用输入与产物：

| 功能 | 需要的输入 | 输出内容 |
| --- | --- | --- |
| `plot-wave-maps` | `ww3.YYYY.nc` | 波高 / 方向等空间图 |
| `plot-spectrum` | `ww3.YYYY_spec.nc` 和 `points.list` | 点位方向谱或频谱图 |
| `plot-jason3` / `plot-jason3-swh` | WW3 场输出 + Jason-3 轨道数据 | 卫星过境对比图 |
| `plot-ndbc` | WW3 输出 + NDBC 观测数据 | 浮标对比图 |

绘图不会重新运行 WW3；如果结果文件缺失，先回到下载结果或运行日志排查。

对应 params.yml 与 CLI：

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


#### 风场图

![](public/resource/README-media/wind_20210223_000000.png)



#### 二维谱图

![](public/resource/README-media/spectrum_P0500_time_20210224_120000.png)

![](public/resource/README-media/spectrum_P0500_time_20210223_000000.png)




#### 波高图

![](public/resource/README-media/3021c4434de128e783c2b06f6ba4c1fe876cf416.png)
![](public/resource/README-media/bde9091a001999fdacde4c1f804fc5c025a9995f.png)


#### 风涌浪图

![](public/resource/README-media/30f4c0333842e78da6437616709d0c884177e7b5.png)
![](public/resource/README-media/1968aff8588d84dab9e4750a8e97be006177d709.png)



#### 卫星拟合图

![](public/resource/README-media/a705779452ff987b9ffe37f1d18743b72c7f9695.png)



## 7. 项目结构

```
WW3Tool/
├── run.py                  # 唯一入口：依赖检查 → 语言切换 → 分发到 GUI / Shell / CLI
├── params.yml              # 算例参数模板（勿直接运行；用 workdir 创建副本后编辑）
├── public/                 # 全局资源
│   ├── languages/          #   zh_CN.json / en_US.json 翻译文件
│   ├── 7.14_nml/           #   WW3 namelist 模板（ww3_shel.nml, ww3_prnc.nml 等）
│   ├── 6.07_nml/           #   WW3 namelist 模板（ww3_shel.nml, ww3_prnc.nml 等）
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

GUI 模式和 Shell 模式最终都调用 src/workflows/application/ 中的用例函数。



## 8.数据获取

### 下载风场文件

#### ERA5

[https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download)

下图是 ERA5 的数据下载，你需要先注册一个账号才能下载，注册账号需要注意你的英文名字不能是随机的字母，否则无法注册。


![](public/resource/README-media/7b5a66fa59267d896d32953edbd4b398b59989d3.png)

![](public/resource/README-media/49723f276ff95abc61c5a37578dd195e241e86c1.png)

![](public/resource/README-media/344439033b50144dc811dc44c58c9ccec1a47605.png)

![](public/resource/README-media/3d2a902b95c03729037e8ebae50def9a272c42c1.png)







#### CFSR

[http://tds.hycom.org/thredds/catalog/datasets/force/ncep_cfsv2/netcdf/catalog.html](http://tds.hycom.org/thredds/catalog/datasets/force/ncep_cfsv2/netcdf/catalog.html)

找到 cfsv2-sec2_2025_01hr_uv-10m.nc 注意结尾是 uv-10m 的

如果你想下载全球整年的数据点击

HTTPServer: //tds. hycom. org/thredds/fileServer/datasets/force/ncep_cfsv2/netcdf/cfsv2-sec2_2025_01hr_uv-10m.nc

如果你想下载指定区域指定时间范围的风场，选择点击 NetcdfSubset: //ncss. hycom. org/thredds/ncss/grid/datasets/force/ncep_cfsv2/netcdf/cfsv2-sec2_2025_01hr_uv-10m.nc

打开后选择左侧的两个 wndewd 和 wndnwd ，拉到下面选择 Choose Output Format: netCDF

如果你发现无法输入经纬度，则取消选中 Disable horizontal subsetting

![](public/resource/README-media/20305146a39edf9f584b455200bab685abb455f6.png)

然后点击下面的 Time range 标签，输入时间范围，最后 submit



#### CCMP

[https://data.remss.com/ccmp/v03.1/](https://data.remss.com/ccmp/v03.1/)

这个很简单，直接下载就行

### 下载流场、水位场

[https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/download?dataset=cmems_mod_glo_phy_anfc_0.083deg_PT1H-m_202406](https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/download?dataset=cmems_mod_glo_phy_anfc_0.083deg_PT1H-m_202406)

选择下面的 Variables，如果你不需要水位场，取消选中 Sea surface height above geoid

然后输入范围和时间即可，最后点击 DOWNLOAD

![](public/resource/README-media/224d9c7b204410af0f2bb5fa7fbe85d37697748d.png)



### 下载冰场

[https://data.marine.copernicus.eu/product/GLOBAL_MULTIYEAR_PHY_001_030/download?dataset=cmems_mod_glo_phy_my_0.083deg_P1D-m_202311](https://data.marine.copernicus.eu/product/GLOBAL_MULTIYEAR_PHY_001_030/download?dataset=cmems_mod_glo_phy_my_0.083deg_P1D-m_202311)

可以下载海冰场和流场

海冰包括海冰覆盖 Sea ice area fraction 、海冰厚度场 Sea ice thickness

![](public/resource/README-media/d64991a6199b7e91b49be401afeca00ffde51619.png)



### JASON 3 数据

https://www.ncei.noaa.gov/products/jason-satellite-products


### NDBC 浮标数据

https://www.ndbc.noaa.gov

## 授权协议

本软件基于 GPLv3 授权的框架开发，根据 GPLv3 协议要求，整体以 GPLv3 方式发布。
