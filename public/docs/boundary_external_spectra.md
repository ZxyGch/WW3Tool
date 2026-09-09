# 外部边界谱单向嵌套：首版实施记录

设计依据：`public/WW3Tool_单向嵌套支持方案.md`。代码基线 WW3Tool 0.1.30。

## 实现范围

- 单层结构化矩形网格（`mesh_type: structured`、`grid_type: normal`、非周期）。
- 输入：WW3 原生二维点谱 NetCDF（`ww3_netcdf`）。ASCII 与直接导入 `nest.ww3` 明确不支持。
- 空间映射：最近邻默认（球面距离）；两点线性权重与 `ww3_bounc` INTERP=2 相同，使用经纬度平面投影，不是大圆。
- 目标方向轴与 `ww3_ounp` 一致：`TH(ITH)=DTH*(THOFF+ITH-1)`，`DIR=MOD(450-THD,360)`。`NTH=24, THOFF=0` 时为 90°、75°、60°。
- 谱缺测：保留 NetCDF 掩码，拒绝 `_FillValue` / 缺测，禁止当成能量。
- 复用规范化谱包：源文件不在本机时必须核对有效时间窗、网格指纹、谱离散、`source.files`、插值参数与规范化文件哈希；来源变化报 `BOUNDARY_STALE`。复用时恢复活动掩码引用。
- 时间分片：先按站点合并各文件时间轴，再检查覆盖并切片读取；单文件不必单独覆盖整个积分窗口。
- 锁：`O_EXCL` 锁文件跨节点互斥。身份是作业 UUID（`--lock-owner`），禁止用裸 PID；同 PID 不同节点不得重入或释放。关闭边界（`mode=none`）、`deferred_remote` 写计划、热启动复制 `restart.ww3` 与改积分起点，都必须先拿同一把锁，并保持到运行结束。
- 运行：`local.sh` / `server.sh` 的 `--workdir` 覆盖 YAML 中的本机绝对路径。脚本与 Python `LocalRunService` 顺序为：获取作业锁 → 热启动准备 → 边界 pregrid → `ww3_grid` → 边界 postgrid（`ww3_bounc`）→ 强迫与积分；EXIT / finally 时释放。`local.sh` 用 `--execution-context local`，`server.sh` 用 `compute`。计算节点按本机 POSIX 路径读取远程谱，可执行文件用服务器 ST 映射。
- 基础掩码：首次准备记下 `boundary/mask_origin.json` 的原始 `MASK%FILENAME/IDLA`；再次准备禁止按派生 `IDLA=1` 读基础掩码；关闭边界时恢复原始读取参数。
- 入口：GUI 卡片、CLI、交互式终端、JSON/schema；MCP 从 argparse 自动暴露新命令。

## 配置

工作目录缺少 `boundary` 时 `mode: none`。根模板中的 `source.files` 不会自动启用其他算例。启用时必须填写正的 `max_distance_km` 与 `max_time_gap_seconds`；`50 km` / `10800 s` / `1024 MiB` 仅为示例。

ST 名称与可执行目录按用户配置的不透明字符串解析。`ww3_bounc` 只在选定目录中查找。

## 命令

- `inspect-boundary [workdir] [--remote]`
- `prepare-boundary [workdir]`
- `boundary-status [workdir] [--remote]`
- `download-boundary-report [workdir]`
- `validate [workdir] --stage boundary`

## 真实 WW3 验收

入口：`tests/workflows/run_boundary_ww3_live.py`。产物只写 gitignore 的 `workSpace/boundary_ww3_verify/`，不提交 `.nc` / `nest.ww3`。根 `params.yml` 的 `local_run.local_st` 仍指向仓库外空目录，验收把可执行目录写进各算例工作目录 YAML，不改用户根 ST 映射。

本机实际二进制（均为 arm64、Open MPI 5、`mpirun -np 1` 跑 `ww3_shel`）：

| 版本 | ST 名（不透明） | 可执行目录 | switch |
| --- | --- | --- | --- |
| 6.07 | `6.07 ST4 RECT` | `WW3Tool/WW3-6.07.1/model/exe_ST4` | `F90 NOGRB NC4 DIST MPI PR3 UNO … ST4 …`（无 SMC） |
| 7.14 | `7.14 ST2 RECT` | `WW3Tool/WW3/build/ST2/bin` | `NCO NOGRB DIST MPI PR3 UQ ST2 …`（无 SMC） |

