# WW3Tool Restart / 热启动支持方案

本文档描述 WW3 重启动机制、WW3Tool 现状差距、目标用户场景、配置与实现设计、验收标准与分阶段落地计划。与 `WW3常用配置补充计划.md` §3.1 对齐并展开为可实施规格。

---

## 1. 背景与目标

### 1.1 WW3 中的 Restart 是什么

`restart.ww3` 是二进制重启动文件，保存某一时刻全网格二维谱场状态。主积分程序 `ww3_shel`（单层）或 `ww3_multi`（嵌套）在启动时读取它作为初始海浪场。

| 方式 | 如何得到 `restart.ww3` | 何时使用 |
|------|------------------------|----------|
| **冷启动** | `ww3_strt` 按风场/JONSWAP 等生成初值 | 新算例、换网格后第一次跑 |
| **热启动** | 上一次积分输出的 `restart.ww3` 或 `restartN.ww3` 改名 | 延长预报、中断续跑、批量事件接力 |

WW3 手册（`manual/zh/run/design_zh.tex`）要点：

- 热启动**必须**有与当前 `mod_def.ww3` 网格/谱离散一致的 `restart.ww3`。
- 积分中可按 `DATE%RESTART`（单层）或 `ALLDATE%RESTART`（multi）**写出**新的 restart；`STRIDE=0` 表示不写。
- 运行中可产出 `restart1.ww3` … `restart9.ww3`；续跑前通常 `mv restart001.ww3 restart.ww3`（具体编号依版本与配置）。

### 1.2 WW3Tool 要解决的问题

当前 WW3Tool **每次运行都执行 `ww3_strt`**，仅配置了 restart **写出**时间窗（`DATE%RESTART%STRIDE` 多为模板默认 86400），**没有**：

- 从外部/上次运行引入 `restart.ww3` 的准备流程；
- 热启动时跳过 `ww3_strt`；
- 热启动时 `DOMAIN%START` 与 restart 时刻对齐；
- 嵌套各层 `restart.levelK` 的分别管理；
- GUI/CLI 一键切换冷/热启动。

目标：**在不大改现有工作流的前提下，支持冷启动（默认不变）与热启动（续跑/延长预报）**。

---

## 2. 用户场景

### 2.1 场景 A：延长预报（最常见）

- 已跑完 `2025-01-03` → `2025-01-05`，工作目录有 `restart.ww3`（或 `restart001.ww3`）。
- 希望接着跑到 `2025-01-10`。
- **要求**：`DOMAIN%START` = restart 内时刻（如 `20250105 235959` 或最后写出时刻）；`DOMAIN%STOP` = 新结束时间；强迫 `FORCING%TIMESTOP` 覆盖新时段；**不跑 `ww3_strt`**。


### 2.2 场景 B：中断续跑

- `ww3_shel` / `ww3_multi` 中途失败，目录里已有最近 checkpoint 的 `restartN.ww3`。
- 用户选定该文件，从同一 `DOMAIN%STOP` 重新提交。
- 与 A 类似，但 `end_date` 不变。

### 2.3 场景 C：嵌套网格热启动

- 各层 `levelK/restart.ww3` 或根目录 `restart.levelK`（`local.sh` staging 规则）。
- `ww3_multi` 前需把各层 restart 汇总到根目录命名；**每层**有 restart 则跳过该层 `ww3_strt`。
- `ALLDATE%RESTART%STRIDE` 与单层一致，由 `ww3.output_step` 同步驱动。

### 2.4 场景 D：跨工作目录复用 restart

- 从事件 A 的 workdir 拷贝 `restart.ww3` 到事件 B（网格、谱参数相同）。
- `restart.input_file` 指向源路径；prepare 阶段 copy 或 symlink 到目标 workdir。

### 2.5 非目标（首版不做）

- `ww3_uprstr` 同化更新 restart；
- 换网格后的 restart 插值（需专门工具）；
- 自动从 NetCDF 场重建 restart。



## 3. WW3Tool 现状

| 环节 | 现状 | 位置 |
|------|------|------|
| 运行流程 | 固定 `ww3_grid` → `ww3_prnc` → **`ww3_strt`** → `ww3_shel`/`ww3_multi` | `local.sh`、`server.sh`、`run_service.py` |
| restart 写出 | 写入 `DATE%RESTART%START/STOP`，**STRIDE 常保留模板 86400**，未接 `params.yml` | `ww3_shel_nml.py`、`ww3_multi_nml.py` |
| restart 读入 | 无准备逻辑；依赖 `ww3_strt` 生成 | — |
| 嵌套 staging | `restart.ww3` → `restart.$lv` | `local.sh` L155 |
| 配置 | `WW3Config` 仅有 `start_date`/`end_date`，无 restart 段 | `config_models.py`、`params.yml` |
| 文档 | README 提到「后续扩展」 | `README.zh-CN.md` §5.5 |



