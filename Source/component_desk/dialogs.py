"""Forms for editing component specifications and recording stock changes."""

from __future__ import annotations

from pathlib import Path
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QStyle, QStyleOptionComboBox, QStyleOptionSpinBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from .database import CATEGORIES, MAX_QUANTITY, Database, engineering, parameter_summary
from .specifications import CHIP_SPECS, COMPONENT_SPECS, MODEL_REQUIRED_CATEGORIES, field_applies, field_required, normalize_power_type, power_field_applies
from .style import icon


def error(parent, exc):
    QMessageBox.warning(parent, "无法完成操作", str(exc))


def label(text, name="Subtle"):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    return widget


def button(text, name="", icon_name="", callback=None):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    if icon_name:
        widget.setIcon(icon(icon_name, "white" if name == "Primary" else "#71859D"))
    if callback:
        widget.clicked.connect(callback)
    return widget


class QuantitySpinBox(QSpinBox):
    """Paint clear step arrows over the styled native spin buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("QuantityInput")
        self.setAccessibleName("数量")
        self.arrows = {
            (direction, enabled): icon(direction, "#172B43" if enabled else "#94A3B8", 16)
            for direction in ("chevron-up", "chevron-down") for enabled in (False, True)
        }

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        for control, flag, direction in [
            (QStyle.SubControl.SC_SpinBoxUp, QAbstractSpinBox.StepEnabledFlag.StepUpEnabled, "chevron-up"),
            (QStyle.SubControl.SC_SpinBoxDown, QAbstractSpinBox.StepEnabledFlag.StepDownEnabled, "chevron-down"),
        ]:
            rect = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, control, self)
            enabled = self.isEnabled() and bool(option.stepEnabled & flag)
            self.arrows[(direction, enabled)].paint(painter, rect.adjusted(5, 1, -5, -1))
        painter.end()


def integer(value=0):
    widget = QuantitySpinBox()
    widget.setRange(0, MAX_QUANTITY)
    widget.setValue(value)
    widget.setGroupSeparatorShown(True)
    return widget


class CategoryComboBox(QComboBox):
    """Keep preset dropdown arrows visible for both editable and fixed choices."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ComponentCategory")
        self.arrow_icon = icon("chevron-down", "#172B43", 16)
        self.disabled_arrow_icon = icon("chevron-down", "#94A3B8", 16)

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        arrow = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                           QStyle.SubControl.SC_ComboBoxArrow, self)
        painter = QPainter(self)
        (self.arrow_icon if self.isEnabled() else self.disabled_arrow_icon).paint(painter, arrow.adjusted(4, 0, -4, 0))
        painter.end()


class SpecificationStack(QStackedWidget):
    """Let each category use only the height its current form needs."""

    def sizeHint(self):
        return self.currentWidget().sizeHint() if self.currentWidget() else super().sizeHint()

    def minimumSizeHint(self):
        return self.currentWidget().minimumSizeHint() if self.currentWidget() else super().minimumSizeHint()