7.14 的 ST4 构建在 `WW3/build/ST4/bin`，switch 含 `SMC`，首版 RECT 验收**不使用**，也不得写成已支持 7.14 ST4 RECT。

小矩形：NX=13、NY=9、SX=SY=0.25°、X0=120°、Y0=10°、水深 4000 m（`DEPTH%SF=-1`）、西边界向内一格、静水初值 `ITYPE=5`、`FLSOU=F`、无风。谱：FREQ1=0.08 Hz、NK=10、NTH=24、THOFF=0，能量在传播去向 90° 的箱（与原生 ounp 方向轴一致，目标向东）。预先门槛：入射内部 Hs≥0.15 m，零边界 &lt;0.02 m，热启动相对差≤0.25。

2026-09-09 方向轴与线性公式修正后重跑结果（两套 8 个算例全部 `ok=True`，`run_boundary_ww3_live.py` 退出码 0）：

| 算例 | 6.07 ST4 RECT | 7.14 ST2 RECT |
| --- | --- | --- |
| 单边入射 | 内部最大 Hs=1.500；西侧先有能量（1.43 vs 0.03） | 内部最大 Hs=1.502；同样西侧先到 |
| 零边界对照 | 内部 Hs=0 | 内部 Hs=0 |
| 输入不足 | prepare 报 `BOUNDARY_TIME_COVERAGE`，未积分 | 同左 |
| 边界关闭 | 托管 `nest.ww3` 归档，MASK 指回无边界掩码 | 同左 |
| 两点线性 | `ww3_bounc` INTERP=2，NBI=7，nest 中可读 7 条映射 | 同左 |
| 多站点一文件 | 3 个不同站点均进入 mapping | 同左 |
| 时间分片 | 与单文件 nest 的 NBI/NK/NTH/时刻数一致 | 同左 |
| 热启动 | 6 h checkpoint 续跑，内部 Hs 相对差 0 | 同左 |

WW3 场输出 `DIR` 为 270.1°（6.07）/ 270.2°（7.14），这是输出量的来向约定；能量从西边界进入、东侧迟到（6.07 西 1.437 对东 0.035；7.14 西 1.489 对东 1.3e-5），与输入去向东一致。方向轴修正前该值约 263°（偏 7°），修正后偏差降到 0.1–0.2°，可视为方向轴对齐的直接证据。目标方向轴必须用 `MOD(450-THD,360)`，禁止 `270−θ`（那是来向）。

7.14 `ww3_bounc` 要求 `efth` 带 `_FillValue`；写出规范化谱时已补上。读取源谱时必须保留掩码并拒绝填充值。`nest.ww3` 每个时刻必须含 NBO2 条谱记录，谱值必须有限，并抽样与规范化输入核对：只接受 `efth/(2π)`（`ww3_bounc` 写出 `ABPIN2 = SPEC2D * tpiinv`），禁止把裸 `efth` 当作通过。最近邻核验边界坐标和主源索引；线性按源点编号对权重，两点权重均为 0.5 时允许 WW3 与预览的源顺序对调。

单元测试：`tests/workflows/test_boundary_*.py`（45 项）。单元测试不能代替上表两套真实积分。

2026-09-09 重跑已覆盖此前的两项缺口：

- 方向轴：能量注入去向 90° 箱，两套 WW3 场输出来向 270.1° / 270.2°，偏差 0.1–0.2°。
- linear 权重：`nest.ww3` 的 `RDBPO` 已按源点编号与预览逐点比对（`ww3_bounc_nml.py` 中 `check_linear_weights`，容差 0.02）。本算例 7 个目标点权重为 0.875/0.75/0.625/0.5/0.625/0.75/0.875，只有中点是 0.5/0.5，其余 6 点为非平凡权重，WW3 实际值与预览完全一致。中点 6.07 与 7.14 的 `IPBPO` 顺序相反（`DIST_SPHERE` 与 `DIST_HAVERSINE` 取舍不同），权重相同，属允许的对调。
- `tpiinv`：直接从 `nest.ww3` 二进制重算 Hs 得 1.5000 m（输入 1.5 m），证实写入的是 `efth/(2π)` 而非裸 `efth`。

