import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QLabel

from component_desk.database import CATEGORIES, Database, validate_component
from component_desk.dialogs import ComponentDialog
from component_desk.specifications import ADDITIONAL_COMPONENT_SPECS, COMPONENT_SPECS, MODEL_REQUIRED_CATEGORIES, NEW_COMPONENT_SPECS
from component_desk.window import MainWindow


NEW_SAMPLES = {
    "电池管理芯片": ({"model": "TEST-BATTERY", "package": "QFN-24", "battery_function": "充电管理",
                      "battery_chemistry": "锂离子 / 锂聚合物", "series_cells": "1", "supply_voltage": ("3.9", "13.5"),
                      "charge_voltage_v": "4.2", "charge_current_a": "3", "charge_method": "开关降压", "control_interface": "I²C"},
                     {"battery_function": "充电管理", "battery_chemistry": "锂离子 / 锂聚合物", "series_cells": 1,
                      "supply_voltage_min_v": 3.9, "supply_voltage_max_v": 13.5, "charge_voltage_v": 4.2,
                      "charge_current_a": 3, "charge_method": "开关降压", "control_interface": "I²C"}),
    "电感": ({"package": "4040", "inductance_h": "4.7", "inductance_h_unit": "uH", "inductor_type": "功率电感",
               "rated_current_a": "3", "saturation_current_a": "4.5", "dc_resistance_ohm": "30", "dc_resistance_ohm_unit": "mΩ"},
              {"inductance_h": 4.7e-6, "inductor_type": "功率电感", "rated_current_a": 3,
               "saturation_current_a": 4.5, "dc_resistance_ohm": 0.03}),
    "TVS管": ({"model": "TEST-ESD", "package": "SOD-323", "tvs_type": "ESD 防静电", "polarity": "双向",
                "standoff_voltage_v": "3.3", "clamping_voltage_v": "8", "junction_capacitance_pf": "0.22", "channel_count": "1",
                "esd_rating": "IEC 61000-4-2：接触 ±8 kV"},
               {"tvs_type": "ESD 防静电", "polarity": "双向", "standoff_voltage_v": 3.3, "clamping_voltage_v": 8,
                "junction_capacitance_pf": 0.22, "channel_count": 1, "esd_rating": "IEC 61000-4-2：接触 ±8 kV"}),
    "二极管": ({"model": "TEST-DIODE", "package": "SMA", "diode_type": "肖特基", "reverse_voltage_v": "40",
                "forward_current_a": "1", "forward_voltage_v": "0.45", "reverse_leakage_ua": "0"},
               {"diode_type": "肖特基", "reverse_voltage_v": 40, "forward_current_a": 1,
                "forward_voltage_v": 0.45, "reverse_leakage_ua": 0}),
    "晶振": ({"package": "3225", "oscillator_type": "无源晶振", "frequency_hz": "32.768", "frequency_hz_unit": "kHz",
               "frequency_tolerance_ppm": "20", "load_capacitance_pf": "12.5", "esr_ohm": "70000"},
              {"oscillator_type": "无源晶振", "frequency_hz": 32768, "frequency_tolerance_ppm": 20,
               "load_capacitance_pf": 12.5, "esr_ohm": 70000}),
    "MOS管": ({"model": "TEST-PMOS", "package": "SOT-23", "channel_type": "P 沟道", "vds_rating_v": "30",
                "continuous_current_a": "3", "rds_on_mohm": "50", "rds_test_conditions": "VGS=-4.5 V、TJ=25 °C",
                "vgs_limit": "±20 V", "vgs_threshold_v": "-1.2"},
               {"channel_type": "P 沟道", "vds_rating_v": 30, "continuous_current_a": 3, "rds_on_mohm": 50,
                "rds_test_conditions": "VGS=-4.5 V、TJ=25 °C", "vgs_limit": "±20 V", "vgs_threshold_v": -1.2}),
    "共模电感": ({"package": "0805", "choke_type": "信号线", "common_mode_impedance_ohm": "90",
                  "common_mode_impedance_ohm_unit": "Ω", "impedance_frequency_hz": "100", "impedance_frequency_hz_unit": "MHz",
                  "rated_current_a": "0.3", "line_count": "2", "application_interface": "USB"},
                 {"choke_type": "信号线", "common_mode_impedance_ohm": 90, "impedance_frequency_hz": 1e8,
                  "rated_current_a": 0.3, "line_count": 2, "application_interface": "USB"}),
}
NEW_SAMPLES.update({
    "三极管": ({"model": "TEST-PNP", "package": "SOT-23", "transistor_type": "PNP", "vce_rating_v": "45",
                "collector_current_a": "0.5", "dc_gain": "200", "transition_frequency_hz": "100",
                "transition_frequency_hz_unit": "MHz", "pin_assignment": "1=B、2=E、3=C"},
               {"transistor_type": "PNP", "vce_rating_v": 45, "collector_current_a": 0.5, "dc_gain": 200,
                "transition_frequency_hz": 1e8, "pin_assignment": "1=B、2=E、3=C"}),
    "磁珠": ({"package": "0603", "impedance_ohm": "600", "impedance_ohm_unit": "Ω",
               "impedance_frequency_hz": "100", "impedance_frequency_hz_unit": "MHz", "bead_application": "电源滤波",
               "rated_current_a": "1", "dc_resistance_ohm": "100", "dc_resistance_ohm_unit": "mΩ"},
              {"impedance_ohm": 600, "impedance_frequency_hz": 1e8, "bead_application": "电源滤波",
               "rated_current_a": 1, "dc_resistance_ohm": 0.1}),
    "连接器": ({"package": "直插", "connector_type": "排针", "contact_count": "10", "pitch_mm": "2.54",
                "gender": "公头", "mounting": "直插", "row_count": "2"},
               {"connector_type": "排针", "contact_count": 10, "pitch_mm": 2.54, "gender": "公头", "mounting": "直插", "row_count": 2}),
    "运算放大器": ({"model": "TEST-OPAMP", "package": "SOIC-8", "channel_count": "2", "amplifier_type": "低功耗",
                    "supply_voltage": ("1.8", "5.5"), "gain_bandwidth_hz": "1", "gain_bandwidth_hz_unit": "MHz",
                    "offset_voltage_uv": "0", "input_bias_na": "0.005", "rail_to_rail": "输入和输出"},
                   {"channel_count": 2, "amplifier_type": "低功耗", "supply_voltage_min_v": 1.8, "supply_voltage_max_v": 5.5,
                    "gain_bandwidth_hz": 1e6, "offset_voltage_uv": 0, "input_bias_na": 0.005, "rail_to_rail": "输入和输出"}),
    "逻辑芯片": ({"model": "TEST-LOGIC", "package": "SOT-23-5", "logic_function": "缓冲器", "logic_family": "LVC",
                  "channel_count": "1", "supply_voltage": ("1.65", "5.5"), "propagation_delay_ns": "3", "output_structure": "三态"},
                 {"logic_function": "缓冲器", "logic_family": "LVC", "channel_count": 1, "supply_voltage_min_v": 1.65,
                  "supply_voltage_max_v": 5.5, "propagation_delay_ns": 3, "output_structure": "三态"}),
    "存储芯片": ({"model": "TEST-EEPROM", "package": "SOIC-8", "memory_type": "EEPROM", "capacity_bits": "64",
                  "capacity_bits_unit": "Kbit", "memory_interface": "I²C", "supply_voltage": ("1.8", "5.5"),
                  "write_endurance": "1000000", "retention_years": "100", "organization": "8K × 8 bit"},
                 {"memory_type": "EEPROM", "capacity_bits": 65536, "memory_interface": "I²C", "supply_voltage_min_v": 1.8,
                  "supply_voltage_max_v": 5.5, "write_endurance": 1000000, "retention_years": 100, "organization": "8K × 8 bit"}),
})


