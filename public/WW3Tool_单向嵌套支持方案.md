# WW3Tool 单向嵌套支持方案

本文档描述 WW3Tool 支持 WAVEWATCH III 单向嵌套的设计方案。目标是在保留当前 `ww3_multi` 多网格耦合路线的基础上，新增一条更稳健、可检查、便于分层调试的单向嵌套路线。

---

## 1. 背景与目标

WW3Tool 当前的嵌套网格主要走 `ww3_multi` 路线：

```text
level0 + level1 + ... -> ww3_multi 一次性耦合运行
```

这种方式适合多网格同步耦合，但配置复杂，对网格重叠、边界点、掩码、资源分配都有较高要求。很多实际任务只是需要“外层粗网格提供内层细网格边界”，并不需要细网格反向影响粗网格。此时更适合单向嵌套。

单向嵌套的核心流程是：

```text
level0 先运行
  -> 输出 level1 所需边界谱
  -> level1 读取边界谱后运行
    -> 输出 level2 所需边界谱
    -> level2 继续运行
```

也就是能量和谱信息只从粗网格传给细网格，细网格不反馈粗网格。

本方案目标：

1. 保留现有 `ww3_multi` 行为，避免破坏旧工作目录。
2. 新增 `one_way` 嵌套模式。
3. 支持结构化矩形网格的两层与多层单向嵌套。
4. 让 GUI、`params.yml`、`local.sh`、`server.sh` 对单向嵌套有一致语义。
5. 默认结果仍然以最细层输出为主。

---

## 2. 总体设计

WW3Tool 的嵌套网格分成两种模式：

```text
ww3_multi  : 当前模式，多网格耦合，一次性运行 ww3_multi
one_way    : 单向嵌套，父网格先跑，子网格读取父网格边界后再跑
```

建议继续使用现有目录结构：

```text
workdir/
├── params.yml
├── level0/
│   ├── ww3_grid.nml
│   ├── ww3_prnc.nml
│   ├── ww3_shel.nml
│   ├── ww3_ounf.nml
│   ├── ww3_ounp.nml
│   ├── mod_def.ww3
│   └── ...
├── level1/
│   ├── ww3_grid.nml
│   ├── ww3_prnc.nml
│   ├── ww3_shel.nml
│   ├── boundary_from_level0.ww3
│   └── ...
└── level2/
    ├── ww3_grid.nml
    ├── ww3_shel.nml
    ├── boundary_from_level1.ww3
    └── ...
```

`ww3_multi` 模式仍按现有逻辑把各层文件 staging 到根目录，并运行：

```bash
mpirun -n "$MPI_NPROCS" ww3_multi
```

`one_way` 模式不使用 `ww3_multi.nml`，而是逐层执行：

```text
level0 -> level1 -> level2 -> ... -> levelN
```

每一层都可以视为一个独立的 WW3 单层算例。

---

## 3. 配置设计

### 3.1 推荐配置结构

建议在 `grid.structured.nested` 下增加 `mode` 和 `one_way` 配置：

```yaml
grid:
  grid_type: nested

  structured:
    nested:
      mode: one_way        # ww3_multi | one_way

      levels:
        - name: level0
          lon_min: 100.0
          lon_max: 140.0
          lat_min: 0.0
          lat_max: 45.0
          dx: 0.10
          dy: 0.10

        - name: level1
          parent: level0
          lon_min: 118.0
          lon_max: 128.0
          lat_min: 26.0
          lat_max: 34.0
          dx: 0.05
          dy: 0.05

      one_way:
        # null 表示使用 ww3.output_step
        boundary_step: null

        # 子网格边界距离父网格边界至少几个父网格单元
        boundary_margin_cells: 3

        # finest：只导出最细层结果；all：每层都导出
        output_levels: finest

        # 子网格是否继续使用本地风、流、水位强迫
        forcing_policy: native_plus_boundary
```

### 3.2 兼容旧配置

为了不破坏已有工作目录：

```yaml
grid:
  grid_type: nested
```

如果没有显式配置 `grid.structured.nested.mode`，默认等价于：

```yaml
grid:
  structured:
    nested:
      mode: ww3_multi
```

