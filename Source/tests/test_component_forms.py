import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from component_desk.database import CATEGORIES, Database, parameter_summary
from component_desk.dialogs import ComponentDialog


class ComponentFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(self.temp.name)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def form(self, category="贴片电容", value="100", unit="nF"):
        dialog = ComponentDialog(self.db)
        dialog.category.setCurrentText(category)
        fields = dialog.spec_widgets[category]
        fields["value"].setText(value)
        fields["unit"].setText(unit)
        fields["package"].setCurrentText("0603")
        fields["voltage_v" if category == "贴片电容" else "power_w"].setCurrentText("25" if category == "贴片电容" else "0.125")
        fields["tolerance_percent"].setCurrentText("10" if category == "贴片电容" else "1")
        return dialog, fields

    def test_capacitance_units_and_supplementary_parameters(self):
        for unit, factor in [("pF", 1e-12), ("nF", 1e-9), ("µF", 1e-6), ("mF", 1e-3), ("F", 1)]:
            with self.subTest(unit=unit):
                dialog, fields = self.form(value="2.2", unit=unit)
                fields["voltage_v"].setCurrentText("6.3")
                fields["tolerance_percent"].setCurrentText("±10%")
                fields["dielectric"].setCurrentText("X7R")
                dialog.temperature_range.setText("-55～125 °C")
                dialog.model.setText("CAP-TEST")
                dialog.manufacturer.setText("Test Manufacturer")
                dialog.save()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                item = self.db.get_component(dialog.saved_id)
                self.assertAlmostEqual(item["parameters"]["capacitance_f"] / factor, 2.2)
                self.assertEqual(item["parameters"]["voltage_v"], 6.3)
                self.assertEqual(item["parameters"]["tolerance_percent"], 10)
                self.assertEqual(item["parameters"]["dielectric"], "X7R")
                self.assertEqual(item["parameters"]["operating_temperature"], "-55～125 °C")
                self.assertEqual(item["model"], "CAP-TEST")
                self.assertEqual(item["total_quantity"], 0)
                self.assertIn("±10%", item["summary"])
                self.assertIn("6.3 V", item["summary"])

    def test_resistance_units_zero_ohm_and_fractional_power(self):
        for unit, factor, number in [("Ω", 1, 100), ("kΩ", 1e3, 4.7), ("MΩ", 1e6, 1), ("Ω", 1, 0)]:
            with self.subTest(unit=unit, number=number):
                dialog, fields = self.form("贴片电阻", str(number), unit)
                fields["power_w"].setCurrentText("1/8")
                fields["tolerance_percent"].setCurrentText("1")
                fields["temperature_coefficient"].setText("±100 ppm/°C")
                dialog.save()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                item = self.db.get_component(dialog.saved_id)
                self.assertEqual(item["parameters"]["resistance_ohm"], number * factor)
                self.assertEqual(item["parameters"]["power_w"], 0.125)
                self.assertEqual(item["parameters"]["temperature_coefficient"], "±100 ppm/°C")
                self.assertIn("0.125 W", item["summary"])

    def test_typed_unit_aliases_save_and_reopen_with_correct_values(self):
        cases = [("贴片电容", " uF ", 2.2e-6), ("贴片电容", "µF", 2.2e-6),
                 ("贴片电容", "μF", 2.2e-6), ("贴片电容", "nf", 2.2e-9),
                 ("贴片电阻", "ohm", 2.2), ("贴片电阻", "kohm", 2200),
                 ("贴片电阻", "Mohm", 2.2e6)]
        for category, unit, expected in cases:
            with self.subTest(category=category, unit=unit):
                dialog, _ = self.form(category, "2.2", unit)
                dialog.save()
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                item = self.db.get_component(dialog.saved_id)
                key = "capacitance_f" if category == "贴片电容" else "resistance_ohm"
                self.assertAlmostEqual(item["parameters"][key] / expected, 1)
                edit = ComponentDialog(self.db, item)
                edit.save()
                self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
                self.assertAlmostEqual(self.db.get_component(item["id"])["parameters"][key] / expected, 1)

    def test_invalid_or_mismatched_typed_units_never_write(self):
        for category, unit in [("贴片电容", "kΩ"), ("贴片电容", "MF"),
                               ("贴片电容", "abc"), ("贴片电阻", "uF"),
                               ("贴片电阻", "mohm"), ("贴片电阻", "abc")]:
            with self.subTest(category=category, unit=unit):
                dialog, _ = self.form(category, "2.2", unit)
                with patch("component_desk.dialogs.error") as show_error:
                    dialog.save()
                    show_error.assert_called_once()
                    self.assertIn("单位", str(show_error.call_args.args[1]))
                self.assertIsNone(dialog.saved_id)
                self.assertEqual(self.db.statistics()["count"], 0)

    def test_unknown_optional_parameters_are_not_invented(self):
        dialog, _ = self.form()
        dialog.save()
        params = self.db.get_component(dialog.saved_id)["parameters"]
        self.assertEqual(set(params), {"capacitance_f", "voltage_v", "tolerance_percent"})
        summary = parameter_summary("贴片电容", params)
        self.assertNotIn("0 V", summary)
        self.assertNotIn("dielectric", params)
        self.assertNotIn("operating_temperature", params)

    def test_required_parameters_block_new_and_existing_component_saves(self):
        for category, value, unit, keys in [
            ("贴片电容", "100", "nF", ["value", "unit", "package", "voltage_v", "tolerance_percent"]),
            ("贴片电阻", "4.7", "kΩ", ["value", "unit", "package", "power_w", "tolerance_percent"]),
        ]:
            original, _ = self.form(category, value, unit)
            original.save()
            component = self.db.get_component(original.saved_id)
            for existing in [False, True]:
                for key in keys:
                    with self.subTest(category=category, existing=existing, key=key):
                        if existing:
                            dialog = ComponentDialog(self.db, component)
                            fields = dialog.spec_widgets[category]
                        else:
                            dialog, fields = self.form(category, value, unit)
                        widget = fields[key]
                        widget.setCurrentText(" ") if hasattr(widget, "setCurrentText") else widget.setText(" ")
                        before = self.db.list_components()
                        with patch("component_desk.dialogs.error") as show_error:
                            dialog.save()
                            show_error.assert_called_once()
                            if key != "package":
                                self.assertIn("必填", str(show_error.call_args.args[1]))
                        self.assertIsNone(dialog.saved_id)
                        self.assertEqual(self.db.list_components(), before)
                        self.assertEqual(self.db.get_component(component["id"]), component)

    def test_edit_round_trip_preserves_stock_history_and_unedited_fields(self):
        attachment = Path(self.temp.name) / "manual.pdf"
        attachment.write_bytes(b"%PDF fixture")
        filename = self.db.copy_attachment(attachment, "datasheet")
        component_id = self.db.save_component({
            "name": "精密电阻", "category": "贴片电阻", "package": "0402",
            "parameters": {"resistance_ohm": 12345.6789, "custom_parameter": "keep"},
            "notes": "保留备注", "warning_quantity": 4, "datasheet": filename,
        }, initial_location="A柜", initial_quantity=20)
        component = self.db.get_component(component_id)
        history = self.db.history(component_id)
        edit = ComponentDialog(self.db, component)
        edit.spec_widgets["贴片电阻"]["power_w"].setCurrentText("0.25")
        edit.spec_widgets["贴片电阻"]["tolerance_percent"].setCurrentText("1")
        edit.save()
        updated = self.db.get_component(component_id)
        self.assertAlmostEqual(updated["parameters"]["resistance_ohm"], 12345.6789)
        self.assertEqual(updated["parameters"]["custom_parameter"], "keep")
        self.assertEqual(updated["datasheet"], filename)
        self.assertEqual(updated["notes"], "保留备注")
        self.assertEqual(updated["warning_quantity"], 4)
        self.assertEqual(updated["stocks"], component["stocks"])
        self.assertEqual(self.db.history(component_id), history)
        self.assertEqual(updated["parameters"]["tolerance_percent"], 1)

    def test_invalid_numeric_values_and_missing_package_never_write(self):
        cases = [("value", "0"), ("value", "-1"), ("value", "nan"), ("value", "inf"),
                 ("value", ""), ("value", "abc"), ("voltage_v", "-25"),
                 ("tolerance_percent", "101"), ("package", "")]
        for key, text in cases:
            with self.subTest(key=key, text=text):
                dialog, fields = self.form()
                widget = fields[key]
                widget.setCurrentText(text) if hasattr(widget, "setCurrentText") else widget.setText(text)
                with patch("component_desk.dialogs.error") as show_error:
                    dialog.save()
                    show_error.assert_called_once()
                self.assertIsNone(dialog.saved_id)
                self.assertEqual(self.db.statistics()["count"], 0)
        dialog, fields = self.form("贴片电阻", "4.7", "kΩ")
        fields["power_w"].setCurrentText("1/0")
        with patch("component_desk.dialogs.error") as show_error:
            dialog.save()
            show_error.assert_called_once()
        self.assertEqual(self.db.statistics()["count"], 0)

    def test_category_change_does_not_reuse_other_category_parameters(self):
        component_id = self.db.save_component({"name": "测试元件", "category": "贴片电阻", "package": "0603",
                                               "parameters": {"resistance_ohm": 4700, "power_w": 0.1}})
        dialog = ComponentDialog(self.db, self.db.get_component(component_id))
        dialog.category.setCurrentText("贴片电容")
        fields = dialog.spec_widgets["贴片电容"]
        fields["value"].setText("100")
        fields["unit"].setText("nF")
        fields["package"].setCurrentText("0805")
        fields["voltage_v"].setCurrentText("25")
        fields["tolerance_percent"].setCurrentText("10")
        dialog.save()
        params = self.db.get_component(component_id)["parameters"]
        self.assertIn("capacitance_f", params)
        self.assertNotIn("resistance_ohm", params)
        self.assertNotIn("power_w", params)

    def test_existing_unsupported_category_is_not_readded_to_the_form(self):
        component_id = self.db.save_component({"name": "旧资料", "category": "贴片电阻", "package": "0603",
                                               "parameters": {"resistance_ohm": 4700, "power_w": 0.1, "tolerance_percent": 1}},
                                              initial_location="A柜", initial_quantity=20)
        with self.db.connection:
            self.db.connection.execute("UPDATE components SET category=?, parameters_json=? WHERE id=?",
                                       ("已停用分类", '{"old_parameter": "keep"}', component_id))
        old = self.db.get_component(component_id)
        dialog = ComponentDialog(self.db, old)
        self.assertEqual([dialog.category.itemText(i) for i in range(dialog.category.count())], list(CATEGORIES))
        with patch("component_desk.dialogs.error") as show_error:
            dialog.save()
            show_error.assert_called_once()
        self.assertEqual(self.db.get_component(component_id), old)
        fields = dialog.spec_widgets["贴片电容"]
        fields["value"].setText("100")
        fields["unit"].setText("nF")
        fields["package"].setCurrentText("0603")
        fields["voltage_v"].setCurrentText("50")
        fields["tolerance_percent"].setCurrentText("10")
        dialog.save()
        updated = self.db.get_component(component_id)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertNotIn("old_parameter", updated["parameters"])
        self.assertEqual(updated["stocks"], old["stocks"])
        self.assertEqual(updated["category"], "贴片电容")


if __name__ == "__main__":
    unittest.main()