class ComponentDialog(QDialog):
    """Specifications for the component categories currently being defined."""

    SUPPORTED_CATEGORIES = CATEGORIES

    def __init__(self, db: Database, component=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.component = component or {}
        self.saved_id = None
        self.setWindowTitle("编辑元件" if component else "新增元件")
        self.resize(650, 800)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(label(self.windowTitle(), "Title"))
        root.addWidget(label("带 * 的项目必填；选填参数可留空。库存数量通过入库操作添加。"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("FormBody")
        form = QFormLayout(content)
        form.setContentsMargins(2, 12, 12, 12)
        form.setVerticalSpacing(12)
        forms = [form]
        self.category = CategoryComboBox()
        self.category.addItems(self.SUPPORTED_CATEGORIES)
        current = self.component.get("category", self.SUPPORTED_CATEGORIES[0])
        if current not in self.SUPPORTED_CATEGORIES:
            current = self.SUPPORTED_CATEGORIES[0]
        self.category.setCurrentText(current)
        form.addRow("元件类别", self.category)
        self.specs = SpecificationStack()
        self.specs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.specs.currentChanged.connect(self.specs.updateGeometry)
        self.spec_widgets = {}
        self.spec_forms = {}
        for category in self.SUPPORTED_CATEGORIES:
            params = self.component.get("parameters", {}) if category == self.component.get("category") else {}
            if category in COMPONENT_SPECS:
                page, rows, fields = self.chip_page(category, params,
                                                  self.component.get("package", "") if category == current else "",
                                                  self.component.get("model", "") if category == current else "")
                forms.append(rows)
                self.spec_widgets[category] = fields
                self.spec_forms[category] = rows
                self.specs.addWidget(page)
                continue
            page = QWidget()
            rows = QFormLayout(page)
            forms.append(rows)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setVerticalSpacing(12)
            cap = category == "贴片电容"
            key = "capacitance_f" if cap else "resistance_ohm"
            units = [("pF", 1e-12), ("nF", 1e-9), ("µF", 1e-6), ("mF", 1e-3), ("F", 1)] if cap else [("Ω", 1), ("kΩ", 1e3), ("MΩ", 1e6)]
            value = QLineEdit()
            value.setPlaceholderText("例如：100" if cap else "例如：4.7；支持 0 Ω 电阻")
            unit = QLineEdit()
            unit.setPlaceholderText("单位，如 uF" if cap else "单位，如 kΩ")
            unit.setToolTip("手动输入单位：pF、nF、uF / µF、mF、F" if cap else "手动输入单位：Ω / ohm、kΩ / kohm、MΩ / Mohm")
            unit.setAccessibleName("容值单位（必填）" if cap else "阻值单位（必填）")
            unit.setFixedWidth(120)
            if key in params:
                number = float(params[key])
                factor = next((f for _, f in reversed(units) if number >= f), units[0][1])
                unit.setText(next(title for title, f in units if f == factor))
                value.setText(format(number / factor, ".15g"))
            value_row = QWidget()
            value_layout = QHBoxLayout(value_row)
            value_layout.setContentsMargins(0, 0, 0, 0)
            value_layout.addWidget(value, 1)
            value_layout.addWidget(unit)
            rows.addRow("容值 *" if cap else "阻值 *", value_row)
            package = self.combo(["", "0201", "0402", "0603", "0805", "1206", "1210", "1812", "2010", "2512"], self.component.get("package", "") if category == current else "")
            package.lineEdit().setPlaceholderText("选择常用封装，或输入自定义封装")
            rows.addRow("封装 *", package)
            rating_key = "voltage_v" if cap else "power_w"
            options = ["", "6.3", "10", "16", "25", "50", "100"] if cap else ["", "0.0625", "0.1", "0.125", "0.25", "0.5", "1", "2"]
            rating = self.combo(options, format(params[rating_key], ".15g") if rating_key in params else "")
            rating.lineEdit().setPlaceholderText("请选择或输入额定电压，例如 25" if cap else "请选择或输入功率，例如 0.125 或 1/8")
            precision = self.combo(["", "0.1", "0.5", "1", "2", "5", "10", "20"], format(params["tolerance_percent"], ".15g") if "tolerance_percent" in params else "")
            precision.lineEdit().setPlaceholderText("请选择或输入精度，例如 1 表示 ±1%")
            if cap:
                rows.addRow("额定电压 (V) *", rating)
                rows.addRow("精度 (±%) *", precision)
            else:
                rows.addRow("精度 (±%) *", precision)
                rows.addRow("功率 (W) *", rating)
            fields = {"value": value, "unit": unit, "package": package, rating_key: rating, "tolerance_percent": precision}
            if cap:
                extra = self.combo(["", "C0G/NP0", "X7R", "X5R", "X7S", "Y5V", "其他"], str(params.get("dielectric", "")))
                rows.addRow("介质 / 温度特性", extra)
                fields["dielectric"] = extra
            else:
                extra = QLineEdit(str(params.get("temperature_coefficient", "")))
                extra.setPlaceholderText("例如：±100 ppm/°C；可留空")
                rows.addRow("温度系数", extra)
                fields["temperature_coefficient"] = extra
            self.spec_widgets[category] = fields
            self.specs.addWidget(page)
        self.specs.setCurrentIndex(self.category.currentIndex())
        self.category.currentIndexChanged.connect(self.specs.setCurrentIndex)
        form.addRow(self.specs)
        form.addRow(label("补充信息（选填）", "Heading"))
        self.temperature_range = QLineEdit(str(self.component.get("parameters", {}).get("operating_temperature", "")))
        self.temperature_range.setPlaceholderText("例如：-55～125 °C")
        self.name = QLineEdit(self.component.get("name", ""))
        self.name.setPlaceholderText("留空时按元件参数或芯片型号自动生成")
        self.model = QLineEdit(self.component.get("model", ""))
        self.manufacturer = QLineEdit(self.component.get("manufacturer", ""))
        form.addRow("工作温度范围", self.temperature_range)
        form.addRow("元件名称", self.name)
        form.addRow("型号", self.model)
        form.addRow("厂家", self.manufacturer)
        self.common_form = form
        self.category.currentTextChanged.connect(self.update_common_fields)
        self.update_common_fields(current)
        self.update_power_fields()
        for category, definitions in COMPONENT_SPECS.items():
            for selector in {field.show_when[0] for field in definitions if field.show_when}:
                self.spec_widgets[category][selector].currentTextChanged.connect(
                    lambda _text, category=category: self.update_conditional_fields(category))
            self.update_conditional_fields(category)
        # Every stacked specification page shares the outer form's label column.
        labels = []
        for layout in forms:
            layout.setHorizontalSpacing(12)
            layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
            for row in range(layout.rowCount()):
                item = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if item and item.widget():
                    labels.append(item.widget())
        label_width = max(widget.sizeHint().width() + widget.fontMetrics().horizontalAdvance(" *") for widget in labels)
        for widget in labels:
            widget.setFixedWidth(label_width)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton("保存元件", QDialogButtonBox.ButtonRole.AcceptRole)
        self.save_button.setObjectName("Primary")
        self.cancel_button = buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def combo(options, current):
        widget = CategoryComboBox()
        widget.setEditable(True)
        widget.addItems(options)
        widget.setCurrentText(current)
        return widget

    def chip_page(self, category, params, package, model):
        page = QWidget()
        rows = QFormLayout(page)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setVerticalSpacing(12)
        model_widget = QLineEdit(model)
        required_model = category in MODEL_REQUIRED_CATEGORIES
        model_widget.setPlaceholderText("请输入完整型号" if required_model else "可留空；填写器件型号")
        rows.addRow("型号 *" if required_model else "型号", model_widget)
        packages = ["", "SOT-23", "SOT-23-5", "SOT-223", "SOIC-8", "TSSOP-8", "TSSOP-16", "QFN-32", "QFN-48", "LQFP-48", "LQFP-64", "BGA"]
        if category in {"电感", "共模电感", "磁珠"}:
            packages = ["", "0402", "0603", "0805", "1206", "1210", "2020", "3030", "4040", "5050", "直插"]
        elif category == "晶振":
            packages = ["", "1612", "2016", "2520", "3225", "5032", "7050", "HC-49S", "圆柱直插"]
        elif category in {"TVS管", "二极管", "MOS管", "三极管"}:
            packages = ["", "SOD-123", "SOD-323", "SOD-523", "SMA", "SMB", "SMC", "SOT-23", "SOT-23-6", "SOT-89", "SOT-223", "SOIC-8", "DFN", "TO-220", "TO-252", "TO-263"]
        elif category == "连接器":
            packages = ["", "贴片", "直插", "线缆端", "面板安装", "压接"]
        package_widget = self.combo(packages, package)
        package_widget.lineEdit().setPlaceholderText("选择或手动输入封装")
        rows.addRow("封装 / 外形 *" if category == "连接器" else "封装 *", package_widget)
        fields = {"package": package_widget, "model": model_widget}
        for field in COMPONENT_SPECS[category]:
            title = field.title + (f" ({field.unit})" if field.unit and field.kind not in {"frequency", "engineering"} else "") + (" *" if field.required else "")
            if field.kind == "engineering":
                value_text, unit_text = "", ""
                if field.key in params:
                    number = float(params[field.key])
                    factor, unit_text = next(((factor, unit) for factor, unit in field.engineering_units if number >= factor), field.engineering_units[-1])
                    value_text = format(number / factor, ".15g")
                value = QLineEdit(value_text)
                value.setPlaceholderText("请输入数值" if field.required else "可留空；请输入数值")
                unit = QLineEdit(unit_text)
                unit.setPlaceholderText("单位，如 " + ("Kbit" if field.key == "capacity_bits" else field.engineering_units[-2][1]))
                unit.setToolTip("手动输入单位：" + "、".join(unit for _, unit in field.engineering_units))
                if field.key == "capacity_bits":
                    unit.setToolTip("区分 bit（位）与 B（字节）：1 B = 8 bit；K / M / G 按 1024 换算。\n支持 bit、Kbit、Mbit、Gbit、B、KB、MB、GB，以及 KiB / MiB / GiB。")
                unit.setAccessibleName(field.title + "单位")
                unit.setFixedWidth(120)
                row = QWidget()
                horizontal = QHBoxLayout(row)
                horizontal.setContentsMargins(0, 0, 0, 0)
                horizontal.addWidget(value, 1)
                horizontal.addWidget(unit)
                fields[field.key] = value
                fields[field.key + "_unit"] = unit
                rows.addRow(title, row)
                continue
            if field.kind == "multiline":
                widget = QTextEdit()
                widget.setObjectName("MultiLineSpecification")
                widget.setAcceptRichText(False)
                widget.setPlainText(str(params.get(field.key, "")))
                widget.setPlaceholderText(field.placeholder)
                fields[field.key] = widget
                rows.addRow(title, widget)
                continue
            if field.kind == "frequency":
                value_text, unit_text = "", ""
                if field.key in params:
                    value_text, unit_text = engineering(params[field.key], [(1e6, "GHz"), (1e3, "MHz"), (1, "kHz"), (1e-3, "Hz")]).split()
                value = QLineEdit(value_text)
                value.setPlaceholderText("可留空；例如 500")
                unit = QLineEdit(unit_text)
                unit.setPlaceholderText("单位，如 kHz")
                unit.setToolTip("手动输入单位：Hz、kHz、MHz、GHz；数值和单位同时填写或同时留空。")
                unit.setAccessibleName("开关频率单位")
                unit.setFixedWidth(120)
                row = QWidget()
                horizontal = QHBoxLayout(row)
                horizontal.setContentsMargins(0, 0, 0, 0)
                horizontal.addWidget(value, 1)
                horizontal.addWidget(unit)
                fields[field.key] = value
                fields["switching_frequency_unit"] = unit
                rows.addRow(title, row)
                continue
            if field.kind == "range":
                row = QWidget()
                horizontal = QHBoxLayout(row)
                horizontal.setContentsMargins(0, 0, 0, 0)
                limits = []
                for endpoint, placeholder in [("min", "最小值"), ("max", "最大值")]:
                    key = f"{field.key}_{endpoint}_v"
                    widget = QLineEdit(format(params[key], ".15g") if key in params else "")
                    widget.setPlaceholderText(placeholder)
                    widget.setToolTip("最小值、最大值均必填；固定电压填写相同数值。" if field.required else "两个端点同时填写或同时留空；固定电压填写相同数值。")
                    if limits:
                        horizontal.addWidget(label("～", ""))
                    horizontal.addWidget(widget, 1)
                    limits.append(widget)
                fields[field.key] = tuple(limits)
                rows.addRow(title, row)
                continue
            if field.kind in {"choice", "toggle"}:
                if field.key == "power_type" or field.kind == "toggle":
                    widget = CategoryComboBox()
                    widget.addItems(["", *field.options])
                    placeholder = "请选择 DCDC、LDO 或 PMU" if field.key == "power_type" else "请选择" if field.required else "请选择，未知可留空"
                    if field.key == "ldo_output_mode":
                        placeholder = "请选择固定输出或可调输出"
                    widget.setPlaceholderText(placeholder)
                    current_value = normalize_power_type(params.get(field.key, "")) if field.key == "power_type" else str(params.get(field.key, ""))
                    widget.setCurrentIndex(widget.findText(current_value) if current_value else -1)
                else:
                    widget = self.combo(["", *field.options], str(params.get(field.key, "")))
                    widget.lineEdit().setPlaceholderText("请选择或输入" if field.required else "可留空，支持手动输入")
            else:
                value = params.get(field.key, "")
                widget = QLineEdit(format(value, ".15g") if isinstance(value, (int, float)) else str(value))
                widget.setPlaceholderText(field.placeholder or ("请输入数值" if field.required else "可留空；请输入数值" if field.kind in {"number", "integer"} else "可留空；请输入内容"))
            fields[field.key] = widget
            rows.addRow(title, widget)
        if category == "电源管理芯片":
            self.power_form = rows
            fields["dropout_voltage_mv"].setPlaceholderText("可留空；例如 200 表示 200 mV")
            fields["power_type"].currentTextChanged.connect(self.update_power_fields)
            fields["ldo_output_mode"].currentTextChanged.connect(self.update_power_fields)
            fields["pmu_charger"].currentTextChanged.connect(self.update_power_fields)
        return page, rows, fields

    def update_common_fields(self, category):
        self.common_form.setRowVisible(self.model, category not in COMPONENT_SPECS)
        self.specs.updateGeometry()

    def update_conditional_fields(self, category):
        fields = self.spec_widgets[category]
        selectors = {field.show_when[0] for field in COMPONENT_SPECS[category] if field.show_when}
        parameters = {key: fields[key].currentText() for key in selectors}
        for field in COMPONENT_SPECS[category]:
            if field.show_when is None:
                continue
            widget = fields[field.key]
            row = widget[0].parentWidget() if isinstance(widget, tuple) else widget.parentWidget() if field.kind == "engineering" else widget
            visible = field_applies(field, parameters)
            self.spec_forms[category].setRowVisible(row, visible)
            row.setEnabled(visible)
        self.specs.updateGeometry()

    def update_power_fields(self, *_):
        fields = self.spec_widgets.get("电源管理芯片")
        if not fields:
            return
        power_type = fields["power_type"].currentText()
        ldo_mode = fields["ldo_output_mode"].currentText()
        if power_type == "LDO":
            low, high = fields["output_voltage"]
            fixed = fields["output_voltage_v"]
            if ldo_mode == "固定输出" and not fixed.text().strip() and low.text().strip() and low.text().strip() == high.text().strip():
                fixed.setText(low.text().strip())
            elif ldo_mode == "可调输出" and not low.text().strip() and not high.text().strip() and fixed.text().strip():
                low.setText(fixed.text().strip())
                high.setText(fixed.text().strip())
        for field in CHIP_SPECS["电源管理芯片"]:
            widget = fields[field.key]
            row_widget = widget[0].parentWidget() if isinstance(widget, tuple) else widget
            if field.kind == "frequency":
                row_widget = widget.parentWidget()
            visible = power_field_applies(field.key, power_type, fields["pmu_charger"].currentText(), ldo_mode)
            self.power_form.setRowVisible(row_widget, visible)
            row_widget.setEnabled(visible)
            required = visible and field_required(field, power_type)
            title = field.title + (f" ({field.unit})" if field.unit and field.kind != "frequency" else "") + (" *" if required else "")
            self.power_form.labelForField(row_widget).setText(title)
            if field.kind == "number":
                widget.setPlaceholderText("请输入数值" if required else field.placeholder or "可留空；请输入数值")
            elif field.kind == "range":
                for endpoint in widget:
                    endpoint.setToolTip("最小值、最大值均必填；固定电压填写相同数值。" if required else "两个端点同时填写或同时留空；固定电压填写相同数值。")
            elif field.kind == "frequency":
                widget.setPlaceholderText("例如 500" if required else "可留空；例如 500")
                fields["switching_frequency_unit"].setAccessibleName("开关频率单位（必填）" if required else "开关频率单位")
                fields["switching_frequency_unit"].setToolTip("手动输入单位：Hz、kHz、MHz、GHz；数值和单位都必填。" if required else "手动输入单位：Hz、kHz、MHz、GHz。")
        self.specs.updateGeometry()

    @staticmethod
    def number(text, title, allow_zero=False, optional=False, fraction=False, signed=False):
        text = text.strip()
        if not text and optional:
            return None
        if not text:
            raise ValueError(f"请填写{title}，此项为必填。")
        try:
            if fraction and "/" in text:
                numerator, denominator = text.split("/")
                value = float(numerator) / float(denominator)
            else:
                value = float(text)
        except (ValueError, ZeroDivisionError):
            raise ValueError(f"请填写有效的{title}数值。") from None
        if not math.isfinite(value) or (value < 0 and not signed) or (not allow_zero and value == 0):
            if signed:
                raise ValueError(f"{title}必须是有限数值。")
            raise ValueError(f"{title}必须是{'非负' if allow_zero else '大于零的'}有限数值。")
        return value

    @staticmethod
    def unit_factor(text, capacitance):
        unit = text.strip().replace("μ", "µ").replace("Ω", "Ω")
        if not unit:
            raise ValueError("请填写容值单位，此项为必填。" if capacitance else "请填写阻值单位，此项为必填。")
        if capacitance:
            factors = {"pF": 1e-12, "pf": 1e-12, "nF": 1e-9, "nf": 1e-9,
                       "uF": 1e-6, "uf": 1e-6, "µF": 1e-6, "µf": 1e-6,
                       "mF": 1e-3, "mf": 1e-3, "F": 1, "f": 1}
        else:
            factors = {"Ω": 1, "ohm": 1, "Ohm": 1, "OHM": 1,
                       "kΩ": 1e3, "KΩ": 1e3, "kohm": 1e3, "kOhm": 1e3,
                       "Kohm": 1e3, "KOhm": 1e3, "MΩ": 1e6, "Mohm": 1e6, "MOhm": 1e6}
        if unit not in factors:
            examples = "pF、nF、uF / µF、mF、F" if capacitance else "Ω / ohm、kΩ / kohm、MΩ / Mohm"
            raise ValueError(f"无法识别{'容值' if capacitance else '阻值'}单位，请输入：{examples}。")
        return factors[unit]

    @classmethod
    def frequency_khz(cls, value_text, unit_text, optional=True):
        if optional and not value_text.strip() and not unit_text.strip():
            return None
        value = cls.number(value_text, "开关频率")
        unit = unit_text.strip()
        if not unit:
            raise ValueError("请填写开关频率单位。")
        factors = {"Hz": 1e-3, "hz": 1e-3, "kHz": 1, "KHz": 1, "khz": 1,
                   "MHz": 1e3, "mhz": 1e3, "GHz": 1e6, "ghz": 1e6}
        if unit not in factors:
            raise ValueError("无法识别开关频率单位，请输入：Hz、kHz、MHz、GHz。")
        normalized = value * factors[unit]
        if not math.isfinite(normalized) or normalized == 0:
            raise ValueError("开关频率超出可保存的数值范围。")
        return normalized

    def component_data(self):
        category = self.category.currentText()
        if category in COMPONENT_SPECS:
            return self.chip_component_data(category)
        params = dict(self.component.get("parameters", {})) if category == self.component.get("category") else {}
        fields = self.spec_widgets[category]
        cap = category == "贴片电容"
        value = self.number(fields["value"].text(), "容值" if cap else "阻值", allow_zero=not cap)
        normalized = value * self.unit_factor(fields["unit"].text(), cap)
        if not math.isfinite(normalized) or (value > 0 and normalized == 0):
            raise ValueError("容值或阻值超出可保存的数值范围。")
        params["capacitance_f" if cap else "resistance_ohm"] = normalized
        key = "voltage_v" if cap else "power_w"
        rating = self.number(fields[key].currentText(), "额定电压" if cap else "功率", fraction=not cap)
        tolerance_text = fields["tolerance_percent"].currentText().strip().removeprefix("±").removesuffix("%").strip()
        tolerance = self.number(tolerance_text, "精度")
        if tolerance > 100:
            raise ValueError("精度百分比不能超过 100。")
        params[key] = rating
        params["tolerance_percent"] = tolerance
        extra_key = "dielectric" if cap else "temperature_coefficient"
        widget = fields[extra_key]
        text = widget.currentText().strip() if isinstance(widget, QComboBox) else widget.text().strip()
        params.pop(extra_key, None)
        if text:
            params[extra_key] = text
        package = fields["package"].currentText().strip()
        if not package:
            raise ValueError("请选择或填写封装。")
        units = [(1, "F"), (1e-3, "mF"), (1e-6, "µF"), (1e-9, "nF"), (1e-12, "pF")] if cap else [(1e6, "MΩ"), (1e3, "kΩ"), (1, "Ω")]
        default_name = f"{category} {engineering(normalized, units)}"
        return self.finish_component_data(category, package, params, default_name)

    def chip_component_data(self, category):
        fields = self.spec_widgets[category]
        package = fields["package"].currentText().strip()
        if not package:
            raise ValueError("请选择或填写封装。")
        model = fields["model"].text().strip()
        if category in MODEL_REQUIRED_CATEGORIES and not model:
            raise ValueError("请填写型号，此项为必填。")
        params = dict(self.component.get("parameters", {})) if category == self.component.get("category") else {}
        selectors = {field.show_when[0] for field in COMPONENT_SPECS[category] if field.show_when}
        applicability = {key: fields[key].currentText() for key in selectors}
        for field in COMPONENT_SPECS[category]:
            widget = fields[field.key]
            if not field_applies(field, applicability) or category == "电源管理芯片" and not power_field_applies(field.key, fields["power_type"].currentText(), fields["pmu_charger"].currentText(), fields["ldo_output_mode"].currentText()):
                keys = [f"{field.key}_{endpoint}_v" for endpoint in ("min", "max")] if field.kind == "range" else [field.key]
                for key in keys:
                    params.pop(key, None)
                continue
            required = field_required(field, fields["power_type"].currentText() if category == "电源管理芯片" else "")
            if field.kind == "range":
                values = [self.number(w.text(), field.title, allow_zero=True, optional=not required, signed=field.signed) for w in widget]
                if (values[0] is None) != (values[1] is None):
                    raise ValueError(f"{field.title}请同时填写最小值和最大值，或同时留空。")
                if values[0] is not None and values[0] > values[1]:
                    raise ValueError(f"{field.title}的最小值不能大于最大值。")
                for endpoint, value in zip(("min", "max"), values):
                    key = f"{field.key}_{endpoint}_v"
                    params.pop(key, None)
                    if value is not None:
                        params[key] = value
                continue
            params.pop(field.key, None)
            if not widget.isEnabled():
                continue
            if field.kind == "multiline":
                text = widget.toPlainText().strip()
            else:
                text = widget.currentText().strip() if isinstance(widget, QComboBox) else widget.text().strip()
            if required and not text:
                raise ValueError(f"请填写{field.title}，此项为必填。")
            if field.kind == "frequency":
                value = self.frequency_khz(text, fields["switching_frequency_unit"].text(), optional=not required)
            elif field.kind == "engineering":
                value = self.engineering_value(text, fields[field.key + "_unit"].text(), field, optional=not required)
            elif field.kind in ("number", "integer"):
                value = self.number(text, field.title, optional=not required,
                                    allow_zero=field.allow_zero or field.signed or field.key in {"flash_kb", "ram_kb", "dropout_voltage_mv", "quiescent_current_ua", "pmu_dcdc_count", "pmu_ldo_count", "output_voltage_v", "reverse_leakage_ua"},
                                    signed=field.signed)
                if value is not None and field.kind == "integer":
                    if not value.is_integer():
                        raise ValueError(f"{field.title}必须是整数。")
                    value = int(value)
            else:
                value = text or None
            if value is not None:
                params[field.key] = value
        summary = parameter_summary(category, params)
        default_name = model or f"{category} {summary if summary != '—' else ''}".strip()
        return self.finish_component_data(category, package, params, default_name, model=model)

    @classmethod
    def engineering_value(cls, value_text, unit_text, field, optional=True):
        if optional and not value_text.strip() and not unit_text.strip():
            return None
        value = cls.number(value_text, field.title)
        unit = unit_text.strip().replace("μ", "µ").replace("Ω", "Ω")
        aliases = {"uH": "µH", "uh": "µH", "µh": "µH", "nh": "nH", "mh": "mH", "h": "H",
                   "hz": "Hz", "khz": "kHz", "KHz": "kHz", "mhz": "MHz", "ghz": "GHz",
                   "ohm": "Ω", "Ohm": "Ω", "kohm": "kΩ", "KΩ": "kΩ", "mohm": "mΩ",
                   "kbit": "Kbit", "KiB": "KB", "MiB": "MB", "GiB": "GB"}
        unit = aliases.get(unit, unit)
        factors = {unit: factor for factor, unit in field.engineering_units}
        if unit not in factors:
            raise ValueError(f"请填写有效的{field.title}单位：{'、'.join(factors)}。")
        normalized = value * factors[unit]
        if not math.isfinite(normalized) or normalized == 0:
            raise ValueError(f"{field.title}超出可保存的数值范围。")
        if field.integer_value:
            if not normalized.is_integer():
                raise ValueError(f"{field.title}换算后必须是整数位数。")
            return int(normalized)
        return normalized

    def finish_component_data(self, category, package, params, default_name, model=None):
        params.pop("operating_temperature", None)
        if self.temperature_range.text().strip():
            params["operating_temperature"] = self.temperature_range.text().strip()
        return {**self.component, "name": self.name.text().strip() or default_name,
                "category": category, "package": package, "parameters": params,
                "model": self.model.text() if model is None else model, "manufacturer": self.manufacturer.text()}

    def save(self):
        try:
            self.saved_id = self.db.save_component(self.component_data(), self.component.get("id"))
        except Exception as exc:
            error(self, exc)
            return
        self.accept()


class StockDialog(QDialog):
    def __init__(self, db: Database, component: dict, kind="入库", parent=None):
        super().__init__(parent)
        self.db, self.component = db, component
        self.setWindowTitle(f"{kind} · {component['name']}")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addWidget(label(component["name"], "Heading"))
        root.addWidget(label(f"总库存 {component['total_quantity']:,} 件 · {component['package']}"))
        form = QFormLayout()
        form.setVerticalSpacing(14)
        self.kind = CategoryComboBox()
        self.kind.addItems(["入库", "领用", "盘点"])
        self.kind.setCurrentText(kind)
        self.location = CategoryComboBox()
        for item in db.locations():
            self.location.addItem(item["name"], item["id"])
        if component["stocks"]:
            self.location.setCurrentIndex(self.location.findData(component["stocks"][0]["location_id"]))
        self.balance = label("")
        self.amount = integer(1)
        self.amount_label = QLabel("数量")
        self.note = QLineEdit()
        self.note.setPlaceholderText("例如：采购补货 / 项目领用 / 实物盘点")
        form.addRow("操作类型", self.kind)
        location_row = QWidget()
        location_layout = QHBoxLayout(location_row)
        location_layout.setContentsMargins(0, 0, 0, 0)
        location_layout.addWidget(self.location, 1)
        location_layout.addWidget(button("新增库位", callback=self.add_location))
        form.addRow("库位", location_row)
        form.addRow("", self.balance)
        form.addRow(self.amount_label, self.amount)
        form.addRow("备注", self.note)
        root.addLayout(form)
        self.explanation = label("")
        self.explanation.setWordWrap(True)
        root.addWidget(self.explanation)
        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton("确认保存", QDialogButtonBox.ButtonRole.AcceptRole)
        self.save_button.setObjectName("Primary")
        buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.kind.currentTextChanged.connect(self.update_balance)
        self.location.currentIndexChanged.connect(self.update_balance)
        self.update_balance()

    def update_balance(self):
        stock = next((s for s in self.component["stocks"] if s["location_id"] == self.location.currentData()), None)
        balance = stock["quantity"] if stock else 0
        self.balance.setText(f"此库位当前有 {balance:,} 件")
        counting = self.kind.currentText() == "盘点"
        self.amount_label.setText("实物数量" if counting else "数量")
        self.amount.setMinimum(0 if counting else 1)
        if counting:
            self.amount.setValue(balance)
        self.explanation.setText("盘点会将此库位库存调整为填写的实物数量，并记录差额。" if counting else "保存后会更新所选库位的库存，并生成一条出入库记录。")
        self.save_button.setEnabled(self.location.count() > 0)

    def add_location(self):
        name, accepted = QInputDialog.getText(self, "新增库位", "库位名称（例如：A柜 · 03格）")
        if accepted:
            try:
                location_id = self.db.add_location(name)
                self.location.addItem(name.strip(), location_id)
                self.location.setCurrentIndex(self.location.count() - 1)
            except Exception as exc:
                error(self, exc)

    def save(self):
        try:
            self.db.change_stock(self.component["id"], self.location.currentData(), self.kind.currentText(), self.amount.value(), self.note.text())
        except Exception as exc:
            error(self, exc)
            return
        self.accept()


class LocationDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.changed = False
        self.setWindowTitle("库位管理")
        self.resize(780, 560)
        self.setMinimumSize(680, 480)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(label("库位管理", "Title"))
        root.addWidget(label("管理存放位置，可删除空库位，已有出入库记录会保留。"))
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("搜索库位名称…")
        self.search.setClearButtonEnabled(True)
        self.empty_only = QCheckBox("只看空库位")
        filters.addWidget(self.search, 1)
        filters.addWidget(self.empty_only)
        root.addLayout(filters)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["库位名称", "元件种类", "库存件数", "状态"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            self.table.setColumnWidth(col, 115)
        root.addWidget(self.table, 1)
        self.empty_message = label("暂无库位，点击“新增库位”添加存放位置。")
        self.empty_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_message)
        self.summary = label("")
        root.addWidget(self.summary)
        self.selection_hint = label("")
        self.selection_hint.setWordWrap(True)
        root.addWidget(self.selection_hint)
        actions = QHBoxLayout()
        self.add_button = button("新增库位", "Primary", "plus", self.add)
        self.rename_button = button("重命名", callback=self.rename)
        self.remove_button = button("删除库位", callback=self.remove)
        actions.addWidget(self.add_button)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        actions.addWidget(button("关闭", callback=self.accept))
        root.addLayout(actions)
        self.search.textChanged.connect(lambda: self.reload())
        self.empty_only.toggled.connect(lambda: self.reload())
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.reload()

    def selected_location(self):
        index = self.table.currentRow()
        return self.rows[index] if self.table.selectedItems() and 0 <= index < len(self.rows) else None

    def reload(self, select_id=None):
        selected = self.selected_location() if hasattr(self, "rows") else None
        if select_id is None and selected:
            select_id = selected["id"]
        all_rows = self.db.locations()
        query = self.search.text().strip().casefold()
        self.rows = [row for row in all_rows if query in row["name"].casefold()
                     and (not self.empty_only.isChecked() or row["total_quantity"] == 0)]
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(self.rows))
        for row, data in enumerate(self.rows):
            values = [data["name"], data["component_count"], f"{data['total_quantity']:,}",
                      "有库存" if data["total_quantity"] else "空库位"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if col:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
            self.table.setRowHeight(row, 44)
        if self.rows:
            index = next((i for i, row in enumerate(self.rows) if row["id"] == select_id), 0)
            self.table.selectRow(index)
        self.table.blockSignals(False)
        self.empty_message.setVisible(not self.rows)
        self.empty_message.setText("暂无库位，点击“新增库位”添加存放位置。" if not all_rows else "没有符合条件的库位。")
        empty_count = sum(row["total_quantity"] == 0 for row in all_rows)
        self.summary.setText(f"显示 {len(self.rows)} / {len(all_rows)} 个库位 · 空库位 {empty_count} 个")
        self.update_actions()

    def update_actions(self):
        row = self.selected_location()
        removable = bool(row and row["total_quantity"] == 0)
        self.rename_button.setEnabled(row is not None)
        self.remove_button.setEnabled(removable)
        hint = "选择一个库位，可重命名或删除空库位。"
        if row:
            hint = "此库位为空，可以删除；已有出入库记录仍保留。" if removable else "此库位仍有库存，清空库存后才能删除。"
        self.selection_hint.setText(hint)
        self.remove_button.setToolTip(hint)

    def add(self):
        name, accepted = QInputDialog.getText(self, "新增库位", "库位名称")
        if accepted:
            try:
                location_id = self.db.add_location(name)
                self.changed = True
                self.search.clear()
                self.reload(location_id)
            except Exception as exc:
                error(self, exc)


    def rename(self):
        row = self.selected_location()
        if row is None:
            return
        name, accepted = QInputDialog.getText(self, "重命名库位", "库位名称", text=row["name"])
        if accepted:
            try:
                self.db.rename_location(row["id"], name)
                self.changed = True
                self.search.clear()
                self.reload(row["id"])
            except Exception as exc:
                error(self, exc)

    def remove(self):
        row = self.selected_location()
        if row is None:
            return
        if row["total_quantity"] > 0:
            error(self, ValueError("此库位仍有库存，清空库存后才能删除。"))
            return
        answer = QMessageBox.question(
            self, "删除库位", f"确定删除空库位“{row['name']}”吗？\n\n"
            "删除后不再显示在库位列表和库存操作中，已有出入库记录会保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.remove_location(row["id"])
            self.changed = True
            self.reload()
        except Exception as exc:
            error(self, exc)


class SettingsDialog(QDialog):
    def __init__(self, db: Database, change_directory, open_directory, create_backup,
                 demo=False, directory_override=False, parent=None):
        super().__init__(parent)
        self.db = db
        self.change_directory = change_directory
        self.setWindowTitle("设置 / 数据目录")
        self.resize(700, 500)
        self.setMinimumWidth(580)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(label("设置", "Title"))
        root.addWidget(label("本地数据存储", "Heading"))
        form = QFormLayout()
        form.setVerticalSpacing(14)
        self.current_path = QLineEdit(str(db.directory))
        self.current_path.setReadOnly(True)
        self.current_path.setToolTip(str(db.directory))
        form.addRow("当前目录", self.current_path)
        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.new_path = QLineEdit(str(db.directory))
        self.new_path.setPlaceholderText(r"例如：D:\电子元件数据")
        path_layout.addWidget(self.new_path, 1)
        self.browse_button = button("选择文件夹…", icon_name="folder", callback=self.browse)
        path_layout.addWidget(self.browse_button)
        form.addRow("存储目录", path_row)
        root.addLayout(form)
        description = label("选择一个独立的空文件夹。保存后会复制元件资料、库存记录、照片、PDF 和已有备份，并立即使用新目录。旧目录保留一份原数据。")
        description.setWordWrap(True)
        root.addWidget(description)
        if demo:
            root.addWidget(label("当前是演示模式：目录设置单独保存，不影响个人模式。"))
        if directory_override:
            hint = label("本次启动使用了 --data-dir。设置会用于下次普通启动；再次指定 --data-dir 时，命令行路径优先。")
            hint.setWordWrap(True)
            root.addWidget(hint)
        self.result_label = label("")
        self.result_label.setWordWrap(True)
        root.addWidget(self.result_label)
        actions = QHBoxLayout()
        actions.addWidget(button("打开当前目录", icon_name="folder", callback=open_directory))
        actions.addWidget(button("创建完整备份", icon_name="download", callback=create_backup))
        actions.addStretch()
        root.addLayout(actions)
        root.addStretch()
        footer = QHBoxLayout()
        footer.addWidget(label("目录选择会在下次启动时自动记住。"))
        footer.addStretch()
        self.save_button = button("保存并迁移", "Primary", callback=self.save)
        footer.addWidget(self.save_button)
        footer.addWidget(button("关闭", callback=self.accept))
        root.addLayout(footer)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择数据存储文件夹（空文件夹）", self.new_path.text() or str(self.db.directory))
        if path:
            self.new_path.setText(path)
            self.result_label.clear()

    def save(self):
        try:
            path = self.new_path.text().strip()
            if not path:
                raise ValueError("请选择数据存储文件夹。")
            if not Path(path).expanduser().is_absolute():
                raise ValueError("请输入完整的绝对路径，或点击“选择文件夹”。")
            self.save_button.setEnabled(False)
            changed = self.change_directory(Path(path))
            self.current_path.setText(str(self.db.directory))
            self.current_path.setToolTip(str(self.db.directory))
            self.new_path.setText(str(self.db.directory))
            self.result_label.setText("数据已迁移并保存，正在使用新目录；旧目录保留原数据。" if changed else "存储目录已保存，下次启动将继续使用此目录。")
            self.result_label.setStyleSheet("color: #138E82;")
        except Exception as exc:
            self.result_label.setText("未修改存储目录，请检查后重试。")
            self.result_label.setStyleSheet("color: #B37B27;")
            error(self, exc)
        finally:
            self.save_button.setEnabled(True)
