"""Shared specification definitions for forms, persistence and detail views."""

from dataclasses import dataclass


POWER_TYPES = ("DCDC", "LDO", "PMU")
LDO_OUTPUT_MODES = ("固定输出", "可调输出")
PMU_CHARGE_FIELDS = frozenset({"pmu_battery_spec", "pmu_charge_voltage_v", "pmu_charge_current_a"})


def normalize_power_type(value):
    """Keep DC/DC spellings and the common PMIC name compatible with the form."""
    text = str(value).strip()
    upper = text.upper()
    if upper in {"DCDC", "DC/DC", "DC-DC"}:
        return "DCDC"
    if upper in {"PMU", "PMIC"}:
        return "PMU"
    return "LDO" if upper == "LDO" else text


def power_field_applies(key, power_type, charger="", ldo_mode=""):
    power_type = normalize_power_type(power_type)
    if key == "power_type":
        return True
    if power_type not in POWER_TYPES:
        return False
    field = next((field for field in CHIP_SPECS["电源管理芯片"] if field.key == key), None)
    if field is None or field.power_types and power_type not in field.power_types:
        return False
    if key == "output_voltage":
        return power_type == "DCDC" or ldo_mode == "可调输出"
    if key == "output_voltage_v":
        return ldo_mode == "固定输出"
    return key not in PMU_CHARGE_FIELDS or charger == "支持"


def field_required(field, power_type=""):
    return field.required or normalize_power_type(power_type) in field.required_power_types


@dataclass(frozen=True)
class ChipField:
    key: str
    title: str
    kind: str = "text"
    unit: str = ""
    options: tuple[str, ...] = ()
    placeholder: str = ""
    required: bool = False
    signed: bool = False
    power_types: tuple[str, ...] = ()
    required_power_types: tuple[str, ...] = ()
    engineering_units: tuple[tuple[float, str], ...] = ()
    show_when: tuple[str, tuple[str, ...]] | None = None
    positive: bool = False
    allow_zero: bool = False
    integer_value: bool = False


