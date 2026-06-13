# meshgen

[English](#english) | [简体中文](#简体中文)

## English

`meshgen` bundles three WW3 mesh workflows in one place:

- **Structured rectilinear grid** (`structured_generator`)
- **SMC grid** (`smc_generator`)
- **Unstructured triangle mesh** (`unstructured_generator`)

Each is a wrapper around upstream tools—[gridgen](https://gitlab.ifremer.fr/wave/tools/gridgen), [SMCGTools](https://github.com/ww3-opentools/SMCGTools), and [WW3-tools/unst_msh_gen](https://github.com/NOAA-EMC/WW3-tools/tree/develop/unst_msh_gen)—adapted for WAVEWATCH III grid setup.

### Directory layout

```text
meshgen/
├── get_reference_data.py
├── reference_data/                  # external reference data
├── structured_generator/            # structured (regular / curvilinear) grids
├── smc_generator/                   # SMC (SMCGTools)
└── unstructured_generator/          # unstructured (unst_msh_gen)
```

### Quick start

**1) Reference data**

You need `reference_data` first (bathymetry, coastline-related `.mat` / `.nc`, etc.).

**Default — GitHub split release (recommended)**

Run:

```bash
cd meshgen
python3 get_reference_data.py
```

**2) Generate a grid**

Each workflow is run from its folder with `python create_grid.py` (see each subfolder’s README for options).

The structured generator ships two stacks: **gridgen** (upstream/MATLAB-oriented) and **pygridgen** (Python port produced with AI assistance to avoid MATLAB). The project mainly uses **pygridgen**; outputs may differ slightly from gridgen but are acceptable for typical use.

More detail:

- `structured_generator/README.md`
- `smc_generator/README.md`
- `unstructured_generator/README.md`

---

## 简体中文

`meshgen` 将三类 WW3 网格流程整合在一个目录中：

- **结构化矩形网格生成器**（`structured_generator`）
- **SMC 网格生成器**（`smc_generator`）
- **非结构三角形网格生成器**（`unstructured_generator`）

它们分别是对 [gridgen](https://gitlab.ifremer.fr/wave/tools/gridgen)、[SMCGTools](https://github.com/ww3-opentools/SMCGTools)、[WW3-tools/unst_msh_gen](https://github.com/NOAA-EMC/WW3-tools/tree/develop/unst_msh_gen) 的二次封装，以适配 WAVEWATCH III 的网格要求。

### 目录结构

```text
meshgen/
├── get_reference_data.py
├── reference_data/                  # 外部参考数据
├── structured_generator/            # 结构化（规则/曲线）网格
├── smc_generator/                   # SMC 网格包装（SMCGTools）
└── unstructured_generator/          # 非结构网格包装（unst_msh_gen）
```

### 快速开始

**1）准备参考数据**

开始前需要准备好 `reference_data` (水深、岸线相关 `.mat` / `.nc` 等)，执行：

```bash
python get_reference_data.py
```





**2）生成网格**

每种网格一般可在对应目录下执行 `python create_grid.py`（具体参数见各子目录 README）。

结构化网格生成器包含两套实现：**gridgen** 为官方原始流程，**pygridgen** 为用 AI 辅助从原版转换的 Python 实现，以便脱离 MATLAB。当前主要使用 **pygridgen**；生成结果与 gridgen 可能存在细微差异，但在常见场景下可接受。

更多说明见：

- `structured_generator/README.md` 
- `smc_generator/README.md`
- `unstructured_generator/README.md`