def fill_sample(dialog, category):
    dialog.category.setCurrentText(category)
    fields = dialog.spec_widgets[category]
    for key, value in NEW_SAMPLES[category][0].items():
        widget = fields[key]
        if isinstance(widget, tuple):
            for endpoint, text in zip(widget, value):
                endpoint.setText(text)
        elif hasattr(widget, "setCurrentText"):
            widget.setCurrentText(value)
        else:
            widget.setText(value)
    return fields


class NewComponentFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "data")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_all_eighteen_categories_save_edit_filter_restart_csv_and_backup(self):
        self.assertEqual(CATEGORIES[5:], tuple(NEW_SAMPLES))
        self.assertEqual(len(CATEGORIES), 18)
        location = self.db.add_location("新元件盒")
        saved = {}
        for category, (_, expected) in NEW_SAMPLES.items():
            with self.subTest(category=category):
                dialog = ComponentDialog(self.db)
                fill_sample(dialog, category)
                dialog.save()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                component_id = dialog.saved_id
                self.db.change_stock(component_id, location, "入库", 7)
                before = self.db.get_component(component_id)
                self.assertEqual(before["parameters"], expected)
                self.assertNotEqual(before["summary"], "—")
                history = self.db.history(component_id)
                edit = ComponentDialog(self.db, before)
                edit.manufacturer.setText("测试厂家")
                edit.save()
                self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
                after = self.db.get_component(component_id)
                self.assertEqual(after["parameters"], expected)
                self.assertEqual(after["stocks"], before["stocks"])
                self.assertEqual(self.db.history(component_id), history)
                self.assertEqual(self.db.list_components(category=category)[0]["id"], component_id)
                saved[component_id] = after
        self.db.close()
        self.db = Database(self.root / "data")
        csv_file = self.root / "new-categories.csv"
        self.db.export_csv(csv_file)
        imported = Database(self.root / "imported")
        try:
            self.assertEqual(imported.import_csv(csv_file), len(NEW_SAMPLES))
            for component_id, before in saved.items():
                self.assertEqual(self.db.get_component(component_id), before)
                self.assertEqual(imported.get_component(component_id)["parameters"], before["parameters"])
                self.assertEqual(imported.get_component(component_id)["total_quantity"], 7)
        finally:
            imported.close()
        history = self.db.history()
        backup = self.root / "new-categories.zip"
        self.db.backup(backup)
        for component_id in saved:
            self.db.remove_component(component_id)
        self.db.restore(backup)
        self.assertEqual(self.db.history(), history)
        for component_id, before in saved.items():
            self.assertEqual(self.db.get_component(component_id), before)

    def test_required_fields_and_invalid_values_never_save(self):
        for category in NEW_SAMPLES:
            required = ["package", *(["model"] if category in MODEL_REQUIRED_CATEGORIES else []),
                        *(field.key for field in COMPONENT_SPECS[category] if field.required)]
            for key in required:
                with self.subTest(category=category, key=key):
                    dialog = ComponentDialog(self.db)
                    fields = fill_sample(dialog, category)
                    widget = fields[key]
                    if hasattr(widget, "setCurrentIndex"):
                        widget.setCurrentIndex(-1)
                        if widget.isEditable():
                            widget.setEditText("")
                    else:
                        widget.clear()
                    with patch("component_desk.dialogs.error") as show_error:
                        dialog.save()
                        show_error.assert_called_once()
                    self.assertIsNone(dialog.saved_id)
            params = NEW_SAMPLES[category][1]
            data = {"name": "TEST", "model": "TEST", "package": "TEST", "category": category}
            for field in NEW_COMPONENT_SPECS[category]:
                if field.required:
                    with self.subTest(category=category, missing=field.key), self.assertRaises(ValueError):
                        validate_component({**data, "parameters": {key: value for key, value in params.items() if key != field.key}})
            for key, value in params.items():
                if not isinstance(value, (int, float)) or key == "vgs_threshold_v":
                    continue
                with self.subTest(category=category, invalid=key), self.assertRaises(ValueError):
                    validate_component({**data, "parameters": {**params, key: float("nan")}})
        self.assertEqual(self.db.statistics()["count"], 0)

    def test_units_require_both_inputs_and_reject_unknown_overflow_underflow(self):
        for category, key in (("电感", "inductance_h"), ("晶振", "frequency_hz"), ("共模电感", "impedance_frequency_hz")):
            for number, unit in (("", "MHz"), ("1", ""), ("1", "rpm"), ("0", "Hz"), ("1e308", "GHz"), ("5e-324", "nH")):
                with self.subTest(category=category, number=number, unit=unit):
                    dialog = ComponentDialog(self.db)
                    fields = fill_sample(dialog, category)
                    fields[key].setText(number)
                    fields[key + "_unit"].setText(unit)
                    with self.assertRaises(ValueError):
                        dialog.component_data()
        for unit in ("uH", "µH", "μH"):
            dialog = ComponentDialog(self.db)
            fields = fill_sample(dialog, "电感")
            fields["inductance_h_unit"].setText(unit)
            self.assertEqual(dialog.component_data()["parameters"]["inductance_h"], 4.7e-6)

    def test_conditional_battery_crystal_and_diode_fields_keep_drafts_exclude_hidden(self):
        cases = [("电池管理芯片", "battery_function", "电池保护", "charge_current_a", "overcharge_voltage_v", "4.3", "充电管理"),
                 ("晶振", "oscillator_type", "有源晶振", "load_capacitance_pf", "output_signal", "LVCMOS", "无源晶振"),
                 ("二极管", "diode_type", "稳压", None, "zener_voltage_v", "5.1", "肖特基")]
        for category, selector, changed, hidden, shown, value, original in cases:
            with self.subTest(category=category):
                dialog = ComponentDialog(self.db)
                fields = fill_sample(dialog, category)
                fields[selector].setCurrentText(changed)
                if hidden:
                    self.assertFalse(fields[hidden].isEnabled())
                    fields[hidden].setText("invalid hidden draft")
                self.assertTrue(fields[shown].isEnabled())
                if hasattr(fields[shown], "setCurrentText"):
                    fields[shown].setCurrentText(value)
                else:
                    fields[shown].setText(value)
                params = dialog.component_data()["parameters"]
                self.assertIn(shown, params)
                if hidden:
                    self.assertNotIn(hidden, params)
                    fields[hidden].setText(str(NEW_SAMPLES[category][1][hidden]))
                fields[selector].setCurrentText(original)
                self.assertFalse(fields[shown].isEnabled())
                self.assertNotIn(shown, dialog.component_data()["parameters"])
                fields[selector].setCurrentText(changed)
                self.assertIn(shown, dialog.component_data()["parameters"])

    def test_new_category_switch_preserves_stock_and_detail_units(self):
        dialog = ComponentDialog(self.db)
        fill_sample(dialog, "电感")
        dialog.save()
        component_id = dialog.saved_id
        self.db.change_stock(component_id, self.db.add_location("元件盒"), "入库", 4)
        history = self.db.history(component_id)
        window = MainWindow(self.db)
        try:
            window.refresh(component_id)
            texts = [label.text() for label in window.findChildren(QLabel)]
            self.assertIn("4.7 µH", texts)
            self.assertIn("30 mΩ", texts)
            edit = ComponentDialog(self.db, self.db.get_component(component_id))
            fill_sample(edit, "MOS管")
            edit.save()
            self.assertEqual(self.db.get_component(component_id)["parameters"], NEW_SAMPLES["MOS管"][1])
            self.assertEqual(self.db.get_component(component_id)["total_quantity"], 4)
            self.assertEqual([{key: value for key, value in row.items() if key not in {"name", "model"}}
                              for row in self.db.history(component_id)],
                             [{key: value for key, value in row.items() if key not in {"name", "model"}} for row in history])
            window.refresh(component_id)
            window.category_filter.setCurrentIndex(window.category_filter.findData("MOS管"))
            self.assertEqual(window.table.rowCount(), 1)
            self.assertIn("-1.2 V", [label.text() for label in window.findChildren(QLabel)])
        finally:
            window.close()

    def test_memory_capacity_bits_and_bytes_convert_to_integer_bits(self):
        cases = [("64", "Kbit", 65536), ("8", "KB", 65536), ("8", "KiB", 65536),
                 ("1", "MB", 8388608), ("1", "Mbit", 1048576), ("0.5", "KB", 4096)]
        for number, unit, bits in cases:
            with self.subTest(number=number, unit=unit):
                dialog = ComponentDialog(self.db)
                fields = fill_sample(dialog, "存储芯片")
                fields["capacity_bits"].setText(number)
                fields["capacity_bits_unit"].setText(unit)
                dialog.save()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                component = self.db.get_component(dialog.saved_id)
                self.assertEqual(component["parameters"]["capacity_bits"], bits)
                edit = ComponentDialog(self.db, component)
                self.assertEqual(edit.component_data()["parameters"]["capacity_bits"], bits)
        for number, unit in (("0.5", "bit"), ("1", "kb"), ("1", ""), ("nan", "KB"), ("0", "bit")):
            dialog = ComponentDialog(self.db)
            fields = fill_sample(dialog, "存储芯片")
            fields["capacity_bits"].setText(number)
            fields["capacity_bits_unit"].setText(unit)
            with self.assertRaises(ValueError):
                dialog.component_data()
        data = {"name": "TEST", "model": "TEST", "package": "SOIC-8", "category": "存储芯片"}
        with self.assertRaises(ValueError):
            validate_component({**data, "parameters": {"memory_type": "SRAM", "capacity_bits": 0.5}})

    def test_memory_and_logic_type_switch_excludes_hidden_fields(self):
        dialog = ComponentDialog(self.db)
        fields = fill_sample(dialog, "存储芯片")
        fields["memory_type"].setCurrentText("SRAM")
        self.assertFalse(fields["write_endurance"].isEnabled())
        self.assertFalse(fields["retention_years"].isEnabled())
        self.assertNotIn("write_endurance", dialog.component_data()["parameters"])
        fields["memory_type"].setCurrentText("EEPROM")
        self.assertEqual(fields["write_endurance"].text(), "1000000")
        self.assertEqual(dialog.component_data()["parameters"]["write_endurance"], 1000000)
        fields = fill_sample(dialog, "逻辑芯片")
        fields["logic_function"].setCurrentText("电平转换")
        for key, limits in (("supply_a", ("1.2", "1.8")), ("supply_b", ("3", "3.6"))):
            self.assertTrue(fields[key][0].isEnabled())
            for endpoint, value in zip(fields[key], limits):
                endpoint.setText(value)
        params = dialog.component_data()["parameters"]
        self.assertEqual(params["supply_a_min_v"], 1.2)
        self.assertEqual(params["supply_b_max_v"], 3.6)
        fields["logic_function"].setCurrentText("缓冲器")
        self.assertFalse(fields["supply_a"][0].isEnabled())
        self.assertNotIn("supply_a_min_v", dialog.component_data()["parameters"])

    def test_additional_categories_reject_invalid_counts_and_ranges(self):
        cases = [("连接器", "contact_count", "1.5"), ("连接器", "row_count", "0"),
                 ("运算放大器", "channel_count", "1.5"), ("三极管", "vce_rating_v", "-45"),
                 ("逻辑芯片", "channel_count", "-1"), ("磁珠", "rated_current_a", "0")]
        for category, key, value in cases:
            with self.subTest(category=category, key=key):
                dialog = ComponentDialog(self.db)
                fields = fill_sample(dialog, category)
                fields[key].setText(value)
                with patch("component_desk.dialogs.error") as show_error:
                    dialog.save()
                    show_error.assert_called_once()
                self.assertIsNone(dialog.saved_id)
        self.assertEqual(self.db.statistics()["count"], 0)
        for category in ("运算放大器", "逻辑芯片", "存储芯片"):
            dialog = ComponentDialog(self.db)
            fields = fill_sample(dialog, category)
            fields["supply_voltage"][1].clear()
            with self.assertRaises(ValueError):
                dialog.component_data()


if __name__ == "__main__":
    unittest.main()
