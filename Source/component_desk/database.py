"""SQLite persistence and inventory rules. No GUI dependency."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .specifications import CHIP_SPECS, COMPONENT_SPECS, MODEL_REQUIRED_CATEGORIES, NEW_COMPONENT_SPECS, POWER_TYPES, SIGNED_VOLTAGE_PARAMETERS, current_parameters, field_applies, field_required, power_field_applies

CATEGORIES = ("贴片电容", "贴片电阻", "主控芯片", "电源管理芯片", "协议收发芯片", *NEW_COMPONENT_SPECS)
CSV_FIELDS = (
    "id", "name", "model", "category", "manufacturer", "package",
    "parameters_json", "warning_quantity", "notes", "location", "quantity",
)
SCHEMA_VERSION = 1
MAX_QUANTITY = 1_000_000_000


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def quantity(value, label="数量") -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label}必须是非负整数。")
    try:
        number = int(str(value))
    except (ValueError, TypeError):
        raise ValueError(f"{label}必须是非负整数。") from None
    if not 0 <= number <= MAX_QUANTITY:
        raise ValueError(f"{label}须在 0 到 {MAX_QUANTITY:,} 之间。")
    return number


def format_number(value) -> str:
    return f"{float(value):g}"


def engineering(value, units) -> str:
    number = float(value)
    for factor, unit in units:
        if number >= factor:
            return f"{format_number(number / factor)} {unit}"
    factor, unit = units[-1]
    return f"{format_number(number / factor)} {unit}"


def parameter_summary(category: str, params: dict) -> str:
    if category == "贴片电阻" and "resistance_ohm" in params:
        parts = [engineering(params["resistance_ohm"], [(1e6, "MΩ"), (1e3, "kΩ"), (1, "Ω")])]
        if "tolerance_percent" in params:
            parts.append(f"±{format_number(params['tolerance_percent'])}%")
        if "power_w" in params:
            parts.append(f"{format_number(params['power_w'])} W")
        return " / ".join(parts)
    if category == "贴片电容" and "capacitance_f" in params:
        parts = [engineering(params["capacitance_f"], [(1, "F"), (1e-3, "mF"), (1e-6, "µF"), (1e-9, "nF"), (1e-12, "pF")])]
        if "voltage_v" in params:
            parts.append(f"{format_number(params['voltage_v'])} V")
        if "tolerance_percent" in params:
            parts.append(f"±{format_number(params['tolerance_percent'])}%")
        if params.get("dielectric"):
            parts.append(str(params["dielectric"]))
        return " / ".join(parts)
    parts = []
    if category == "主控芯片":
        for key, unit in [("clock_mhz", "MHz"), ("flash_kb", "KB Flash"), ("ram_kb", "KB RAM")]:
            if key in params:
                parts.append(f"{format_number(params[key])} {unit}")
    elif category == "电源管理芯片":
        if params.get("power_type"):
            parts.append(str(params["power_type"]))
        if params.get("power_type") == "PMU":
            for key, title in (("pmu_dcdc_count", "DCDC"), ("pmu_ldo_count", "LDO")):
                if key in params:
                    parts.append(f"{format_number(params[key])} 路 {title}")
            if params.get("pmu_control_interface"):
                parts.append(str(params["pmu_control_interface"]))
        if "output_voltage_min_v" in params and "output_voltage_max_v" in params:
            parts.append(f"{format_number(params['output_voltage_min_v'])}～{format_number(params['output_voltage_max_v'])} V")
        elif "output_voltage_v" in params:
            parts.append(f"{format_number(params['output_voltage_v'])} V")
        if "output_current_a" in params:
            parts.append(f"{format_number(params['output_current_a'])} A")
    elif category == "协议收发芯片":
        if params.get("protocol"):
            parts.append(str(params["protocol"]))
        for key, unit in [("data_rate_mbps", "Mbps"), ("channel_count", "路")]:
            if key in params:
                parts.append(f"{format_number(params[key])} {unit}")
        if params.get("isolation"):
            parts.append(str(params["isolation"]))
    elif category in NEW_COMPONENT_SPECS:
        summary_keys = {
            "电池管理芯片": ("battery_function", "battery_chemistry", "series_cells", "charge_current_a"),
            "电感": ("inductance_h", "rated_current_a", "saturation_current_a"),
            "TVS管": ("tvs_type", "polarity", "standoff_voltage_v", "junction_capacitance_pf"),
            "二极管": ("diode_type", "reverse_voltage_v", "forward_current_a", "zener_voltage_v"),
            "晶振": ("oscillator_type", "frequency_hz", "load_capacitance_pf", "output_signal"),
            "MOS管": ("channel_type", "vds_rating_v", "continuous_current_a", "rds_on_mohm"),
            "共模电感": ("choke_type", "common_mode_impedance_ohm", "impedance_frequency_hz", "inductance_h", "rated_current_a"),
            "三极管": ("transistor_type", "vce_rating_v", "collector_current_a", "dc_gain"),
            "磁珠": ("impedance_ohm", "impedance_frequency_hz", "rated_current_a"),
            "连接器": ("connector_type", "contact_count", "pitch_mm", "gender"),
            "运算放大器": ("channel_count", "amplifier_type", "gain_bandwidth_hz", "offset_voltage_uv"),
            "逻辑芯片": ("logic_function", "logic_family", "channel_count"),
            "存储芯片": ("memory_type", "capacity_bits", "memory_interface", "clock_frequency_hz"),
        }
        for field in NEW_COMPONENT_SPECS[category]:
            if field.key not in summary_keys[category] or field.key not in params:
                continue
            value = params[field.key]
            if field.kind == "engineering":
                parts.append(engineering(value, field.engineering_units))
            else:
                parts.append(f"{format_number(value) if isinstance(value, (int, float)) else value} {field.unit}".strip())
    return " / ".join(parts) or str(params.get("description", "—"))


def validate_component(data: dict, *, require_current_specs=True) -> dict:
    cleaned = {key: str(data.get(key, "")).strip() for key in (
        "name", "model", "category", "manufacturer", "package", "notes", "photo", "datasheet"
    )}
    if not cleaned["name"]:
        raise ValueError("请填写元件名称。")
    if cleaned["category"] not in CATEGORIES:
        raise ValueError("请选择有效的元件分类。")
    cleaned["warning_quantity"] = quantity(data.get("warning_quantity", 0), "预警数量")
    params = data.get("parameters", {})
    if not isinstance(params, dict):
        raise ValueError("规格参数必须是 JSON 对象。")
    params = current_parameters(cleaned["category"], params)
    for key, value in params.items():
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError(f"参数 {key} 的类型无效。")
        if isinstance(value, (int, float)) and (not math.isfinite(value) or value < 0 and key not in SIGNED_VOLTAGE_PARAMETERS):
            raise ValueError(f"参数 {key} 必须是有限的非负数。")
    if cleaned["category"] in COMPONENT_SPECS:
        if not cleaned["package"]:
            raise ValueError("封装为必填项。")
        if cleaned["category"] in MODEL_REQUIRED_CATEGORIES and not cleaned["model"]:
            raise ValueError("型号为必填项。")
        if cleaned["category"] == "电源管理芯片" and params.get("power_type") not in POWER_TYPES:
            raise ValueError("请选择芯片类型：DCDC、LDO 或 PMU。")
        for field in COMPONENT_SPECS[cleaned["category"]]:
            if not field_applies(field, params):
                continue
            required = field.required
            if cleaned["category"] == "协议收发芯片" and not require_current_specs and field.key != "protocol":
                required = False
            if cleaned["category"] == "电源管理芯片" and require_current_specs:
                required = field_required(field, params.get("power_type", "")) and power_field_applies(
                    field.key, params.get("power_type", ""), params.get("pmu_charger", ""), params.get("ldo_output_mode", ""))
            if field.kind != "range" and required and not str(params.get(field.key, "")).strip():
                raise ValueError(f"请填写{field.title}，此项为必填。")
            if field.kind == "toggle" and field.key in params and params[field.key] not in field.options:
                raise ValueError(f"请选择有效的{field.title}。")
            if field.kind == "range":
                low, high = (f"{field.key}_{endpoint}_v" for endpoint in ("min", "max"))
                if low not in params and high not in params:
                    if required:
                        raise ValueError(f"请填写{field.title}，此项为必填。")
                    continue
                if low not in params or high not in params:
                    raise ValueError(f"{field.title}需要同时填写两个端点。")
                if not all(isinstance(params[key], (int, float)) for key in (low, high)):
                    raise ValueError(f"{field.title}必须使用数值。")
                if params[low] > params[high]:
                    raise ValueError(f"{field.title}的最小值不能大于最大值。")
            elif field.kind in ("number", "integer", "frequency", "engineering") and field.key in params:
                value = params[field.key]
                if not isinstance(value, (int, float)):
                    raise ValueError(f"{field.title}必须使用数值。")
                if (field.kind == "integer" or field.integer_value) and value % 1 != 0:
                    raise ValueError(f"{field.title}必须是整数。")
                if field.positive and value <= 0:
                    raise ValueError(f"{field.title}必须大于零。")
                if field.key == "tolerance_percent" and value > 100:
                    raise ValueError("精度百分比不能超过 100。")
                if cleaned["category"] == "协议收发芯片" and require_current_specs and value <= 0:
                    raise ValueError(f"{field.title}必须大于零。")
                if field.kind == "frequency" and value <= 0:
                    raise ValueError(f"{field.title}必须大于零。")
                if field.key == "output_current_a" and params.get("power_type") == "DCDC" and value <= 0:
                    raise ValueError(f"{field.title}必须大于零。")
                if field.key in {"pmu_charge_voltage_v", "pmu_charge_current_a"} and value <= 0:
                    raise ValueError(f"{field.title}必须大于零。")
    cleaned["parameters"] = dict(params)
    for key in ("photo", "datasheet"):
        if cleaned[key] and (Path(cleaned[key]).name != cleaned[key] or "/" in cleaned[key] or "\\" in cleaned[key]):
            raise ValueError("附件必须存放在程序的附件目录。")
    return cleaned


class Database:
    def __init__(self, directory: Path | str):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.attachments = self.directory / "attachments"
        self.attachments.mkdir(exist_ok=True)
        self.path = self.directory / "inventory.sqlite3"
        self._connect()
        self._initialize()

    def _connect(self):
        self.connection = sqlite3.connect(self.path, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def _initialize(self):
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise ValueError("数据库版本与本程序不兼容。请使用对应版本的软件。")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS components (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', category TEXT NOT NULL,
                manufacturer TEXT NOT NULL DEFAULT '', package TEXT NOT NULL DEFAULT '',
                parameters_json TEXT NOT NULL DEFAULT '{}',
                warning_quantity INTEGER NOT NULL DEFAULT 0 CHECK(warning_quantity >= 0),
                notes TEXT NOT NULL DEFAULT '', photo TEXT NOT NULL DEFAULT '',
                datasheet TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS retired_locations (
                location_id INTEGER PRIMARY KEY REFERENCES locations(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS stocks (
                component_id TEXT NOT NULL REFERENCES components(id),
                location_id INTEGER NOT NULL REFERENCES locations(id),
                quantity INTEGER NOT NULL CHECK(quantity >= 0),
                PRIMARY KEY(component_id, location_id)
            );
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY,
                component_id TEXT NOT NULL REFERENCES components(id),
                location_id INTEGER NOT NULL REFERENCES locations(id),
                kind TEXT NOT NULL, delta INTEGER NOT NULL,
                balance INTEGER NOT NULL CHECK(balance >= 0),
                note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS movement_component ON movements(component_id, id);
            PRAGMA user_version = 1;
        """)

    def close(self):
        self.connection.close()

    def migrate_to(self, directory: Path | str, persist=None) -> bool:
        """Copy to an empty directory and switch this instance only after saving succeeds.

        The original directory is preserved. Failure leaves the source connection usable
        and removes only the files created by this migration.
        """
        target = Path(directory).expanduser().resolve()
        if target == self.directory:
            if persist:
                persist(target)
            return False
        if target.is_relative_to(self.directory) or self.directory.is_relative_to(target):
            raise ValueError("新目录不能是当前数据目录的子目录或父目录，请选择独立的空文件夹。")
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise ValueError("请选择空文件夹。目标目录已有文件，无法迁移到此目录。")
        target.mkdir(parents=True, exist_ok=True)
        installed = []
        candidate = None
        try:
            with tempfile.TemporaryDirectory(prefix=".migration-", dir=target) as temp:
                stage = Path(temp).resolve()
                snapshot = stage / "inventory.sqlite3"
                with closing(sqlite3.connect(snapshot)) as outgoing:
                    self.connection.backup(outgoing)
                shutil.copytree(self.attachments, stage / "attachments")
                if (self.directory / "backups").exists():
                    shutil.copytree(self.directory / "backups", stage / "backups")
                self._validate_snapshot(snapshot)
                for component in self.list_components():
                    for kind in ("photo", "datasheet"):
                        filename = component[kind]
                        if filename and not (stage / "attachments" / filename).is_file():
                            raise ValueError("当前数据缺少引用的附件，请补齐后再迁移。")
                if any(entry.resolve() != stage for entry in target.iterdir()):
                    raise ValueError("目标目录出现了其他文件，请选择空文件夹重试。")
                for name in ("inventory.sqlite3", "attachments", "backups"):
                    if (stage / name).exists():
                        output = target / name
                        if output.exists():
                            raise ValueError("目标目录出现同名文件，迁移已取消。")
                        os.rename(stage / name, output)
                        installed.append(output)
                candidate = sqlite3.connect(target / "inventory.sqlite3", timeout=10)
                candidate.row_factory = sqlite3.Row
                candidate.execute("PRAGMA foreign_keys = ON")
                candidate.execute("SELECT COUNT(*) FROM components").fetchone()
                if persist:
                    persist(target)
            # Keep object identity so all UI actions and app shutdown use the new connection.
            self.connection.close()
            self.directory = target
            self.path = target / "inventory.sqlite3"
            self.attachments = target / "attachments"
            self.connection = candidate
            candidate = None
            return True
        except Exception:
            if candidate is not None:
                candidate.close()
            for output in reversed(installed):
                # These exact paths were created above inside the resolved target.
                if output.parent.resolve() != target:
                    raise RuntimeError("迁移清理路径无效。")
                if output.is_dir():
                    shutil.rmtree(output)
                else:
                    output.unlink(missing_ok=True)
            raise

    def locations(self) -> list[dict]:
        return [dict(row) for row in self.connection.execute("""
            SELECT l.*, COUNT(CASE WHEN s.quantity > 0 THEN 1 END) AS component_count,
                   COALESCE(SUM(s.quantity), 0) AS total_quantity
            FROM locations l LEFT JOIN stocks s ON s.location_id = l.id
            WHERE NOT EXISTS (SELECT 1 FROM retired_locations r WHERE r.location_id=l.id)
            GROUP BY l.id ORDER BY l.name
        """)]

    def add_location(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("库位名称不能为空。")
        try:
            with self.connection:
                row = self.connection.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
                if row and self.connection.execute("SELECT 1 FROM retired_locations WHERE location_id=?", (row["id"],)).fetchone():
                    self.connection.execute("DELETE FROM retired_locations WHERE location_id=?", (row["id"],))
                    return row["id"]
                return self.connection.execute("INSERT INTO locations(name) VALUES (?)", (name,)).lastrowid
        except sqlite3.IntegrityError:
            raise ValueError("此库位名称已存在。") from None

    def rename_location(self, location_id: int, name: str):
        name = name.strip()
        if not name:
            raise ValueError("库位名称不能为空。")
        try:
            with self.connection:
                result = self.connection.execute("""UPDATE locations SET name=? WHERE id=?
                    AND NOT EXISTS (SELECT 1 FROM retired_locations WHERE location_id=locations.id)""", (name, location_id))
                if not result.rowcount:
                    raise ValueError("库位不存在。")
        except sqlite3.IntegrityError:
            raise ValueError("此库位名称已存在。") from None

    def remove_location(self, location_id: int):
        """Remove an empty location from use while retaining any movement history."""
        with self.connection:
            if not self.connection.execute("""SELECT 1 FROM locations WHERE id=?
                AND NOT EXISTS (SELECT 1 FROM retired_locations WHERE location_id=locations.id)""", (location_id,)).fetchone():
                raise ValueError("库位不存在。")
            if self.connection.execute("SELECT 1 FROM stocks WHERE location_id=? AND quantity>0", (location_id,)).fetchone():
                raise ValueError("此库位仍有库存，请先领用或调整库存至零，再删除库位。")
            self.connection.execute("DELETE FROM stocks WHERE location_id=?", (location_id,))
            if self.connection.execute("SELECT 1 FROM movements WHERE location_id=?", (location_id,)).fetchone():
                self.connection.execute("INSERT INTO retired_locations(location_id) VALUES (?)", (location_id,))
            else:
                self.connection.execute("DELETE FROM locations WHERE id=?", (location_id,))

    def _location_id(self, name: str) -> int:
        if not name.strip():
            raise ValueError("请选择存放库位。")
        self.connection.execute("INSERT OR IGNORE INTO locations(name) VALUES (?)", (name.strip(),))
        location_id = self.connection.execute("SELECT id FROM locations WHERE name=?", (name.strip(),)).fetchone()[0]
        self.connection.execute("DELETE FROM retired_locations WHERE location_id=?", (location_id,))
        return location_id

    def save_component(self, data: dict, component_id: str | None = None,
                       initial_location: str = "", initial_quantity: int = 0) -> str:
        cleaned = validate_component(data)
        amount = quantity(initial_quantity)
        stamp = now()
        fields = ("name", "model", "category", "manufacturer", "package", "parameters_json",
                  "warning_quantity", "notes", "photo", "datasheet")
        values = [json.dumps(cleaned["parameters"], ensure_ascii=False) if key == "parameters_json"
                  else cleaned[key] for key in fields]
        with self.connection:
            if component_id:
                result = self.connection.execute(
                    f"UPDATE components SET {', '.join(f'{key}=?' for key in fields)}, updated_at=? WHERE id=?",
                    (*values, stamp, component_id),
                )
                if not result.rowcount:
                    raise ValueError("此元件不存在。")
            else:
                component_id = str(uuid.uuid4())
                self.connection.execute(
                    f"INSERT INTO components(id, {', '.join(fields)}, created_at, updated_at) "
                    f"VALUES ({', '.join('?' for _ in range(len(fields) + 3))})",
                    (component_id, *values, stamp, stamp),
                )
                if amount:
                    self._change_stock(component_id, self._location_id(initial_location), "入库", amount, "初始库存")
        return component_id

    def list_components(self, search="", category="", package="", location_id=None, low_only=False) -> list[dict]:
        rows = self.connection.execute("""
            SELECT c.*, COALESCE(SUM(s.quantity), 0) AS total_quantity
            FROM components c LEFT JOIN stocks s ON s.component_id = c.id
            GROUP BY c.id ORDER BY c.created_at, c.rowid
        """).fetchall()
        stock_rows = self.connection.execute("""
            SELECT s.*, l.name AS location FROM stocks s JOIN locations l ON l.id=s.location_id
            ORDER BY l.name
        """).fetchall()
        by_component = {}
        for stock in stock_rows:
            by_component.setdefault(stock["component_id"], []).append(dict(stock))
        result = []
        for row in rows:
            item = dict(row)
            item["parameters"] = current_parameters(item["category"], json.loads(item.pop("parameters_json")))
            item["summary"] = parameter_summary(item["category"], item["parameters"])
            item["stocks"] = by_component.get(item["id"], [])
            item["low"] = item["total_quantity"] < item["warning_quantity"]
            if category and item["category"] != category:
                continue
            if package and item["package"] != package:
                continue
            if location_id is not None and not any(s["location_id"] == location_id for s in item["stocks"]):
                continue
            if low_only and not item["low"]:
                continue
            searchable = " ".join([item["name"], item["model"], item["manufacturer"], item["category"],
                                  item["package"], item["summary"], item["notes"],
                                  *(s["location"] for s in item["stocks"])])
            if search.strip() and not all(token.casefold() in searchable.casefold() for token in search.split()):
                continue
            result.append(item)
        return result

    def get_component(self, component_id: str) -> dict | None:
        return next((item for item in self.list_components() if item["id"] == component_id), None)

    def remove_component(self, component_id: str):
        """Remove one component and its dependent rows in a single transaction.

        Locations, backup archives and attachment files remain intact; files might
        also be referenced by other components or needed to recover old data.
        """
        with self.connection:
            if not self.connection.execute("SELECT 1 FROM components WHERE id=?", (component_id,)).fetchone():
                raise ValueError("此元件不存在，可能已经被移除。")
            self.connection.execute("DELETE FROM movements WHERE component_id=?", (component_id,))
            self.connection.execute("DELETE FROM stocks WHERE component_id=?", (component_id,))
            self.connection.execute("DELETE FROM components WHERE id=?", (component_id,))

    def statistics(self) -> dict:
        components = self.list_components()
        return {
            "count": len(components), "quantity": sum(item["total_quantity"] for item in components),
            "low": sum(item["low"] for item in components), "locations": len(self.locations()),
            "used_locations": self.connection.execute("SELECT COUNT(DISTINCT location_id) FROM stocks WHERE quantity>0").fetchone()[0],
            "categories": {category: sum(item["category"] == category for item in components) for category in CATEGORIES},
        }

    def _change_stock(self, component_id, location_id, kind, amount, note):
        if not self.connection.execute("SELECT 1 FROM components WHERE id=?", (component_id,)).fetchone():
            raise ValueError("元件不存在。")
        row = self.connection.execute("SELECT quantity FROM stocks WHERE component_id=? AND location_id=?",
                                      (component_id, location_id)).fetchone()
        current = row[0] if row else 0
        delta = amount if kind == "入库" else -amount if kind == "领用" else amount - current
        balance = current + delta
        if balance < 0:
            raise ValueError(f"所选库位只有 {current:,} 件，领用数量不能超过库存。")
        if balance > MAX_QUANTITY:
            raise ValueError("该库位库存超过允许的数量上限。")
        self.connection.execute("""
            INSERT INTO stocks(component_id, location_id, quantity) VALUES (?, ?, ?)
            ON CONFLICT(component_id, location_id) DO UPDATE SET quantity=excluded.quantity
        """, (component_id, location_id, balance))
        self.connection.execute("""
            INSERT INTO movements(component_id, location_id, kind, delta, balance, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (component_id, location_id, kind, delta, balance, note.strip(), now()))

    def change_stock(self, component_id: str, location_id: int, kind: str, amount: int, note=""):
        if kind not in ("入库", "领用", "盘点"):
            raise ValueError("库存操作类型无效。")
        amount = quantity(amount)
        if kind != "盘点" and amount == 0:
            raise ValueError("入库和领用数量必须大于 0。")
        with self.connection:
            if not self.connection.execute("""SELECT 1 FROM locations WHERE id=?
                AND NOT EXISTS (SELECT 1 FROM retired_locations WHERE location_id=locations.id)""", (location_id,)).fetchone():
                raise ValueError("所选库位不存在。")
            self._change_stock(component_id, location_id, kind, amount, note)

    def history(self, component_id=None, limit=1000) -> list[dict]:
        query = """
            SELECT m.*, c.name, c.model, l.name AS location FROM movements m
            JOIN components c ON c.id=m.component_id JOIN locations l ON l.id=m.location_id
        """
        args = []
        if component_id:
            query += " WHERE m.component_id=?"
            args.append(component_id)
        query += " ORDER BY m.id DESC LIMIT ?"
        args.append(limit)
        return [dict(row) for row in self.connection.execute(query, args)]

    def copy_attachment(self, source: Path | str, kind: str) -> str:
        source = Path(source)
        allowed = {"photo": {".png", ".jpg", ".jpeg", ".bmp", ".webp"}, "datasheet": {".pdf"}}
        if kind not in allowed or source.suffix.lower() not in allowed[kind]:
            raise ValueError("附件格式无效。照片支持 PNG/JPG/BMP/WebP，数据手册支持 PDF。")
        if not source.is_file():
            raise ValueError("所选附件不存在。")
        filename = f"{uuid.uuid4().hex}{source.suffix.lower()}"
        shutil.copy2(source, self.attachments / filename)
        return filename

    def export_csv(self, destination: Path | str):
        with Path(destination).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for item in self.list_components():
                base = {key: item[key] for key in CSV_FIELDS if key in item}
                base["parameters_json"] = json.dumps(item["parameters"], ensure_ascii=False)
                stocks = item["stocks"] or [{"location": "", "quantity": 0}]
                for stock in stocks:
                    writer.writerow({**base, "location": stock["location"], "quantity": stock["quantity"]})

    def import_csv(self, source: Path | str) -> int:
        """Import new components only. Entire file validates before writing; all writes atomic."""
        groups = {}
        with Path(source).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(CSV_FIELDS).issubset(reader.fieldnames):
                raise ValueError("CSV 列名不正确。请先导出 CSV，按导出格式填写。")
            for line, row in enumerate(reader, 2):
                try:
                    component_id = row["id"].strip() or str(uuid.uuid4())
                    uuid.UUID(component_id)
                    data = {**row, "parameters": json.loads(row["parameters_json"] or "{}")}
                    data = validate_component(data)
                    amount = quantity(row["quantity"])
                    location = row["location"].strip()
                    if amount and not location:
                        raise ValueError("库存大于零时必须填写库位。")
                    if component_id in groups and data != groups[component_id]["data"]:
                        raise ValueError("相同 ID 的元件资料不一致。")
                    group = groups.setdefault(component_id, {"data": data, "stocks": {}})
                    if location in group["stocks"]:
                        raise ValueError("相同元件和库位重复出现。")
                    group["stocks"][location] = amount
                except (ValueError, TypeError, AttributeError) as error:
                    raise ValueError(f"CSV 第 {line} 行：{error}") from None
        with self.connection:
            for component_id, group in groups.items():
                if self.connection.execute("SELECT 1 FROM components WHERE id=?", (component_id,)).fetchone():
                    raise ValueError("CSV 中包含已存在的元件 ID。导入只新增元件，不覆盖现有库存。")
                data = group["data"]
                stamp = now()
                self.connection.execute("""
                    INSERT INTO components(id,name,model,category,manufacturer,package,parameters_json,
                        warning_quantity,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """, (component_id, data["name"], data["model"], data["category"], data["manufacturer"],
                      data["package"], json.dumps(data["parameters"], ensure_ascii=False), data["warning_quantity"],
                      data["notes"], stamp, stamp))
                for location, amount in group["stocks"].items():
                    if location:
                        self._change_stock(component_id, self._location_id(location), "入库", amount, "CSV 导入")
        return len(groups)

    def backup(self, destination: Path | str):
        destination = Path(destination).resolve()
        if destination == self.path or destination.is_relative_to(self.attachments):
            raise ValueError("备份文件不能覆盖数据库或存放在附件目录。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="backup-", dir=self.directory) as temp:
            snapshot = Path(temp) / "inventory.sqlite3"
            with closing(sqlite3.connect(snapshot)) as target:
                self.connection.backup(target)
            archive_path = Path(temp) / "backup.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "inventory.sqlite3")
                archive.writestr("manifest.json", json.dumps({"app": "ComponentDesk", "schema": SCHEMA_VERSION, "created_at": now()}))
                for file in self.attachments.iterdir():
                    if file.is_file():
                        archive.write(file, f"attachments/{file.name}")
            # Copy next to destination so the final replace is atomic even on another drive.
            fd, temporary_name = tempfile.mkstemp(prefix=".component-backup-", dir=destination.parent)
            os.close(fd)
            try:
                shutil.copyfile(archive_path, temporary_name)
                os.replace(temporary_name, destination)
            finally:
                Path(temporary_name).unlink(missing_ok=True)

    @staticmethod
    def _validate_snapshot(snapshot: Path):
        with closing(sqlite3.connect(snapshot)) as check:
            check.row_factory = sqlite3.Row
            if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("备份中的数据库损坏。")
            if check.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise ValueError("备份的数据库版本不兼容。")
            required = {
                "components": {"id", "name", "model", "category", "manufacturer", "package", "parameters_json", "warning_quantity", "notes", "photo", "datasheet", "created_at", "updated_at"},
                "locations": {"id", "name"},
                "stocks": {"component_id", "location_id", "quantity"},
                "movements": {"id", "component_id", "location_id", "kind", "delta", "balance", "note", "created_at"},
            }
            for table, columns in required.items():
                actual = {row["name"] for row in check.execute(f"PRAGMA table_info({table})")}
                if not columns.issubset(actual):
                    raise ValueError("备份中的数据库结构不完整。")
            if check.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("备份中的库存关联信息无效。")
            if check.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='retired_locations'").fetchone():
                if "location_id" not in {row["name"] for row in check.execute("PRAGMA table_info(retired_locations)")}:
                    raise ValueError("备份中的库位结构不完整。")
                if check.execute("""SELECT 1 FROM retired_locations r LEFT JOIN locations l ON l.id=r.location_id
                    WHERE l.id IS NULL""").fetchone() or check.execute("""SELECT 1 FROM retired_locations r
                    JOIN stocks s ON s.location_id=r.location_id WHERE s.quantity>0""").fetchone():
                    raise ValueError("备份中的已删除库位信息无效。")
            for row in check.execute("SELECT * FROM components"):
                # Older backups may predate newly required specification fields.
                validate_component({**dict(row), "parameters": json.loads(row["parameters_json"])}, require_current_specs=False)
            for row in check.execute("SELECT quantity FROM stocks"):
                quantity(row[0])

    def restore(self, source: Path | str) -> Path:
        """Validate first, keep automatic backup, and roll back filesystem replacement on failure."""
        with tempfile.TemporaryDirectory(prefix="restore-", dir=self.directory) as temp:
            extracted = Path(temp) / "extracted"
            extracted.mkdir()
            (extracted / "attachments").mkdir()
            with zipfile.ZipFile(source) as archive:
                if sum(info.file_size for info in archive.infolist()) > 1024 ** 3:
                    raise ValueError("备份展开后的大小超过 1 GB。")
                seen = set()
                for info in archive.infolist():
                    name = info.filename
                    if info.is_dir() and name == "attachments/":
                        continue
                    allowed = name in ("inventory.sqlite3", "manifest.json") or (
                        name.startswith("attachments/") and len(name.split("/")) == 2
                        and name.split("/")[1] not in ("", ".", "..") and "\\" not in name and ":" not in name
                    )
                    if not allowed or name in seen:
                        raise ValueError("备份包含无效或重复的文件路径。")
                    seen.add(name)
                    target = (extracted / name).resolve()
                    if not target.is_relative_to(extracted.resolve()):
                        raise ValueError("备份附件路径无效。")
                    with archive.open(info) as incoming, target.open("wb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
            if not {"inventory.sqlite3", "manifest.json"}.issubset(seen):
                raise ValueError("备份缺少数据库或清单。")
            manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("app") != "ComponentDesk" or manifest.get("schema") != SCHEMA_VERSION:
                raise ValueError("这不是兼容的元件仓库备份。")
            self._validate_snapshot(extracted / "inventory.sqlite3")
            with closing(sqlite3.connect(extracted / "inventory.sqlite3")) as incoming:
                for photo, datasheet in incoming.execute("SELECT photo,datasheet FROM components"):
                    if any(name and not (extracted / "attachments" / name).is_file() for name in (photo, datasheet)):
                        raise ValueError("备份缺少元件引用的附件。")
            rollback_backup = self.directory / "backups" / f"before-restore-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.zip"
            self.backup(rollback_backup)
            old_db, old_attachments = Path(temp) / "old.sqlite3", Path(temp) / "old-attachments"
            self.close()
            try:
                os.replace(self.path, old_db)
                os.replace(self.attachments, old_attachments)
                os.replace(extracted / "inventory.sqlite3", self.path)
                os.replace(extracted / "attachments", self.attachments)
            except Exception:
                if old_db.exists():
                    os.replace(old_db, self.path)
                if old_attachments.exists():
                    if self.attachments.exists():
                        shutil.rmtree(self.attachments)
                    os.replace(old_attachments, self.attachments)
                raise
            finally:
                self._connect()
                self._initialize()
            return rollback_backup

    def seed_demo(self):
        if self.statistics()["count"]:
            return
        rows = [
            ({"name": "贴片电阻 4.7 kΩ", "category": "贴片电阻", "package": "0603", "parameters": {"resistance_ohm": 4700, "tolerance_percent": 1, "power_w": 0.1}, "warning_quantity": 100, "notes": "常用于上拉电阻，优先领用 A柜库存。"}, "A柜 · 03格", 1000),
            ({"name": "贴片电阻 10 kΩ", "category": "贴片电阻", "package": "0603", "parameters": {"resistance_ohm": 10000, "tolerance_percent": 1, "power_w": 0.1}, "warning_quantity": 100}, "A柜 · 04格", 2400),
            ({"name": "贴片电容 100 nF", "category": "贴片电容", "package": "0603", "parameters": {"capacitance_f": 1e-7, "voltage_v": 50, "tolerance_percent": 10, "dielectric": "X7R"}, "warning_quantity": 200}, "B柜 · 01格", 3600),
            ({"name": "贴片电容 10 µF", "model": "CAP10UF-25", "category": "贴片电容", "package": "0805", "parameters": {"capacitance_f": 1e-5, "voltage_v": 25, "tolerance_percent": 10, "dielectric": "X5R"}, "warning_quantity": 5}, "B柜 · 02格", 24),
            ({"name": "贴片电阻 1 MΩ", "category": "贴片电阻", "package": "1206", "parameters": {"resistance_ohm": 1e6, "tolerance_percent": 1, "power_w": 0.25}, "warning_quantity": 10}, "A柜 · 05格", 6),
            ({"name": "贴片电容 22 pF", "category": "贴片电容", "package": "0402", "parameters": {"capacitance_f": 22e-12, "voltage_v": 50, "tolerance_percent": 5, "dielectric": "C0G/NP0"}, "warning_quantity": 3}, "B柜 · 06格", 12),
        ]
        first_id = None
        for data, location, amount in rows:
            component_id = self.save_component(data, initial_location=location, initial_quantity=amount)
            first_id = first_id or component_id
        spare = self.add_location("备用盒 · 02格")
        self.change_stock(first_id, spare, "入库", 280, "备用库存")
