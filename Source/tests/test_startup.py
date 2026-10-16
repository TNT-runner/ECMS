"""Regression checks for launching from a global Python without PySide6."""

import contextlib
import builtins
import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app

original_import = builtins.__import__


def missing_pyside(name, *args, **kwargs):
    if name.startswith("PySide6"):
        raise ImportError("No module named 'PySide6'")
    return original_import(name, *args, **kwargs)


class StartupTests(unittest.TestCase):
    def test_missing_gui_uses_venv_and_preserves_arguments(self):
        with patch.object(app.sys, "argv", ["app.py", "--demo", "--data-dir", "test-data"]), \
                patch.object(app.sys, "executable", "D:/OtherPython/python.exe"), \
                patch("builtins.__import__", side_effect=missing_pyside), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(app.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                patch.object(app.subprocess, "call", return_value=0) as launch, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(), 0)
        command = launch.call_args.args[0]
        self.assertIn(".venv", command[0])
        self.assertEqual(command[1], str(Path(app.__file__).resolve()))
        self.assertEqual(command[2:], ["--demo", "--data-dir", "test-data"])

    def test_missing_venv_reports_exact_interpreter_and_requirements(self):
        output = io.StringIO()
        with patch.object(app.sys, "argv", ["app.py"]), \
                patch.object(app.sys, "executable", "D:/OtherPython/python.exe"), \
                patch("builtins.__import__", side_effect=missing_pyside), \
                patch.object(Path, "is_file", return_value=False), \
                patch.object(app.subprocess, "call") as launch, \
                contextlib.redirect_stderr(output):
            self.assertEqual(app.main(), 1)
        launch.assert_not_called()
        self.assertIn('"D:/OtherPython/python.exe" -m pip install', output.getvalue())
        self.assertIn(str(Path(app.__file__).resolve().parent / "requirements.txt"), output.getvalue())

    def test_broken_venv_is_not_launched(self):
        with patch.object(app.sys, "argv", ["app.py"]), \
                patch.object(app.sys, "executable", "D:/OtherPython/python.exe"), \
                patch("builtins.__import__", side_effect=missing_pyside), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(app.subprocess, "run", return_value=SimpleNamespace(returncode=1)), \
                patch.object(app.subprocess, "call") as launch, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(app.main(), 1)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
