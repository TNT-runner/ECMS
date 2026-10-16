"""Remember data directories independently from inventory files."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def default_data_directory(demo=False) -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / ("ComponentDeskDemo" if demo else "ComponentDesk")


class AppSettings:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else default_data_directory().parent / "ComponentDeskSettings" / "settings.json"

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"设置文件格式无效：{self.path}")
        return data

    def data_directory(self, demo=False, override: Path | str | None = None) -> Path:
        if override is not None:
            return Path(override).expanduser().resolve()
        key = "demo_data_directory" if demo else "data_directory"
        value = self._read().get(key)
        if value is None:
            return default_data_directory(demo).resolve()
        if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
            raise ValueError(f"设置中的数据目录无效：{self.path}")
        directory = Path(value).resolve()
        # An unavailable custom drive must not silently create an empty inventory.
        if not (directory / "inventory.sqlite3").is_file():
            raise ValueError(f"找不到已设置的数据文件：{directory / 'inventory.sqlite3'}\n"
                             "请检查磁盘是否连接，或使用 --data-dir 指定可用的数据目录。")
        return directory

    def save_data_directory(self, directory: Path | str, demo=False):
        data = self._read()
        data["demo_data_directory" if demo else "data_directory"] = str(Path(directory).resolve())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(filename, self.path)
        finally:
            Path(filename).unlink(missing_ok=True)