CHIP_SPECS = {
    "主控芯片": (
        ChipField("core_architecture", "内核 / 架构", placeholder="例如 Cortex-M4、RISC-V；可留空"),
        ChipField("clock_mhz", "最高主频", "number", "MHz"),
        ChipField("flash_kb", "Flash 容量", "number", "KB"),
        ChipField("ram_kb", "RAM 容量", "number", "KB"),
        ChipField("supply_voltage", "供电电压范围", "range", "V"),
        ChipField("pin_count", "引脚数量", "integer", "个"),
    ),
    "电源管理芯片": (
        ChipField("power_type", "芯片类型", "choice", options=POWER_TYPES, required=True),
        ChipField("input_voltage", "输入电压范围", "range", "V", signed=True, required_power_types=("DCDC",)),
        ChipField("ldo_output_mode", "LDO 输出模式", "toggle", options=LDO_OUTPUT_MODES, power_types=("LDO",), required_power_types=("LDO",)),
        ChipField("output_voltage", "输出电压范围", "range", "V", signed=True, power_types=("DCDC", "LDO"), required_power_types=("DCDC", "LDO")),
        ChipField("output_voltage_v", "输出电压", "number", "V", signed=True, power_types=("LDO",), required_power_types=("LDO",)),
        ChipField("output_current_a", "最大输出电流", "number", "A", power_types=("DCDC", "LDO"), required_power_types=("DCDC",)),
        ChipField("switching_frequency_khz", "开关频率", "frequency", "kHz", power_types=("DCDC",), required_power_types=("DCDC",)),
        ChipField("dropout_voltage_mv", "线性压差", "number", "mV", power_types=("LDO",)),
        ChipField("pmu_dcdc_count", "DCDC 路数", "integer", "路", placeholder="例如 3；没有则填 0，未知可留空", power_types=("PMU",)),
        ChipField("pmu_ldo_count", "LDO 路数", "integer", "路", placeholder="例如 2；没有则填 0，未知可留空", power_types=("PMU",)),
        ChipField("pmu_outputs", "各路输出规格", "multiline", placeholder="每行填写一路的名称、电压范围和最大电流。\n例如 DCDC1：0.9～1.8 V，1.2 A\nLDO1：3.3 V，0.2 A；各路输入电压、频率也可注明。", power_types=("PMU",)),
        ChipField("pmu_control_interface", "控制接口", "choice", options=("I²C", "SPI", "I²C / SPI", "GPIO / EN", "无通信接口"), power_types=("PMU",)),
        ChipField("pmu_sequence", "上电 / 下电时序", "choice", options=("可编程时序", "固定时序", "外部引脚控制", "不支持"), power_types=("PMU",)),
        ChipField("pmu_charger", "电池充电管理", "toggle", options=("支持", "不支持"), power_types=("PMU",)),
        ChipField("pmu_battery_spec", "电池类型 / 节数", placeholder="例如 单节锂离子 / 锂聚合物电池；可留空", power_types=("PMU",)),
        ChipField("pmu_charge_voltage_v", "充电电压", "number", "V", placeholder="例如 4.2；可留空", power_types=("PMU",)),
        ChipField("pmu_charge_current_a", "最大充电电流", "number", "A", placeholder="例如 0.7；可留空", power_types=("PMU",)),
        ChipField("pmu_power_path", "电源路径管理", "choice", options=("支持", "不支持"), power_types=("PMU",)),
        ChipField("pmu_protection", "保护功能", placeholder="例如 欠压锁定、过流、过温、电池温度检测；可留空", power_types=("PMU",)),
        ChipField("pmu_other_functions", "其他集成功能", placeholder="例如 负载开关、LED 驱动、ADC、RTC、电量计、看门狗；可留空", power_types=("PMU",)),
        ChipField("quiescent_current_ua", "静态电流", "number", "µA"),
        ChipField("pin_count", "引脚数量", "integer", "个", power_types=("PMU",)),
    ),
    "协议收发芯片": (
        ChipField("protocol", "协议 / 接口", "choice", options=("CAN", "CAN FD", "RS-485", "RS-422", "RS-232", "LIN", "Ethernet PHY", "USB", "其他"), required=True),
        ChipField("data_rate_mbps", "最高数据速率", "number", "Mbps", required=True),
        ChipField("channel_count", "通道数量", "integer", "路", required=True),
        ChipField("supply_voltage", "供电电压范围", "range", "V", required=True),
        ChipField("logic_voltage_v", "逻辑侧电压", "number", "V", required=True),
        ChipField("isolation", "隔离类型", "choice", options=("非隔离", "隔离")),
    ),
}

