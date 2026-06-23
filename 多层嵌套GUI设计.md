# WW3Tool 多层嵌套 GUI 设计方案

把 grid_panel 现有的**固定两块(外网格 + 内网格)**改造为**可增删的层列表**,与已完成的非 GUI 核心(levels 配置、level0…levelN 目录、ww3_multi.nml 的 N 个 MODEL、运行脚本循环、每层精度)对齐。布局采用**可滚动卡片**(每层一张卡)。

## 1. 现状(2 层硬编码在 GUI 哪里)

| 位置 | 文件 | 硬编码点 |
| --- | --- | --- |
| 区域输入 | steps/grid_panel.py | 写死 grid_*(外)与 grid_inner_*(内)两组 6 个 LineEdit,存于 self.fields[...] |
| 渲染 | grid_panel.render() | 从 grid.outer / grid.inner 逐字段 set_value |
| 回传 | grid_panel.overrides() | 返回 {"outer":…, "inner":…} |
| 生成按钮 | windows/preprocessing_window.py | _setup_outer_grid / _setup_inner_grid 用收缩系数互算外/内 |
| 地图 | preprocessing_window._view_region_map + infrastructure/region_map_renderer.py | 只画 outer + inner 两个框 |
| 写盘 | view_models/pipeline.py | overrides 的 outer/inner → 写 levels[0]/levels[-1](**已改**) |

字段是可编辑的 LineEdit(带经纬度/格距校验器)。"设置外/内网格"按钮按 nested_contraction_coefficient 自动套娃互算一组范围。

## 2. 目标 UI(可滚动卡片)

```
┌─ 嵌套层 ───────────────────[➕ 添加一层]─┐
│ ▌level0（最粗）            [➖ 删除] │  ← level0 经纬度与主域 grid.lon/lat 联动
│   DX [0.05 ] DY [0.05 ]            │
│   西[110.0] 东[130.0]              │
│   南[10.0 ] 北[30.0 ]              │
│   积分步[1800] 输出步[3600]        │
├───────────────────────────────────┤
│ ▌level1                   [➖ 删除] │
│   DX [0.025] DY [0.025]            │
│   西[115.0] 东[125.0]              │
│   南[15.0 ] 北[25.0 ]              │
│   积分步[900 ] 输出步[3600]        │
├───────────────────────────────────┤
│ ▌level2（最细）           [➖ 删除] │
│   …                                │
└───────────────────────────────────┘
  ⚠ level2 的 dx 必须比 level1 更细      ← 实时校验红字
[按收缩系数自动套娃]  [查看地图]
```

- 卡片放进 QScrollArea,层多时整体滚动;每张卡 2 列 × 4 行(8 个字段)。
- level0 标"最粗",最后一张标"最细";中间层只显示 levelI。
- level0 的经纬度即主域边界:改 level0 的西/东/南/北 → 同步 grid.lon/lat(与解析侧"level0 边界缺省取主域"一致)。

## 3. 组件改造

### 3.1 grid_panel.py(主改)

**新增 LevelRow(一张层卡)**:封装该层 8 个 LineEdit(dx/dy、lonW/lonE、latS/latN、compute_precision/output_precision)+ 标题 + 删除按钮,提供:
- to_override() -> dict:返回 {dx, dy, lon:[w,e], lat:[s,n], compute_precision, output_precision}(空串字段省略);
- set_from_region(region):从 GridRegion 填值;
- set_index(i, n):更新标题(level0=最粗 / levelN=最细)与删除按钮可用性(仅剩 1 层时禁删)。

**面板状态**:self.level_rows: list[LevelRow],容器 self.levels_container(QVBoxLayout in QScrollArea)。

**改造方法**:
- render(grid):清空 level_rows,按 grid.nested_levels 重建 N 张卡;normal 时仍只 1 张(就是单网格)。
- overrides():返回 {"mesh_type", "grid_type", "levels":[row.to_override() for row in level_rows]}(不再有 outer/inner key)。
- add_level():在末尾追加一张卡;默认值 = 复制上一层并把 dx/dy 减半、范围向中心收缩一档(用 nested_contraction_coefficient)。
- remove_level(i):删第 i 张卡(≥2 层才允许;normal 固定 1 层)。
- 实时校验 _validate_levels():逐层 dx 递减 + 套娃 + 层数 ≤ 99,违例在卡下方显示红字(不阻断,最终由解析兜底)。

### 3.2 preprocessing_window.py

- 删 _setup_outer_grid / _setup_inner_grid 两个按钮回调;新增:
  - _add_grid_level → grid_panel.add_level();
  - _remove_grid_level(i) → grid_panel.remove_level(i)(按钮在卡内,信号回传索引);
  - _auto_telescope:从 level0 起按 nested_contraction_coefficient 逐层往里算范围,批量填好所有层(替代原"互算外/内")。
- _view_region_map:outer/inner → 遍历 config.grid.nested_levels 求并集定 aspect、画 N 个框。

### 3.3 region_map_renderer.py

outer = grid.outer; inner = grid.inner → for i, lv in enumerate(grid.nested_levels):逐层画矩形框,颜色由粗到细渐变,框边标 levelI。

### 3.4 pipeline.py(overrides → levels)

当前 _build_workdir_params 接受 grid_overrides 里的 outer/inner 并映射到 levels(上次已改)。改为**直接接收 levels 列表**:grid_overrides["levels"] → 逐元素 _coerce_region 后写 nested_raw["levels"],grid_raw["lon"]/["lat"] 取 levels[0] 的经纬度。去掉 outer/inner 分支。

## 4. 数据流

```
params.yml levels ──parse──▶ GridConfig.nested_levels
        ▲                              │ render()
   pipeline 写 levels ◀── overrides({levels:[…]}) ◀── grid_panel 层卡(N 张)
        │                                                    │
        └──────────────── view_map / region_map_renderer 画 N 框 ◀┘
```

## 5. 校验

GUI 侧实时提示(红字),与 configuration.py 已有校验一致:
- 逐层 dx/dy 递减;第 k 层 ⊂ 第 k−1 层(套娃);层数 2–99(nested),normal 固定 1 层。
- GUI 只提示不阻断,生成前由解析 ConfigError 兜底。

## 6. 实施顺序

1. LevelRow 控件类 + grid_panel 动态列表(render / overrides / add / remove / 实时校验)。
2. preprocessing_window:增删层、自动套娃、view_map 画 N 框。
3. region_map_renderer:N 框渲染。
4. pipeline overrides:改传 levels 列表。
5. i18n:新增 step2_add_level / step2_remove_level / step2_level_title / step2_compute_step / step2_output_step 等翻译键。
6. **app 内实测**(PyQt 无法在此环境运行):增删层、套娃自动填、地图 N 框、生成跑通。

## 7. 兼容性

- 旧工作目录若是 coarse/fine 布局:运行脚本与 nml 应用已回退兼容;但 GUI 只认 levels,旧目录在 GUI 里需重新生成。
- GridConfig.outer/inner 作为 levels[0]/levels[-1] 派生访问器保留,其它消费方(grid_tools / match_jason3 / CLI)无需改。