## 4. 配置设计（`params.yml`）

首版放在 **`params.yml` 的 `restart:` 段**，并在 GUI Step 4「WAVEWATCH 配置」中增加“启动方式”下拉选择；**默认值保持冷启动**，旧配置无需修改。

```yaml
restart:
  # cold：走 ww3_strt；restart：使用已有 restart.ww3，跳过 ww3_strt
  mode: cold

  # 手动热启动输入。pick_latest_checkpoint=false 时使用
  # 嵌套可为 map：{ level0: /path/to/restart.ww3, level1: ... }
  input_file: null

  # 手动热启动积分起点。pick_latest_checkpoint=true 时可为空，由最新 checkpoint 自动确定
  # 格式：YYYYMMDD 或 "YYYYMMDD HHMMSS"
  restart_time: null

  # 写出 restart 的间隔（秒），GUI 中与 ww3.output_step 共用同一个输入框
  # → DATE%RESTART%STRIDE / ALLDATE%RESTART%STRIDE
  output_step: 3600

  # Auto Latest / 自动最新：若存在 restart001.ww3 等，自动选最新并链接为 restart.ww3
  pick_latest_checkpoint: true
```

### 4.1 与 `ww3:` 段时间字段的关系

| 字段 | 冷启动 | 热启动 |
|------|--------|--------|
| `ww3.start_date` | `DOMAIN%START` | 仅用于强迫/输出**下界**参考；**积分起点**用 `restart.restart_time` |
| `ww3.end_date` | `DOMAIN%STOP` | `DOMAIN%STOP` |
| `restart.restart_time` | 忽略 | `pick_latest_checkpoint=false` 时使用；`pick_latest_checkpoint=true` 时由最新 checkpoint 自动确定 |

建议在 prepare 日志中**明确打印**：

```text
Restart 模式: restart
  输入: /path/to/restart.ww3
  积分起点 DOMAIN%START: 20250105 235959  (来自 restart_time)
  积分终点 DOMAIN%STOP:   20250110 235959
  写出间隔 DATE%RESTART%STRIDE: 3600
```

避免用户混淆 `start_date` 与热启动起点。

---

## 5. Namelist 映射

### 5.1 单层（`ww3_shel.nml`）

| params | namelist | 说明 |
|--------|----------|------|
| 热启动起点 | `DOMAIN%START` | `restart_time` |
| `ww3.end_date` | `DOMAIN%STOP` | 不变 |
| `restart.output_step`（由 `ww3.output_step` 同步） | `DATE%RESTART%STRIDE` | 替换当前「保留模板 STRIDE」行为 |
| `ww3.start_date` / `restart.restart_time` | `DATE%RESTART%START` | 热启动：= `restart_time`；冷启动：= `start_date` |
| `ww3.end_date` | `DATE%RESTART%STOP` | 不变 |
| `ww3.start_date` / 热启动起点 | `DATE%FIELD`、`DATE%POINT` 等 | 场/点输出起始：冷启动用 `start_date`；热启动用 `restart_time`（或用户可选「从起点起全输出」高级项，首版与 FIELD 一致） |

同步修改：

- `ww3_prnc*.nml`：`FORCING%TIMESTART` ≥ 热启动起点（或仍从 `start_date` 读全段强迫，由风场文件覆盖；**至少** `TIMESTOP` ≥ `end_date`）。
- `ww3_ounf.nml` / `ww3_ounp.nml`：`TIMESTART` 与 `DATE%FIELD` 策略一致。

### 5.2 嵌套（`ww3_multi.nml`）

| params | namelist |
|--------|----------|
| 同上 | `DOMAIN%START` / `DOMAIN%STOP` |
| `restart.output_step`（由 `ww3.output_step` 同步） | `ALLDATE%RESTART%STRIDE`、`ALLDATE%RESTART%START/STOP` |
| 场输出 | `ALLDATE%FIELD` 起始时间对齐热启动起点 |

各层 **不** 单独写 shel namelist；restart 文件按层放在 `levelK/restart.ww3`，prepare 后 staging 为 `restart.levelK`。

### 5.3 写出 STRIDE 当前问题

`ww3_shel_nml.py` 更新 `DATE%RESTART%START/STOP` 但 **未写入 `DATE%RESTART%STRIDE`**，导致一直用模板 86400。实现时应：

```python
DATE%RESTART%STRIDE = '{ww3.output_step}'
```

`ww3.output_step: 0` → `STRIDE = '0'`（关闭写出）。

---

## 6. 工作目录与文件约定

### 6.1 单层 workdir