也就是老工作目录仍然走当前 `ww3_multi` 路线。

### 3.3 不建议的配置方式

不建议新增顶层字段：

```yaml
nesting:
  mode: one_way
```

原因是 WW3Tool 里嵌套网格已经属于 `grid.structured.nested` 的语义，放在同一段里更容易维护，也便于 GUI 和配置加载器做集中校验。

---

## 4. GUI 设计

### 4.1 Step 2：网格生成

在嵌套网格配置区域增加一个下拉框：

```text
嵌套方式:
  多网格耦合
  单向嵌套
```

英文：

```text
Nesting Mode:
  Multi-grid Coupling
  One-way Nesting
```

对应关系：

```text
多网格耦合 / Multi-grid Coupling -> ww3_multi
单向嵌套 / One-way Nesting       -> one_way
```

### 4.2 Step 4：WW3 参数

当选择 `one_way` 时，第四步需要显示：

```text
边界输出间隔
```

英文：

```text
Boundary Output Step
```

首版建议这个值默认跟 `ww3.output_step` 保持一致。如果用户没有特殊需求，不需要单独配置。

当选择 `ww3_multi` 时，不显示单向嵌套边界输出相关配置。

### 4.3 Step 5：Slurm 配置

Slurm 配置不需要新增单向嵌套专属输入。单向嵌套仍然使用：

```yaml
slurm:
  partition:
  nodes:
  cores:
  memory:
  nodelist:
  time:
```

区别在于脚本内部运行方式不同：

```text
ww3_multi 模式：一次 mpirun ww3_multi
one_way 模式：每层依次 mpirun ww3_shel
```

---

## 5. 运行流程

### 5.1 当前 `ww3_multi` 流程

当前嵌套模式大致是：

```text
准备 level0
准备 level1
准备 levelN
把各层 mod_def / restart / out 文件 staging 到根目录
运行 ww3_multi
把最细层结果移回 levelN
运行 ww3_ounf / ww3_ounp / ww3_trnc
```

这个流程继续保留。

### 5.2 新增 `one_way` 流程

单向嵌套运行流程：

```text
for level in level0..levelN:
    进入当前 level 目录
    运行 ww3_grid
    运行 ww3_prnc
    冷启动：运行 ww3_strt
    热启动：使用 restart.ww3，跳过 ww3_strt
    运行 ww3_shel

    如果当前层不是最细层:
        输出下一层需要的边界谱文件
        复制或链接到下一层目录

最细层运行 ww3_ounf / ww3_ounp / ww3_trnc
```

脚本结构建议：

```bash
if [ "$GRID_TYPE" = "nested" ] && [ "$NESTING_MODE" = "ww3_multi" ]; then
    run_nested_ww3_multi
elif [ "$GRID_TYPE" = "nested" ] && [ "$NESTING_MODE" = "one_way" ]; then
    run_nested_one_way
else
    run_single_grid
fi
```

### 5.3 单层执行细节

每一层内部仍遵循 WW3 单层运行顺序：

```bash
ww3_grid
ww3_prnc
ww3_strt      # 仅冷启动
mpirun -n "$MPI_NPROCS" ww3_shel
ww3_ounf
ww3_ounp
ww3_trnc
```

其中 `ww3_ounf`、`ww3_ounp`、`ww3_trnc` 默认只在最细层执行。若 `output_levels: all`，则每一层都执行输出转换。

---

## 6. 边界文件设计

### 6.1 文件命名

建议统一采用清晰命名：

```text
level1/boundary_from_level0.ww3
level2/boundary_from_level1.ww3
```

脚本运行时可以再按 WW3 程序需要软链接成固定文件名，例如：

```bash
ln -sf boundary_from_level0.ww3 nest.ww3
```

这样用户能看懂文件来源，同时不影响 WW3 执行。

### 6.2 父级输出

父级需要为子级边界点输出二维谱边界信息。具体实现应封装在版本适配模块中，不直接散落在脚本里。

建议新增模块：

```text
src/workflows/infrastructure/ww3/one_way_nested.py
src/workflows/infrastructure/ww3/boundary_nml.py
```

职责：

