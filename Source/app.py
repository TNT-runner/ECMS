"""Run Component Desk: python app.py [--demo] [--data-dir PATH]."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from component_desk.settings import AppSettings, default_data_directory


def main():
    parser = argparse.ArgumentParser(description="元件仓库 · 个人离线版")
    parser.add_argument("--data-dir", type=Path, help="自定义数据保存目录")
    parser.add_argument("--demo", action="store_true", help="使用独立演示目录，并在空库中生成示例数据")
    args = parser.parse_args()
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError as exc:
        project_dir = Path(__file__).resolve().parent
        # VS Code may run this file with global Python instead of the project venv.
        venv_python = project_dir / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if venv_python.is_file() and Path(sys.executable).resolve() != venv_python.resolve():
            probe = subprocess.run(
                [str(venv_python), "-c", "from PySide6.QtWidgets import QApplication"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if probe.returncode == 0:
                print("当前 Python 缺少 PySide6，正在使用项目虚拟环境启动。", flush=True)
                return subprocess.call([str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])
        requirements = project_dir / "requirements.txt"
        print(
            f"无法加载 PySide6：{exc}\n"
            f"当前解释器：{sys.executable}\n"
            "请在 PowerShell 中运行以下命令安装依赖：\n"
            f'& "{sys.executable}" -m pip install -r "{requirements}"',
            file=sys.stderr,
        )
        return 1
    from component_desk.database import Database
    from component_desk.style import STYLESHEET
    from component_desk.window import MainWindow

    application = QApplication([sys.argv[0]])
    application.setApplicationName("ComponentDesk")
    application.setOrganizationName("PersonalTools")
    application.setFont(QFont("Microsoft YaHei UI", 9))
    application.setStyle("Fusion")
    application.setStyleSheet(STYLESHEET)
    db = None
    try:
        settings = AppSettings()
        db = Database(settings.data_directory(args.demo, args.data_dir))
        if args.demo:
            db.seed_demo()
        window = MainWindow(db, demo=args.demo, settings=settings, directory_override=args.data_dir is not None)
        window.show()
        return application.exec()
    except Exception as exc:
        QMessageBox.critical(None, "启动失败", str(exc))
        return 1
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
