# WW3Tool 常用 WW3 配置补充计划

本文档整理 NOAA-EMC/WW3 GitHub discussions 和 issues 中高频出现的配置需求，并结合当前 WW3Tool 已有能力，给出后续补齐计划。目标不是服务某一个研究个例，而是补齐别人运行 WW3 时经常会改、也容易出错的通用配置。

## 1. 背景判断

当前 WW3Tool 已覆盖的常用配置包括：网格类型与范围、谱离散参数、积分步长、起止时间、场输出时间间隔、输出变量列表、文件切分、本地/服务器 ST 版本、Slurm 节点和核心、风/流/水位/海冰强迫文件路径。

从 WW3 社区讨论看，最常见的问题集中在 6 类：

1. 重启/续跑：热启动、断点续跑、重启文件命名、重启间隔。
2. 强迫文件读取：变量名不匹配、时间轴/日历、NaN/fill value、风场格式。
3. 边界与嵌套：谱边界输出、`ww3_bounc` 输入、多网格不同强迫。
4. 输出格式：NetCDF 版本、输出前缀、输出类型、谱分区变量。
5. 点位输出：点位二维谱、平均参数、源项输出、谱分区输出。
6. 作业资源：walltime、MPI 启动器、OpenMP 线程、每节点任务数。

参考讨论和 issue：

- https://github.com/NOAA-EMC/WW3/discussions/1597
- https://github.com/NOAA-EMC/WW3/discussions/1592
- https://github.com/NOAA-EMC/WW3/discussions/1596
- https://github.com/NOAA-EMC/WW3/discussions/1578
- https://github.com/NOAA-EMC/WW3/discussions/1590
- https://github.com/NOAA-EMC/WW3/discussions/1553
- https://github.com/NOAA-EMC/WW3/issues/219
- https://github.com/NOAA-EMC/WW3/issues/681
- https://github.com/NOAA-EMC/WW3/issues/1248
- https://github.com/NOAA-EMC/WW3/issues/1601

## 2. 增加原则

1. 首页只放高频、低风险、容易解释的参数。
2. 高级 namelist 开关先放到 `params.yml`，不要一开始塞进 GUI。
3. 默认值必须保持当前行为不变，旧配置文件可以继续运行。
4. 参数命名用“用户理解的含义”，内部再映射到 WW3 namelist。
5. 每个新增参数必须在日志里显示最终写入值，方便排错。

## 3. P0：最应该先加

### 3.1 Restart / Hot Start 配置

社区频率很高，实际批量 WW3 也很需要。现在 WW3Tool 主要按冷启动准备任务，遇到中断、延长预报、从已有 restart 接续时不够方便。

建议新增：

```yaml
restart:
  mode: cold              # cold | restart
  input_file: null        # 已有 restart 文件路径
  output_step: 86400      # restart 输出间隔，秒
  output_dir: null        # null 表示写入当前 workdir
  keep_latest_only: false # 是否只保留最新 restart
```

预期映射：

- `ww3_shel.nml`：控制 restart 输入/输出相关时间。
- 工作目录准备流程：复制或链接 `restart.ww3`。
- `run.log`：记录冷启动/热启动模式、输入 restart 来源、输出间隔。

验收：

- 冷启动默认结果与当前一致。
- `mode: restart` 时，工作目录中可以看到 restart 输入文件被准备，并且日志明确写出来源。
- 断点续跑任务无需手改 namelist。

### 3.2 强迫变量名映射与缺测处理

GitHub 上大量问题不是模型物理，而是 `ww3_prnc` 没读到风、流、水位或海冰。当前 WW3Tool 有自动识别变量名，但不够透明；遇到 WRF、ERA5 变体、区域模式文件时，用户需要手工指定。

建议新增：

```yaml
forcing:
  variable_map:
    wind:
      u: u10
      v: v10
      lon: longitude
      lat: latitude
      time: time
    current:
      u: uo
      v: vo
    level:
      z: zos
    ice:
      conc: siconc
      thick: sithick
  timeshift: "00000000 000000"
  fill_value_policy: mask_nan   # native | mask_nan | replace
  wind_format: uv               # uv | speed_direction
```

预期映射：

