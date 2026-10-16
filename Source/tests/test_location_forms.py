import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from component_desk.database import Database
from component_desk.dialogs import LocationDialog, StockDialog
from component_desk.window import MainWindow


class LocationFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "data")
        self.data = {"name": "测试电阻", "category": "贴片电阻", "package": "0603",
                     "parameters": {"resistance_ohm": 1000}}

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_search_empty_filter_add_rename_and_validation(self):
        self.db.save_component(self.data, initial_location="A柜", initial_quantity=5)
        empty = self.db.add_location("空盒")
        dialog = LocationDialog(self.db)
        self.assertEqual(dialog.table.rowCount(), 2)
        self.assertFalse(dialog.remove_button.isEnabled())
        dialog.empty_only.setChecked(True)
        self.assertEqual(dialog.selected_location()["id"], empty)
        self.assertTrue(dialog.remove_button.isEnabled())
        dialog.search.setText("找不到")
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertFalse(dialog.rename_button.isEnabled())
        self.assertFalse(dialog.remove_button.isEnabled())
        with patch("component_desk.dialogs.QInputDialog.getText", return_value=("新盒", True)):
            dialog.add_button.click()
        self.assertEqual(dialog.selected_location()["name"], "新盒")
        self.assertEqual(dialog.search.text(), "")
        with patch("component_desk.dialogs.QInputDialog.getText", return_value=("备用盒", True)):
            dialog.rename_button.click()
        self.assertEqual(dialog.selected_location()["name"], "备用盒")
        for invalid in (" ", "A柜"):
            with patch("component_desk.dialogs.QInputDialog.getText", return_value=(invalid, True)), \
                    patch("component_desk.dialogs.error") as show_error:
                dialog.rename_button.click()
                show_error.assert_called_once()
        dialog.empty_only.setChecked(False)
        self.assertEqual(dialog.table.rowCount(), 3)
        self.assertTrue(dialog.changed)

    def test_remove_cancel_empty_and_stale_stock(self):
        component_id = self.db.save_component(self.data)
        empty = self.db.add_location("空盒")
        dialog = LocationDialog(self.db)
        with patch("component_desk.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            dialog.remove_button.click()
        self.assertEqual(len(self.db.locations()), 1)
        self.assertFalse(dialog.changed)
        self.db.change_stock(component_id, empty, "入库", 5)
        with patch("component_desk.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
                patch("component_desk.dialogs.error") as show_error:
            dialog.remove_button.click()
            show_error.assert_called_once()
        self.assertEqual(self.db.get_component(component_id)["total_quantity"], 5)
        self.assertFalse(dialog.changed)
        self.db.change_stock(component_id, empty, "领用", 5)
        dialog.reload()
        history = self.db.history()
        with patch("component_desk.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            dialog.remove_button.click()
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertFalse(dialog.remove_button.isEnabled())
        self.assertFalse(dialog.empty_message.isHidden())
        self.assertTrue(dialog.changed)
        self.assertEqual(self.db.history(), history)
        stock = StockDialog(self.db, self.db.get_component(component_id), "入库")
        self.assertEqual(stock.location.count(), 0)
        self.assertFalse(stock.save_button.isEnabled())

    def test_sidebar_management_refreshes_location_filter_and_statistics(self):
        component_id = self.db.save_component(self.data, initial_location="试管盒", initial_quantity=5)
        location_id = self.db.locations()[0]["id"]
        self.db.remove_component(component_id)
        window = MainWindow(self.db)
        window.location_filter.setCurrentIndex(window.location_filter.findData(location_id))

        def manage(dialog):
            with patch("component_desk.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                dialog.remove_button.click()
            dialog.accept()
            return dialog.result()

        try:
            with patch.object(LocationDialog, "exec", manage):
                window.manage_locations()
            self.assertEqual(window.location_filter.count(), 1)
            self.assertIsNone(window.location_filter.currentData())
            self.assertEqual(window.stat_labels["locations"].text(), "0 / 0")
            self.assertEqual(self.db.locations(), [])
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