```
workdir/
├── mod_def.ww3
├── restart.ww3          # 热启动输入；冷启动由 ww3_strt 生成
├── restart001.ww3       # 积分写出（可选）
├── wind.nc / wind.ww3
├── ww3_shel.nml
└── run.log
```

### 6.2 嵌套 workdir

```
workdir/
├── ww3_multi.nml
├── mod_def.level0, restart.level0, wind.level0, ...
├── level0/restart.ww3   # 层内副本（prepare 后）
└── level1/restart.ww3
```

热启动 prepare：

1. 若 `input_file` 为字符串 → 单层：link/copy 到 `restart.ww3`。
2. 若 `input_file` 为 dict / 列表（按 level 名）→ 各 `levelK/restart.ww3` + staging。
3. `pick_latest_checkpoint: true` 时，在目标目录扫描 `restart*.ww3`，取最新修改时间且谱头合法的作为输入，并由该 checkpoint 自动确定热启动时刻（首版可简化为「最大编号 N + 可解析时间」）。

### 6.3 校验（prepare 阶段必做）

| 检查 | 失败处理 |
|------|----------|
| `mod_def.ww3` 存在 | 报错：需先 `ww3_grid` |
| restart 文件存在且非空 | 报错：指定 `input_file` 或先冷启动 |
| 网格未变（对比 `grid.meta` / mod_def 哈希，可选） | 警告或拒绝热启动 |
| 手动模式下 `restart_time` 与文件内时间（若可解析） | 警告不一致 |
| 自动 checkpoint 模式无法确定 restart 时刻 | 报错：请关闭自动选择并手动填写 `restart_time` |
| 热启动起点 >= `end_date` | 拒绝 |

时间解析策略：`pick_latest_checkpoint=true` 时优先从最新 checkpoint 自动确定；若无法解析，再要求用户关闭自动选择并手动填写 `restart_time`。手动模式仍需校验 `restart_time` 与文件内时刻是否一致。

---

## 7. 运行流程改造

### 7.1 单层

```text
ww3_grid → ww3_prnc* → [冷启动: ww3_strt] → ww3_shel → 后处理
                      [热启动: 跳过 ww3_strt，要求 restart.ww3]
```

修改文件：

- `public/scripts/local.sh`、`public/scripts/server.sh`
- `src/workflows/infrastructure/local/run_service.py`

伪代码：

```bash
if restart_mode == "restart" && [ -f restart.ww3 ]; then
  log "热启动：跳过 ww3_strt"
else
  run_step ww3_strt
fi
```

### 7.2 嵌套

```text
for each levelK:
  ww3_grid → ww3_prnc* → [有 restart.ww3 则跳过 ww3_strt，否则 ww3_strt]
stage → ww3_multi → 后处理（最细层）
```

## 8. 代码模块划分

| 模块 | 职责 | 建议路径 |
|------|------|----------|
| `RestartConfig` | dataclass + YAML 解析 | `config_models.py` |
| `restart_service.py` | 校验、copy/link、选 checkpoint、嵌套多层 | `src/workflows/infrastructure/ww3/restart_service.py` |
| `ww3_shel_nml.py` | `DATE%RESTART%STRIDE`、热启动 `DOMAIN%START` | 已有文件扩展 |
| `ww3_multi_nml.py` | `ALLDATE%RESTART%STRIDE`、热启动 `DOMAIN%START` | 已有文件扩展 |
| `ww3_prnc_nml.py` | 强迫时间窗与热启动起点对齐 | 已有文件 |
| `prepare_ww3_files` | 调用 `restart_service.prepare_restart()` | `ww3_namelist_adapter.py` |
| `run_service` / shell | 条件跳过 `ww3_strt` | 见 §7 |
| i18n | `tr("restart_mode_hot", ...)` | `locales/*.json` |

### 8.1 `restart_service.prepare_restart()` 接口（草案）

```python
def prepare_restart(
    workdir: Path,
    config: RestartConfig,
    ww3: WW3Config,
    *,
    nested_levels: list[Path] | None,
    log: LogCallback,
) -> PreparedRestart:
    """返回实际使用的 restart 路径、restart_time、是否跳过 ww3_strt。"""
```

---

## 9. CLI / GUI

### 9.1 CLI（阶段 B 即可用）

```bash
# params.yml 设 restart.mode=restart 后
python3 run.py prepare-ww3 workdir_name
python3 run.py local-run workdir_name
```

可选覆盖：

```bash
python3 run.py prepare-ww3 workdir --restart-mode restart \
  --restart-file /path/to/restart.ww3 \
  --restart-time "20250105 235959"
```

### 9.2 GUI

Step 4 增加启动方式下拉：

