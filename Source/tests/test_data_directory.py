import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from component_desk.database import Database
from component_desk.settings import AppSettings, default_data_directory


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "original"
        self.target = self.root / "新数据目录"
        self.db = Database(self.source)
        self.db.seed_demo()
        self.settings = AppSettings(self.root / "config" / "settings.json")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_migration_preserves_history_attachments_backups_and_restart(self):
        component = self.db.list_components()[0]
        pdf = self.root / "manual.pdf"
        pdf.write_bytes(b"%PDF-1.4 fixture")
        photo = self.root / "photo.png"
        photo.write_bytes(b"photo fixture")
        self.db.save_component({**component, "datasheet": self.db.copy_attachment(pdf, "datasheet"),
                                "photo": self.db.copy_attachment(photo, "photo")}, component["id"])
        self.db.backup(self.source / "backups" / "original.zip")
        before = self.db.list_components()
        history = self.db.history()
        self.assertTrue(self.db.migrate_to(self.target, self.settings.save_data_directory))
        self.assertEqual(self.db.directory, self.target)
        self.assertEqual(self.db.list_components(), before)
        self.assertEqual(self.db.history(), history)
        self.assertEqual((self.target / "backups" / "original.zip").read_bytes(), (self.source / "backups" / "original.zip").read_bytes())
        for kind in ("photo", "datasheet"):
            filename = self.db.get_component(component["id"])[kind]
            self.assertEqual((self.target / "attachments" / filename).read_bytes(), (self.source / "attachments" / filename).read_bytes())
        restored_settings = AppSettings(self.settings.path)
        restarted = Database(restored_settings.data_directory())
        original = Database(self.source)
        try:
            self.assertEqual(restarted.list_components(), before)
            self.db.change_stock(component["id"], component["stocks"][0]["location_id"], "领用", 1)
            self.assertEqual(original.get_component(component["id"])["total_quantity"], 1280)
            self.assertEqual(self.db.get_component(component["id"])["total_quantity"], 1279)
        finally:
            restarted.close()
            original.close()

    def test_nonempty_destination_keeps_source_and_existing_file(self):
        self.target.mkdir()
        marker = self.target / "existing.txt"
        marker.write_text("keep me", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.db.migrate_to(self.target, self.settings.save_data_directory)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(self.db.directory, self.source)
        self.assertEqual(self.db.statistics()["quantity"], 7322)
        self.assertFalse(self.settings.path.exists())

    def test_nested_or_parent_directory_rejected(self):
        for path in (self.source / "nested", self.root):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.db.migrate_to(path)
        self.assertFalse((self.source / "nested").exists())

    def test_copy_failure_does_not_save_setting_or_switch_database(self):
        with patch("component_desk.database.shutil.copytree", side_effect=OSError("磁盘空间不足")), self.assertRaises(OSError):
            self.db.migrate_to(self.target, self.settings.save_data_directory)
        self.assertEqual(self.db.directory, self.source)
        self.assertEqual(self.db.statistics()["quantity"], 7322)
        self.assertFalse(self.settings.path.exists())
        self.assertEqual(list(self.target.iterdir()), [])

    def test_settings_failure_removes_copied_files_and_keeps_source(self):
        self.settings.save_data_directory(self.source)
        previous_settings = self.settings.path.read_bytes()
        with patch("component_desk.settings.os.replace", side_effect=PermissionError("设置不可写")), self.assertRaises(PermissionError):
            self.db.migrate_to(self.target, self.settings.save_data_directory)
        self.assertEqual(self.db.directory, self.source)
        self.assertEqual(self.db.statistics()["quantity"], 7322)
        self.assertEqual(self.settings.path.read_bytes(), previous_settings)
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(list(self.settings.path.parent.glob(".settings-*")), [])

    def test_missing_attachment_does_not_switch_directory(self):
        component = self.db.list_components()[0]
        self.db.save_component({**component, "datasheet": "missing.pdf"}, component["id"])
        with self.assertRaises(ValueError):
            self.db.migrate_to(self.target, self.settings.save_data_directory)
        self.assertEqual(self.db.directory, self.source)
        self.assertFalse(self.settings.path.exists())
        self.assertEqual(list(self.target.iterdir()), [])

    def test_current_directory_can_be_remembered_without_copying(self):
        self.assertFalse(self.db.migrate_to(self.source, self.settings.save_data_directory))
        self.assertEqual(AppSettings(self.settings.path).data_directory(), self.source)
        self.assertEqual(self.db.statistics()["quantity"], 7322)

    def test_defaults_and_command_line_override(self):
        self.assertEqual(self.settings.data_directory(), default_data_directory().resolve())
        self.settings.save_data_directory(self.source)
        self.assertEqual(self.settings.data_directory(override=self.target), self.target)
        self.assertEqual(self.settings.data_directory(), self.source)

    def test_demo_and_personal_settings_are_independent(self):
        demo = Database(self.target)
        demo.close()
        self.settings.save_data_directory(self.source)
        self.settings.save_data_directory(self.target, demo=True)
        reopened = AppSettings(self.settings.path)
        self.assertEqual(reopened.data_directory(), self.source)
        self.assertEqual(reopened.data_directory(demo=True), self.target)

    def test_unavailable_saved_directory_does_not_create_empty_database(self):
        self.settings.save_data_directory(self.target)
        with self.assertRaises(ValueError):
            AppSettings(self.settings.path).data_directory()
        self.assertFalse(self.target.exists())

    def test_invalid_settings_does_not_silently_reset_inventory(self):
        self.settings.path.parent.mkdir()
        self.settings.path.write_text('{"data_directory":"relative"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.settings.data_directory()
        self.assertEqual(self.settings.data_directory(override=self.source), self.source)


if __name__ == "__main__":
    unittest.main()