INDUCTANCE_UNITS = ((1, "H"), (1e-3, "mH"), (1e-6, "µH"), (1e-9, "nH"))
FREQUENCY_UNITS = ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz"), (1, "Hz"))
NEW_COMPONENT_SPECS = {
    "电池管理芯片": (
        ChipField("battery_function", "管理功能", "toggle", options=("充电管理", "电池保护", "电量计", "综合管理"), required=True),
        ChipField("battery_chemistry", "电池类型", "choice", options=("锂离子 / 锂聚合物", "磷酸铁锂", "镍氢", "铅酸", "其他")),
        ChipField("series_cells", "串联电池节数", "integer", "节", positive=True),
        ChipField("supply_voltage", "供电电压范围", "range", "V"),
        ChipField("charge_voltage_v", "充电截止电压", "number", "V", show_when=("battery_function", ("充电管理", "综合管理")), positive=True),
        ChipField("charge_current_a", "最大充电电流", "number", "A", show_when=("battery_function", ("充电管理", "综合管理")), positive=True),
        ChipField("charge_method", "充电方式", "choice", options=("线性充电", "开关降压", "开关升压", "升降压"), show_when=("battery_function", ("充电管理", "综合管理"))),
        ChipField("power_path", "电源路径管理", "toggle", options=("支持", "不支持"), show_when=("battery_function", ("充电管理", "综合管理"))),
        ChipField("overcharge_voltage_v", "过充保护阈值", "number", "V", show_when=("battery_function", ("电池保护", "综合管理")), positive=True),
        ChipField("overdischarge_voltage_v", "过放保护阈值", "number", "V", show_when=("battery_function", ("电池保护", "综合管理")), positive=True),
        ChipField("protection_features", "保护功能", placeholder="例如 过流、短路、过温、电池温度检测；可留空"),
        ChipField("gauge_algorithm", "电量计量方式", "choice", options=("库仑计量", "电压估算", "阻抗跟踪", "其他"), show_when=("battery_function", ("电量计", "综合管理"))),
        ChipField("control_interface", "通信 / 控制接口", "choice", options=("I²C", "SMBus", "SPI", "单线接口", "引脚控制", "无通信接口")),
        ChipField("quiescent_current_ua", "静态电流", "number", "µA"),
    ),
    "电感": (
        ChipField("inductance_h", "感值", "engineering", "H", required=True, engineering_units=INDUCTANCE_UNITS, positive=True),
        ChipField("inductor_type", "电感类型", "choice", options=("功率电感", "射频电感", "叠层电感", "绕线电感", "其他")),
        ChipField("tolerance_percent", "感值精度", "number", "%", positive=True),
        ChipField("rated_current_a", "额定电流 Irms", "number", "A", positive=True),
        ChipField("saturation_current_a", "饱和电流 Isat", "number", "A", positive=True),
        ChipField("dc_resistance_ohm", "直流电阻 DCR", "engineering", "Ω", engineering_units=((1e3, "kΩ"), (1, "Ω"), (1e-3, "mΩ")), positive=True),
        ChipField("self_resonance_hz", "自谐振频率", "engineering", "Hz", engineering_units=FREQUENCY_UNITS, positive=True),
        ChipField("shielding", "屏蔽方式", "choice", options=("屏蔽", "非屏蔽", "半屏蔽")),
    ),
    "TVS管": (
        ChipField("tvs_type", "保护类型", "choice", options=("ESD 防静电", "TVS 瞬态抑制"), required=True),
        ChipField("polarity", "方向", "choice", options=("单向", "双向"), required=True),
        ChipField("standoff_voltage_v", "反向工作电压 VRWM", "number", "V", required=True, positive=True),
        ChipField("breakdown_voltage_v", "击穿电压 VBR", "number", "V", positive=True),
        ChipField("clamping_voltage_v", "钳位电压 VC", "number", "V", positive=True),
        ChipField("peak_pulse_current_a", "峰值脉冲电流 IPP", "number", "A", positive=True),
        ChipField("peak_pulse_power_w", "峰值脉冲功率", "number", "W", positive=True),
        ChipField("junction_capacitance_pf", "结电容", "number", "pF", positive=True),
        ChipField("channel_count", "保护通道数量", "integer", "路", positive=True),
        ChipField("esd_rating", "ESD 耐受等级", placeholder="例如 IEC 61000-4-2：接触 ±8 kV、空气 ±15 kV；可留空"),
        ChipField("pulse_conditions", "脉冲 / 测试条件", placeholder="例如 8/20 µs；VC、IPP 对应的测试条件；可留空"),
    ),
    "二极管": (
        ChipField("diode_type", "二极管类型", "choice", options=("肖特基", "整流", "快恢复", "开关", "稳压", "发光", "其他"), required=True),
        ChipField("reverse_voltage_v", "最大反向电压", "number", "V", positive=True),
        ChipField("forward_current_a", "额定正向电流", "number", "A", positive=True),
        ChipField("forward_voltage_v", "正向压降 VF", "number", "V", positive=True),
        ChipField("surge_current_a", "浪涌正向电流", "number", "A", positive=True),
        ChipField("reverse_leakage_ua", "反向漏电流", "number", "µA"),
        ChipField("recovery_time_ns", "反向恢复时间", "number", "ns", positive=True),
        ChipField("zener_voltage_v", "稳压电压 VZ", "number", "V", show_when=("diode_type", ("稳压",)), positive=True),
        ChipField("power_w", "额定功率", "number", "W", positive=True),
        ChipField("configuration", "内部结构", "choice", options=("单管", "双管共阳", "双管共阴", "双管串联", "整流桥", "其他")),
        ChipField("test_conditions", "参数测试条件", placeholder="例如 VF @ IF=1 A、VR=40 V；可留空"),
    ),
    "晶振": (
        ChipField("oscillator_type", "晶振类型", "toggle", options=("无源晶振", "有源晶振", "TCXO", "VCXO", "OCXO"), required=True),
        ChipField("frequency_hz", "标称频率", "engineering", "Hz", required=True, engineering_units=FREQUENCY_UNITS, positive=True),
        ChipField("frequency_tolerance_ppm", "频率精度", "number", "ppm", positive=True),
        ChipField("frequency_stability_ppm", "温度频率稳定度", "number", "ppm", positive=True),
        ChipField("load_capacitance_pf", "负载电容 CL", "number", "pF", show_when=("oscillator_type", ("无源晶振",)), positive=True),
        ChipField("esr_ohm", "等效串联电阻 ESR", "number", "Ω", show_when=("oscillator_type", ("无源晶振",)), positive=True),
        ChipField("drive_level_uw", "驱动功率", "number", "µW", show_when=("oscillator_type", ("无源晶振",)), positive=True),
        ChipField("supply_voltage", "供电电压范围", "range", "V", show_when=("oscillator_type", ("有源晶振", "TCXO", "VCXO", "OCXO"))),
        ChipField("output_signal", "输出信号", "choice", options=("CMOS", "LVCMOS", "LVDS", "LVPECL", "HCSL", "正弦波"), show_when=("oscillator_type", ("有源晶振", "TCXO", "VCXO", "OCXO"))),
        ChipField("enable_function", "使能 / 待机功能", "choice", options=("OE 输出使能", "待机", "无"), show_when=("oscillator_type", ("有源晶振", "TCXO", "VCXO", "OCXO"))),
    ),
    "MOS管": (
        ChipField("channel_type", "沟道类型", "choice", options=("N 沟道", "P 沟道", "N+P 沟道"), required=True),
        ChipField("vds_rating_v", "漏源耐压 |VDS|", "number", "V", required=True, positive=True),
        ChipField("continuous_current_a", "连续漏极电流 |ID|", "number", "A", positive=True),
        ChipField("rds_on_mohm", "导通电阻 RDS(on)", "number", "mΩ", positive=True),
        ChipField("rds_test_conditions", "导通电阻测试条件", placeholder="例如 VGS=4.5 V、ID=5 A、TJ=25 °C；可留空"),
        ChipField("vgs_limit", "栅源电压额定值", placeholder="例如 ±20 V 或 -12～+12 V；可留空"),
        ChipField("vgs_threshold_v", "栅极阈值电压 VGS(th)", "number", "V", signed=True),
        ChipField("gate_charge_nc", "总栅极电荷 Qg", "number", "nC", positive=True),
        ChipField("power_w", "耗散功率", "number", "W", positive=True),
        ChipField("configuration", "内部结构", "choice", options=("单管", "双管", "互补对管", "其他")),
    ),
    "共模电感": (
        ChipField("choke_type", "应用类型", "choice", options=("信号线", "电源线", "其他"), required=True),
        ChipField("common_mode_impedance_ohm", "共模阻抗", "engineering", "Ω", engineering_units=((1e3, "kΩ"), (1, "Ω")), positive=True),
        ChipField("impedance_frequency_hz", "阻抗测试频率", "engineering", "Hz", engineering_units=FREQUENCY_UNITS, positive=True),
        ChipField("inductance_h", "共模感值", "engineering", "H", engineering_units=INDUCTANCE_UNITS, positive=True),
        ChipField("rated_current_a", "额定电流", "number", "A", positive=True),
        ChipField("dc_resistance_ohm", "每线直流电阻 DCR", "engineering", "Ω", engineering_units=((1, "Ω"), (1e-3, "mΩ")), positive=True),
        ChipField("rated_voltage_v", "额定电压", "number", "V", positive=True),
        ChipField("line_count", "线路数量", "integer", "线", positive=True),
        ChipField("application_interface", "适用接口", "choice", options=("USB", "CAN", "Ethernet", "HDMI", "电源", "其他")),
        ChipField("test_conditions", "测试条件 / 补充规格", placeholder="例如 感值 @ 100 kHz；可补充差模参数和耐压；可留空"),
    ),
}
ADDITIONAL_COMPONENT_SPECS = {
    "三极管": (
        ChipField("transistor_type", "三极管类型", "choice", options=("NPN", "PNP", "NPN 达林顿", "PNP 达林顿", "其他"), required=True),
        ChipField("vce_rating_v", "集电极耐压 |VCEO|", "number", "V", positive=True),
        ChipField("collector_current_a", "集电极电流 |IC|", "number", "A", positive=True),
        ChipField("dc_gain", "直流放大倍数 hFE", "number", positive=True),
        ChipField("vce_saturation_v", "饱和压降 |VCE(sat)|", "number", "V", positive=True),
        ChipField("transition_frequency_hz", "特征频率 fT", "engineering", "Hz", engineering_units=FREQUENCY_UNITS, positive=True),
        ChipField("power_w", "耗散功率", "number", "W", positive=True),
        ChipField("configuration", "内部结构", "choice", options=("单管", "双管", "互补对管", "其他")),
        ChipField("pin_assignment", "引脚排列", placeholder="例如 1=B、2=E、3=C；可留空"),
        ChipField("test_conditions", "参数测试条件", placeholder="例如 hFE @ IC=100 mA、VCE=1 V；可留空"),
    ),
    "磁珠": (
        ChipField("impedance_ohm", "标称阻抗", "engineering", "Ω", required=True, engineering_units=((1e3, "kΩ"), (1, "Ω")), positive=True),
        ChipField("impedance_frequency_hz", "阻抗测试频率", "engineering", "Hz", required=True, engineering_units=FREQUENCY_UNITS, positive=True),
        ChipField("bead_application", "应用类型", "choice", options=("电源滤波", "信号滤波", "其他")),
        ChipField("rated_current_a", "额定电流", "number", "A", positive=True),
        ChipField("dc_resistance_ohm", "直流电阻 DCR", "engineering", "Ω", engineering_units=((1, "Ω"), (1e-3, "mΩ")), positive=True),
        ChipField("tolerance_percent", "阻抗精度", "number", "%", positive=True),
    ),
    "连接器": (
        ChipField("connector_type", "连接器类型", "choice", options=("排针", "排母", "接线端子", "USB", "FPC / FFC", "板对板", "线对板", "同轴", "其他"), required=True),
        ChipField("contact_count", "触点数量", "integer", "个", required=True, positive=True),
        ChipField("pitch_mm", "触点间距", "number", "mm", positive=True),
        ChipField("gender", "公母类型", "choice", options=("公头", "母座", "无性别", "其他")),
        ChipField("mounting", "安装方式", "choice", options=("贴片", "直插", "压接", "螺钉固定", "线缆端", "其他")),
        ChipField("orientation", "出线 / 插接方向", "choice", options=("垂直", "水平 / 弯角", "其他")),
        ChipField("row_count", "排数", "integer", "排", positive=True),
        ChipField("rated_current_a", "额定电流 / 触点", "number", "A", positive=True),
        ChipField("rated_voltage_v", "额定电压", "number", "V", positive=True),
        ChipField("interface_spec", "接口 / 配对规格", placeholder="例如 USB Type-C、FPC 下接、配对料号；可留空"),
    ),
    "运算放大器": (
        ChipField("channel_count", "通道数量", "integer", "路", required=True, positive=True),
        ChipField("amplifier_type", "运放类型", "choice", options=("通用", "精密", "低功耗", "高速", "零漂", "仪表放大器", "其他")),
        ChipField("supply_voltage", "总供电电压范围", "range", "V"),
        ChipField("gain_bandwidth_hz", "增益带宽积 GBW", "engineering", "Hz", engineering_units=FREQUENCY_UNITS, positive=True),
        ChipField("slew_rate_v_us", "压摆率 SR", "number", "V/µs", positive=True),
        ChipField("offset_voltage_uv", "输入失调电压绝对值", "number", "µV", allow_zero=True),
        ChipField("input_bias_na", "输入偏置电流绝对值", "number", "nA", allow_zero=True),
        ChipField("noise_nv_sqrthz", "输入电压噪声密度", "number", "nV/√Hz", positive=True),
        ChipField("rail_to_rail", "轨到轨能力", "choice", options=("输入和输出", "仅输入", "仅输出", "均不支持")),
        ChipField("quiescent_current_ua", "每通道静态电流", "number", "µA"),
        ChipField("test_conditions", "测试条件 / 供电说明", placeholder="例如 总供电 10 V 对应 ±5 V；噪声 @ 1 kHz；可留空"),
    ),
    "逻辑芯片": (
        ChipField("logic_function", "逻辑功能", "choice", options=("与门", "或门", "非门", "与非门", "或非门", "异或门", "缓冲器", "触发器", "锁存器", "移位寄存器", "计数器", "译码器", "电平转换", "其他"), required=True),
        ChipField("logic_family", "逻辑系列", "choice", options=("HC", "HCT", "LVC", "AHC", "AHCT", "AUP", "LS", "其他")),
        ChipField("channel_count", "通道 / 门数量", "integer", "路", positive=True),
        ChipField("supply_voltage", "供电电压范围", "range", "V"),
        ChipField("supply_a", "A 侧供电电压范围", "range", "V", show_when=("logic_function", ("电平转换",))),
        ChipField("supply_b", "B 侧供电电压范围", "range", "V", show_when=("logic_function", ("电平转换",))),
        ChipField("propagation_delay_ns", "传播延迟", "number", "ns", positive=True),
        ChipField("max_frequency_hz", "最高工作频率", "engineering", "Hz", engineering_units=FREQUENCY_UNITS, positive=True),
        ChipField("output_structure", "输出结构", "choice", options=("推挽", "开漏", "三态", "其他")),
        ChipField("output_current_ma", "输出驱动电流绝对值", "number", "mA", positive=True),
        ChipField("test_conditions", "逻辑电平 / 测试条件", placeholder="例如 VIH / VIL、传播延迟对应的 VCC 和负载；可留空"),
    ),
    "存储芯片": (
        ChipField("memory_type", "存储类型", "choice", options=("EEPROM", "NOR Flash", "NAND Flash", "FRAM", "SRAM", "DRAM", "ROM", "其他"), required=True),
        ChipField("capacity_bits", "存储容量", "engineering", "bit", required=True, positive=True, integer_value=True,
                  engineering_units=((2**30, "Gbit"), (2**20, "Mbit"), (2**10, "Kbit"),
                                     (8 * 2**30, "GB"), (8 * 2**20, "MB"), (8 * 2**10, "KB"), (8, "B"), (1, "bit"))),
        ChipField("memory_interface", "存储接口", "choice", options=("I²C", "SPI", "QSPI", "OSPI", "并行", "SDR SDRAM", "DDR", "其他")),
        ChipField("supply_voltage", "供电电压范围", "range", "V"),
        ChipField("clock_frequency_hz", "最高时钟频率", "engineering", "Hz", engineering_units=FREQUENCY_UNITS, positive=True),
        ChipField("bus_width_bits", "数据总线位宽", "integer", "bit", positive=True),
        ChipField("write_endurance", "写入 / 擦写寿命", "integer", "次", positive=True,
                  show_when=("memory_type", ("EEPROM", "NOR Flash", "NAND Flash", "FRAM"))),
        ChipField("retention_years", "数据保持时间", "number", "年", positive=True,
                  show_when=("memory_type", ("EEPROM", "NOR Flash", "NAND Flash", "FRAM", "ROM"))),
        ChipField("access_time_ns", "访问时间", "number", "ns", positive=True),
        ChipField("organization", "组织结构 / 补充规格", placeholder="例如 8K × 8 bit、页大小、地址位数；可留空"),
    ),
}
NEW_COMPONENT_SPECS.update(ADDITIONAL_COMPONENT_SPECS)
COMPONENT_SPECS = {**CHIP_SPECS, **NEW_COMPONENT_SPECS}
MODEL_REQUIRED_CATEGORIES = frozenset((*CHIP_SPECS, "电池管理芯片", "TVS管", "二极管", "MOS管", "三极管", "运算放大器", "逻辑芯片", "存储芯片"))