- `src/workflows/infrastructure/ww3/ww3_prnc_nml.py`
- `ww3_prnc.nml` 中对应 forcing type 的变量名、时间偏移和读取方式。

验收：

- 默认仍自动识别旧文件。
- 手动填写变量名后，生成的 `ww3_prnc.nml` 与日志中显示一致。
- 遇到 NaN/fill value 时，日志说明采用的处理策略。

### 3.3 场输出格式与谱分区场变量

当前 `output_scheme` 已能决定 `FIELD%LIST`，但缺少几个常被讨论的输出控制：NetCDF 版本、文件前缀、场输出类型、谱分区编号。谱分区相关变量如 `PHS/PTP/PDIR/PWS/PNR/TWS` 是否有意义，关键取决于 `FIELD%PARTITION`。

建议新增：

```yaml
output:
  netcdf_version: 4
  file_prefix: "ww3."
  field_type: 4
  field_partitions: "0 1"
  samefile: true
```

预期映射：

- `ww3_ounf.nml`
- `FIELD%TYPE`
- `FIELD%PARTITION`
- `FILE%NETCDF`
- `FILE%PREFIX`

验收：

- `field_partitions` 修改后，`ww3_ounf.nml` 中 `FIELD%PARTITION` 立即变化。
- 默认仍输出当前 `PHS/PTP/PDIR/PWS/PNR/TWS` 对应的分区。
- 日志明确区分“场输出谱分区变量”和 `ww3_shel.nml` 中 raw partition 输出通道。

### 3.4 Slurm 作业运行参数

当前 `server.sh` 里 walltime、MPI 启动方式和部分并行环境还比较硬编码。别人迁移到不同服务器时，这几个参数非常常改。

建议新增：

```yaml
slurm:
  walltime: "2880:00:00"
  launcher: mpirun       # mpirun | srun
  omp_threads: 1
  ntasks_per_node: null
  extra_sbatch: []
```

预期映射：

- `public/scripts/server.sh`
- 生成或复制到 workdir 的 `server.sh`
- `run.log`

验收：

- 修改 `walltime` 后，`#SBATCH --time` 变化。
- 修改 `launcher` 后，执行命令在 `mpirun` 和 `srun` 之间切换。
- `OMP_NUM_THREADS` 明确写入脚本和日志。

## 4. P1：建议加，但不必先上首页

### 4.1 点位输出细项

点位输出在社区中很常见，尤其是二维谱、平均参数、源项、点位谱分区。当前 WW3Tool 已生成点位和 `ww3_ounp.nml`，但没有把 `POINT%TYPE` 和 `SPECTRA%OUTPUT` 显式配置化。

建议新增：

```yaml
point_output:
  type: spectra              # inventory | spectra | parameters | source_terms
  spectra_output: transfer   # print | table_1d | transfer | partition
  samefile: true
  buffer: 100
```

预期映射：

- `ww3_ounp.nml`
- `POINT%TYPE`
- `SPECTRA%OUTPUT`
- `POINT%SAMEFILE`
- `POINT%BUFFER`

首页策略：

- 首页只保留一个“点位谱输出模式”下拉。
- 高级设置里再暴露 `samefile`、`buffer`。

### 4.2 边界谱输出与输入

嵌套和外边界是 WW3 常用能力。官方讨论里常见做法是先用 `ww3_ounp` 输出边界点方向谱，再通过 `ww3_bounc` 或 `ww3_bound` 用作嵌套输入。

建议新增：

```yaml
boundary:
  enabled: false
  mode: one_way
  points_file: null
  spectra_format: netcdf
  output_step: 3600
  input_files: []
  check_boundary_points: true
```

预期映射：

- `ww3_ounp.nml`：边界点谱输出。
- `ww3_bounc.nml` / `ww3_bound.nml`：边界输入。
- 工作目录准备流程：检查边界点是否落在有效海点附近。

首页策略：

- 暂时不放首页。
- 在嵌套网格工作流稳定后加入“边界谱”高级页。

### 4.3 多网格每层强迫

多网格问题里，经常需要粗网格和细网格使用不同分辨率风场。当前 WW3Tool 配置更偏单套 forcing。

建议新增：

```yaml
nested:
  per_level_forcing: false
  levels:
    - name: level0
      wind: null
      current: null
      level: null
    - name: level1
      wind: null
      current: null
      level: null
  comm_frac: auto
```