1. 根据父子网格关系确定边界点。
2. 生成父级边界输出配置。
3. 生成子级边界输入配置。
4. 屏蔽 WW3 6.07 和 7.14 的 namelist 差异。

### 6.3 子级输入

子级运行时必须读取父级输出的边界谱文件。子级仍然可以继续使用自己的风场、流场、水位等强迫：

```yaml
forcing_policy: native_plus_boundary
```

含义：

```text
边界波浪谱来自父网格
本地风场/流场/水位仍来自子网格自己的强迫文件
```

这也是首版最推荐的方式。

---

## 7. 校验规则

单向嵌套必须在准备阶段做严格校验。

### 7.1 空间关系校验

每个子网格必须满足：

```text
child.lon_min > parent.lon_min
child.lon_max < parent.lon_max
child.lat_min > parent.lat_min
child.lat_max < parent.lat_max
```

并且子网格边界到父网格边界至少保留：

```yaml
boundary_margin_cells: 3
```

对应物理距离：

```text
3 * parent.dx
3 * parent.dy
```

### 7.2 分辨率校验

子网格分辨率应高于父网格：

```text
child.dx < parent.dx
child.dy < parent.dy
```

建议首版要求整倍数关系：

```text
parent.dx / child.dx = integer
parent.dy / child.dy = integer
```

这样边界插值更稳定。

### 7.3 时间范围校验

子网格时间范围不能超过父网格：

```text
child.start_time >= parent.start_time
child.end_time   <= parent.end_time
```

如果所有层级使用同一套 `ww3.start_date` / `ww3.end_date`，则直接通过。

### 7.4 谱离散校验

首版建议所有层级共享同一套谱参数：

```yaml
ww3:
  spectrum:
    freq1:
    nk:
    nth:
    xfr:
```

如果父子网格谱离散不同，边界谱插值会复杂很多，不建议首版支持。

### 7.5 掩码与水深校验

子网格边界点应落在父网格有效湿点区域。如果边界点对应父网格陆地或掩码点，应该阻止运行并提示：

```text
子网格边界落在父网格无效海点上，请扩大父网格范围或调整子网格边界。
```

---

## 8. 热启动关系

单向嵌套下，每一层都是独立运行的 `ww3_shel`，因此每一层也需要独立处理 restart。

冷启动：

```text
level0: ww3_strt
level1: ww3_strt + boundary_from_level0
level2: ww3_strt + boundary_from_level1
```

热启动：

```text
level0: 使用 level0/restart.ww3，跳过 ww3_strt
level1: 使用 level1/restart.ww3，跳过 ww3_strt，同时读取 boundary_from_level0
level2: 使用 level2/restart.ww3，跳过 ww3_strt，同时读取 boundary_from_level1
```

如果某一层缺少 restart 文件，不能只让这一层冷启动而其他层热启动。首版建议直接报错：

```text
单向嵌套热启动要求每一层都有 restart.ww3。
```

---

## 9. 下载结果策略

默认只下载最细层：

```text
levelN/out_grd.*
levelN/out_pnt.*
levelN/ww3.*.nc
levelN/restart*.ww3
```

如果配置：

```yaml
grid:
  structured:
    nested:
      one_way:
        output_levels: all
```

则下载全部层级结果：

```text
level0/
level1/
levelN/
```

GUI 上可以先不暴露这个选项，默认 `finest` 即可。

---

## 10. 代码改造点

### 10.1 配置模型

修改：

```text
src/workflows/domain/config_models.py
src/workflows/application/configuration.py
```

新增：

```python
NestedMode = Literal["ww3_multi", "one_way"]
```

以及单向嵌套配置：

```python
class OneWayNestedConfig:
    boundary_step: Optional[int]
    boundary_margin_cells: int
    output_levels: Literal["finest", "all"]
    forcing_policy: Literal["native_plus_boundary"]
```

### 10.2 Namelist 适配

修改或新增：

```text
src/workflows/infrastructure/ww3/ww3_shel_nml.py
src/workflows/infrastructure/ww3/boundary_nml.py
src/workflows/infrastructure/ww3/one_way_nested.py
```

`ww3_shel_nml.py` 负责单层运行配置。  
`boundary_nml.py` 负责父级边界输出与子级边界输入。  
`one_way_nested.py` 负责层级关系、文件命名、校验、脚本变量生成。