def field_applies(field, parameters):
    return field.show_when is None or parameters.get(field.show_when[0]) in field.show_when[1]


SIGNED_VOLTAGE_PARAMETERS = frozenset(
    f"{field.key}_{endpoint}_v"
    for fields in COMPONENT_SPECS.values() for field in fields if field.signed
    for endpoint in ("min", "max")
) | {field.key for fields in COMPONENT_SPECS.values() for field in fields if field.signed and field.kind != "range"}


def current_parameters(category, parameters):
    """Normalize older records and exclude parameters inapplicable to their type."""
    removed = {"controller_type", "interfaces"} if category == "主控芯片" else set()
    if category == "协议收发芯片":
        removed.update({"duplex", "pin_count"})
    if category == "电源管理芯片":
        removed.update({"topology", "output_mode"})
    params = {key: value for key, value in parameters.items() if key not in removed}
    for field in COMPONENT_SPECS.get(category, ()):
        if not field_applies(field, params):
            keys = [f"{field.key}_{endpoint}_v" for endpoint in ("min", "max")] if field.kind == "range" else [field.key]
            for key in keys:
                params.pop(key, None)
    if category == "电源管理芯片" and "power_type" in params:
        params["power_type"] = normalize_power_type(params["power_type"])
        if params["power_type"] == "LDO":
            if "ldo_output_mode" not in params and parameters.get("output_mode") in LDO_OUTPUT_MODES:
                params["ldo_output_mode"] = parameters["output_mode"]
            if "ldo_output_mode" not in params and "output_voltage_v" in params:
                params["ldo_output_mode"] = "固定输出"
            low, high = params.get("output_voltage_min_v"), params.get("output_voltage_max_v")
            if params.get("ldo_output_mode") == "固定输出":
                if "output_voltage_v" not in params and low is not None and low == high:
                    params["output_voltage_v"] = low
                if "output_voltage_v" in params:
                    params.pop("output_voltage_min_v", None)
                    params.pop("output_voltage_max_v", None)
            elif params.get("ldo_output_mode") == "可调输出" and "output_voltage_v" in params:
                voltage = params.pop("output_voltage_v")
                for endpoint in ("min", "max"):
                    params.setdefault(f"output_voltage_{endpoint}_v", voltage)
        elif "output_voltage_v" in params:
            voltage = params.pop("output_voltage_v")
            for endpoint in ("min", "max"):
                params.setdefault(f"output_voltage_{endpoint}_v", voltage)
        if params["power_type"] in POWER_TYPES:
            for field in CHIP_SPECS["电源管理芯片"]:
                # Keep existing LDO voltage data until the user explicitly chooses its mode.
                if params["power_type"] == "LDO" and field.key == "output_voltage" and "output_voltage_v" not in params:
                    continue
                if not power_field_applies(field.key, params["power_type"], params.get("pmu_charger", ""), params.get("ldo_output_mode", "")):
                    keys = [f"{field.key}_{endpoint}_v" for endpoint in ("min", "max")] if field.kind == "range" else [field.key]
                    for key in keys:
                        params.pop(key, None)
    return params
