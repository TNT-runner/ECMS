"""Exercise actual Qt forms offscreen and render the resulting main window."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMenu, QMessageBox, QScrollArea, QStyle, QStyleOptionSpinBox

from component_desk.database import CATEGORIES, Database
from component_desk.dialogs import ComponentDialog, LocationDialog, StockDialog
from component_desk.style import STYLESHEET
from component_desk.settings import AppSettings
from component_desk.window import MainWindow
from test_new_component_forms import NEW_SAMPLES, fill_sample


def click_quantity_arrow(field, up):
    option = QStyleOptionSpinBox()
    field.initStyleOption(option)
    control = QStyle.SubControl.SC_SpinBoxUp if up else QStyle.SubControl.SC_SpinBoxDown
    rect = field.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, control, field)
    QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=rect.center())


def main():
    application = QApplication([])
    # Qt's offscreen platform on Windows has no system font discovery.
    if not QFontDatabase.families():
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc"
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    application.setFont(QFont("Microsoft YaHei UI", 9))
    application.setStyle("Fusion")
    application.setStyleSheet(STYLESHEET)
    output = Path(__file__).resolve().parents[1] / ".test-output"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        db = Database(Path(temp) / "data")
        settings = AppSettings(Path(temp) / "config" / "settings.json")
        try:
            empty_window = MainWindow(db, settings=settings)
            assert empty_window.table.rowCount() == 0
            assert not empty_window.in_button.isEnabled()
            assert empty_window.selected_component() is None
            empty_window.close()
            db.seed_demo()
            window = MainWindow(db, demo=True, settings=settings)
            window.resize(1600, 1000)
            window.show()
            QTest.qWait(100)
            assert [window.category_filter.itemText(i) for i in range(window.category_filter.count())] == ["类别：全部", *CATEGORIES]
            window.grab().save(str(output / "preview.png"))
            location_count = len(db.locations())

            def manage_locations():
                dialog = next(item for item in window.findChildren(LocationDialog) if item.isVisible())
                assert dialog.table.rowCount() == location_count
                with patch("component_desk.dialogs.QInputDialog.getText", return_value=("测试空库位", True)):
                    QTest.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton)
                assert dialog.selected_location()["name"] == "测试空库位"
                with patch("component_desk.dialogs.QInputDialog.getText", return_value=("试管盒 · 空格", True)):
                    QTest.mouseClick(dialog.rename_button, Qt.MouseButton.LeftButton)
                removed_id = dialog.selected_location()["id"]
                assert dialog.remove_button.isEnabled()
                dialog.grab().save(str(output / "location-management.png"))
                QTest.mouseClick(dialog.empty_only, Qt.MouseButton.LeftButton)
                assert all(row["total_quantity"] == 0 for row in dialog.rows)
                dialog.reload(removed_id)
                dialog.grab().save(str(output / "empty-locations.png"))
                with patch("component_desk.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                    QTest.mouseClick(dialog.remove_button, Qt.MouseButton.LeftButton)
                assert removed_id not in [row["id"] for row in db.locations()]
                dialog.accept()

            QTimer.singleShot(100, manage_locations)
            window.manage_locations()
            assert window.location_filter.count() == location_count + 1
            assert len(db.locations()) == location_count
            def capture_menu():
                menu = next(menu for menu in window.findChildren(QMenu) if menu.isVisible())
                assert menu.actions()[-1].text() == "移除元件"
                menu.setActiveAction(menu.actions()[1])
                menu.grab().save(str(output / "context-menu.png"))
                menu.close()

            QTimer.singleShot(100, capture_menu)
            window.table_menu(window.table.visualItemRect(window.table.item(0, 0)).center())
            assert window.table.rowCount() == 6
            window.category_filter.setCurrentIndex(window.category_filter.findData("贴片电阻"))
            assert window.table.rowCount() == 3
            window.navigate("low")
            assert window.table.rowCount() == 1
            window.navigate("all")
            QTest.keyClicks(window.search, "CAP10UF")
            QTest.qWait(200)
            assert window.table.rowCount() == 1
            assert window.selected_component()["name"] == "贴片电容 10 µF"
            window.search.clear()
            QTest.qWait(200)
            window.package_filter.setCurrentIndex(window.package_filter.findData("0603"))
            assert window.table.rowCount() == 3
            location_id = next(row["id"] for row in db.locations() if row["name"] == "A柜 · 03格")
            window.location_filter.setCurrentIndex(window.location_filter.findData(location_id))
            assert window.table.rowCount() == 1
            window.package_filter.setCurrentIndex(0)
            window.location_filter.setCurrentIndex(0)
            assert window.table.rowCount() == 6
            window.table.sortItems(3, Qt.SortOrder.DescendingOrder)
            assert window.table.item(0, 3).number == 3600

            # Create a capacitor through the restored form with normalized units.
            dialog = ComponentDialog(db, parent=window)
            assert [dialog.category.itemText(i) for i in range(dialog.category.count())] == list(CATEGORIES)
            fields = dialog.spec_widgets["贴片电容"]
            fields["value"].setText("2.2")
            QTest.keyClicks(fields["unit"], "uF")
            fields["package"].setCurrentText("0805")
            fields["voltage_v"].setCurrentText("25")
            fields["tolerance_percent"].setCurrentText("10")
            fields["dielectric"].setCurrentText("X7R")
            dialog.temperature_range.setText("-55～125 °C")
            dialog.name.setText("测试电容 2.2 µF")
            dialog.show()
            QTest.qWait(100)
            # The right-hand arrow opens the category list and selects the matching page.
            QTest.mouseClick(dialog.category, Qt.MouseButton.LeftButton,
                             pos=QPoint(dialog.category.width() - 14, dialog.category.height() // 2))
            QTest.qWait(50)
            assert dialog.category.view().isVisible()
            QTest.keyClick(dialog.category.view(), Qt.Key.Key_Home)
            QTest.keyClick(dialog.category.view(), Qt.Key.Key_Down)
            QTest.keyClick(dialog.category.view(), Qt.Key.Key_Return)
            assert dialog.category.currentText() == "贴片电阻"
            assert dialog.spec_widgets["贴片电阻"]["value"].isVisible()
            assert not fields["value"].isVisible()
            dialog.category.setCurrentText("贴片电容")
            # Editable preset fields show the same arrow and still accept custom text.
            dielectric = fields["dielectric"]
            QTest.mouseClick(dielectric, Qt.MouseButton.LeftButton,
                             pos=QPoint(dielectric.width() - 14, dielectric.height() // 2))
            QTest.qWait(50)
            assert dielectric.view().isVisible()
            dielectric.view().window().grab().save(str(output / "editable-presets.png"))
            QTest.keyClick(dielectric.view(), Qt.Key.Key_Escape)
            dielectric.setCurrentText("自定义介质")
            assert dielectric.currentText() == "自定义介质"
            dielectric.setCurrentText("X7R")
            dialog.grab().save(str(output / "capacitor-form.png"))
            QTest.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
            assert dialog.result() == QDialog.DialogCode.Accepted
            new_id = dialog.saved_id
            component = db.get_component(new_id)
            assert abs(component["parameters"]["capacitance_f"] - 2.2e-6) < 1e-15
            assert component["total_quantity"] == 0
            addition = StockDialog(db, component, "入库", window)
            addition.show()
            QTest.qWait(50)
            addition.amount.setValue(30)
            click_quantity_arrow(addition.amount, True)
            assert addition.amount.value() == 31
            click_quantity_arrow(addition.amount, False)
            assert addition.amount.value() == 30
            addition.amount.setValue(1)
            click_quantity_arrow(addition.amount, False)
            assert addition.amount.value() == 1
            addition.amount.setValue(addition.amount.maximum())
            click_quantity_arrow(addition.amount, True)
            assert addition.amount.value() == addition.amount.maximum()
            addition.amount.setValue(30)
            addition.grab().save(str(output / "quantity-input.png"))
            addition.save()
            component = db.get_component(new_id)
            assert component["total_quantity"] == 30

            stock = StockDialog(db, component, "领用", window)
            stock.show()
            QTest.qWait(50)
            stock.amount.setValue(7)
            click_quantity_arrow(stock.amount, True)
            assert stock.amount.value() == 8
            click_quantity_arrow(stock.amount, False)
            assert stock.amount.value() == 7
            stock.note.setText("UI smoke test")
            stock.save()
            assert stock.result() == QDialog.DialogCode.Accepted
            assert db.get_component(new_id)["total_quantity"] == 23

            counting = StockDialog(db, db.get_component(new_id), "盘点", window)
            counting.show()
            QTest.qWait(50)
            counting.amount.setValue(0)
            click_quantity_arrow(counting.amount, False)
            assert counting.amount.value() == 0
            click_quantity_arrow(counting.amount, True)
            assert counting.amount.value() == 1
            counting.close()

            edit = ComponentDialog(db, db.get_component(new_id), window)
            edit.show()
            QTest.qWait(100)
            edit.spec_widgets["贴片电容"]["voltage_v"].setCurrentText("50")
            edit.name.setText("测试电容（已编辑）")
            QTest.mouseClick(edit.save_button, Qt.MouseButton.LeftButton)
            assert edit.result() == QDialog.DialogCode.Accepted
            assert db.get_component(new_id)["parameters"]["voltage_v"] == 50
            assert db.get_component(new_id)["name"] == "测试电容（已编辑）"
            assert db.get_component(new_id)["total_quantity"] == 23

            window.refresh(new_id)
            assert window.table.rowCount() == 7
            assert window.selected_component()["id"] == new_id
            window.show_component_history(new_id)
            assert window.pages.currentIndex() == 1
            assert window.history_table.rowCount() == 2
            window.grab().save(str(output / "history.png"))
            window.navigate("all")
            first = next(item for item in db.list_components() if item["name"] == "贴片电阻 4.7 kΩ")
            window.refresh(first["id"])
            QTest.qWait(120)
            window.grab().save(str(output / "main-window.png"))
            form = ComponentDialog(db, first, window)
            form.show()
            QTest.qWait(100)
            form.grab().save(str(output / "resistor-form.png"))
            form.close()
            window.resize(1180, 740)
            application.processEvents()
            window.grab().save(str(output / "compact-window.png"))
            # Apply the new settings through the actual browse/save controls.
            source = db.directory
            before_history = db.history()
            target = Path(temp).resolve() / "迁移后的库存"
            settings_dialog = window.make_settings_dialog()
            settings_dialog.show()
            with patch("component_desk.dialogs.QFileDialog.getExistingDirectory", return_value=str(target)):
                QTest.mouseClick(settings_dialog.browse_button, Qt.MouseButton.LeftButton)
            assert settings_dialog.new_path.text() == str(target)
            QTest.mouseClick(settings_dialog.save_button, Qt.MouseButton.LeftButton)
            QTest.qWait(100)
            assert db.directory == target
            assert db.history() == before_history
            assert window.table.rowCount() == 7
            assert settings_dialog.current_path.text() == str(target)
            assert "数据已迁移" in settings_dialog.result_label.text()
            assert (source / "inventory.sqlite3").is_file()
            settings_dialog.grab().save(str(output / "settings.png"))
            with patch("component_desk.dialogs.error") as show_error:
                settings_dialog.new_path.setText("")
                QTest.mouseClick(settings_dialog.save_button, Qt.MouseButton.LeftButton)
                show_error.assert_called_once()
            assert db.directory == target
            settings_dialog.close()
            restarted_db = Database(AppSettings(settings.path).data_directory(demo=True))
            try:
                restarted_window = MainWindow(restarted_db, demo=True, settings=settings)
                assert restarted_window.table.rowCount() == 7
                assert restarted_db.history() == before_history
                restarted_window.close()
            finally:
                restarted_db.close()
            window.refresh(new_id)
            with patch("component_desk.window.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
                window.remove_component()
            assert db.get_component(new_id) is not None
            assert window.table.rowCount() == 7

            def trigger_remove():
                menu = next(menu for menu in window.findChildren(QMenu) if menu.isVisible())
                menu.actions()[-1].trigger()
                menu.close()

            with patch("component_desk.window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                QTimer.singleShot(100, trigger_remove)
                point = window.table.visualItemRect(window.table.item(window.table.currentRow(), 0)).center()
                window.table_menu(point)
            assert db.get_component(new_id) is None
            assert db.history(new_id) == []
            assert window.table.rowCount() == 6
            assert window.history_component_filter.findData(new_id) == -1
            assert window.stat_labels["count"].text() == "6"
            with patch("component_desk.window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                while window.selected_id:
                    window.remove_component()
            assert window.table.rowCount() == 0
            assert not window.edit_button.isEnabled()
            assert window.selected_component() is None
            assert db.history() == []
            # New chip categories have their own fields and use the same inventory flow.
            for category, screenshot, values in [
                ("主控芯片", "controller-form.png", {"model": "TEST-MCU", "package": "LQFP-64", "core_architecture": "Cortex-M4", "clock_mhz": "168", "flash_kb": "512", "ram_kb": "128", "supply_voltage": ("3", "3.6"), "pin_count": "64"}),
                ("电源管理芯片", "power-form.png", {"model": "TEST-DCDC", "package": "SOIC-8", "power_type": "DCDC", "input_voltage": ("4.5", "36"), "output_voltage": ("1.2", "12"), "output_current_a": "3", "switching_frequency_khz": "500", "switching_frequency_unit": "kHz", "quiescent_current_ua": "50"}),
                ("协议收发芯片", "transceiver-form.png", {"model": "TEST-CANFD", "package": "SOIC-8", "protocol": "CAN FD", "data_rate_mbps": "5", "channel_count": "1", "supply_voltage": ("3", "3.6"), "logic_voltage_v": "3.3", "isolation": "非隔离"}),
            ]:
                chip = ComponentDialog(db, parent=window)
                chip.category.setCurrentText(category)
                fields = chip.spec_widgets[category]
                for key, value in values.items():
                    widget = fields[key]
                    if isinstance(widget, tuple):
                        for endpoint, text in zip(widget, value):
                            endpoint.setText(text)
                    elif hasattr(widget, "setPlainText"):
                        widget.setPlainText(value)
                    elif hasattr(widget, "setCurrentText"):
                        widget.setCurrentText(value)
                    else:
                        widget.setText(value)
                chip.show()
                QTest.qWait(80)
                chip.grab().save(str(output / screenshot))
                if category == "电源管理芯片":
                    fields["power_type"].setCurrentText("LDO")
                    fields["model"].setText("TEST-LDO")
                    fields["ldo_output_mode"].setCurrentText("固定输出")
                    fields["output_voltage_v"].setText("3.3")
                    fields["dropout_voltage_mv"].setText("200")
                    application.processEvents()
                    chip.grab().save(str(output / "ldo-form.png"))
                    fields["ldo_output_mode"].setCurrentText("可调输出")
                    fields["output_voltage"][0].setText("1.2")
                    fields["output_voltage"][1].setText("5")
                    application.processEvents()
                    chip.grab().save(str(output / "ldo-adjustable-form.png"))
                    fields["power_type"].setCurrentText("DCDC")
                    fields["model"].setText("TEST-DCDC")
                    fields["output_voltage"][0].setText("1.2")
                    fields["output_voltage"][1].setText("12")
                    fields["switching_frequency_khz"].setText("500")
                    fields["switching_frequency_unit"].setText("kHz")
                QTest.mouseClick(chip.save_button, Qt.MouseButton.LeftButton)
                assert chip.result() == QDialog.DialogCode.Accepted
                window.refresh(chip.saved_id)
                window.category_filter.setCurrentIndex(window.category_filter.findData(category))
                assert window.table.rowCount() == 1
                assert window.selected_component()["category"] == category
            window.category_filter.setCurrentIndex(0)
            assert window.table.rowCount() == 3
            pmu = ComponentDialog(db, parent=window)
            pmu.category.setCurrentText("电源管理芯片")
            fields = pmu.spec_widgets["电源管理芯片"]
            values = {"power_type": "PMU", "model": "TEST-PMU", "package": "VQFN-48", "pmu_dcdc_count": "3", "pmu_ldo_count": "2",
                      "pmu_outputs": "DCDC1：0.9～1.8 V，1.5 A\nLDO1：3.3 V，0.2 A", "pmu_control_interface": "I²C",
                      "pmu_sequence": "可编程时序", "pmu_charger": "支持", "pmu_battery_spec": "单节锂离子电池",
                      "pmu_charge_voltage_v": "4.2", "pmu_charge_current_a": "1.5", "pmu_power_path": "支持",
                      "pmu_protection": "欠压锁定、过流、过温", "pmu_other_functions": "ADC、LED 驱动", "quiescent_current_ua": "80", "pin_count": "48"}
            for key, value in values.items():
                widget = fields[key]
                if hasattr(widget, "setCurrentText"):
                    widget.setCurrentText(value)
                elif hasattr(widget, "setPlainText"):
                    widget.setPlainText(value)
                else:
                    widget.setText(value)
            fields["input_voltage"][0].setText("2.8")
            fields["input_voltage"][1].setText("6.3")
            pmu.show()
            QTest.qWait(80)
            assert fields["pmu_outputs"].height() >= 100
            pmu.grab().save(str(output / "pmu-form.png"))
            scroll = pmu.findChild(QScrollArea)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            application.processEvents()
            pmu.grab().save(str(output / "pmu-form-bottom.png"))
            QTest.mouseClick(pmu.save_button, Qt.MouseButton.LeftButton)
            assert pmu.result() == QDialog.DialogCode.Accepted
            window.refresh(pmu.saved_id)
            assert window.selected_component()["parameters"]["pmu_outputs"] == values["pmu_outputs"]
            assert "3 路 DCDC" in window.selected_component()["summary"]
            assert any(item.text() == values["pmu_outputs"] for item in window.findChildren(QLabel))
            assert window.table.rowCount() == 4
            window.resize(1600, 1000)
            QTest.qWait(100)
            window.grab().save(str(output / "chip-inventory.png"))
            screenshots = ("battery-management", "inductor", "tvs", "diode", "crystal", "mosfet", "common-mode-choke",
                           "transistor", "ferrite-bead", "connector", "opamp", "logic", "memory")
            for (category, _), screenshot in zip(NEW_SAMPLES.items(), screenshots):
                dialog = ComponentDialog(db, parent=window)
                fields = fill_sample(dialog, category)
                dialog.show()
                QTest.qWait(80)
                dialog.grab().save(str(output / (screenshot + "-form.png")))
                if category == "晶振":
                    fields["oscillator_type"].setCurrentText("有源晶振")
                    assert not fields["load_capacitance_pf"].isEnabled()
                    fields["supply_voltage"][0].setText("3")
                    fields["supply_voltage"][1].setText("3.6")
                    fields["output_signal"].setCurrentText("LVCMOS")
                    application.processEvents()
                    dialog.grab().save(str(output / "active-crystal-form.png"))
                    fields["oscillator_type"].setCurrentText("无源晶振")
                elif category == "电池管理芯片":
                    fields["battery_function"].setCurrentText("电池保护")
                    assert not fields["charge_current_a"].isEnabled()
                    fields["overcharge_voltage_v"].setText("4.3")
                    fields["overdischarge_voltage_v"].setText("2.8")
                    application.processEvents()
                    dialog.grab().save(str(output / "battery-protection-form.png"))
                    fields["battery_function"].setCurrentText("充电管理")
                QTest.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
                assert dialog.result() == QDialog.DialogCode.Accepted
                window.refresh(dialog.saved_id)
                window.category_filter.setCurrentIndex(window.category_filter.findData(category))
                assert window.table.rowCount() == 1
                assert window.selected_component()["parameters"] == NEW_SAMPLES[category][1]
            window.category_filter.setCurrentIndex(0)
            assert window.table.rowCount() == 4 + len(NEW_SAMPLES)
            window.grab().save(str(output / "expanded-inventory.png"))
            window.close()
            application.processEvents()
        finally:
            db.close()
    print("UI smoke passed: eighteen category forms, visible editable dropdown arrows, conditional fields, manual units, location management, inventory, migration and restart; screenshots saved.")


if __name__ == "__main__":
    main()