### 10.3 脚本

修改：

```text
public/scripts/local.sh
public/scripts/server.sh
```

新增函数：

```bash
run_nested_one_way() {
    discover_nested_levels
    validate_one_way_levels

    for level in "${LEVELS[@]}"; do
        run_single_level "$level"

        if ! is_finest_level "$level"; then
            export_boundary_for_next_level "$level"
            prepare_child_boundary "$level"
        fi
    done

    export_finest_outputs
}
```

### 10.4 GUI

修改：

```text
src/desktop/windows/preprocessing_window.py
src/desktop/steps/ww3_panel.py
public/languages/zh_CN.json
public/languages/en_US.json
```

新增翻译：

```json
{
  "nesting_mode": "嵌套方式",
  "multi_grid_coupling": "多网格耦合",
  "one_way_nesting": "单向嵌套",
  "boundary_output_step": "边界输出间隔"
}
```

英文：

```json
{
  "nesting_mode": "Nesting Mode",
  "multi_grid_coupling": "Multi-grid Coupling",
  "one_way_nesting": "One-way Nesting",
  "boundary_output_step": "Boundary Output Step"
}
```

---

## 11. 日志设计

准备阶段应明确打印当前嵌套模式：

```text
✅ Nested grid mode: One-way Nesting
✅ Levels: level0 -> level1 -> level2
✅ Boundary output step: 3600 s
✅ Output levels: finest
```

每一层运行时打印：

```text
▶ Running level0
✅ level0 finished
✅ Boundary exported: level1/boundary_from_level0.ww3

▶ Running level1
✅ Boundary input: boundary_from_level0.ww3
✅ level1 finished
```

失败时必须指出是哪一层失败：

```text
❌ level1 failed while reading boundary_from_level0.ww3
```

---

## 12. 实施阶段

### 阶段一：配置与 GUI

1. 增加 `mode: ww3_multi | one_way`。
2. GUI 增加“嵌套方式”下拉框。
3. 默认旧配置仍走 `ww3_multi`。
4. 准备阶段日志能显示当前嵌套模式。

### 阶段二：脚本分流

1. `local.sh` / `server.sh` 把 nested 分成两条路径。
2. `ww3_multi` 路径保持原行为。
3. `one_way` 路径先实现逐层运行框架。

### 阶段三：边界输出与读取

1. 实现父级边界输出配置。
2. 实现子级边界输入配置。
3. 支持两层结构化矩形网格。
4. 跑一个小算例验证。

### 阶段四：多层与热启动

1. 支持 level0 -> level1 -> level2。
2. 热启动时要求每层都有 restart。
3. 下载结果默认取最细层。

### 阶段五：文档与测试

1. 更新 `README.zh-CN.md`。
2. 增加配置解析测试。
3. 增加脚本 dry-run 测试。
4. 增加一个最小双层嵌套样例。

---

## 13. 验收标准

首版可认为完成的标准：

1. `grid_type: nested` 且 `mode: ww3_multi` 时，旧工作流不变。
2. `grid_type: nested` 且 `mode: one_way` 时，不生成、不运行 `ww3_multi.nml`。
3. 两层结构化网格可以顺序执行：

```text
level0 ww3_shel -> boundary_from_level0.ww3 -> level1 ww3_shel
```

4. 最细层可以正常生成 `ww3_ounf` / `ww3_ounp` 输出。
5. GUI 中能选择“多网格耦合”或“单向嵌套”。
6. 子网格超出父网格、边界贴边、分辨率不合理时会阻止运行并给出明确错误。
7. 远程运行和本地运行使用同一套嵌套模式语义。

---

## 14. 结论

WW3Tool 支持单向嵌套时，不应继续强行复用 `ww3_multi` 的运行逻辑，而应把它作为独立嵌套模式：

```text
ww3_multi：多网格耦合，一次性运行
one_way：父级先跑，输出边界，子级再跑
```

首版建议只支持结构化矩形网格，默认输出最细层结果，并要求所有层级共享谱离散。这样可以用最小改动获得一个更稳健、可调试、适合实际近岸细化计算的嵌套方案。
