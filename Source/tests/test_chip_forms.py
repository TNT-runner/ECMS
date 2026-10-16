import os
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from component_desk.database import CATEGORIES, Database, validate_component
from component_desk.dialogs import ComponentDialog
from component_desk.specifications import CHIP_SPECS


DCDC_PARAMETERS = {"power_type": "DCDC", "input_voltage_min_v": 4.5, "input_voltage_max_v": 36,
                   "output_voltage_min_v": 1.2, "output_voltage_max_v": 12,
                   "output_current_a": 3, "switching_frequency_khz": 500}
TRANSCEIVER_PARAMETERS = {"protocol": "RS-485", "data_rate_mbps": 0.5, "channel_count": 1,
                          "supply_voltage_min_v": 3, "supply_voltage_max_v": 3.6, "logic_voltage_v": 3.3}


class ChipFormTests(unittest.TestCase):
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

    def form(self, category="电源管理芯片", power_type="DCDC"):
        dialog = ComponentDialog(self.db)
        dialog.category.setCurrentText(category)
        fields = dialog.spec_widgets[category]
        fields["model"].setText("TEST-CHIP")
        fields["package"].setCurrentText("SOIC-8")
        if category != "主控芯片":
            key, value = {"电源管理芯片": ("power_type", power_type),
                          "协议收发芯片": ("protocol", "RS-485")}[category]
            fields[key].setCurrentText(value)
        if category == "电源管理芯片" and power_type == "DCDC":
            for key, values in (("input_voltage", ("4.5", "36")), ("output_voltage", ("1.2", "12"))):
                for endpoint, value in zip(fields[key], values):
                    endpoint.setText(value)
            fields["output_current_a"].setText("3")
            fields["switching_frequency_khz"].setText("500")
            fields["switching_frequency_unit"].setText("kHz")
        elif category == "电源管理芯片" and power_type == "LDO":
            fields["ldo_output_mode"].setCurrentText("可调输出")
            fields["output_voltage"][0].setText("1.2")
            fields["output_voltage"][1].setText("12")
        elif category == "协议收发芯片":
            fields["data_rate_mbps"].setText("0.5")
            fields["channel_count"].setText("1")
            fields["supply_voltage"][0].setText("3")
            fields["supply_voltage"][1].setText("3.6")
            fields["logic_voltage_v"].setText("3.3")
        return dialog, fields

    def test_original_categories_and_minimal_chip_records(self):
        self.assertEqual(CATEGORIES[:5], ("贴片电容", "贴片电阻", "主控芯片", "电源管理芯片", "协议收发芯片"))
        for category, expected in [("主控芯片", {}), ("电源管理芯片", DCDC_PARAMETERS),
                                   ("协议收发芯片", TRANSCEIVER_PARAMETERS)]:
            with self.subTest(category=category):
                dialog, _ = self.form(category)
                dialog.save()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                component = self.db.get_component(dialog.saved_id)
                self.assertEqual(component["parameters"], expected)
                self.assertEqual(component["name"], "TEST-CHIP")
                self.assertEqual(component["total_quantity"], 0)
                self.assertEqual(len(self.db.list_components(category=category)), 1)

    def test_controller_and_transceiver_values_survive_edit_and_restart(self):
        for category in ("主控芯片", "协议收发芯片"):
            dialog, fields = self.form(category)
            if category == "主控芯片":
                expected = {"clock_mhz": 168, "flash_kb": 512, "ram_kb": 128, "pin_count": 64}
                fields["core_architecture"].setText("Cortex-M4")
            else:
                expected = {"data_rate_mbps": 0.5, "channel_count": 1, "logic_voltage_v": 3.3}
                fields["isolation"].setCurrentText("隔离")
            for key, value in expected.items():
                fields[key].setText(str(value))
            fields["supply_voltage"][0].setText("3")
            fields["supply_voltage"][1].setText("3.6")
            dialog.save()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            component_id = dialog.saved_id
            location = self.db.add_location(category + "盒")
            self.db.change_stock(component_id, location, "入库", 12)
            before = self.db.get_component(component_id)
            history = self.db.history(component_id)
            edit = ComponentDialog(self.db, before)
            edit.manufacturer.setText("测试厂家")
            edit.save()
            self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
            self.db.close()
            self.db = Database(self.root / "data")
            after = self.db.get_component(component_id)
            self.assertEqual(after["parameters"], before["parameters"])
            for key, value in expected.items():
                self.assertEqual(after["parameters"][key], value)
            self.assertEqual(after["stocks"], before["stocks"])
            self.assertEqual(self.db.history(component_id), history)

    def test_removed_controller_fields_do_not_return_from_existing_records(self):
        dialog, fields = self.form("主控芯片")
        fields["clock_mhz"].setText("168")
        dialog.save()
        component_id = dialog.saved_id
        location = self.db.add_location("主控盒")
        self.db.change_stock(component_id, location, "入库", 5)
        with self.db.connection:
            self.db.connection.execute("UPDATE components SET parameters_json=? WHERE id=?",
                                       (json.dumps({"clock_mhz": 168, "controller_type": "MCU", "interfaces": "UART", "custom": "keep"}), component_id))
        component = self.db.get_component(component_id)
        self.assertEqual(component["parameters"], {"clock_mhz": 168, "custom": "keep"})
        self.assertNotIn("MCU", component["summary"])
        edit = ComponentDialog(self.db, component)
        edit.save()
        self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
        updated = self.db.get_component(component_id)
        self.assertEqual(updated["parameters"], component["parameters"])
        self.assertEqual(updated["stocks"], component["stocks"])
        csv_file = self.root / "controllers.csv"
        self.db.export_csv(csv_file)
        with csv_file.open(encoding="utf-8-sig", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(json.loads(row["parameters_json"]), component["parameters"])

    def test_ldo_frequency_is_inapplicable_and_negative_ranges_are_supported(self):
        dialog, fields = self.form()
        fields["switching_frequency_khz"].setText("500")
        fields["switching_frequency_unit"].setText("kHz")
        fields["power_type"].setCurrentText("LDO")
        fields["ldo_output_mode"].setCurrentText("固定输出")
        self.assertFalse(fields["switching_frequency_khz"].isEnabled())
        self.assertFalse(fields["switching_frequency_unit"].isEnabled())
        self.assertTrue(fields["dropout_voltage_mv"].isEnabled())
        for key, low, high in [("input_voltage", "-10", "-3")]:
            fields[key][0].setText(low)
            fields[key][1].setText(high)
        fields["output_voltage_v"].setText("-2.5")
        fields["dropout_voltage_mv"].setText("200")
        fields["quiescent_current_ua"].setText("50")
        fields["output_current_a"].setText("0.3")
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        component = self.db.get_component(dialog.saved_id)
        self.assertEqual(component["parameters"]["input_voltage_min_v"], -10)
        self.assertEqual(component["parameters"]["output_voltage_v"], -2.5)
        self.assertIn("-2.5 V", component["summary"])
        self.assertNotIn("output_voltage_min_v", component["parameters"])
        self.assertNotIn("switching_frequency_khz", component["parameters"])
        self.assertNotIn("topology", component["parameters"])
        edit = ComponentDialog(self.db, component)
        fields = edit.spec_widgets["电源管理芯片"]
        fields["power_type"].setCurrentText("DCDC")
        fields["output_voltage"][0].setText("1.2")
        fields["output_voltage"][1].setText("12")
        fields["switching_frequency_khz"].setText("1000")
        fields["switching_frequency_unit"].setText("kHz")
        edit.save()
        updated = self.db.get_component(dialog.saved_id)
        self.assertNotIn("dropout_voltage_mv", updated["parameters"])
        self.assertNotIn("output_voltage_v", updated["parameters"])
        self.assertEqual(updated["parameters"]["switching_frequency_khz"], 1000)

    def test_power_type_selection_controls_complete_rows_and_retains_drafts(self):
        dialog = ComponentDialog(self.db)
        dialog.category.setCurrentText("电源管理芯片")
        fields = dialog.spec_widgets["电源管理芯片"]
        self.assertNotIn("topology", fields)
        self.assertNotIn("output_mode", fields)
        self.assertIn("ldo_output_mode", fields)
        selector = fields["power_type"]
        self.assertFalse(selector.isEditable())
        self.assertEqual([selector.itemText(i) for i in range(selector.count()) if selector.itemText(i)], ["DCDC", "LDO", "PMU"])
        self.assertEqual(selector.currentText(), "")
        for field in CHIP_SPECS["电源管理芯片"]:
            widget = fields[field.key]
            row = widget[0].parentWidget() if isinstance(widget, tuple) else widget
            if field.kind == "frequency":
                row = widget.parentWidget()
            self.assertEqual(dialog.power_form.isRowVisible(row), field.key == "power_type")
        pmu_fields = {"pmu_dcdc_count", "pmu_ldo_count", "pmu_outputs", "pmu_control_interface", "pmu_sequence",
                      "pmu_charger", "pmu_battery_spec", "pmu_charge_voltage_v", "pmu_charge_current_a",
                      "pmu_power_path", "pmu_protection", "pmu_other_functions", "pin_count"}
        for power_type, hidden in [("DCDC", pmu_fields | {"dropout_voltage_mv", "ldo_output_mode", "output_voltage_v"}),
                                   ("LDO", pmu_fields | {"switching_frequency_khz", "output_voltage", "output_voltage_v"}),
                                   ("PMU", {"output_voltage", "output_current_a", "switching_frequency_khz", "dropout_voltage_mv",
                                            "ldo_output_mode", "output_voltage_v", "pmu_battery_spec", "pmu_charge_voltage_v", "pmu_charge_current_a"})]:
            selector.setCurrentText(power_type)
            for field in CHIP_SPECS["电源管理芯片"]:
                widget = fields[field.key]
                row = widget[0].parentWidget() if isinstance(widget, tuple) else widget
                if field.kind == "frequency":
                    row = widget.parentWidget()
                self.assertEqual(dialog.power_form.isRowVisible(row), field.key not in hidden)
                self.assertEqual(row.isEnabled(), field.key not in hidden)
        selector.setCurrentText("DCDC")
        fields["output_voltage"][0].setText("1.2")
        fields["output_voltage"][1].setText("12")
        fields["switching_frequency_khz"].setText("500")
        selector.setCurrentText("LDO")
        fields["ldo_output_mode"].setCurrentText("固定输出")
        fields["output_voltage_v"].setText("3.3")
        fields["dropout_voltage_mv"].setText("200")
        selector.setCurrentText("DCDC")
        self.assertEqual(fields["switching_frequency_khz"].text(), "500")
        selector.setCurrentText("LDO")
        self.assertEqual(fields["output_voltage_v"].text(), "3.3")
        fields["model"].setText("TEST-LDO")
        fields["package"].setCurrentText("SOT-223")
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        params = self.db.get_component(dialog.saved_id)["parameters"]
        self.assertEqual(params, {"power_type": "LDO", "ldo_output_mode": "固定输出", "output_voltage_v": 3.3, "dropout_voltage_mv": 200})
        edit = ComponentDialog(self.db, self.db.get_component(dialog.saved_id))
        self.assertEqual(edit.spec_widgets["电源管理芯片"]["output_voltage_v"].text(), "3.3")
        self.assertTrue(edit.power_form.isRowVisible(edit.spec_widgets["电源管理芯片"]["dropout_voltage_mv"]))

    def test_power_validation_normalizes_legacy_types_and_excludes_inapplicable_values(self):
        data = {"name": "TEST", "model": "TEST", "package": "SOIC-8", "category": "电源管理芯片"}
        for alias in ("DC/DC", "DC-DC", "dcdc"):
            params = validate_component({**data, "parameters": {**DCDC_PARAMETERS, "power_type": alias, "dropout_voltage_mv": "invalid"}})["parameters"]
            self.assertEqual(params, DCDC_PARAMETERS)
        for alias in ("PMIC", "pmu"):
            params = validate_component({**data, "parameters": {"power_type": alias, "output_current_a": "invalid"}})["parameters"]
            self.assertEqual(params, {"power_type": "PMU"})
        for invalid in ("", "负载开关", "充电管理"):
            with self.assertRaises(ValueError):
                validate_component({**data, "parameters": {"power_type": invalid}})
        params = validate_component({**data, "parameters": {"power_type": "LDO", "ldo_output_mode": "可调输出", "output_voltage_min_v": 3.3,
                                   "output_voltage_max_v": 3.3, "switching_frequency_khz": "invalid"}})["parameters"]
        self.assertEqual(params, {"power_type": "LDO", "ldo_output_mode": "可调输出", "output_voltage_min_v": 3.3, "output_voltage_max_v": 3.3})
        component_id = self.db.save_component({**data, "parameters": DCDC_PARAMETERS})
        with self.db.connection:
            self.db.connection.execute("UPDATE components SET parameters_json=? WHERE id=?",
                                       (json.dumps({**DCDC_PARAMETERS, "power_type": "DC/DC", "topology": "降压 Buck", "custom": "keep"}), component_id))
        edit = ComponentDialog(self.db, self.db.get_component(component_id))
        self.assertEqual(edit.spec_widgets["电源管理芯片"]["power_type"].currentText(), "DCDC")
        edit.save()
        self.assertEqual(self.db.get_component(component_id)["parameters"],
                         {**DCDC_PARAMETERS, "custom": "keep"})

    def test_pmu_optional_parameters_and_zero_channel_counts(self):
        for counts in ({}, {"pmu_dcdc_count": 4, "pmu_ldo_count": 0}):
            with self.subTest(counts=counts):
                dialog, fields = self.form(power_type="PMU")
                fields["power_type"].setCurrentText("PMU")
                for key, value in counts.items():
                    fields[key].setText(str(value))
                dialog.save()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                self.assertEqual(self.db.get_component(dialog.saved_id)["parameters"], {"power_type": "PMU", **counts})

    def test_pmu_multi_output_parameters_survive_edit_restart_csv_backup_and_type_switch(self):
        dialog, fields = self.form(power_type="PMU")
        fields["power_type"].setCurrentText("PMU")
        expected = {"power_type": "PMU", "pmu_dcdc_count": 3, "pmu_ldo_count": 2,
                    "pmu_outputs": "DCDC1：0.9～1.8 V，1.5 A\nLDO1：3.3 V，0.2 A",
                    "pmu_control_interface": "I²C", "pmu_sequence": "可编程时序", "pmu_charger": "支持",
                    "pmu_battery_spec": "单节锂离子 / 锂聚合物电池", "pmu_charge_voltage_v": 4.2,
                    "pmu_charge_current_a": 1.5, "pmu_power_path": "支持", "pmu_protection": "欠压、过流、过温",
                    "pmu_other_functions": "ADC、LED 驱动", "quiescent_current_ua": 80, "pin_count": 48}
        for key, value in expected.items():
            widget = fields[key]
            if hasattr(widget, "setCurrentText"):
                widget.setCurrentText(str(value))
            elif hasattr(widget, "setPlainText"):
                widget.setPlainText(value)
            else:
                widget.setText(str(value))
        fields["input_voltage"][0].setText("2.8")
        fields["input_voltage"][1].setText("6.3")
        expected.update(input_voltage_min_v=2.8, input_voltage_max_v=6.3)
        fields["output_voltage"][0].setText("invalid hidden draft")
        fields["switching_frequency_khz"].setText("invalid hidden draft")
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        component_id = dialog.saved_id
        location = self.db.add_location("PMU 盒")
        self.db.change_stock(component_id, location, "入库", 9)
        component = self.db.get_component(component_id)
        history = self.db.history(component_id)
        self.assertEqual(component["parameters"], expected)
        self.assertIn("3 路 DCDC", component["summary"])
        self.assertIn("2 路 LDO", component["summary"])
        edit = ComponentDialog(self.db, component)
        self.assertEqual(edit.spec_widgets["电源管理芯片"]["pmu_outputs"].toPlainText(), expected["pmu_outputs"])
        edit.manufacturer.setText("测试厂家")
        edit.save()
        self.db.close()
        self.db = Database(self.root / "data")
        component = self.db.get_component(component_id)
        self.assertEqual(component["parameters"], expected)
        csv_file = self.root / "pmu.csv"
        self.db.export_csv(csv_file)
        imported = Database(self.root / "imported")
        try:
            self.assertEqual(imported.import_csv(csv_file), 1)
            self.assertEqual(imported.get_component(component_id)["parameters"], expected)
        finally:
            imported.close()
        backup = self.root / "pmu.zip"
        self.db.backup(backup)
        self.db.remove_component(component_id)
        self.db.restore(backup)
        self.assertEqual(self.db.get_component(component_id), component)
        edit = ComponentDialog(self.db, component)
        fields = edit.spec_widgets["电源管理芯片"]
        fields["power_type"].setCurrentText("DCDC")
        fields["output_current_a"].setText("3")
        for endpoint in fields["output_voltage"]:
            endpoint.setText("5")
        fields["switching_frequency_khz"].setText("500")
        fields["switching_frequency_unit"].setText("kHz")
        edit.save()
        self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
        updated = self.db.get_component(component_id)
        self.assertFalse(any(key.startswith("pmu_") for key in updated["parameters"]))
        self.assertNotIn("pin_count", updated["parameters"])
        self.assertEqual(updated["stocks"], component["stocks"])
        self.assertEqual(self.db.history(component_id), history)

    def test_pmu_charger_support_controls_battery_fields_and_saved_parameters(self):
        dialog, fields = self.form(power_type="PMU")
        fields["power_type"].setCurrentText("PMU")
        self.assertFalse(fields["pmu_charger"].isEditable())
        fields["pmu_charger"].setCurrentText("支持")
        fields["pmu_battery_spec"].setText("单节锂电池")
        fields["pmu_charge_voltage_v"].setText("4.2")
        fields["pmu_charge_current_a"].setText("0.7")
        dialog.save()
        edit = ComponentDialog(self.db, self.db.get_component(dialog.saved_id))
        fields = edit.spec_widgets["电源管理芯片"]
        fields["pmu_charger"].setCurrentText("不支持")
        for key in ("pmu_battery_spec", "pmu_charge_voltage_v", "pmu_charge_current_a"):
            self.assertFalse(edit.power_form.isRowVisible(fields[key]))
            self.assertFalse(fields[key].isEnabled())
        fields["pmu_charger"].setCurrentText("支持")
        self.assertEqual(fields["pmu_charge_voltage_v"].text(), "4.2")
        fields["pmu_charger"].setCurrentText("不支持")
        fields["pmu_charge_current_a"].setText("invalid hidden draft")
        edit.save()
        self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.db.get_component(dialog.saved_id)["parameters"], {"power_type": "PMU", "pmu_charger": "不支持"})
        data = {"name": "TEST", "model": "TEST", "package": "QFN-48", "category": "电源管理芯片"}
        params = validate_component({**data, "parameters": {"power_type": "PMU", "pmu_charger": "不支持",
                                   "pmu_charge_current_a": "invalid", "output_voltage_min_v": "invalid"}})["parameters"]
        self.assertEqual(params, {"power_type": "PMU", "pmu_charger": "不支持"})

    def test_invalid_pmu_channel_counts_and_charge_values_never_save(self):
        for key, text in [("pmu_dcdc_count", "-1"), ("pmu_ldo_count", "1.5"), ("pmu_dcdc_count", "nan"),
                          ("pmu_charge_voltage_v", "-4.2"), ("pmu_charge_current_a", "0"), ("pmu_charge_current_a", "inf")]:
            with self.subTest(key=key, text=text):
                dialog, fields = self.form()
                fields["power_type"].setCurrentText("PMU")
                fields["pmu_charger"].setCurrentText("支持")
                fields[key].setText(text)
                with patch("component_desk.dialogs.error") as show_error:
                    dialog.save()
                    show_error.assert_called_once()
                self.assertIsNone(dialog.saved_id)
                self.assertEqual(self.db.statistics()["count"], 0)

    def test_frequency_manual_units_are_converted_and_survive_edit_and_restart(self):
        empty = ComponentDialog(self.db)
        self.assertEqual(empty.spec_widgets["电源管理芯片"]["switching_frequency_unit"].text(), "")
        for value, unit, expected in [("500000", "Hz", 500), ("500", "kHz", 500),
                                       ("1.5", "MHz", 1500), ("0.001", "GHz", 1000),
                                       (" 2 ", " mhz ", 2000)]:
            with self.subTest(value=value, unit=unit):
                dialog, fields = self.form()
                fields["switching_frequency_khz"].setText(value)
                fields["switching_frequency_unit"].setText(unit)
                dialog.save()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                component_id = dialog.saved_id
                self.db.close()
                self.db = Database(self.root / "data")
                component = self.db.get_component(component_id)
                self.assertEqual(component["parameters"]["switching_frequency_khz"], expected)
                edit = ComponentDialog(self.db, component)
                self.assertEqual(edit.component_data()["parameters"], component["parameters"])
                edit.save()
                self.assertEqual(self.db.get_component(component_id)["parameters"], component["parameters"])

    def test_invalid_or_incomplete_frequency_and_unit_never_save(self):
        for value, unit in [("500", ""), ("", "kHz"), ("500", "rpm"), ("500", "mHz"),
                            ("0", "MHz"), ("-1", "kHz"), ("nan", "Hz"), ("inf", "MHz"),
                            ("1e308", "GHz"), ("5e-324", "Hz")]:
            with self.subTest(value=value, unit=unit):
                dialog, fields = self.form()
                fields["switching_frequency_khz"].setText(value)
                fields["switching_frequency_unit"].setText(unit)
                with patch("component_desk.dialogs.error") as show_error:
                    dialog.save()
                    show_error.assert_called_once()
                self.assertIsNone(dialog.saved_id)
                self.assertEqual(self.db.statistics()["count"], 0)

    def test_dcdc_required_specs_block_ui_database_and_csv_saves(self):
        dialog, fields = self.form()
        for key in ("input_voltage", "output_voltage", "output_current_a", "switching_frequency_khz"):
            widget = fields[key]
            row = widget[0].parentWidget() if isinstance(widget, tuple) else widget.parentWidget() if key == "switching_frequency_khz" else widget
            self.assertTrue(dialog.power_form.labelForField(row).text().endswith(" *"))
        for key, value in [("input_voltage", ("", "")), ("output_voltage", ("", "")),
                           ("output_current_a", ""), ("switching_frequency_khz", ""), ("switching_frequency_unit", "")]:
            with self.subTest(key=key):
                dialog, fields = self.form()
                if isinstance(value, tuple):
                    for endpoint, text in zip(fields[key], value):
                        endpoint.setText(text)
                else:
                    fields[key].setText(value)
                with patch("component_desk.dialogs.error") as show_error:
                    dialog.save()
                    show_error.assert_called_once()
                self.assertIsNone(dialog.saved_id)
                self.assertEqual(self.db.statistics()["count"], 0)
        data = {"name": "TEST", "model": "TEST", "package": "SOIC-8", "category": "电源管理芯片"}
        for key in DCDC_PARAMETERS.keys() - {"power_type"}:
            params = {name: value for name, value in DCDC_PARAMETERS.items() if name != key}
            with self.subTest(missing=key), self.assertRaises(ValueError):
                self.db.save_component({**data, "parameters": params})
        component_id = self.db.save_component({**data, "parameters": DCDC_PARAMETERS})
        edit = ComponentDialog(self.db, self.db.get_component(component_id))
        edit.spec_widgets["电源管理芯片"]["output_current_a"].clear()
        with patch("component_desk.dialogs.error") as show_error:
            edit.save()
            show_error.assert_called_once()
        self.assertEqual(self.db.get_component(component_id)["parameters"], DCDC_PARAMETERS)
        csv_file = self.root / "missing-frequency.csv"
        self.db.export_csv(csv_file)
        with csv_file.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            names, rows = reader.fieldnames, list(reader)
        params = dict(DCDC_PARAMETERS)
        params.pop("switching_frequency_khz")
        rows[0]["parameters_json"] = json.dumps(params)
        with csv_file.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=names)
            writer.writeheader()
            writer.writerows(rows)
        imported = Database(self.root / "imported")
        try:
            with self.assertRaises(ValueError):
                imported.import_csv(csv_file)
            self.assertEqual(imported.statistics()["count"], 0)
        finally:
            imported.close()

    def test_transceiver_required_specs_block_ui_database_and_csv_saves(self):
        dialog, fields = self.form("协议收发芯片")
        self.assertNotIn("duplex", fields)
        self.assertNotIn("pin_count", fields)
        form = fields["data_rate_mbps"].parentWidget().layout()
        for key in ("data_rate_mbps", "channel_count", "supply_voltage", "logic_voltage_v"):
            widget = fields[key]
            row = widget[0].parentWidget() if isinstance(widget, tuple) else widget
            self.assertTrue(form.labelForField(row).text().endswith(" *"))
            if not isinstance(widget, tuple):
                self.assertNotIn("可留空", widget.placeholderText())
        cases = [("data_rate_mbps", ""), ("channel_count", ""), ("logic_voltage_v", ""),
                 ("supply_voltage", ("", "")), ("supply_voltage", ("3", "")),
                 ("supply_voltage", ("", "3.6")), ("supply_voltage", ("4", "3")),
                 ("data_rate_mbps", "0"), ("channel_count", "0"), ("logic_voltage_v", "0")]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                dialog, fields = self.form("协议收发芯片")
                if isinstance(value, tuple):
                    for endpoint, text in zip(fields[key], value):
                        endpoint.setText(text)
                else:
                    fields[key].setText(value)
                with patch("component_desk.dialogs.error") as show_error:
                    dialog.save()
                    show_error.assert_called_once()
                self.assertIsNone(dialog.saved_id)
                self.assertEqual(self.db.statistics()["count"], 0)
        data = {"name": "TEST", "model": "TEST", "package": "SOIC-8", "category": "协议收发芯片"}
        for key in TRANSCEIVER_PARAMETERS:
            params = {name: value for name, value in TRANSCEIVER_PARAMETERS.items() if name != key}
            with self.subTest(missing=key), self.assertRaises(ValueError):
                self.db.save_component({**data, "parameters": params})
        component_id = self.db.save_component({**data, "parameters": TRANSCEIVER_PARAMETERS})
        edit = ComponentDialog(self.db, self.db.get_component(component_id))
        edit.spec_widgets["协议收发芯片"]["logic_voltage_v"].clear()
        with patch("component_desk.dialogs.error") as show_error:
            edit.save()
            show_error.assert_called_once()
        self.assertEqual(self.db.get_component(component_id)["parameters"], TRANSCEIVER_PARAMETERS)
        csv_file = self.root / "missing-transceiver-voltage.csv"
        self.db.export_csv(csv_file)
        with csv_file.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            names, rows = reader.fieldnames, list(reader)
        params = dict(TRANSCEIVER_PARAMETERS)
        params.pop("logic_voltage_v")
        rows[0]["parameters_json"] = json.dumps(params)
        with csv_file.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=names)
            writer.writeheader()
            writer.writerows(rows)
        imported = Database(self.root / "imported")
        try:
            with self.assertRaises(ValueError):
                imported.import_csv(csv_file)
            self.assertEqual(imported.statistics()["count"], 0)
        finally:
            imported.close()

    def test_removed_transceiver_fields_and_old_backup_preserve_stock_history(self):
        dialog, _ = self.form("协议收发芯片")
        dialog.save()
        component_id = dialog.saved_id
        location = self.db.add_location("收发芯片盒")
        self.db.change_stock(component_id, location, "入库", 9)
        history = self.db.history(component_id)
        legacy = {**TRANSCEIVER_PARAMETERS, "duplex": "半双工", "pin_count": 8, "custom": "keep"}
        with self.db.connection:
            self.db.connection.execute("UPDATE components SET parameters_json=? WHERE id=?",
                                       (json.dumps(legacy), component_id))
        component = self.db.get_component(component_id)
        expected = {**TRANSCEIVER_PARAMETERS, "custom": "keep"}
        self.assertEqual(component["parameters"], expected)
        edit = ComponentDialog(self.db, component)
        edit.save()
        self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.db.get_component(component_id)["stocks"], component["stocks"])
        csv_file = self.root / "transceivers.csv"
        self.db.export_csv(csv_file)
        with csv_file.open(encoding="utf-8-sig", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(json.loads(row["parameters_json"]), expected)
        legacy = {"protocol": "RS-485", "duplex": "半双工", "pin_count": 8, "custom": "keep"}
        with self.db.connection:
            self.db.connection.execute("UPDATE components SET parameters_json=? WHERE id=?",
                                       (json.dumps(legacy), component_id))
        before = self.db.get_component(component_id)
        backup = self.root / "old-transceiver.zip"
        self.db.backup(backup)
        self.db.remove_component(component_id)
        self.db.restore(backup)
        self.assertEqual(self.db.get_component(component_id), before)
        self.assertEqual(self.db.history(component_id), history)
        edit = ComponentDialog(self.db, before)
        with patch("component_desk.dialogs.error") as show_error:
            edit.save()
            show_error.assert_called_once()
        self.assertEqual(self.db.get_component(component_id), before)
        fields = edit.spec_widgets["协议收发芯片"]
        for key in ("data_rate_mbps", "channel_count", "logic_voltage_v"):
            fields[key].setText(str(TRANSCEIVER_PARAMETERS[key]))
        fields["supply_voltage"][0].setText("3")
        fields["supply_voltage"][1].setText("3.6")
        edit.save()
        self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
        updated = self.db.get_component(component_id)
        self.assertEqual(updated["parameters"], expected)
        self.assertEqual(updated["stocks"], before["stocks"])
        self.assertEqual(self.db.history(component_id), history)

    def test_fixed_and_adjustable_ldo_modes_validate_and_preserve_inventory(self):
        dialog, fields = self.form(power_type="LDO")
        fields["ldo_output_mode"].setCurrentIndex(-1)
        with self.assertRaises(ValueError):
            dialog.component_data()
        fields["ldo_output_mode"].setCurrentText("固定输出")
        self.assertFalse(fields["ldo_output_mode"].isEditable())
        self.assertTrue(dialog.power_form.isRowVisible(fields["output_voltage_v"]))
        self.assertFalse(dialog.power_form.isRowVisible(fields["output_voltage"][0].parentWidget()))
        with self.assertRaises(ValueError):
            dialog.component_data()
        fields["output_voltage_v"].setText("3.3")
        fields["output_voltage"][0].setText("invalid hidden draft")
        dialog.save()
        component_id = dialog.saved_id
        self.assertEqual(self.db.get_component(component_id)["parameters"],
                         {"power_type": "LDO", "ldo_output_mode": "固定输出", "output_voltage_v": 3.3})
        location = self.db.add_location("LDO 盒")
        self.db.change_stock(component_id, location, "入库", 8)
        component = self.db.get_component(component_id)
        history = self.db.history(component_id)
        edit = ComponentDialog(self.db, component)
        fields = edit.spec_widgets["电源管理芯片"]
        self.assertEqual(fields["output_voltage_v"].text(), "3.3")
        fields["ldo_output_mode"].setCurrentText("可调输出")
        self.assertTrue(edit.power_form.isRowVisible(fields["output_voltage"][0].parentWidget()))
        self.assertFalse(edit.power_form.isRowVisible(fields["output_voltage_v"]))
        self.assertEqual([endpoint.text() for endpoint in fields["output_voltage"]], ["3.3", "3.3"])
        fields["output_voltage"][0].setText("1.2")
        fields["output_voltage"][1].setText("5")
        edit.save()
        updated = self.db.get_component(component_id)
        self.assertEqual(updated["parameters"], {"power_type": "LDO", "ldo_output_mode": "可调输出",
                                                "output_voltage_min_v": 1.2, "output_voltage_max_v": 5})
        self.assertEqual(updated["stocks"], component["stocks"])
        self.assertEqual(self.db.history(component_id), history)

    def test_legacy_ldo_ranges_require_explicit_mode_without_guessing(self):
        for low, high in ((3.3, 3.3), (1.2, 5)):
            dialog, _ = self.form()
            dialog.save()
            params = {"power_type": "LDO", "output_voltage_min_v": low, "output_voltage_max_v": high}
            with self.db.connection:
                self.db.connection.execute("UPDATE components SET parameters_json=? WHERE id=?", (json.dumps(params), dialog.saved_id))
            component = self.db.get_component(dialog.saved_id)
            self.assertEqual(component["parameters"], params)
            edit = ComponentDialog(self.db, component)
            fields = edit.spec_widgets["电源管理芯片"]
            self.assertEqual(fields["ldo_output_mode"].currentText(), "")
            with self.assertRaises(ValueError):
                edit.component_data()
            fields["ldo_output_mode"].setCurrentText("可调输出")
            edit.save()
            self.assertEqual(self.db.get_component(dialog.saved_id)["parameters"], {**params, "ldo_output_mode": "可调输出"})

    def test_older_backup_with_incomplete_dcdc_specs_can_still_restore(self):
        dialog, _ = self.form()
        dialog.save()
        location = self.db.add_location("旧电源盒")
        self.db.change_stock(dialog.saved_id, location, "入库", 6)
        with self.db.connection:
            self.db.connection.execute("UPDATE components SET parameters_json=? WHERE id=?", ('{"power_type":"DCDC"}', dialog.saved_id))
        before = self.db.get_component(dialog.saved_id)
        history = self.db.history(dialog.saved_id)
        backup = self.root / "old-dcdc.zip"
        self.db.backup(backup)
        self.db.remove_component(dialog.saved_id)
        self.db.restore(backup)
        self.assertEqual(self.db.get_component(dialog.saved_id), before)
        self.assertEqual(self.db.history(dialog.saved_id), history)
        edit = ComponentDialog(self.db, before)
        with patch("component_desk.dialogs.error") as show_error:
            edit.save()
            show_error.assert_called_once()
        self.assertEqual(self.db.get_component(dialog.saved_id), before)

    def test_adjustable_ldo_output_range_survives_edit(self):
        dialog, fields = self.form(power_type="LDO")
        self.assertTrue(dialog.power_form.isRowVisible(fields["output_voltage"][0].parentWidget()))
        fields["output_voltage"][0].setText("1.2")
        fields["output_voltage"][1].setText("5")
        fields["dropout_voltage_mv"].setText("200")
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        component = self.db.get_component(dialog.saved_id)
        self.assertEqual(component["parameters"], {"power_type": "LDO", "ldo_output_mode": "可调输出",
                         "output_voltage_min_v": 1.2, "output_voltage_max_v": 5, "dropout_voltage_mv": 200})
        edit = ComponentDialog(self.db, component)
        edit.save()
        self.assertEqual(self.db.get_component(dialog.saved_id)["parameters"], component["parameters"])

    def test_legacy_ldo_modes_migrate_without_losing_voltage_stock_or_history(self):
        cases = [("LDO", "固定输出", {"output_voltage_v": -3.3}, (-3.3, -3.3)),
                 ("LDO", "可调输出", {"output_voltage_min_v": 1.2, "output_voltage_max_v": 5}, (1.2, 5)),
                 ("DCDC", "固定输出", {"output_voltage_min_v": 5, "output_voltage_max_v": 5}, (5, 5))]
        location = self.db.add_location("电源盒")
        for power_type, mode, voltages, expected in cases:
            with self.subTest(power_type=power_type, mode=mode):
                dialog, _ = self.form()
                dialog.save()
                component_id = dialog.saved_id
                self.db.change_stock(component_id, location, "入库", 7)
                original = self.db.get_component(component_id)
                history = self.db.history(component_id)
                with self.db.connection:
                    legacy = {"power_type": power_type, "output_mode": mode, "custom": "keep", **voltages}
                    if power_type == "DCDC":
                        legacy = {**DCDC_PARAMETERS, **legacy}
                    self.db.connection.execute("UPDATE components SET parameters_json=? WHERE id=?",
                        (json.dumps(legacy), component_id))
                component = self.db.get_component(component_id)
                params = {"power_type": power_type, "custom": "keep",
                          "output_voltage_min_v": expected[0], "output_voltage_max_v": expected[1]}
                if power_type == "DCDC":
                    params = {**DCDC_PARAMETERS, **params}
                elif mode == "固定输出":
                    params = {"power_type": "LDO", "custom": "keep", "ldo_output_mode": mode, "output_voltage_v": expected[0]}
                else:
                    params["ldo_output_mode"] = mode
                self.assertEqual(component["parameters"], params)
                edit = ComponentDialog(self.db, component)
                self.assertNotIn("output_mode", edit.spec_widgets["电源管理芯片"])
                edit.save()
                updated = self.db.get_component(component_id)
                self.assertEqual(updated["parameters"], params)
                self.assertEqual(updated["stocks"], original["stocks"])
                self.assertEqual(self.db.history(component_id), history)
                csv_file = self.root / "power-chips.csv"
                self.db.export_csv(csv_file)
                with csv_file.open(encoding="utf-8-sig", newline="") as handle:
                    row = next(row for row in csv.DictReader(handle) if row["id"] == component_id)
                self.assertEqual(json.loads(row["parameters_json"]), params)

    def test_invalid_ranges_numeric_values_and_required_fields_never_save(self):
        cases = [("input_voltage", ("5", "3")), ("input_voltage", ("5", "")),
                 ("input_voltage", ("nan", "10")), ("output_current_a", "-1"),
                 ("switching_frequency_khz", "inf"), ("power_type", ""), ("package", ""), ("model", "")]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                dialog, fields = self.form()
                widget = fields[key]
                if isinstance(widget, tuple):
                    for field, text in zip(widget, value):
                        field.setText(text)
                elif hasattr(widget, "setCurrentText"):
                    widget.setCurrentText(value)
                else:
                    widget.setText(value)
                with patch("component_desk.dialogs.error") as show_error:
                    dialog.save()
                    show_error.assert_called_once()
                self.assertEqual(self.db.statistics()["count"], 0)
        dialog, fields = self.form("协议收发芯片")
        fields["channel_count"].setText("1.5")
        with patch("component_desk.dialogs.error") as show_error:
            dialog.save()
            show_error.assert_called_once()
        self.assertEqual(self.db.statistics()["count"], 0)

    def test_chip_category_switch_replaces_parameters_and_keeps_inventory(self):
        dialog, fields = self.form("主控芯片")
        fields["clock_mhz"].setText("72")
        dialog.save()
        location = self.db.add_location("芯片盒")
        self.db.change_stock(dialog.saved_id, location, "入库", 10)
        edit = ComponentDialog(self.db, self.db.get_component(dialog.saved_id))
        edit.category.setCurrentText("协议收发芯片")
        fields = edit.spec_widgets["协议收发芯片"]
        fields["model"].setText("TEST-TRANSCEIVER")
        fields["package"].setCurrentText("SOIC-8")
        fields["protocol"].setCurrentText("CAN FD")
        fields["data_rate_mbps"].setText("5")
        fields["channel_count"].setText("1")
        fields["supply_voltage"][0].setText("3")
        fields["supply_voltage"][1].setText("3.6")
        fields["logic_voltage_v"].setText("3.3")
        edit.save()
        self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
        updated = self.db.get_component(dialog.saved_id)
        self.assertNotIn("clock_mhz", updated["parameters"])
        self.assertEqual(updated["parameters"]["protocol"], "CAN FD")
        self.assertEqual(updated["total_quantity"], 10)

    def test_chip_ranges_and_stock_survive_csv_backup_restore(self):
        dialog, fields = self.form()
        fields["switching_frequency_khz"].setText("1.5")
        fields["switching_frequency_unit"].setText("MHz")
        fields["input_voltage"][0].setText("4.5")
        fields["input_voltage"][1].setText("36")
        fields["output_voltage"][0].setText("-12")
        fields["output_voltage"][1].setText("-5")
        dialog.save()
        location = self.db.add_location("电源盒")
        self.db.change_stock(dialog.saved_id, location, "入库", 9)
        before = self.db.get_component(dialog.saved_id)
        csv_file = self.root / "chips.csv"
        self.db.export_csv(csv_file)
        imported = Database(self.root / "imported")
        try:
            self.assertEqual(imported.import_csv(csv_file), 1)
            self.assertEqual(imported.get_component(dialog.saved_id)["parameters"], before["parameters"])
            self.assertEqual(imported.get_component(dialog.saved_id)["total_quantity"], 9)
        finally:
            imported.close()
        backup = self.root / "chips.zip"
        self.db.backup(backup)
        self.db.remove_component(dialog.saved_id)
        self.db.restore(backup)
        self.assertEqual(self.db.get_component(dialog.saved_id), before)


if __name__ == "__main__":
    unittest.main()
