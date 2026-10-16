import csv
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from component_desk.database import CSV_FIELDS, Database


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.db = Database(self.path / "data")
        self.data = {"name": "4.7 kΩ 电阻", "category": "贴片电阻", "package": "0603",
                     "parameters": {"resistance_ohm": 4700, "tolerance_percent": 1}, "warning_quantity": 10}

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_new_component_persists_after_reopen(self):
        component_id = self.db.save_component(self.data, initial_location="A柜", initial_quantity=50)
        self.db.close()
        self.db = Database(self.path / "data")
        item = self.db.get_component(component_id)
        self.assertEqual(item["total_quantity"], 50)
        self.assertEqual(item["parameters"]["resistance_ohm"], 4700)

    def test_multiple_locations_and_balances(self):
        component_id = self.db.save_component(self.data, initial_location="A柜", initial_quantity=50)
        a = self.db.locations()[0]["id"]
        b = self.db.add_location("备用盒")
        self.db.change_stock(component_id, b, "入库", 20)
        self.db.change_stock(component_id, a, "领用", 12)
        self.db.change_stock(component_id, b, "盘点", 5)
        item = self.db.get_component(component_id)
        self.assertEqual(item["total_quantity"], 43)
        self.assertEqual(sum(row["delta"] for row in self.db.history(component_id)), 43)
        self.assertEqual(self.db.history(component_id)[0]["balance"], 5)

    def test_insufficient_stock_rolls_back_and_uses_selected_location(self):
        component_id = self.db.save_component(self.data, initial_location="A柜", initial_quantity=100)
        b = self.db.add_location("空库位")
        before = len(self.db.history())
        with self.assertRaises(ValueError):
            self.db.change_stock(component_id, b, "领用", 1)
        self.assertEqual(self.db.get_component(component_id)["total_quantity"], 100)
        self.assertEqual(len(self.db.history()), before)

    def test_failed_initial_stock_does_not_create_component(self):
        with self.assertRaises(ValueError):
            self.db.save_component(self.data, initial_quantity=1)
        self.assertEqual(self.db.statistics()["count"], 0)

    def test_validation_of_quantity_and_parameters(self):
        for value in (-1, 1.5, True, 1_000_000_001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.db.save_component(self.data, initial_location="A柜", initial_quantity=value)
        for value in (float("nan"), float("inf"), -4700):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.db.save_component({**self.data, "parameters": {"resistance_ohm": value}})
        with self.assertRaises(ValueError):
            self.db.save_component({**self.data, "category": "已停用分类"})

    def test_filters_and_warning_use_total_stock(self):
        component_id = self.db.save_component(self.data, initial_location="A柜", initial_quantity=4)
        b = self.db.add_location("备用盒")
        self.assertEqual(len(self.db.list_components(low_only=True)), 1)
        self.db.change_stock(component_id, b, "入库", 8)
        self.assertEqual(len(self.db.list_components(low_only=True)), 0)
        self.assertEqual(len(self.db.list_components(search="4.7 kΩ 备用", package="0603", location_id=b)), 1)
        self.assertEqual(len(self.db.list_components(category="贴片电容")), 0)

    def test_edit_retains_stocks_and_history(self):
        component_id = self.db.save_component(self.data, initial_location="A柜", initial_quantity=50)
        self.db.save_component({**self.data, "name": "精密电阻"}, component_id)
        self.assertEqual(self.db.get_component(component_id)["name"], "精密电阻")
        self.assertEqual(self.db.get_component(component_id)["total_quantity"], 50)
        self.assertEqual(len(self.db.history(component_id)), 1)

    def test_remove_component_preserves_other_components_and_locations(self):
        removed_id = self.db.save_component(self.data, initial_location="A柜", initial_quantity=50)
        location_id = self.db.locations()[0]["id"]
        self.db.change_stock(removed_id, self.db.add_location("备用盒"), "入库", 10)
        kept_id = self.db.save_component({**self.data, "name": "保留元件"}, initial_location="A柜", initial_quantity=20)
        kept_component = self.db.get_component(kept_id)
        kept_history = self.db.history(kept_id)
        self.db.remove_component(removed_id)
        self.assertIsNone(self.db.get_component(removed_id))
        self.assertEqual(self.db.history(removed_id), [])
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM stocks WHERE component_id=?", (removed_id,)).fetchone()[0], 0)
        self.assertEqual(self.db.get_component(kept_id), kept_component)
        self.assertEqual(self.db.history(kept_id), kept_history)
        self.assertEqual(self.db.statistics()["quantity"], 20)
        self.assertIn(location_id, [row["id"] for row in self.db.locations()])
        self.assertEqual(self.db.connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.db.close()
        self.db = Database(self.path / "data")
        self.assertIsNone(self.db.get_component(removed_id))
        self.assertIsNotNone(self.db.get_component(kept_id))

    def test_remove_empty_location_after_component_removal(self):
        component_id = self.db.save_component(self.data, initial_location="试管盒", initial_quantity=50)
        location_id = self.db.locations()[0]["id"]
        self.db.remove_component(component_id)
        self.db.remove_location(location_id)
        self.assertEqual(self.db.locations(), [])
        self.assertEqual(self.db.statistics()["locations"], 0)
        self.assertEqual(self.db.connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        with self.assertRaises(ValueError):
            self.db.remove_location(location_id)
        self.db.close()
        self.db = Database(self.path / "data")
        self.assertEqual(self.db.locations(), [])

    def test_location_with_stock_cannot_be_removed(self):
        component_id = self.db.save_component(self.data, initial_location="A柜", initial_quantity=5)
        location_id = self.db.locations()[0]["id"]
        empty = self.db.add_location("空盒")
        self.db.change_stock(component_id, empty, "盘点", 0)
        before = self.db.get_component(component_id)
        history = self.db.history()
        with self.assertRaisesRegex(ValueError, "仍有库存"):
            self.db.remove_location(location_id)
        self.assertEqual(self.db.get_component(component_id), before)
        self.assertEqual(self.db.history(), history)
        self.db.remove_location(empty)
        self.assertEqual([row["id"] for row in self.db.locations()], [location_id])
        self.assertEqual(self.db.get_component(component_id)["total_quantity"], 5)
        self.assertEqual(self.db.history(), history)

    def test_empty_location_removal_preserves_history_restart_backup_and_reuse(self):
        component_id = self.db.save_component(self.data, initial_location="历史盒", initial_quantity=5)
        location_id = self.db.locations()[0]["id"]
        self.db.change_stock(component_id, location_id, "领用", 5)
        history = self.db.history()
        self.db.remove_location(location_id)
        self.assertEqual(self.db.locations(), [])
        self.assertEqual(self.db.get_component(component_id)["stocks"], [])
        self.assertEqual(self.db.history(), history)
        with self.assertRaises(ValueError):
            self.db.change_stock(component_id, location_id, "入库", 1)
        with self.assertRaises(ValueError):
            self.db.rename_location(location_id, "旧盒")
        backup = self.path / "removed-location.zip"
        self.db.backup(backup)
        self.db.close()
        self.db = Database(self.path / "data")
        self.assertEqual(self.db.locations(), [])
        self.assertEqual(self.db.history(), history)
        self.assertEqual(self.db.add_location("历史盒"), location_id)
        self.db.change_stock(component_id, location_id, "入库", 2)
        self.db.restore(backup)
        self.assertEqual(self.db.locations(), [])
        self.assertEqual(self.db.history(), history)
        self.assertEqual(self.db.add_location(" 历史盒 "), location_id)
        self.assertEqual(self.db.locations()[0]["total_quantity"], 0)
        with self.assertRaisesRegex(ValueError, "已存在"):
            self.db.add_location("历史盒")
        self.db.change_stock(component_id, location_id, "入库", 3)
        self.assertEqual(self.db.get_component(component_id)["total_quantity"], 3)
        self.assertEqual(len(self.db.history()), len(history) + 1)

    def test_location_removal_failure_rolls_back_zero_stock(self):
        component_id = self.db.save_component(self.data, initial_location="A柜", initial_quantity=5)
        location_id = self.db.locations()[0]["id"]
        self.db.change_stock(component_id, location_id, "领用", 5)
        before = self.db.get_component(component_id)
        history = self.db.history()
        self.db.connection.execute("CREATE TRIGGER reject_retirement BEFORE INSERT ON retired_locations BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.remove_location(location_id)
        self.assertEqual(self.db.get_component(component_id), before)
        self.assertEqual(self.db.history(), history)
        self.assertEqual(len(self.db.locations()), 1)

    def test_old_database_and_backup_upgrade_location_management(self):
        component_id = self.db.save_component(self.data, initial_location="旧库位", initial_quantity=5)
        location_id = self.db.locations()[0]["id"]
        self.db.change_stock(component_id, location_id, "领用", 5)
        history = self.db.history()
        with self.db.connection:
            self.db.connection.execute("DROP TABLE retired_locations")
        backup = self.path / "old-locations.zip"
        self.db.backup(backup)
        self.db.close()
        self.db = Database(self.path / "data")
        self.db.remove_location(location_id)
        self.db.restore(backup)
        self.assertEqual([row["id"] for row in self.db.locations()], [location_id])
        self.assertEqual(self.db.history(), history)
        self.db.remove_location(location_id)
        self.assertEqual(self.db.locations(), [])
        self.assertEqual(self.db.history(), history)

    def test_csv_import_can_reuse_removed_location_without_losing_history(self):
        component_id = self.db.save_component(self.data, initial_location="循环盒", initial_quantity=3)
        location_id = self.db.locations()[0]["id"]
        self.db.change_stock(component_id, location_id, "领用", 3)
        history = self.db.history(component_id)
        self.db.remove_location(location_id)
        path = self.path / "reused-location.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerow({**{key: value for key, value in self.data.items() if key in CSV_FIELDS},
                             "parameters_json": json.dumps(self.data["parameters"]),
                             "location": "循环盒", "quantity": 4})
        self.assertEqual(self.db.import_csv(path), 1)
        self.assertEqual(self.db.locations()[0]["id"], location_id)
        self.assertEqual(self.db.statistics()["quantity"], 4)
        self.assertEqual(self.db.history(component_id), history)

    def test_remove_failure_rolls_back_stock_and_history(self):
        component_id = self.db.save_component(self.data, initial_location="A柜", initial_quantity=50)
        before = self.db.get_component(component_id)
        history = self.db.history()
        self.db.connection.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON components BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.remove_component(component_id)
        self.assertEqual(self.db.get_component(component_id), before)
        self.assertEqual(self.db.history(), history)

    def test_remove_missing_component_changes_nothing(self):
        self.db.save_component(self.data)
        with self.assertRaises(ValueError):
            self.db.remove_component("unknown-id")
        self.assertEqual(self.db.statistics()["count"], 1)

    def test_remove_preserves_shared_attachments_and_backup(self):
        file = self.path / "manual.pdf"
        file.write_bytes(b"%PDF-1.4 fixture")
        filename = self.db.copy_attachment(file, "datasheet")
        first = self.db.save_component({**self.data, "datasheet": filename})
        second = self.db.save_component({**self.data, "name": "保留元件", "datasheet": filename})
        backup = self.db.directory / "backups" / "original.zip"
        self.db.backup(backup)
        backup_bytes = backup.read_bytes()
        self.db.remove_component(first)
        self.assertEqual((self.db.attachments / filename).read_bytes(), file.read_bytes())
        self.assertEqual(self.db.get_component(second)["datasheet"], filename)
        self.assertEqual(backup.read_bytes(), backup_bytes)

    def test_csv_round_trip_preserves_multiple_locations_and_zero_stock(self):
        first = self.db.save_component(self.data, initial_location="A柜", initial_quantity=50)
        self.db.change_stock(first, self.db.add_location("备用盒"), "入库", 3)
        self.db.save_component({**self.data, "name": "零库存元件"})
        path = self.path / "export.csv"
        self.db.export_csv(path)
        other = Database(self.path / "other")
        try:
            self.assertEqual(other.import_csv(path), 2)
            self.assertEqual(other.get_component(first)["total_quantity"], 53)
            self.assertEqual(len(other.get_component(first)["stocks"]), 2)
            self.assertEqual(other.statistics()["count"], 2)
        finally:
            other.close()

    def test_csv_duplicate_existing_id_rolls_back_whole_import(self):
        existing = self.db.save_component(self.data)
        other = Database(self.path / "source")
        path = self.path / "conflict.csv"
        try:
            other.save_component({**self.data, "name": "新元件"})
            # Generate a CSV whose second group conflicts with current database.
            other.save_component(self.data)
            other.export_csv(path)
        finally:
            other.close()
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[1]["id"] = existing
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        with self.assertRaises(ValueError):
            self.db.import_csv(path)
        self.assertEqual(self.db.statistics()["count"], 1)

    def test_csv_invalid_last_row_saves_nothing(self):
        self.db.seed_demo()
        path = self.path / "invalid.csv"
        self.db.export_csv(path)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[-1]["quantity"] = "-3"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        other = Database(self.path / "other")
        try:
            with self.assertRaises(ValueError):
                other.import_csv(path)
            self.assertEqual(other.statistics()["count"], 0)
        finally:
            other.close()

    def test_backup_restore_includes_attachments_and_pre_restore_backup(self):
        pdf = self.path / "datasheet.pdf"
        pdf.write_bytes(b"%PDF-1.4 example fixture")
        attached = self.db.copy_attachment(pdf, "datasheet")
        component_id = self.db.save_component({**self.data, "datasheet": attached}, initial_location="A柜", initial_quantity=50)
        backup = self.path / "backup.zip"
        self.db.backup(backup)
        location_id = self.db.locations()[0]["id"]
        self.db.change_stock(component_id, location_id, "领用", 10)
        self.db.add_location("新增库位")
        rollback = self.db.restore(backup)
        self.assertEqual(self.db.get_component(component_id)["total_quantity"], 50)
        self.assertEqual((self.db.attachments / attached).read_bytes(), pdf.read_bytes())
        self.assertTrue(rollback.is_file())
        self.db.restore(rollback)
        self.assertEqual(self.db.get_component(component_id)["total_quantity"], 40)
        self.assertIn("新增库位", [row["name"] for row in self.db.locations()])

    def test_invalid_backup_cannot_change_current_database(self):
        component_id = self.db.save_component(self.data)
        bad = self.path / "bad.zip"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("../escape.txt", "bad")
        with self.assertRaises(ValueError):
            self.db.restore(bad)
        self.assertIsNotNone(self.db.get_component(component_id))
        self.assertFalse((self.path / "escape.txt").exists())

    def test_demo_is_idempotent_and_accurate(self):
        self.db.seed_demo()
        self.db.seed_demo()
        self.assertEqual(self.db.statistics()["count"], 6)
        self.assertEqual(self.db.statistics()["quantity"], 7322)
        self.assertEqual(self.db.statistics()["low"], 1)
        self.assertEqual({item["category"] for item in self.db.list_components()}, {"贴片电容", "贴片电阻"})


if __name__ == "__main__":
    unittest.main()