预期映射：

- `ww3_multi.nml`
- 各层网格 forcing 准备目录。
- 多层 `ww3_prnc` 输入文件。

首页策略：

- 只在选择 nested/multi-grid 后显示。

## 5. P2：仅做高级覆盖，不建议普通用户配置

### 5.1 源项 namelist override

例如 ST4 的 `BETAMAX`、`SIN4` 等源项参数，社区中确实有人改，但这类参数强依赖编译开关和物理方案。放到首页会制造误用。

建议仅提供高级覆盖：

```yaml
advanced_namelist_overrides:
  ww3_grid:
    SIN4%BETAMAX: null
  ww3_shel: {}
  ww3_ounf: {}
  ww3_ounp: {}
```

验收：

- 默认不写任何 override。
- 用户显式填写后，日志列出被覆盖的 namelist 字段。
- GUI 里只放“高级 namelist 覆盖”，不做成普通表单。

## 6. 不建议近期加入的配置

1. GRIB2 输出：有需求但依赖后处理链，当前 NetCDF 更符合 WW3Tool 工作流。
2. 全网格二维谱输出：用户常问，但 WW3 标准流程不适合把它当普通配置项。
3. 极细物理源项参数：适合研究型 fork，不适合默认工具首页。
4. 所有 namelist 字段全量 GUI 化：维护成本高，也会让用户更难判断该改什么。

## 7. 实施顺序

### 阶段 A：配置层兼容

1. 在 `params.yml` 增加 `restart`、`output`、`point_output`、`slurm` 新字段默认值。
2. 更新配置解析模型，保证缺省时不破坏旧配置。
3. 增加配置读取单元测试或最小脚本检查。

完成标准：旧 `params.yml` 和新 `params.yml` 都能被读取，默认生成结果不变。

### 阶段 B：namelist 写入

1. `ww3_ounf_nml.py` 支持 `FIELD%PARTITION`、`FIELD%TYPE`、`FILE%NETCDF`、`FILE%PREFIX`。
2. `ww3_ounp_nml.py` 支持 `POINT%TYPE`、`SPECTRA%OUTPUT`、`POINT%SAMEFILE`、`POINT%BUFFER`。
3. `ww3_prnc_nml.py` 支持手动变量名映射和缺测策略。
4. `ww3_shel_nml.py` 支持 restart 模式与输出间隔。

完成标准：准备 workdir 后，相关 namelist 字段与 `params.yml` 一致，日志能看到对应写入记录。

### 阶段 C：脚本与日志

1. `server.sh` 支持 `walltime`、`launcher`、`omp_threads`。
2. `local.sh` 继续支持本地 ST 下拉选择，不要求手填 bin 路径。
3. 复制 `server.sh` 和 `local.sh` 的日志继续合并显示并翻译。
4. 所有新增配置写入 `run.log`，且追加写入，不清空旧日志。

完成标准：本地运行和服务器运行日志都能追踪配置来源。

### 阶段 D：GUI 暴露

首页优先暴露：

1. Restart 模式：冷启动/续跑、restart 文件、输出间隔。
2. 输出高级项：NetCDF 版本、场输出类型、谱分区编号。
3. Slurm：walltime、启动器、OpenMP 线程。
4. 点位输出模式：二维谱/平均参数/源项/谱分区。

暂不放首页：

1. 边界谱输入输出。
2. 多网格每层强迫。
3. 源项 namelist override。

完成标准：修改 GUI 设置后，主页和 `params.yml` 立即一致，准备任务时无需手改 namelist。

## 8. 推荐默认值

```yaml
restart:
  mode: cold
  input_file: null
  output_step: 86400
  output_dir: null
  keep_latest_only: false

output:
  netcdf_version: 4
  file_prefix: "ww3."
  field_type: 4
  field_partitions: "0 1"
  samefile: true

point_output:
  type: spectra
  spectra_output: transfer
  samefile: true
  buffer: 100

slurm:
  walltime: "2880:00:00"
  launcher: mpirun
  omp_threads: 1
  ntasks_per_node: null
  extra_sbatch: []
```

这些默认值的原则是：保持当前工作流行为基本不变，同时把原来隐藏或硬编码的常用配置显式化。
