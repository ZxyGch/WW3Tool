# WW3Tool

## 基本介绍

![](public/resource/README-media/2026-03-29%2012.28.47.png)

Youtube: [https://m.youtube.com/watch?v=PHXLP1FrZmw&pp=ygUHd3czdG9vbA%3D%3D](https://m.youtube.com/watch?v=PHXLP1FrZmw&pp=ygUHd3czdG9vbA%3D%3D)

WW3Tool 是 WAVEWATCH III 模型的前置准备操作软件，使用本软件可以完成基本的 WAVEWATCH III 流程化运行。

本软件包括以下功能：

1. 支持多种强迫场：风场 (ERA5，CFSR，CCMP)、流场 (Copernicus)、水位场(Copernicus)、海冰场(Copernicus)，包含对强迫场的自动修复功能 （纬度排序、时间修复、变量修复）

2. gridgen，pygridgen 结构化矩形网格生成，JIGSAW 三角形非结构化网格生成，SMCGTools SMC 网格生成，对于结构化矩形网格支持最多两层的嵌套网格模式

3. 支持区域计算、二维谱点计算、航迹计算

4. 支持 Slurm 脚本配置（ssh 配置、slurm 核数、节点数、CPU）

5. 自动配置 ww3_grid.nml，ww3_prnc.nml ，ww3_shel.nml，ww3_ounf.nml，ww3_multi.nml 等文件，配置包括：网格文件配置、计算精度、输出精度、时间范围、二维谱点计算、航迹计算、谱分区输出、强迫场配置。

6. 波高图、波高视频、等高线图、二维谱图、JASON3 卫星轨迹图、二维谱图

这个软件可以运行在 Win/Linux/Mac，几乎完全由 Python 组成（保留 gridgen 原始 Matlab 代码）

软件支持中英文切换，交互式终端可通过 `--lang en_US` 切换到英文，默认为中文。

实际运行的 WAVEWATCH III 模型需要自行在安装本地或服务器上，本软件暂时无法提供安装程序，请查看教程：[https://github.com/ZxyGch/WAVEWATCH-III-INSTALL-TUTORIAL](https://github.com/ZxyGch/WAVEWATCH-III-INSTALL-TUTORIAL)

我本科不是海洋科学的，现在是研究生一年级，目前掌握的 WAVEWATCH III 用法只有这些，如果你有更多的想法，请联系我 [atomgoto@gmail.com](mailto:atomgoto@gmail.com) 或在 issue 中提出意见

如果你觉得这个工具不错，请给我一颗 ⭐️ 🥳



## 快速开始

```sh
python3 runDesktop.py
```

如果还有什么安装失败或缺失的包，请手动安装



### 交互式命令行

如果更习惯终端操作，可以使用 `runInteractive.py` 进入交互式 REPL 环境：

```sh
python3 runInteractive.py
python3 runInteractive.py /path/to/workdir/params.yml
python3 runInteractive.py --lang en_US
```



### 指令化预处理流程

新架构代码从 `src` 开始维护。如果希望在流程脚本或服务器任务中调用预处理功能，可以使用 `src/run.py`：

```sh
python3 src/run.py
python3 src/run.py create-workdir myRun
python3 src/run.py validate /path/to/workdir/params.yml
python3 src/run.py prepare-forcing /path/to/workdir/params.yml
python3 src/run.py generate-grid /path/to/workdir/params.yml
python3 src/run.py prepare-ww3 /path/to/workdir/params.yml
python3 src/run.py run /path/to/workdir/params.yml
python3 src/run.py upload /path/to/workdir/params.yml --confirm
python3 src/run.py submit /path/to/workdir/params.yml
python3 src/run.py check-status /path/to/workdir/params.yml
python3 src/run.py download-results /path/to/workdir/params.yml
python3 src/run.py plot-wave-maps /path/to/workdir/params.yml
python3 src/run.py plot-jason3 /path/to/workdir/params.yml
python3 src/run.py plot-ndbc /path/to/workdir/params.yml --download
```

单独执行 `python3 src/run.py` 会检查运行所需依赖；如果有缺失，会自动依据 `src/requirements.txt` 安装。CLI 不允许直接使用项目根目录的 `params.yml`（那是模板），必须先用 `create-workdir` 创建工作目录，然后对工作目录的 `params.yml` 执行操作。也可以使用 `python3 src/run.py print-example` 单独输出模板内容。

命令按功能分为四组：预处理（`create-workdir`、`validate`、`prepare-forcing`、`generate-grid`、`prepare-ww3`、`run-pre-workflow`）、后处理/绘图（`plot-wave-maps`、`plot-spectrum`、`plot-jason3`、`plot-jason3-swh`、`download-jason3`、`plot-ndbc`）、远程运维（`connect-test`、`ssh`、`list-files`、`upload`、`submit`、`check-status`、`queue-status`、`download-results`、`download-log`、`clear-remote`、`cancel-job`）、辅助（`print-example`、`config`、`print`）。

`prepare-forcing` 只执行第一步强迫场准备，包括复制/移动、变量识别、风场标准化和组合强迫场自动关联。`generate-grid` 单独执行网格生成，支持 `--no-cache` 跳过缓存。`prepare-ww3` 只生成 WW3 namelist 文件（ww3_grid.nml、ww3_shel.nml、ww3_prnc.nml 等），不会重跑强迫场和网格，适合在已经准备好强迫场和网格之后单独调整 WW3 配置。

指令入口直接调用 `src/workflows`。桌面入口的预处理主页同样调用 workflows，当前覆盖强迫场准备、参数校验和预处理文件生成；其余界面动作会按步骤迁移到相同逻辑。

显式使用 `run` 会读取工作目录的 YAML 参数文件，完成强迫场准备、网格生成、计算模式产物和 WW3 配置文件生成，但不会自动执行 WAVEWATCH III、上传服务器或绘图。如果工作目录中已经有网格文件，可以使用 `--skip-grid` 跳过网格生成：

```sh
python3 src/run.py run /path/to/workdir/params.yml --skip-grid
```

`params.yml` 中的 `grid` 参数按网格类型分组：`structured` 包含水深、海岸线精度及 pygridgen 阈值；`smc` 包含水深类型、细化层数、物理和边界参数；`unstructured` 包含三角网格尺度、梯度、深水阈值及区域边界细分参数。`grid_type: nested` 时可显式填写 `inner`，也可以省略 `inner` 并由 `nested_contraction_coefficient` 自动生成内网格区域。

`params.yml` 顶部的 `presets` 预存可用选项，供脚本校验并供后续桌面界面复用，包括输出字段方案、ST 路径、水深、海岸线精度和文件分割。代码本身不预设任何 ST 版本，所有 ST 预设完全由 `params.yml` 中的 `presets.st` 定义，以名称映射服务器可执行目录路径，例如 `ST2: /public/home/.../model/exe`，随后由 `ww3.st: ST2` 选择使用哪条路径。`presets.output_scheme` 中完整定义字段数组，例如 `standard: [HS, DIR, FP, T02, WND]`，实际运行时通过 `ww3.output_scheme: standard` 选择方案。

`ww3_grid` 直接使用 `ww3_grid.nml` 键名，例如 `SPECTRUM%XFR`、`TIMESTEPS%DTMAX`、`GRID%ZLIM`，用于配置频谱离散、数值积分步长和近岸深度参数。嵌套网格还可以通过 `ww3.inner_compute_precision` 与 `ww3.inner_output_precision` 单独配置内网格输出；`slurm.server_script_path` 可选用自定义 `server.sh` 模板。




## 环境配置

本软件支持 Python ≥ 3.8，经测试可在以下系统环境下正常运行：

- Windows 11
- Ubuntu 24
- macOS 15

本软件不要求在本地安装 WAVEWATCH III，本地运行仅作为可选方案，仅需确保服务器端已正确部署以下环境：

- WAVEWATCH III
- Slurm 作业调度系统




## 功能实现细节

### 创建工作目录

![](public/resource/README-media/2026-03-29%2012.46.28.png)

程序启动时选择或创建工作目录，这一步是强制的，不允许跳过。

我们默认的新工作目名称是当前时间，下面会最多显示 3 个最近的工作目录。

工作目录本质上没有什么特殊的，只是一个文件夹而已，用于存放我们在运行中产生的各种文件，例如网格文件，风场文件，WAVEWATCH III 配置文件。

工作目录的默认路径是 WW3Tool/workSpace，在设置页面可以更改默认的工作目录



### 选择强迫场文件

风场可以使用来自 [ERA5](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download) ， [CFSR](http://tds.hycom.org/thredds/catalog/datasets/force/ncep_cfsv2/netcdf/catalog.html) ，[CCMP](https://data.remss.com/ccmp/v03.1/) 的数据

其他强迫场我暂时只尝试了 Copernicus 的流场、水位场、海冰场

![](public/resource/README-media/2026-03-29%2012.47.52.png)

我已经在 WW3Tool/public/forcing 预先准备好了几个强迫场文件，你可以直接选择使用（当然，这只是为了测试）。

由于 WAVEWATCH 要求纬度必须从小到大，而 ERA5 的风场数据纬度默认是从大到小，因此，我在这里加上了隐含的转换逻辑，会判断是否纬度是从小到大的，如果不是则会自动转换。

![](public/resource/README-media/2026-03-29%2012.48.29.png)

并且对于 CFSR 的风场会自动修复变量名称符合 WW3 的要求

另外 Copernicus 强迫场的时间标签也会在这个过程中自动修复。

强迫场文件会被自动复制（如果你想剪切，在设置页面可以更改）到当前工作目录，并改名为 wind.nc，current.nc，level.nc，ice.nc ，右侧的日志会同时输出强迫场文件的信息。

通常，我们只使用风场作为强迫场即可，并且软件不允许只使用其他强迫场而不包含风场。

如果一个文件内包含多种强迫场，那么会自动填充相应的按钮，并且这个文件在工作目录会命名为类似 current_level.nc ，表明其中包含的强迫场




### 生成网格文件

#### reference_data

reference_data 数据包内含 gebco、etopo1/2 及海岸边界等文件，它们是网格生成的必要数据，如果没有 reference_data，将无法生成网格文件。

如果 WW3Tool/WW3-Grid-Generator/reference_data 没有找到这些数据文件，那么在第二步生成网格时会弹出一个下载窗口

![](public/resource/README-media/2026-03-29%2012.52.20.png)

点击下载按钮：程序会从自动从 [GitHub Release](https://github.com/ZxyGch/WW3Tool/releases/tag/data) 下载（大约 6.5GB）。

![](public/resource/README-media/2026-03-29%2013.04.16.png)

若 GitHub下载过慢或失败，可从 [OneDrive](https://tiangongeducn-my.sharepoint.com/:u:/r/personal/1911650207_tiangong_edu_cn/Documents/reference_data.zip?csf=1&web=1&e=SXDbA9) 或[百度网盘](https://pan.baidu.com/s/1SxQEfiaomdi3CXFOXC6DMw?pwd=cb48) 手动下载，解压到 WW3Tool/WW3-Grid-Generator/reference_data








#### 结构化矩形网格

##### 单网格

![](public/resource/README-media/2026-03-29%2013.28.40.png)

点击生成网格，会调用 WW3-Grid-Generator/structured_generator/pygridgen 生成网格文件到工作目录.

DX/DY 越小，精度越高，因为 DX/DY 是网格之间的间距

最后在工作目录下，会多出四个文件 grid.bot 、grid.obst、grid.meta、grid.mask_nobound

1. **`grid.bot`**
   - 格式：ASCII 文本文件
   - 内容：网格水深数据 (来)
   - 单位：来 (实际值 = 文件值 / 1000)
   - 尺寸：Ny × Nx

2. **`grid.mask_nobound`**
   - 格式：ASCII 文本文件
   - 内容：陆海掩膜
   - 值：0 = 陆地，1 = 海洋
   - 尺寸：Ny × Nx

3. **`grid.obst`**
   - 格式：ASCII 文本文件
   - 内容：x 和 y 方向的障碍物值
   - 单位：0-1 之间的比例 (实际值 = 文件值 / 100)
   - 尺寸：Ny × Nx (x 方向)，Ny × Nx (y 方向)

4. **`grid.meta`**(实际上是 ww3_grid. nml，用于同步一些配置)
   - 格式：ASCII 文本文件
   - 内容：供 WAVEWATCH III `ww3_grid` 使用的网格描述
   - 包含：网格尺寸、分辨率、范围等信息

   生成的网格会自动缓存到 WW3Tool/WW3-Grid-Generator/cache


   

##### 嵌套网格

![](public/resource/README-media/2026-03-29%2013.49.42.png)

嵌套网格我们使用的是 Two-way nesting

我们在设置页面的规定了一个：嵌套网格收缩系数，我们默认设置为 1.1 倍

当我们点击设置外网格我们会自动根据内网格的范围向外扩张，相当于内网格的 1.1 倍

同理，点击设置内网格，会自动根据外网格的范围向内收缩 1.1 倍

嵌套模式下生成网格会生成执行两次，一次生成外网格，一次生成内网格。

我们在嵌套网格模式下生成的网格，会在当前工作目录创建两个文件夹：coarse 和 fine，其中 coarse 存放外网格，fine 存放内网格。

当工作目录存在 coarse 和 fine 文件夹时，打开该目录会自动切换到嵌套网格模式，这对后续的很多操作都会产生影响，因此我们规定当本地已经存在 coarse 和 fine 文件夹或者已经存在其他网格文件，禁止切换网格类型。




#### SMC 网格


#### 非结构化三角形网格




#### 网格缓存

为了避免无意义的计算，每次生成的网格我们都会在 WW3Tool/WW3-Grid-Generator/cache 中缓存。

根据网格的生成参数生成 key，作为文件夹的名称，这样每次生成网格的时候会先遍历缓存，如果已经存在缓存了，则直接使用缓存的网格文件。

每个缓存文件夹下，还有 params.json 可以查看

```json
{
  "cache_key": "c161115dfd8bde7b30fd01826a3c292ada7835df377a81b9ee59f73acc28328b",
  "source_dir": "/Users/zxy/ocean/WW3Tool/workSpace/2026-01-11_23-18-38",
  "parameters": {
    "dx": 0.05,
    "dy": 0.05,
    "lon_range": [
      110.0,
      130.0
    ],
    "lat_range": [
      10.0,
      30.0
    ],
    "ref_dir": "/Users/zxy/ocean/WW3Tool/WW3-Grid-Generator/reference_data",
    "bathymetry": "GEBCO",
    "coastline_precision": "full"
  }
}
```




#### 查看地图

注意虚线内的范围才是真正的地图范围
![](public/resource/README-media/2026-03-29%2016.59.47.png)



### 选择计算模式

![](public/resource/README-media/2026-03-29%2014.32.55.png)

其实这三种计算模式计算量上是一样的，但是最终输出的结果有些不同，看似谱空间逐点计算模式和航迹模式似乎是只计算几个点，但是计算的实际是整个地图范围。

普通的区域计算模式就是基础的 ww3_ounf 输出

谱空间逐点计算模式就是加了个 ww3_ounp

航迹模式就是 ww3_trnc

在第四步的配置参数可以看出他们的配置区别



#### 区域计算模式

普通的计算模式



#### 谱空间逐点计算模式

![](public/resource/README-media/2026-03-29%2014.55.42.png)

我们可以点击从地图上选点，会打开一个窗口

我们在地图上点击选点，注意蓝色虚线方框内的是网格文件的范围，我们只能在这里面选点，选好后我们点击完成按钮。

![](public/resource/README-media/2026-03-29%2014.56.14.png)

随后，在第四步的确认参数时会在工作目录生成一个 points.list 文件

```swift
117 18 '0'
126 21 '1'
127 20 '2'
115 15 '3'
128 14 '4'
126 18 '5'
```

points.list 的三列分别是：经度、纬度、点名称，当某个工作目录存在 points.list 文件时，打开该工作目录计算模式会自动切换到：谱空间逐点计算，并自动导入 points.list 的点

最后我们经过 WW3 的运算后可以得到 ww3.2025_spec.nc 在绘图界面

![](public/resource/README-media/2026-03-29%2015.49.57.png)

我们可以画出二维谱图

![](workSpace/global/photo/spectrum/spectrum_3_time_20250104_120000.png)


#### 航迹模式

![](public/resource/README-media/2026-03-29%2015.52.47.png)

和谱空间逐点计算模式很像，但是新增了一列时间，在第四步确认参数的时候会生成一个文件：track_i.ww3，格式如下

```
WAVEWATCH III TRACK LOCATIONS DATA 
20250103 000000   113.121   19.314    0
20250104 000000   126.442   21.132    1
20250105 000000   126.365   16.356    2
```

最后我们会使用 ww3_trnc 输出一个 ww3.2025_trck.nc





### 配置运行参数


![](public/resource/README-media/2026-03-29%2016.37.17.png)

![](public/resource/README-media/2026-03-29%2016.14.29.png)
我们添加了风场、水位场、流场作为强迫场，冰场可以添加，但是我们生成的网格区域没有冰，因此在这里不做展示。

我们使用的是航迹模式，这个模式会比普通的区域计算模式多一些配置日志，顺便把航迹模式的特有的配置讲解一下。


```log
✅ 已复制 10 个 public/ww3 文件到当前工作目录
✅ 已成功同步 grid.meta 参数到 ww3_grid.nml
✅ 已修改 ww3_shel，ww3_ounf 的谱分区输出方案
✅ 已更新 server.sh：-J=202501, -p=CPU6240R, -n=48, -N=1, MPI_NPROCS=48, CASENAME=202501, ST=ST2
✅ 已更新 ww3_ounf.nml：FIELD%TIMESTART=20250103，FIELD%TIMESTRIDE=3600秒
✅ 已更新 ww3_shel.nml：DOMAIN%START=20250103, DOMAIN%STOP=20250105, DATE%FIELD%STRIDE=1800s
✅ 已修改 ww3_prnc.nml：FORCING%TIMESTART = '20250103 000000', FORCING%TIMESTOP = '20250105 235959'
✅ 已复制并修改 ww3_prnc_current.nml：FORCING%FIELD%CURRENTS = T
✅ 已复制并修改 ww3_prnc_level.nml：FORCING%FIELD%WATER_LEVELS = T
✅ 已修改 ww3_shel.nml：更新 INPUT%FORCING%* 设置
✅ 已生成 track_i.ww3 文件
✅ 已修改 ww3_shel.nml：添加 DATE%TRACK（航迹模式）
✅ 已修改 ww3_trnc.nml：TRACK%TIMESTART = '20250103 000000', TRACK%TIMESTRIDE = '3600'
```



#### 普通网格

首先，我们会把 WW3Tool/public/ww3 目录下的所有文件复制到当前工作目录

```
✅ 已复制 10 个 public/ww3 文件到当前工作目录
```

其中包含 

![](public/resource/README-media/2026-03-29%2016.18.02.png)

---

接下来

```log
✅ 已成功同步 grid.meta 参数到 ww3_grid.nml
```

我们会把 grid.meta 的

```
&GRID_NML
  GRID%TYPE            =  'RECT'
  GRID%COORD           =  'SPHE'
  GRID%CLOS            =  'NONE'
/


&RECT_NML
  RECT%NX              =  201
  RECT%NY              =  201
  RECT%SX              =   0.100000000000
  RECT%SY              =   0.100000000000
  RECT%X0              =  110.0000
  RECT%Y0              =   10.0000
/

&DEPTH_NML
  DEPTH%SF             = 0.001
  DEPTH%FILENAME       = 'grid.bot'
/

&OBST_NML
  OBST%SF              = 0.010
  OBST%FILENAME        = 'grid.obst'
/
```

同步到 ww3_grid.nml 相同的位置


---

然后修改谱分区输出方案

```swift
✅ 已修改 ww3_shel，ww3_ounf 的谱分区输出方案
```

ww3_shel.nml 的 TYPE%FIELD%LIST

```swift
&OUTPUT_TYPE_NML
  TYPE%FIELD%LIST       = 'HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS'
/
```

ww3_ounf.nml 的 FIELD%LIST

```swift
&FIELD_NML
  FIELD%TIMESTART        =  '20250103 000000'
  FIELD%TIMESTRIDE       =  '3600'
  FIELD%LIST             =  'HS DIR FP T02 WND PHS PTP PDIR PWS PNR TWS'
  FIELD%PARTITION        =  '0 1'
  FIELD%TYPE             =  4
/
```

谱分区的输出方案在设置页面可以配置 

![](public/resource/README-media/2026-03-29%2016.26.34.png)


---

再然后，我们修改 server.sh 文件

```log
✅ 已更新 server.sh：-J=202501, -p=CPU6240R, -n=48, -N=1, MPI_NPROCS=48, CASENAME=202501, ST=ST2
```

```sh
#SBATCH -J 202501
#SBATCH -p CPU6240R
#SBATCH -n 48
#SBATCH -N 1
#SBATCH --time=2880:00:00

#wavewatch3--ST2
export PATH=/public/home//software/wavewatch3/model/exe/exe:$PATH

MPI_NPROCS=48

CASENAME=202501
```

---

```log
✅ 已更新 ww3_ounf.nml：FIELD%TIMESTART=20250103，FIELD%TIMESTRIDE=3600秒
```

然后修改 ww3_ounf.nml，找到下面

```swift
&FIELD_NML
  FIELD%TIMESTART        =  '20250103 000000'
  FIELD%TIMESTRIDE       =  '3600'
  FIELD%LIST             =  'HS LM T02 T0M1 T01 FP DIR SPR DP PHS PTP PLP PDIR PSPR PWS TWS PNR'
  FIELD%PARTITION        =  '0 1'
  FIELD%TYPE             =  4
/
```

FIELD%TIMESTART 为起始时间，FIELD%TIMESTRIDE 是输出精度

---

```log
✅ 已更新 ww3_shel.nml：DATE%FIELD%START=20250103, DATE%FIELD%STRIDE=1800s, DATE%FIELD%STOP=20250105
```

我们修改 ww3_shel.nml

```swift
&DOMAIN_NML
  DOMAIN%START           =  '20250103 000000'
  DOMAIN%STOP            =  '20250105 235959'
/

&OUTPUT_DATE_NML
  DATE%FIELD          = '20250103 000000' '1800' '20250105 235959'
  DATE%TRACK          = '20250103 000000' '1800' '20250105 000000'
  DATE%RESTART        = '20250103 000000' '86400' '20250105 235959'
/
```

其中日期即为起始日期，另外 DATE%FIELD 和 DATE%TRACK 中间的 '1800' 是计算时间步长

其中 DATE%TRACK 是航迹模式会单独添加的一条，默认是没有的。

---

```log
✅ 已修改 ww3_prnc.nml：FORCING%TIMESTART = '20250103 000000', FORCING%TIMESTOP = '20250105 235959'
✅ 已复制并修改 ww3_prnc_current.nml：FORCING%FIELD%CURRENTS = T
✅ 已复制并修改 ww3_prnc_level.nml：FORCING%FIELD%WATER_LEVELS = T
```

然后我们修改 ww3_prnc.nml 的时间范围，这是为了在之后的 ww3_prnc 限制时间范围

```sh
&FORCING_NML
  FORCING%TIMESTART            = '19000101 000000'  
  FORCING%TIMESTOP             = '29001231 000000'  
  FORCING%FIELD%WINDS          = T
  FORCING%FIELD%CURRENTS       = F
  FORCING%FIELD%WATER_LEVELS   = F
  FORCING%FIELD%ICE_CONC       = F
  FORCING%FIELD%ICE_PARAM1     = F
  FORCING%GRID%LATLON          = T
/
```

然后我们根据选择的强迫场生成 ww3_prnc_current.nml ww3_prnc_level.nml，对于冰场，冰场的浓度和厚度会分成两个 ww3_prnc_ice.nml 和 ww3_prnc_ice1.nml

我们会根据强迫场修改强迫场的开关，每个 ww3_prnc.nml 文件的强迫场开关 FORCING%FIELD% 只能打开一个（设为 T），但是在后续处理的时候我们会把每个  ww3_prnc_.nml 重命名为 ww3_prnc.nml ，因为 ww3_prnc 只能固定读取  ww3_prnc.nml

我们还修改了强迫场的文件名和强迫场变量

```
&FILE_NML
  FILE%FILENAME      = 'wind.nc'
  FILE%LONGITUDE     = 'longitude'
  FILE%LATITUDE      = 'latitude'
  FILE%VAR(1)        = 'u10'
  FILE%VAR(2)        = 'v10'
/

&FILE_NML
  FILE%FILENAME      = 'current_level.nc'
  FILE%LONGITUDE     = 'longitude'
  FILE%LATITUDE      = 'latitude'
  FILE%VAR(1)        = 'uo'
  FILE%VAR(2)        = 'vo'
/

&FILE_NML
  FILE%FILENAME      = 'current_level.nc'
  FILE%LONGITUDE     = 'longitude'
  FILE%LATITUDE      = 'latitude'
  FILE%VAR(1)        = 'zos'
/
```


---

```log
✅ 已修改 ww3_shel.nml：更新 INPUT%FORCING%* 设置
```

根据我们使用的强迫场，修改 ww3_shel.nml

```
&INPUT_NML
  INPUT%FORCING%WINDS         = 'T'
  INPUT%FORCING%WATER_LEVELS  = 'T'
  INPUT%FORCING%CURRENTS      = 'T'
  INPUT%FORCING%ICE_CONC      = 'F'
  INPUT%FORCING%ICE_PARAM1    = 'F'
/
```




---

根据当前的航迹模式的点列表或者谱空间逐点计算的点列表我们生成

```log
✅ 已生成 track_i.ww3 文件
```

track_i.ww3 的格式

```
WAVEWATCH III TRACK LOCATIONS DATA 
20250103 000000   113.1   19.3    0
20250104 000000   126.4   21.1    1
20250105 000000   126.4   16.4    2
```



---

```log
✅ 已修改 ww3_shel.nml：添加 DATE%TRACK（航迹模式）
```

我们还会在 ww3_shel.nml 添加

```
&OUTPUT_DATE_NML
   DATE%FIELD          = '20250103 000000' '1800' '20250105 235959'
   DATE%TRACK          = '20250103 000000' '1800' '20250103 000000'
   DATE%RESTART        = '20250103 000000' '86400' '20250105 235959'
/
```

---

```log
✅ 已修改 ww3_trnc.nml：TRACK%TIMESTART = '20250103 000000', TRACK%TIMESTRIDE = '3600'
```

修改 ww3_trnc.nml 

```
&TRACK_NML
  TRACK%TIMESTART        =  '20250103 000000'
  TRACK%TIMESTRIDE       =  '3600'
  TRACK%TIMESPLIT        =  8
/
```

---

```log
✅ 已修改 namelists.nml：将 E3D 从 0 改为 1
```

二维谱点计算模式的时候我们还会修改 namelists.nml

```swift
&OUTS E3D = 0 /
```



#### 嵌套网格



![](public/resource/README-media/2026-03-29%2017.02.34.png)
![](public/resource/README-media/2026-03-29%2017.03.44.png)

我们首先生成了嵌套网格，在工作目录创建了 coarse 和 fine 目录，然后选择了二维谱计算模式。


```log
======================================================================
🔄 【工作目录】开始处理公共文件...
✅ 已复制 server.sh, ww3_multi.nml, local.sh 到当前工作目录
✅ 已更新 server.sh：-J=202501, -p=CPU6240R, -n=48, -N=1, MPI_NPROCS=48, CASENAME=202501, ST=ST2
✅ 已更新 ww3_multi.nml：起始=20250103, 结束=20250105, 计算精度=1800s，强迫场=风场、流场、水位场、海冰场、海冰厚度，计算资源：coarse=0.60, fine=0.40，ALLTYPE%POINT%FILE = './fine/points.list'，ALLDATE%POINT = '20250103 000000' '1800' '20250105 235959'，ALLTYPE%FIELD%LIST = 'WND HS T02 FP DIR PHS PTP PDIR PWS TWS PNR' (谱分区输出)

======================================================================
🔄 【外网格】开始处理外网格...
✅ 已复制 9 个 public/ww3 文件到当前工作目录
✅ 已成功同步 grid.meta 参数到 ww3_grid.nml
✅ 已更新 ww3_ounf.nml：FIELD%TIMESTART=20250103，FIELD%TIMESTRIDE=3600秒
✅ 已更新 ww3_shel.nml（谱空间逐点计算模式）：起始=20250103, 结束=20250105, 计算步长=1800s，添加 TYPE%POINT%FILE = 'points.list'，添加 DATE%POINT 和 DATE%BOUNDARY
✅ 已修改 ww3_prnc.nml：FORCING%FIELD%WINDS = T, FILE%FILENAME = '../wind.nc'
✅ 已修改 ww3_prnc.nml：FORCING%TIMESTART = '20250103 000000', FORCING%TIMESTOP = '20250105 235959'
✅ 已复制并修改 ww3_prnc_current.nml：FORCING%FIELD%CURRENTS = T
✅ 已复制并修改 ww3_prnc_level.nml：FORCING%FIELD%WATER_LEVELS = T
✅ 已复制并修改 ww3_prnc_ice.nml：FORCING%FIELD%ICE_CONC = T
✅ 已复制并修改 ww3_prnc_ice1.nml：FORCING%FIELD%ICE_PARAM1 = T
✅ 已修改 ww3_shel.nml：更新 INPUT%FORCING%* 设置
✅ 已修改 namelists.nml：将 E3D 从 0 改为 1
✅ 已创建 points.list 文件，包含 4 个点位
✅ 已修改 ww3_ounp.nml：POINT%TIMESTART = '20250103 000000'，POINT%TIMESTRIDE = '3600'（谱空间逐点计算模式）

======================================================================
🔄 【内网格】开始处理内网格...
✅ 已复制 9 个 public/ww3 文件到当前工作目录
✅ 已修改 ww3_shel，ww3_ounf 的谱分区输出方案
✅ 已成功同步 grid.meta 参数到 ww3_grid.nml
✅ 已更新 ww3_ounf.nml：FIELD%TIMESTART=20250103，FIELD%TIMESTRIDE=3600秒
✅ 已更新 ww3_shel.nml（谱空间逐点计算模式）：起始=20250103, 结束=20250105, 计算步长=1800s，添加 TYPE%POINT%FILE = 'points.list'，添加 DATE%POINT 和 DATE%BOUNDARY
✅ 已修改 ww3_prnc.nml：FORCING%FIELD%WINDS = T, FILE%FILENAME = '../wind.nc'
✅ 已修改 ww3_prnc.nml：FORCING%TIMESTART = '20250103 000000', FORCING%TIMESTOP = '20250105 235959'
✅ 已复制并修改 ww3_prnc_current.nml：FORCING%FIELD%CURRENTS = T
✅ 已复制并修改 ww3_prnc_level.nml：FORCING%FIELD%WATER_LEVELS = T
✅ 已复制并修改 ww3_prnc_ice.nml：FORCING%FIELD%ICE_CONC = T
✅ 已复制并修改 ww3_prnc_ice1.nml：FORCING%FIELD%ICE_PARAM1 = T
✅ 已修改 ww3_shel.nml：更新 INPUT%FORCING%* 设置
✅ 已修改 namelists.nml：将 E3D 从 0 改为 1
✅ 已创建 points.list 文件，包含 4 个点位
✅ 已修改 ww3_ounp.nml：POINT%TIMESTART = '20250103 000000'，POINT%TIMESTRIDE = '3600'（谱空间逐点计算模式）
```

我们第四步确认参数，观察 Log 输出

```log
✅ 已复制 server.sh, ww3_multi.nml, local.sh 到当前工作目录
```

我们首先把 WW3Tool/public/ww3 目录的 server.sh, local. sh, ww3_multi.nml 复制到了工作目录。

我们引入了 ww3_multi.nml 修改了起始时间，计算精度，强迫场，这其实和 ww3_shel.nml 类似

```sh
&INPUT_GRID_NML
  INPUT(1)%NAME                  = 'wind'
  INPUT(1)%FORCING%WINDS         = T
  
  INPUT(2)%NAME                  = 'current'
  INPUT(2)%FORCING%CURRENTS      = T
  
  INPUT(3)%NAME                  = 'level'
  INPUT(3)%FORCING%WATER_LEVELS  = T
  
  INPUT(4)%NAME                  = 'ice'
  INPUT(4)%FORCING%ICE_CONC      = T

  INPUT(5)%NAME                  = 'ice1'
  INPUT(5)%FORCING%ICE_PARAM1    = T
/

&MODEL_GRID_NML

  MODEL(1)%NAME                  = 'coarse'
  MODEL(1)%FORCING%WINDS         = 'native'
  MODEL(1)%FORCING%CURRENTS      = 'native'
  MODEL(1)%FORCING%WATER_LEVELS  = 'native'
  MODEL(1)%FORCING%ICE_CONC      = 'native'
  MODEL(1)%FORCING%ICE_PARAM1    = 'native'
  MODEL(1)%RESOURCE              = 1 1 0.00 0.35 F

  MODEL(2)%NAME                  = 'fine'
  MODEL(2)%FORCING%WINDS         = 'native'
  MODEL(2)%FORCING%CURRENTS      = 'native'
  MODEL(2)%FORCING%WATER_LEVELS  = 'native'
  MODEL(2)%FORCING%ICE_CONC      = 'native'
  MODEL(2)%FORCING%ICE_PARAM1    = 'native'
  MODEL(2)%RESOURCE              = 2 1 0.35 1.00 F
/
```

其中

INPUT (I)%FORCING%ICE_CONC = 冰浓度
INPUT (I)%FORCING%ICE_PARAM1 = 冰厚度

关于海冰强迫场目前程序还有很多没有完善的问题。

注意 MODEL (2)%FORCING%WINDS = 'native' 其中的 native 表示开启，no 表示关闭

MODEL (1)%RESOURCE 和 MODEL (2)%RESOURCE 表示分配的计算资源比例

至于其他的 Log ，很容易理解，我们只是按照普通网格的方式处理了内外网格

值得注意的是，我们修改了 ww3_prnc.nml：FILE%FILENAME = '../wind.nc' ，这是为了避免强迫场文件占用两倍的空间，所以指向了共同的引用。




#### 谱空间逐点计算模式

```log
✅ 已修改 namelists.nml：将 E3D 从 0 改为 1
✅ 已创建 points.list 文件，包含 4 个点位
✅ 已修改 ww3_ounp.nml：POINT%TIMESTART = '20250103 000000'，POINT%TIMESTRIDE = '3600'（谱空间逐点计算模式）
```

上一节的日志中，这三个日志是关于谱空间逐点计算模式的日志，这些日志都很好理解

对于 E3D 从 0 改为 1，如果谱分区输出方案包含 EF，那么也会执行




### 本地运行

![](public/resource/README-media/2026-03-30%2014.06.33.png)

本地运行实际执行的是 local.sh

如果选择本地执行，确保你已经在本地配置好了 WAVEWATCH III，选择 bin 目录，其中应该包含下面这些程序

```
gx_outf    ww3_bound  ww3_grid   ww3_ounf   ww3_outp   ww3_shel   

ww3_trck   gx_outp    ww3_gint   ww3_gspl   ww3_ounp   ww3_prep   

ww3_strt   ww3_trnc   ww3_bounc  ww3_grib   ww3_multi  ww3_outf   

ww3_prnc   ww3_systrk ww3_uprstr
```




### 连接服务器

![](public/resource/README-media/2026-03-29%2023.47.34.png)

首先，你需要配置 ssh 账号和密码，在设置页面我们找到服务器配置这个选项

注意默认服务器路径，这是你的服务器存放工作目录的路径

点击连接服务器，连接成功后会先显示一个 CPU 占用排行，这个列表每秒钟刷新一次

如果在第六步提交计算任务到 Slurm ，还会显示任务队列

![](public/resource/README-media/2026-03-30%2016.39.48.png)



### 服务器操作

查看任务队列就是在服务器执行了 squeue -l

![](public/resource/README-media/2026-03-30%2016.40.35.png)

上传工作目录到服务器，就是把当前工作目录上传到服务器工作目录，这在设置页面有配置

![](public/resource/README-media/2026-03-30%2016.41.08.png)

提交计算任务就是在服务器执行了 server.sh 这个脚本，如果运行成功(所有指令正常运行)，会在服务器工作目录生成一个 success.log，包含所有的 WW3执行 Log，如果失败，则会生成一个 fail.log 同样包含所有的 WW3 执行 log，如果没有完成，还在执行，这个 log 文件的名字是 run.log

因此检查是否已完成可以检测是否存在 success.log 或 fail.log，如果是 run. log 说明服务器还在执行。

清空文件夹就是清空当前服务器工作目录文件夹

下载结果到本地会自动下载所有 ww3.nc 文件，如果是嵌套网格模式，只会下载 fine 内的结果文件。

下载 log 文件就是下载 success.log 或 fail.log




### 自动操作

打开一个工作目录，会自动检测是否已经存在转换了的强迫场文件(根据文件名 wind.nc, level.nc,current.nc)，自动填充到强迫场按钮

自动读取网格文件的范围和精度，填充第二步，检测是否包含 coarse 和 fine 文件夹，自动切换到嵌套网格模式

自动检测 points.list 切换到点输出模式，检测到 track_i.ww3 切换到航迹模式，并且自动导入文件中的点列表。

自动读取 server.sh 的 slurm 参数填充第四步，自动检测 ww3_shel.nml 的计算精度，时间范围，谱分区方案。



### 设置页面

设置页面的绝大部分设置都是自动保存的，除了谱分区输出方案

#### 运行方式

运行方式，这个其实只是控制主页的某些元素是否显示罢了，没有什么实际的影响

例如选择本地运行的时候，不会显示 Slurm 参数

#### 强迫场选择

强迫场选择的自动关联就是打开一个文件如果包含多个强迫场，那么可以自动填充其他按钮

文件处理方式就是对原本的强迫场文件的处理方式：复制或剪切。

有些强迫场文件非常大，如果采用复制的方式那么占用的电脑空间显然成倍增加。



#### JASON 数据路径

JASON 数据路径就是绘图的时候用的，比如你想看模拟的结果和 JASON 3 卫星的观测的波高对比。

![](public/resource/README-media/a705779452ff987b9ffe37f1d18743b72c7f9695.png)


#### WW3 配置

WW3 配置就是主页第四步的默认值，确认参数按钮。

文件分割就是 ww3_ounf.nml, ww3_ounp.nml, ww3_trnc.nml 的 TIMESPLIT，比如你计算的时间范围是 3 个月，那么你选择月分割或年分割比较合适，如果你选择日分割，则会每天一个文件。

![](public/resource/README-media/2026-03-30%2016.42.49.png)

频谱参数配置、数值积分时间步长、近岸配置都是 ww3_grid.nml 的配置，在这里修改会同时修改 WW3Tool 和当前工作目录的 ww3_grid.nml （如果存在）

```swift
&SPECTRUM_NML
  SPECTRUM%XFR       =  1.1
  SPECTRUM%FREQ1     =  0.04118
  SPECTRUM%NK        =  32
  SPECTRUM%NTH       =  24
/

&TIMESTEPS_NML
  TIMESTEPS%DTMAX        =  900
  TIMESTEPS%DTXY         =  320
  TIMESTEPS%DTKTH        =  300
  TIMESTEPS%DTMIN        =  15
/
```

谱分区输出是 ww3_shel.nml、 ww3_ounf.nml、ww3_ounp.nml 的配置




#### CPU 配置

在服务器端输入指令

```sh
sinfo
```

可以查看服务器的 CPU (如果你已经服务配置了 slurm)

然后打开软件的设置页面，找到 Slurm 参数一栏，点击 CPU 管理，改成你的服务器的 CPU

![](public/resource/README-media/2026-03-30%2016.42.16.png)


#### 服务器连接

![](public/resource/README-media/2026-03-29%2023.47.34.png)

你需要填写 SSH 账号，以及默认的登录路径，在这个路径，每次的工作目录都会上传到这里。



#### ST 版本管理

![](public/resource/README-media/2026-03-30%2016.42.31.png)

实际上，这个就是你编译的不同版本的 WAVEWATCH，你只需填写它们的路径即可



### 绘图界面

#### 风场绘图

![](public/resource/README-media/54c004948927395c7eb51ecc337f6752a7bc31c2.png)

#### 二维谱绘图

![](public/resource/README-media/bf6f51063f2c2ac60f608bd42d7ff85e21bd0f7b.png)

#### 波高图

![](public/resource/README-media/3021c4434de128e783c2b06f6ba4c1fe876cf416.png)
![](public/resource/README-media/bde9091a001999fdacde4c1f804fc5c025a9995f.png)
#### 风涌浪图

![](public/resource/README-media/30f4c0333842e78da6437616709d0c884177e7b5.png)
![](public/resource/README-media/1968aff8588d84dab9e4750a8e97be006177d709.png)

#### 卫星拟合图

![](public/resource/README-media/a705779452ff987b9ffe37f1d18743b72c7f9695.png)



### 命令行绘图与远程操作

上面介绍的绘图和服务器操作都可以通过 CLI 完成，不需要打开桌面界面。

绘图相关命令：`plot-wave-maps` 绘制波高图（加 `--contour` 使用等高线图），`plot-spectrum` 绘制二维谱图（`--mode normalized/actual`，`--station 3` 指定站点），`plot-jason3` 匹配并绘制 JASON3 卫星数据，`plot-jason3-swh` 绘制卫星 SWH 轨迹图，`download-jason3` 从 NOAA 下载 JASON3 L2 数据，`plot-ndbc` 匹配 NDBC 浮标数据（加 `--download` 自动下载）。

远程操作命令：`connect-test` 测试 SSH 连接，`upload` 上传工作目录（需 `--confirm`），`submit` 提交 Slurm 计算任务（可用 `--script` 指定自定义脚本），`check-status` 检查任务状态，`queue-status` 查看 Slurm 队列，`download-results` 下载结果文件（嵌套模式加 `--nested` 只下载 fine），`download-log` 下载运行日志，`clear-remote` 清空远程工作目录（需 `--confirm`），`cancel-job` 取消 Slurm 任务。

交互式终端还额外提供 `ssh` 命令，可以直接打开 SSH 终端连接到服务器，以及 `config` 命令查看当前配置摘要。



## 文件获取

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