- 单选：**冷启动** / **热启动**
- 首版仅写入 `restart.mode`；冷启动保持现有流程。
- 后续热启动执行逻辑接入后，`Auto Latest / 自动最新`（`pick_latest_checkpoint=true`）时隐藏文件选择器与 `restart_time`；关闭自动最新后才显示并保存手动文件与时间。restart 写出间隔与第四步已有的输出步长共用一个输入框。
- 嵌套热启动后续使用表格按 `level0`…`levelN` 指定各层 restart（可留空=用层目录内已有文件）。

首页**暂不**放 restart；与 `WW3常用配置补充计划.md` §7 一致。

---

## 10. 分阶段实施

### 阶段 A：配置层（1–2 天）

- [ ] `params.yml` 增加 `restart:` 默认值
- [ ] `RestartConfig` + 解析；缺省 `mode: cold`
- [ ] 单元测试：旧 yml 无 `restart` 段仍可加载

### 阶段 B：namelist + prepare（2–3 天）

- [ ] `ww3_shel_nml.py`：写入 `DATE%RESTART%STRIDE`；热启动改 `DOMAIN%START`
- [ ] `ww3_multi_nml.py`：同上 `ALLDATE%RESTART%*`
- [ ] `restart_service.py`：copy/link、校验、日志
- [ ] prepare 日志打印 §4.1 格式

**验收**：`mode: restart` 后 workdir 有 `restart.ww3`，namelist 与 yml 一致；`mode: cold` 与现网一致。

### 阶段 C：运行脚本（1–2 天）

- [ ] `local.sh` / `server.sh` / `run_service.py` 跳过 `ww3_strt`
- [ ] 嵌套逐层判断
- [ ] `run.log` 记录冷/热分支

**验收**：热启动算例不再调用 `ww3_strt`；冷启动仍调用。

### 阶段 D：GUI + 文档（1–2 天）

- [ ] Step 4 控件
- [ ] `README.zh-CN.md` §5.5 增「Restart / 热启动」
- [ ] 本方案链接进 `WW3常用配置补充计划.md` §3.1

### 阶段 E：回归算例（1 天）

- [ ] 小网格冷启动 2 天 → 写出 restart → 热启动再跑 2 天 → 检查 `log.ww3` 无异常、场输出时间连续
- [ ] 嵌套 2 层同样流程
- [ ] 故意删掉 restart → prepare 报错清晰

---

## 11. 测试用例清单

| ID | 描述 | 期望 |
|----|------|------|
| R1 | 默认 cold，无 `restart` 段 | 与当前行为 bit-for-bit 流程一致 |
| R2 | cold + `ww3.output_step: 3600` | `DATE%RESTART%STRIDE=3600` |
| R3 | restart + 工作目录内 `restart.ww3` | 跳过 strt，`DOMAIN%START=restart_time` |
| R4 | restart + 外部 `input_file` | 文件出现在 workdir，`run.log` 记来源 |
| R5 | restart + `ww3.output_step: 0` | 不写 restartN |
| R6 | nested restart 两层均有文件 | 两层跳过 strt，multi 成功 |
| R7 | restart 但 mod_def 缺失 | prepare 失败，错误中文明确 |
| R8 | `restart_time` > `end_date` | prepare 失败 |

---

## 12. 风险与限制

1. **网格/谱不一致**：热启动 restart 必须与当前 `mod_def` 匹配；改 `ww3_grid.nml` 后必须冷启动。
2. **时间对齐**：用户填错 `restart_time` 会导致强迫与初值不匹配；日志与文档需强调。
3. **嵌套复杂度**：各层 restart 时刻应一致；首版要求用户保证，不自动校验层间时间。
4. **远程运行**：`upload` 需包含 `restart.ww3`；检查 `WW3Tool` upload 文件列表是否已包含 `restart*`。
5. **7.14 vs 6.07**：两套 nml 模板均测；`DATE%RESTART` 合并写法与分行写法模板都要覆盖。

---

## 13. 与现有文档关系

- 本方案为 **`WW3常用配置补充计划.md` §3.1** 的详细设计稿。
- 嵌套网格文件布局见 **`嵌套网格设计与问题分析.md`** 与 `README.zh-CN.md` §5.5.7。
- 实现完成后在 `AGENTS.md` 增加一句：热启动通过 `params.yml` 的 `restart.mode` 配置，默认冷启动。

---

## 14. 小结

| 项目 | 内容 |
|------|------|
| 核心改动 | prepare 引入 restart；namelist 对齐时间与 STRIDE；运行跳过 `ww3_strt` |
| 默认行为 | **不变**（`mode: cold`） |
| 首版范围 | 单层 + 嵌套热启动/续跑；不做 uprstr、不做换网格插值 |
| 关键配置 | `restart.mode`、`input_file`、`restart_time`；restart 写出间隔由 `ww3.output_step` 同步 |

建议实施顺序：**A → B → C → E → D**，先保证 CLI/脚本路径可用，再补 GUI。
