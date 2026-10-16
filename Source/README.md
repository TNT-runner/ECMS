# 元件仓库 · 个人离线版

按 `design/component-manager-mockup.svg` 制作的 Python 桌面软件。
使用 **PySide6 / Qt Widgets + SQLite**，运行时不需要联网、账户或数据库服务器。

## 启动

当前项目已经创建 `.venv` 并安装了 PySide6。Windows 下双击 `start.bat`，或者在项目目录的 PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe app.py
```

在 VS Code 中建议通过 `Ctrl+Shift+P` → `Python: Select Interpreter` 选择项目的
`.venv\Scripts\python.exe`。如果使用全局 Python 运行而缺少 PySide6，入口会先检查项目虚拟环境，
可用时自动使用它启动，并保留 `--demo` 和 `--data-dir` 等参数。
如果虚拟环境也不可用，错误提示会给出当前 Python 的完整路径，以及不依赖终端所在目录的安装命令。

首次正常启动是空库存；支持贴片电容、贴片电阻、主控芯片、电源管理芯片、协议收发芯片、电池管理芯片、电感、TVS管、二极管、晶振、MOS管、共模电感、三极管、磁珠、连接器、运算放大器、逻辑芯片、存储芯片十八类元件，也可通过 CSV 导入元件。查看示例界面：

```powershell
.\.venv\Scripts\python.exe app.py --demo
```

演示数据默认使用独立目录，和真实库存分开。`--demo` 只在演示数据库为空时生成六个电容 / 电阻示例元件。
也可以通过 `start.bat --demo` 启动。

在其他电脑首次使用时，先安装 Python 3.10 或更新版本，然后运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

依赖安装需要网络；安装完成后，管理元件的全部功能均可离线使用。
当前已在 Windows、Python 3.13、PySide6 6.11.2 环境验证。

## Windows 可执行文件

打包后的程序位于项目根目录的 `Exe\元件仓库.exe`，双击即可运行，无需另外安装 Python。库存数据沿用“设置 / 数据目录”中的位置；默认保存在 `%LOCALAPPDATA%\ComponentDesk`，不会写入 exe 或其临时解压目录。`--demo` 和 `--data-dir` 参数仍可使用。

源码位于 `Source` 文件夹。在 Windows PowerShell 中重新打包：

```powershell
cd Source
.\build.ps1
```

打包脚本使用本项目 `.venv`，安装打包依赖，生成程序图标，并将单文件 exe 输出到与 `Source` 同级的 `Exe` 文件夹。中间文件位于 `Source\build`；个人库存、设置及附件不会包含在程序中。

## 已实现功能

- 左侧库存导航、库存不足视图、出入库历史视图；分类通过列表上方的下拉框筛选。
- 按名称、型号、厂家、参数、封装、备注及库位搜索，支持多个关键词。
- 分类、封装、库位筛选；点击表头可以排序。
- 新增和编辑十八类元件；切换类别时显示对应的规格参数。带预设选项的控件显示下拉箭头，可从列表选择；可编辑的参数框也支持手动输入自定义值。
- 右键元件可选择“移除元件”，确认后删除该元件资料、库存和出入库记录。库位、附件文件和已有备份保留。
- 电阻支持 Ω、kΩ、MΩ，电容支持 pF、nF、µF、mF、F；保存时分别统一为 Ω 和 F。
- 同一元件可存放在多个库位，总库存为各库位库存之和。
- 入库、领用和盘点；领用不可超过所选库位库存。盘点填写实物数量，历史中记录差额。
- “库位管理”支持搜索、只看空库位、新增、重命名和删除空库位，并显示元件种类、库存件数及使用状态。
- 有库存的库位不可删除；空库位删除后从筛选、库存操作和库位统计中移除，已有出入库历史保留。需要重新使用时，可新增同名库位。
- 可从详情页打开已有元件照片和 PDF 手册。
- CSV 导入与导出。
- 包含数据库、历史和附件的 ZIP 备份与恢复；恢复前自动备份当前数据。

预警规则：总库存 **小于** 预警数量时提示库存不足。预警数量为 0 表示不设置最低库存。

快捷键：`Ctrl+N` 新增元件、`Ctrl+F` 聚焦搜索、`Ctrl+B` 创建备份。
双击列表行编辑元件；右键行可以入库、领用、盘点或查看记录。

## 当前元件参数

| 类别 | 主要参数 | 补充参数（选填） |
| --- | --- | --- |
| 贴片电容 | 容值、封装、额定电压、精度 | 介质 / 温度特性（例如 C0G/NP0、X7R、X5R）、工作温度范围 |
| 贴片电阻 | 阻值、封装、精度、功率 | 温度系数（ppm/°C）、工作温度范围 |
| 主控芯片 | 型号、封装 | 内核 / 架构、最高主频（MHz）、Flash / RAM（KB）、供电电压范围（V）、引脚数量 |
| 电源管理芯片 | 共用：型号、封装、芯片类型（DCDC、LDO、PMU）；DCDC：输入 / 输出电压范围、最大输出电流、开关频率及单位；LDO：固定 / 可调输出模式及对应输出电压 | 共用：静态电流（µA）；LDO：输入电压范围、最大输出电流、线性压差（mV）；PMU：输入电压范围、多路输出规格、控制接口、时序、充电和保护等参数 |
| 协议收发芯片 | 型号、封装、协议 / 接口、最高数据速率（Mbps）、通道数量、供电电压范围（V）、逻辑侧电压（V） | 隔离类型 |
| 电池管理芯片 | 型号、封装、管理功能（充电管理 / 电池保护 / 电量计 / 综合管理） | 电池类型、串联节数、供电范围、充电截止电压、电流及方式、电源路径、保护阈值、保护功能、计量方式、接口、静态电流 |
| 电感 | 封装、感值及单位 | 型号、电感类型、精度、额定电流 Irms、饱和电流 Isat、直流电阻 DCR、自谐振频率、屏蔽方式 |
| TVS管 | 型号、封装、保护类型（ESD 防静电 / TVS 瞬态抑制）、方向、反向工作电压 VRWM | 击穿电压 VBR、钳位电压 VC、峰值脉冲电流 / 功率、结电容、保护通道数、ESD 等级、脉冲及测试条件 |
| 二极管 | 型号、封装、二极管类型 | 最大反向电压、额定正向电流、VF、浪涌电流、漏电流、恢复时间、稳压电压、功率、内部结构、测试条件 |
| 晶振 | 封装、晶振类型、标称频率及单位 | 型号、频率精度、温度稳定度；无源：负载电容、ESR、驱动功率；有源 / TCXO / VCXO / OCXO：供电范围、输出信号、使能功能 |
| MOS管 | 型号、封装、沟道类型、漏源耐压绝对值 | 连续漏极电流绝对值、RDS(on) 及测试条件、栅源电压额定值、VGS(th)、总栅极电荷、耗散功率、内部结构 |
| 共模电感 | 封装、应用类型 | 型号、共模阻抗及测试频率、共模感值、额定电流、每线 DCR、额定电压、线路数量、适用接口、测试条件 |
| 三极管 | 型号、封装、三极管类型 | 集电极耐压和电流绝对值、hFE、饱和压降、特征频率 fT、耗散功率、内部结构、引脚排列、测试条件 |
| 磁珠 | 封装、标称阻抗及单位、阻抗测试频率及单位 | 型号、应用类型、额定电流、DCR、阻抗精度 |
| 连接器 | 封装 / 外形、连接器类型、触点数量 | 型号、触点间距、公母类型、安装方式、插接方向、排数、每触点电流、额定电压、接口及配对规格 |
| 运算放大器 | 型号、封装、通道数量 | 类型、总供电电压范围、GBW、压摆率、失调电压和偏置电流绝对值、噪声密度、轨到轨能力、每通道静态电流、测试条件 |
| 逻辑芯片 | 型号、封装、逻辑功能 | 系列、通道数量、供电范围、电平转换 A / B 侧供电范围、传播延迟、最高工作频率、输出结构和驱动电流、逻辑电平及测试条件 |
| 存储芯片 | 型号、封装、存储类型、容量及单位 | 接口、供电范围、最高时钟频率、总线位宽、写入 / 擦写寿命、保持时间、访问时间、组织结构 |

电容的容值、封装、额定电压、精度必填；电阻的阻值、封装、精度、功率必填。
容值、阻值和单位均由用户手动输入，数值右侧是单位文本框，单位必填。
电容单位支持 `pF`、`nF`、`uF` / `µF` / `μF`、`mF`、`F`；电阻单位支持 `Ω` / `ohm`、`kΩ` / `kohm`、`MΩ` / `Mohm`。
保存时校验单位并换算为 F / Ω；类别框右侧箭头可切换十八种元件类别。
支持 0 Ω 电阻；功率可以填写 `0.125` 或 `1/8`。封装可以选择常用值，也可以输入自定义值。
两类均可选填元件名称、型号和厂家；名称留空时根据类别和容值 / 阻值自动生成。
主控芯片的型号、封装必填；电源芯片额外必填芯片类型，收发芯片额外必填协议、最高数据速率、通道数量、供电电压范围及逻辑侧电压。DCDC 还必填输入电压范围、输出电压范围、最大输出电流和开关频率（数值与单位）；LDO 还必选输出模式并填写对应输出电压。其他参数选填；名称留空时使用型号。
所有类别都可填写工作温度范围和厂家。芯片电压范围填写最小值和最大值，固定电压填写相同数值；选填的范围可将两个端点都留空。
协议收发芯片的供电电压范围两端均必填，最高数据速率和逻辑侧电压须大于零，通道数量须为正整数。双工模式及引脚数量已移除，旧记录中的这两个参数也不再显示或导出；主控芯片及 PMU 的引脚数量仍保留。
电源芯片先在“芯片类型”下拉框中选择 DCDC、LDO 或 PMU，再显示对应参数。DCDC 的输入 / 输出电压范围两端均必填，固定电压的两端填写相同数值；最大输出电流及开关频率也必填。LDO 先选择“固定输出”或“可调输出”：固定型填写单个输出电压，可调型填写输出电压范围的两个端点；输入电压范围、最大输出电流和线性压差选填。不适用的参数行隐藏，保存时只记录当前类型的参数；来回切换时保留尚未保存的输入。两类支持负输入 / 输出电压，旧 DC/DC 写法自动识别为 DCDC。DCDC 拓扑和原来的通用“输出类型”仍不显示，LDO 使用专属的“LDO 输出模式”。
已有 LDO 的明确固定 / 可调记录会自动转换为专属模式；仅有电压范围、没有模式的旧记录保留原电压数据，编辑时须选择其实际模式，不根据范围端点是否相同来推断。旧备份中的不完整规格仍可恢复；新增、编辑及 CSV 导入按当前必填规则校验。

新增分类的型号、封装及主要类型 / 标称值按表中要求填写，其余参数选填。电感、共模电感及晶振的型号可留空，名称由参数生成。感值支持手动输入 `nH`、`uH` / `µH` / `μH`、`mH`、`H`，保存为 H；频率支持 Hz、kHz、MHz、GHz，保存为 Hz；DCR 支持 mΩ、Ω（电感还支持 kΩ），保存为 Ω。数值与单位须一起填写或一起留空，必填参数不可留空。

电池管理芯片按管理功能显示充电、保护或电量计专属参数；晶振按有源 / 无源类型显示适用参数；二极管选择“稳压”时显示稳压电压。切换时保留输入草稿，保存时去掉不适用的参数。MOS 管的耐压及电流填绝对值，P 沟道的阈值电压可填负数。共模电感同时提供阻抗和感值字段，可按数据手册给出的规格填写，阻抗的测试频率单独记录。

参数设计参考厂商的规格说明：[TI 电池充电管理](https://www.ti.com/product/BQ25601)、[TI 电池保护](https://www.ti.com/product/BQ2970)、[Nexperia ESD / TVS](https://www.nexperia.com/products/esd-protection-tvs-filtering-and-signal-conditioning/)、[Coilcraft 电感](https://www.coilcraft.com/en-us/resources/application-notes/selecting-the-best-inductor-for-your-dc-dc-convert/)、[Murata 共模电感](https://corporate.murata.com/en-us/technology/techmag/metamorphosis18/productsmarket/chokecoil)、[Epson 晶体](https://www.epsondevice.com/crystal/en/techinfo/column/crystal-unit/index.html)。

磁珠和连接器的型号可留空，名称按规格生成。磁珠的阻抗须填写对应测试频率；连接器的“封装 / 外形”可填直插、贴片等外形说明。三极管 PNP 器件的耐压、电流及饱和压降填写绝对值。运放供电范围使用总电压，例如 ±5 V 记为 10 V，并可在供电说明中注明。
存储容量明确区分位和字节：1 B = 8 bit，K / M / G 按 1024 换算；支持 bit、Kbit、Mbit、Gbit、B、KB、MB、GB 及 KiB / MiB / GiB，保存为整数 bit。EEPROM / Flash / FRAM 显示写入寿命与保持时间；SRAM / DRAM 隐藏这两项。逻辑功能选择电平转换时显示 A / B 侧供电范围。
六类参数参考：[Nexperia 三极管](https://www.nexperia.com/product/BC817)、[Murata 磁珠](https://www.murata.com/en-us/products/emc/emifil/overview/lineup/bl/lineup/chip-ferrite-beads)、[Molex 连接器](https://www.molex.com/en-us/products/connectors/wire-to-board-connectors)、[TI 运放](https://www.ti.com/product/TLV9002)、[TI 逻辑缓冲器](https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf)、[ST 存储芯片](https://www.st.com/en/memories/m24c64-r.html)。
开关频率参考阻值 / 容值的输入方式：左侧填写数值，右侧手动输入 `Hz`、`kHz`、`MHz` 或 `GHz`，例如 `500` + `kHz`、`1` + `MHz`；DCDC 的数值和单位都必填。保存时统一换算为 kHz，兼容已有频率数据；编辑及详情中自动使用合适的频率单位。
其他小单位数值请按字段标注换算，例如 `500 mA` 填写 `0.5 A`，`500 kbps` 数据速率填写 `0.5 Mbps`。
PMU（电源管理单元）沿用型号、封装、芯片类型必填的规则，其余参数全部选填。参考 [TI TPS65070](https://www.ti.com/product/TPS65070)、[TI TPS65217](https://www.ti.com/product/TPS65217) 和 [ADI ADP5054](https://www.analog.com/en/products/adp5054.html) 的官方资料，将多路供电与部分型号具备的电池充电功能分开录入；旧数据中的 `PMIC` 写法也识别为 PMU。

| PMU 参数 | 填写方式 |
| --- | --- |
| 输入电压范围、静态电流 | 按手册填写输入范围（V）及芯片静态电流（µA），测试条件可在输出规格中注明 |
| DCDC / LDO 路数 | 分别填写非负整数；没有对应输出时填 0，未知可留空 |
| 各路输出规格 | 多行文本，每行记录一路的名称、电压范围和最大电流；可注明各路输入电压、开关频率、并联限制和测试条件 |
| 控制接口 | I²C、SPI、GPIO / EN、无通信接口等，可自定义 |
| 上电 / 下电时序 | 可编程、固定、外部引脚控制等，可自定义 |
| 电池充电管理 | 选择“支持”后显示电池类型 / 节数、充电电压（V）、最大充电电流（A）；不支持或未知时这些参数隐藏 |
| 电源路径管理 | 记录是否支持电源切换及供电路径管理，可补充自定义说明 |
| 保护功能、其他集成功能 | 按型号填写欠压、过流、过温保护及负载开关、LED 驱动、ADC、RTC、电量计、看门狗等实际具备的功能 |
| 引脚数量 | 正整数，未知可留空 |

PMU 的多路输出分别记在“各路输出规格”中，单路芯片的统一输出电压、最大电流、开关频率和压差字段隐藏。列表摘要显示 PMU、DCDC / LDO 路数和控制接口，详情显示完整参数；多行输出说明在编辑、CSV、备份恢复中保留。
新增元件初始库存为 0，保存后通过“入库”选择库位并录入数量。
编辑时保留已有库存、出入库记录和未显示的旧资料。

## 数据存放位置

Windows 默认目录：

```text
%LOCALAPPDATA%\ComponentDesk\
├── inventory.sqlite3       # 元件、库位、库存、历史
├── attachments\            # 程序复制保存的照片和 PDF
└── backups\                # 默认备份及恢复前自动备份
```

演示数据使用 `%LOCALAPPDATA%\ComponentDeskDemo`。
在 **设置 / 数据目录 → 选择文件夹 → 保存并迁移** 中更改存储位置。
请选择独立的空文件夹；可在选择窗口中新建文件夹，也可直接输入完整路径。
保存时会复制数据库、全部出入库历史、照片、PDF 和已有备份，并立即使用新目录。
旧目录保留迁移时的原数据，后续操作只写入新目录；复制或设置保存失败时继续使用原目录。
重启后会自动使用已保存的位置，演示模式和个人模式分别记住各自的目录。
数据和软件源码分开保存，更新代码不会覆盖库存。

目录设置独立保存在 `%LOCALAPPDATA%\ComponentDeskSettings\settings.json`。
如果自定义磁盘不可用，程序会提示检查磁盘，避免自动生成一份空库存。

指定自定义目录：

```powershell
.\.venv\Scripts\python.exe app.py --data-dir "D:\MyComponents"
```

`--data-dir` 优先于设置中的目录，仅覆盖本次启动。更改设置后，下次普通启动使用保存的路径；
如果再次传入 `--data-dir`，仍按命令行指定路径启动。

添加照片或 PDF 时，软件会复制附件，之后移动原文件不会影响已经保存的附件。
完整迁移建议使用程序的 ZIP 备份和恢复功能。

## CSV 格式

先导出一个 CSV 作为模板。列名如下：

```text
id,name,model,category,manufacturer,package,parameters_json,warning_quantity,notes,location,quantity
```

每个“元件 + 库位”一行。同一个元件分布在多个库位时使用相同 ID，并保持元件资料一致。
新元件单行录入可以留空 ID，程序会生成 UUID；多库位元件须使用同一个 UUID。
`category` 使用上表中的十八类名称，新增、编辑、筛选与 CSV 校验共用同一份类别定义。`parameters_json` 示例：

```json
{"resistance_ohm": 4700, "tolerance_percent": 1, "power_w": 0.1}
```

CSV 导入只新增元件，不覆盖现有 ID 或合并现有库存。
有任何一行无效、同一库位重复或 ID 与现有元件冲突，整份文件都不会写入。
CSV 不携带照片、PDF 或旧的出入库历史；导入库存会生成“CSV 导入”记录。
导出数据到一份空数据库可保留元件 ID、分类参数和各库位数量。

## 项目结构

```text
app.py                         # 程序入口、启动参数及数据目录
start.bat                      # Windows 启动脚本
requirements.txt               # GUI 依赖
component_desk/
├── database.py                # SQLite 与库存规则、CSV、备份恢复
├── window.py                  # 主窗口、列表、详情及历史
├── dialogs.py                 # 元件、库存操作及库位表单
├── settings.py                # 数据目录设置的保存与启动加载
├── specifications.py          # 芯片参数的字段定义与单位
└── style.py                   # QSS 样式及 SVG 图标
design/
├── component-manager-mockup.svg
├── component-manager-mockup.png
└── python-app-preview.png     # 实际 Python 程序的离屏截图
tests/
├── test_database.py           # 数据完整性与备份恢复测试
└── smoke_ui.py                # 实际 Qt 表单与导航流程检查
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests\smoke_ui.py
```

测试使用临时数据库，不修改个人库存。界面截图保存在 `.test-output`。
Windows 上 Qt 的离屏平台没有自动发现系统字体，测试脚本会单独加载系统微软雅黑。

## 可选：打包为 EXE

当前交付的是可运行源码，未生成 EXE。后续可以在 Windows 环境使用 PyInstaller：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --name ComponentDesk app.py
```

构建结果位于 `dist\ComponentDesk\ComponentDesk.exe`。分发时复制整个 `ComponentDesk` 文件夹。
数据仍保存在用户的本地数据目录。上述打包命令尚未验证生成物。
