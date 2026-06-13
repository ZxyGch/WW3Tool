# workflows — 架构说明

`workflows/` 是 WW3Tool CLI 和 Desktop 共用的核心代码包，负责所有与 WW3 相关的业务逻辑。
Desktop 层（`src/desktop/`）调用这里，CLI 入口（`src/run.py`）也调用这里，两者不直接共享代码。

---

## 目录结构

```
workflows/
├── domain/           纯数据模型与常量，无任何外部依赖
├── support/          跨层公共工具（日志、翻译）
├── infrastructure/   外部系统的适配与封装（文件 I/O、子进程、绘图库）
├── application/      用例编排——把 infrastructure 的能力组合成完整流程
└── interfaces/       入口适配器——目前仅有 CLI
```

依赖方向（只允许向下指向）：

```
interfaces
    └── application
            └── infrastructure
                    └── domain
            └── support
    └── support
```

---

## 各层详解

### `domain/` — 领域模型

不依赖任何其他层。改动频率低，是整个包的"词汇表"。

| 文件 | 说明 |
|---|---|
| `config_models.py` | 整个流水线的参数数据类（dataclass），涵盖 forcing / grid / ww3 / plot 等所有配置段 |
| `forcing_fields.py` | `ForcingField` 枚举（WIND / CURRENT / LEVEL / ICE）及 `Step1Files` 路径容器 |
| `parameter_catalog.py` | 参数的枚举选项常量，如地形分辨率、输出字段列表、文件分割方式等 |

flowchart LR
    params["params.yml"]
    cfg["configuration.py"]
    models["config_models.py"]
    cli["workflows/application/*"]
    infra["workflows/infrastructure/*"]
    desktop["desktop/*"]

    params --> cfg
    cfg --> models
    models --> cli
    models --> infra
    models --> desktop


### `support/` — 支撑工具

被所有层使用，自身不依赖 domain/infrastructure/application。

| 文件 | 说明 |
|---|---|
| `logging.py` | `CoreLogger`：统一日志接口，支持回调函数（CLI 用 `print`，Desktop 用信号） |
| `translations.py` | `tr(key, default)` 的无 Qt 版本——在 CLI/headless 上下文中直接返回 default |

### `infrastructure/` — 基础设施

封装所有"副作用"：文件读写、子进程调用、第三方库（matplotlib、netCDF4、paramiko）。
**application 层只通过这里与外部世界交互。**

#### `infrastructure/forcing/` — 场文件处理（Step 1）

| 文件 | 说明 |
|---|---|
| `file_path_manager.py` | 计算 workdir 内 wind.nc / current.nc 等目标路径 |
| `file_service.py` | 文件复制 / 移动 / 软链接 |
| `variable_detector.py` | 检测 NetCDF 文件中的变量类型（u/v 风场、SWH 等） |
| `wind_normalize_service.py` | 将不同格式的风场归一化为 WW3 所需的 u/v 分量 |
| `use_cases.py` | `ImportForcingFileUseCase` / `ImportWindForcingUseCase`：组合上面四个类，完成单个场文件的导入 |

> **注意**：`use_cases.py` 位于 infrastructure 层而非 application 层，因为它直接封装了文件 I/O 操作，不包含流程判断。

#### `infrastructure/adapters/` — 高层适配器

| 文件 | 说明 |
|---|---|
| `grid_generation_adapter.py` | 调用 structured / SMC / unstructured 网格生成器（均以子进程方式运行） |
| `grid_visualization_adapter.py` | 在子进程中运行 `grid_visualization/worker.py`，返回生成的图片路径列表 |
| `ww3_namelist_adapter.py` | 组装 WW3 namelist 文件（ww3_shel.nml、ww3_grid.nml 等），通过 fake-widget 适配层调用 `ww3/step4_service.py` |

#### `infrastructure/grid_visualization/` — 网格可视化

| 文件 | 说明 |
|---|---|
| `worker.py` | 主 worker：读取网格文件，用 matplotlib + cartopy 渲染结构化 / SMC / 非结构化三种网格 |
| `rect_grid_desc_parse.py` | 解析 structured 网格的 `.desc` 文本文件 |
| `structured_grid_paths.py` | 管理 structured 网格 workdir 中的文件路径约定 |