`SPECTRUM%FREQ1/XFR/THOFF` 按 `w3gridmd` 的夹取规则处理（`THOFF∈[-0.5,0.5]`、`XFR≥1.00001`、`FR1≥1e-6`）。此前未夹取，越界 THOFF 会算出与 WW3 实际相差整数个方向箱的轴，且无下游检查能发现。

## 与官方做法的一致性

本方案走的是 WW3 官方的**离线单向嵌套**路线：粗网格 `ww3_ounp` 出点谱 → `ww3_bounc` 合成
`nest.ww3` → 细网格 `ww3_shel` 读。`nest.ww3` 由官方 `ww3_bounc` 生成，本工具不自己写。

WW3 7.14 仓库内的对照证据：

- 官方 `ww3_bounc.nml` 只有 `BOUND%FILE`（tp2.17、tp2.19 各 Case）。我们额外写出的
  `MODE='WRITE'`、`INTERP=2`、`VERBOSE=1` 与 `w3nmlbouncmd.F90:239-242` 的默认值逐项相同。
- 官方回归算例中用 `ww3_bounc` 的有 tp1.11、tp2.8、tp2.17、tp2.19；`ww3_bound`（老 ASCII 路线）
  只剩 tr1 在用；`ww3_multi`（多网格在同一可执行内嵌套）出现在约 100 个算例，是另一条主线，
  与本方案并列，不互相取代。首版不支持 `ww3_multi` 嵌套。
- 官方 `boundary*.nc`（`WW3/data_regtests/ww3_tp2.19`、`ww3_tp2.20`）的 `direction` 值为
  `[90, 89, 88, …]`，与 `MOD(450-THD,360)` 逐点吻合，独立印证方向轴公式。

空间映射的定位要说清楚：`ww3_bounc` 内部会用自己的最近邻/两点线性重算一遍映射，本工具的
`mapping.csv` 是**预览与校验**，不是下发给 WW3 的权重。工具的映射只决定哪些站点被规范化并写进
`spec.list`（候选集），最终权重由 WW3 定。验收因此必须回读 `nest.ww3` 的 `IPBPO/RDBPO` 与预览比对。

2026-09-09 用官方 `boundary*.nc` 实测，读入侧原先有两处比官方窄，已修：

- `station_name` 轴顺序：官方写 `(string16, station)`，`ww3_ounp` 写 `(station, string16)`；
  原先只认后者，站名 `wavemaker` 被解成 `w`。
- 方向 `standard_name`：官方是空格分隔的 `sea surface wave to direction`，原先只匹配下划线形式，
  官方文件一律被判 `BOUNDARY_CONVENTION_UNKNOWN` 拒收。

另外 `ww3_ounp` 默认档（`NCVARTYPE<=3`）写的是 `NINT(log10(efth+1e-12)/0.0004)` 的 `NF90_SHORT`，
`units='log10(m2 s rad-1 +1E-12)'`。该串含 `rad`，原先被判成线性谱，而 netCDF4 只做线性解包，
拿到的是 log10 值。现在在单位层拦下并提示改用 `NCVARTYPE=4`。本版不做对数反解
（`ww3_bounc` 自己是按 `10**(raw*scale)-1e-12` 反解的，见 `ww3_bounc.F90:609`）。

## 已知限制

- 嵌套 `ww3_multi`、UNST、SMC、周期/跨日界线目标矩形、频率方向插值、ASCII 输入均报告不支持。
- 服务器来源在本地 `prepare-boundary` 只生成 `deferred_remote` 计划；完整谱检查在计算节点进行。本地 `local.sh` 遇到远程来源会报 `BOUNDARY_LOCATION_MISMATCH`。
- 6.07 / 7.14 RECT 的 `nest.ww3` 线性映射索引与权重已能从真实文件读出；其他构建若布局不同，仍以 `ww3_bounc` 退出码与时间覆盖为准。
- GUI 主题与地图预览未做桌面端实测；预览为 matplotlib 散点，不是完整海陆连通证明。