#### `infrastructure/plot/` — 后处理绘图 workers

每个 worker 接收 `(folder, ..., log_queue, result_queue)` 参数，设计上与 GUI 解耦；
CLI 通过 `queue.SimpleQueue` 同步桥接，Desktop 通过多进程 Queue 异步调用。

| 文件 | 说明 |
|---|---|
| `workers_utils.py` | 公共纯函数：WW3 NetCDF 经纬度解析、SMC/非结构网格判别、Jason 配位展平 |
| `wave_map_worker.py` | `_make_wave_maps_worker`：波高填色图；`_make_contour_maps_worker`：等值线图 |
| `spectrum_worker.py` | 三个频谱 worker：`_generate_first_/all_/selected_spectrum_worker` |
| `jason3_worker.py` | `_match_ww3_jason3_worker`：WW3 × Jason-3 卫星匹配；`_run_jason3_swh_worker`：SWH 分布图 |
| `ndbc_worker.py` | `_match_ww3_ndbc_worker`：WW3 × NDBC 浮标匹配；`_download_ndbc_worker`：下载浮标数据 |

#### `infrastructure/ww3/` — WW3 Namelist 生成逻辑

| 文件 | 说明 |
|---|---|
| `modify_ww3_nml.py` | 底层：读取、修改、写入 `.nml` 文件的字符串操作 |
| `step4_service.py` | 从 src 迁移的业务逻辑 Mixin：计算 WW3 运行参数、生成 `ww3_shel.nml` |

#### `infrastructure/` 直属文件

| 文件 | 说明 |
|---|---|
| `runtime_config.py` | 读取 `public/config.json`；提供 ST 方案、CPU 配置、默认参数等运行时常量 |
| `region_map_renderer.py` | 用 matplotlib + cartopy 将网格经纬度范围渲染成地理预览图（PNG） |

---

### `application/` — 应用用例

编排 infrastructure 层的能力，形成完整的可运行流程。每个文件对应一个功能单元，返回带 `messages` 字段的 Result dataclass，便于 CLI 打印和 Desktop 展示。

#### 预处理（Preprocessing）

| 文件 | 说明 |
|---|---|
| `configuration.py` | YAML 加载、路径解析、参数校验，输出 `PipelineConfig`；包含 `EXAMPLE_YAML` 模板 |
| `preprocessing_workflow.py` | `run_pipeline`：forcing → grid → ww3 namelist 完整流水线；`run_prepare_forcing`：仅场文件 |
| `forcing_preparation.py` | 单步：为所有配置的场字段调用 use_cases，输出 `Step1Files` |
| `forcing_inspection.py` | 只读：输出已选场文件的概览信息（变量范围、时间范围等） |
| `grid_preparation.py` | 单步：`run_generate_grid`，调用 grid_generation_adapter |
| `grid_tools.py` | 只读工具：从 workdir 读取网格边界，供 Desktop 预览使用 |

#### 后处理（Post-processing）

| 文件 | 说明 |
|---|---|
| `plot_wave_maps.py` | `run_wave_maps` / `run_contour_maps`：波高图生成 |
| `plot_spectrum.py` | `run_spectrum(mode="first"/"all"/"selected")`：频谱图生成 |
| `match_jason3.py` | `run_match_jason3` / `run_jason3_swh`：Jason-3 数据匹配与分布图 |
| `match_ndbc.py` | `run_match_ndbc` / `run_download_ndbc`：NDBC 浮标匹配与数据下载 |

---

### `interfaces/` — 入口适配器

| 文件 | 说明 |
|---|---|
| `command_line.py` | `argparse` 解析器 + `main()` 分发；支持预处理、绘图和远程运维命令（见下表） |

**CLI 命令列表：**

| 命令 | 功能 |
|---|---|
| `validate` | 校验 params.yml 合法性 |
| `prepare-forcing` | 仅执行场文件准备 |
| `generate-grid` | 仅执行网格生成 |
| `run [--skip-grid]` | 执行完整预处理流水线 |
| `plot` | 运行 params.yml `plot:` 段中所有 enabled 的绘图任务 |
| `plot-wave-maps [--contour]` | 生成波高填色图或等值线图 |
| `plot-spectrum [--mode] [--station]` | 生成二维频谱图 |
| `match-jason3` | WW3 × Jason-3 匹配 |
| `match-ndbc [--download]` | WW3 × NDBC 匹配，或下载 NDBC 数据 |
| `connect-test` | 测试 SSH 连接 |
| `list-files` | 查看远程工作目录文件列表 |
| `upload --confirm` | 上传本地工作目录到远程 |
| `submit [--script]` | 在远程工作目录执行提交脚本 |
| `check-status` | 检查 success.log / fail.log 状态 |
| `queue-status` | 查看 SLURM 队列 |
| `download-results [--nested]` | 下载远程 WW3 结果文件 |
| `download-log` | 下载 success.log / fail.log |
| `clear-remote --confirm` | 清空远程工作目录 |
| `cancel-job` | 取消 SLURM 任务 |
| `print-example` | 打印带注释的 params.yml 模板 |

---

## 架构评估

### 做得好的地方

**1. 层次边界清晰**
domain → support ← infrastructure ← application ← interfaces 的依赖方向基本干净。
Desktop 可以直接调用 application 层，CLI 也调用同一套代码，实现了重构计划的"共用核心"目标。

**2. 配置集中**
`configuration.py` 是唯一的 YAML 解析入口，所有参数经过类型校验后以强类型 dataclass 传入下游，避免了 `dict.get("key")` 散落全局的问题。

**3. Workers 与 GUI 解耦**
plot 层的 worker 函数接收 `log_queue`/`result_queue` 而非 Qt 信号，Desktop 和 CLI 都能复用，且可以按需放入子进程。

---

### 已处理的历史遗留问题

**① ww3 namelist 的控件适配层** ✅ 已整理

`ModifyWW3NML` / `StepFourServiceMixin` 是 Qt Mixin 类，方法通过 `self.widget.text()` 读取运行参数。`_WW3Adapter` 采用 **Object Adapter 模式**，将 `PipelineConfig` 中的纯 Python 值包装为轻量级控件桩对象，使两个 Mixin 能在无 GUI 环境下工作，且无需修改其内部逻辑（4730 行，Desktop 同样依赖）。

控件桩已提取到 `infrastructure/ww3/widget_stubs.py`，含设计意图注释，不再内联于适配器文件。

**② plot workers 的实时日志** ✅ 已修复

原本用 `queue.SimpleQueue` 桥接导致日志在 worker 完成后才统一输出。现改用 `support/queue_bridge.py` 中的 `ImmediateQueue`：每次 `put()` 立即触发 `logger.log()` 回调，CLI 可看到实时进度。Desktop 多进程路径继续使用 `multiprocessing.Queue`，不受影响。

**③ `forcing/use_cases.py` 命名** ✅ 已改善

文件顶部说明了 "UseCase" 是历史命名遗留，并在末尾提供了符合基础设施惯例的别名：
`ForcingAutoAssociator`、`ForcingFileImporter`、`WindForcingImporter`、`WorkdirForcingScanner`。
旧名称保留以维持与 Desktop 层的向后兼容。

**④ `grid_tools.py` 注释误导** ✅ 已修正

文件注释更新为：工具函数放在 application 层，是为了让未来的 CLI 检查命令也能复用，而非仅供 Desktop 使用。

**⑤ 网格可视化与 plot workers 调用方式不一致** ✅ 已文档化

在 `grid_visualization_adapter.py` 顶部增加说明：grid 可视化必须用子进程，原因是与 Desktop Qt 事件循环共存时 matplotlib 后端会冲突；plot workers 在事件循环不活跃时直接在进程内调用。

---

### 综合评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 层次分离 | ★★★★☆ | 整体清晰，forcing/use_cases 位置略有争议但已文档化 |
| CLI/Desktop 复用 | ★★★★★ | 完全实现，两端调用同一套 application 层 |
| 可测试性 | ★★★★☆ | Workers 和 importers 可单测；widget_stubs.py 使 step4 逻辑也可测 |
| 实时进度反馈 | ★★★★☆ | ImmediateQueue 修复后 CLI 端日志实时可见 |
| 扩展性 | ★★★★☆ | 新增绘图类型或预处理步骤只需在 application 加文件，不影响其他层 |
