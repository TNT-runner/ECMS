"""Main desktop window, modeled after design/component-manager-mockup.svg."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QScrollArea, QSizePolicy, QSplitter,
    QStackedWidget, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .database import CATEGORIES, Database, engineering, format_number
from .dialogs import CategoryComboBox, ComponentDialog, LocationDialog, SettingsDialog, StockDialog, button, error, label
from .settings import AppSettings
from .specifications import COMPONENT_SPECS
from .style import icon


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def line():
    widget = QFrame()
    widget.setObjectName("Line")
    return widget


class NumericItem(QTableWidgetItem):
    def __init__(self, value):
        super().__init__(f"{value:,}")
        self.number = value

    def __lt__(self, other):
        return self.number < other.number if isinstance(other, NumericItem) else super().__lt__(other)


class InventoryTable(QTableWidget):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.columnCount():
            remaining = self.viewport().width() - sum(self.columnWidth(col) for col in range(1, self.columnCount()))
            self.setColumnWidth(0, max(220, remaining))


class ComponentDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        painter.save()
        rect = option.rect
        category = data["category"]
        symbol = {"贴片电阻": "resistor", "贴片电容": "capacitor", "电感": "inductor", "共模电感": "inductor",
                  "TVS管": "diode", "二极管": "diode", "MOS管": "mosfet", "晶振": "crystal", "电池管理芯片": "battery",
                  "三极管": "transistor", "磁珠": "inductor", "连接器": "connector"}.get(category, "chip")
        colors = {"贴片电阻": ("#E3F0EA", "#438F7B"), "贴片电容": ("#EDF3FC", "#698FC5"),
                  "主控芯片": ("#F0EDFB", "#7962B0"), "电源管理芯片": ("#FFF4E7", "#A97530"),
                  "协议收发芯片": ("#E8F4FA", "#367B99"), "电池管理芯片": ("#E3F0EA", "#438F7B"),
                  "电感": ("#FFF4E7", "#A97530"), "共模电感": ("#FFF4E7", "#A97530"),
                  "TVS管": ("#E8F4FA", "#367B99"), "二极管": ("#E8F4FA", "#367B99"),
                  "晶振": ("#F0EDFB", "#7962B0"), "MOS管": ("#EDF3FC", "#698FC5"),
                  "三极管": ("#EDF3FC", "#698FC5"), "磁珠": ("#FFF4E7", "#A97530"),
                  "连接器": ("#E3F0EA", "#438F7B"), "运算放大器": ("#F0EDFB", "#7962B0"),
                  "逻辑芯片": ("#E8F4FA", "#367B99"), "存储芯片": ("#F0EDFB", "#7962B0")}
        bg, fg = colors.get(category, ("#EEF2F6", "#8192A7"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect.x() + 12, rect.y() + 15, 32, 32, 8, 8)
        icon(symbol, fg).paint(painter, rect.x() + 18, rect.y() + 21, 20, 20)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#215E51" if option.state & QStyle.StateFlag.State_Selected else "#33465C"))
        text_rect = rect.adjusted(48, 10, -48, -30)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, painter.fontMetrics().elidedText(data["name"], Qt.TextElideMode.ElideRight, text_rect.width()))
        font.setBold(False)
        font.setPointSizeF(max(8, font.pointSizeF() - 1))
        painter.setFont(font)
        painter.setPen(QColor("#7B8DA2"))
        subtitle = " · ".join(filter(None, [category, data["manufacturer"]]))
        text_rect = rect.adjusted(48, 32, -48, -8)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, painter.fontMetrics().elidedText(subtitle, Qt.TextElideMode.ElideRight, text_rect.width()))
        painter.restore()


class MainWindow(QMainWindow):
    def __init__(self, db: Database, demo=False, settings=None, directory_override=False):
        super().__init__()
        self.db = db
        self.demo = demo
        self.settings = settings if settings is not None else AppSettings()
        self.directory_override = directory_override
        self.selected_id = None
        self.setWindowTitle("元件仓库 · 个人离线版" + (" · 演示数据" if demo else ""))
        self.setWindowIcon(icon("chip", "#138E82"))
        self.resize(1536, 960)
        self.setMinimumSize(1180, 740)
        container = QWidget()
        self.setCentralWidget(container)
        root = QHBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._build_sidebar(root)
        workspace = QWidget()
        workspace.setObjectName("Workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        root.addWidget(workspace, 1)
        self._build_header(workspace_layout)
        body = QVBoxLayout()
        body.setContentsMargins(28, 24, 28, 12)
        body.setSpacing(20)
        workspace_layout.addLayout(body, 1)
        self._build_statistics(body)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self._build_inventory()
        self._build_history()
        self._shortcuts = []
        for key, action in [("Ctrl+N", self.add_component), ("Ctrl+F", self.focus_search), ("Ctrl+B", self.backup)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)
            self._shortcuts.append(shortcut)
        self.refresh()

    def _build_sidebar(self, root):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(16, 26, 16, 20)
        layout.setSpacing(5)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon("chip", "#60D0C0", 32).pixmap(32, 32))
        brand.addWidget(logo)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        texts.addWidget(label("元件仓库", "Brand"))
        texts.addWidget(label("COMPONENT DESK", "BrandSub"))
        brand.addLayout(texts)
        layout.addLayout(brand)
        layout.addSpacing(20)
        layout.addWidget(label("库存管理", "NavSection"))
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = {}
        for key, title, symbol in [("all", "全部元件", "grid"), ("low", "库存不足", "alert"), ("history", "出入库记录", "history")]:
            nav = button(title, "Nav", symbol, lambda checked=False, k=key: self.navigate(k))
            nav.setCheckable(True)
            self.nav_group.addButton(nav)
            self.nav_buttons[key] = nav
            layout.addWidget(nav)
        self.nav_buttons["all"].setChecked(True)
        layout.addSpacing(10)
        layout.addWidget(label("工具", "NavSection"))
        layout.addWidget(button("库位管理", "Nav", "box", self.manage_locations))
        layout.addWidget(button("导入 / 导出", "Nav", "download", self.import_export_dialog))
        layout.addWidget(button("备份与恢复", "Nav", "folder", self.backup_dialog))
        layout.addStretch()
        local = QFrame()
        local.setObjectName("LocalBadge")
        local_layout = QVBoxLayout(local)
        local_layout.setContentsMargins(12, 12, 12, 12)
        local_layout.addWidget(label("● 数据保存在本机", "LocalText"))
        self.backup_label = label("尚未创建备份", "BrandSub")
        self.backup_label.setWordWrap(True)
        local_layout.addWidget(self.backup_label)
        layout.addWidget(local)
        layout.addSpacing(12)
        layout.addWidget(button("设置 / 数据目录", "Nav", "settings", self.settings_dialog))
        scroll = QScrollArea()
        scroll.setObjectName("SidebarScroll")
        scroll.setFixedWidth(212)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(sidebar)
        root.addWidget(scroll)

    def _build_header(self, root):
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(76)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 0, 28, 0)
        self.page_title = label("我的元件", "Title")
        layout.addWidget(self.page_title)
        layout.addSpacing(12)
        badge = label("● 演示数据 · 离线可用" if self.demo else "● 离线可用", "Offline")
        badge.setFixedHeight(28)
        layout.addWidget(badge)
        layout.addStretch()
        layout.addWidget(label("个人工作空间"))
        root.addWidget(header)

    def _build_statistics(self, root):
        row = QHBoxLayout()
        row.setSpacing(16)
        self.stat_labels = {}
        for key, title, symbol, color in [("count", "元件种类", "chip", "#5A91BE"), ("quantity", "库存总数量", "box", "#2C9C88"),
                                          ("low", "库存不足", "alert", "#CA943C"), ("locations", "已使用库位", "grid", "#8B80C1")]:
            card = QFrame()
            card.setObjectName("Card")
            card.setFixedHeight(94)
            layout = QHBoxLayout(card)
            layout.setContentsMargins(20, 13, 20, 13)
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(label(title))
            value = label("0", "WarningValue" if key == "low" else "StatValue")
            self.stat_labels[key] = value
            text.addWidget(value)
            layout.addLayout(text, 1)
            image = QLabel()
            image.setPixmap(icon(symbol, color, 28).pixmap(28, 28))
            layout.addWidget(image)
            row.addWidget(card, 1)
        root.addLayout(row)

    def _build_inventory(self):
        inventory = QWidget()
        layout = QVBoxLayout(inventory)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)
        card = QFrame()
        card.setObjectName("Card")
        card.setMinimumWidth(540)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 8)
        card_layout.setSpacing(0)
        controls = QVBoxLayout()
        controls.setContentsMargins(18, 18, 18, 14)
        controls.setSpacing(12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("搜索型号、参数、封装或存放位置…")
        self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(170)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(160)
        self.search_timer.timeout.connect(self.reload_table)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        toolbar.addWidget(self.search, 1)
        self.in_button = button("入库", icon_name="in", callback=lambda: self.stock_action("入库"))
        self.out_button = button("领用", icon_name="out", callback=lambda: self.stock_action("领用"))
        toolbar.addWidget(self.in_button)
        toolbar.addWidget(self.out_button)
        toolbar.addWidget(button("新增元件", "Primary", "plus", self.add_component))
        controls.addLayout(toolbar)
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.category_filter = CategoryComboBox()
        self.category_filter.addItem("类别：全部", "")
        for category in CATEGORIES:
            self.category_filter.addItem(category, category)
        self.package_filter = CategoryComboBox()
        self.location_filter = CategoryComboBox()
        for combo in (self.category_filter, self.package_filter, self.location_filter):
            combo.setMinimumWidth(104)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.currentIndexChanged.connect(self.filters_changed)
            filters.addWidget(combo)
        self.low_only = QCheckBox("库存不足")
        self.low_only.toggled.connect(self.filters_changed)
        filters.addWidget(self.low_only)
        controls.addLayout(filters)
        card_layout.addLayout(controls)
        self.table = InventoryTable(0, 6)
        self.table.setHorizontalHeaderLabels(["元件名称 / 型号", "关键参数", "封装", "库存", "存放位置", "状态"])
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(False)
        self.table.setItemDelegateForColumn(0, ComponentDelegate(self.table))
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 83)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 137)
        self.table.setColumnWidth(5, 68)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(65)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.itemDoubleClicked.connect(lambda: self.edit_component())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_menu)
        card_layout.addWidget(self.table, 1)
        self.empty_table = label("还没有元件，点击“新增元件”开始建立你的库存。")
        self.empty_table.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_table.setWordWrap(True)
        self.empty_table.setContentsMargins(20, 30, 20, 30)
        card_layout.addWidget(self.empty_table)
        footer = QHBoxLayout()
        footer.setContentsMargins(18, 10, 18, 2)
        self.result_count = label("")
        footer.addWidget(self.result_count)
        footer.addStretch()
        footer.addWidget(label("双击编辑 · 右键查看更多操作"))
        card_layout.addLayout(footer)
        left_area = QWidget()
        left_layout = QVBoxLayout(left_area)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(20)
        left_layout.addWidget(card, 1)
        self._build_recent(left_layout)
        splitter.addWidget(left_area)
        self.detail_card = QFrame()
        self.detail_card.setObjectName("Card")
        self.detail_card.setMinimumWidth(325)
        detail_layout = QVBoxLayout(self.detail_card)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.setContentsMargins(20, 16, 20, 16)
        header.addWidget(label("元件详情", "Heading"))
        header.addStretch()
        self.edit_button = button("编辑资料", "Link", callback=self.edit_component)
        header.addWidget(self.edit_button)
        detail_layout.addLayout(header)
        detail_layout.addWidget(line())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        detail_body = QWidget()
        detail_body.setObjectName("DetailBody")
        self.detail_content = QVBoxLayout(detail_body)
        self.detail_content.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.detail_content.setContentsMargins(20, 16, 20, 16)
        self.detail_content.setSpacing(12)
        scroll.setWidget(detail_body)
        detail_layout.addWidget(scroll, 1)
        detail_layout.addWidget(line())
        actions = QHBoxLayout()
        actions.setContentsMargins(20, 16, 20, 16)
        self.detail_in = button("入库", "Primary", "plus", lambda: self.stock_action("入库"))
        self.detail_out = button("领用", icon_name="out", callback=lambda: self.stock_action("领用"))
        actions.addWidget(self.detail_in, 1)
        actions.addWidget(self.detail_out, 1)
        detail_layout.addLayout(actions)
        splitter.addWidget(self.detail_card)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([880, 380])
        self.pages.addWidget(inventory)

    def _build_history(self):
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        header = QHBoxLayout()
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("搜索元件、库位、操作类型或备注…")
        self.history_search.setClearButtonEnabled(True)
        self.history_search.textChanged.connect(self.reload_history)
        header.addWidget(self.history_search, 1)
        self.history_component_filter = CategoryComboBox()
        self.history_component_filter.setMinimumWidth(210)
        self.history_component_filter.currentIndexChanged.connect(self.reload_history)
        header.addWidget(self.history_component_filter)
        layout.addLayout(header)
        layout.addWidget(label("保留每次库存变动的时间、数量与操作后的余额。"))
        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(["时间", "元件名称", "库位", "操作", "变动数量", "库位余额", "备注"])
        self.history_table.verticalHeader().hide()
        self.history_table.setShowGrid(False)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for col, width in enumerate([165, 235, 145, 70, 100, 100, 180]):
            self.history_table.setColumnWidth(col, width)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.history_table, 1)
        self.history_count = label("")
        layout.addWidget(self.history_count)
        self.pages.addWidget(card)

    def _build_recent(self, root):
        card = QFrame()
        card.setObjectName("Card")
        card.setFixedHeight(94)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 12)
        heading = QHBoxLayout()
        heading.addWidget(label("最近操作", "Heading"))
        heading.addStretch()
        heading.addWidget(button("查看全部 →", "Link", callback=lambda: self.navigate("history")))
        layout.addLayout(heading)
        self.recent_text = label("还没有出入库记录。")
        self.recent_text.setWordWrap(True)
        layout.addWidget(self.recent_text)
        root.addWidget(card)

    def focus_search(self):
        search = self.history_search if self.pages.currentIndex() == 1 else self.search
        search.setFocus()
        search.selectAll()

    def navigate(self, key):
        self.nav_buttons[key].setChecked(True)
        if key == "history":
            self.pages.setCurrentIndex(1)
            self.page_title.setText("出入库记录")
            self.reload_history()
            return
        self.pages.setCurrentIndex(0)
        self.page_title.setText("库存不足" if key == "low" else "我的元件")
        self.category_filter.blockSignals(True)
        self.low_only.blockSignals(True)
        self.category_filter.setCurrentIndex(0)
        self.low_only.setChecked(key == "low")
        self.category_filter.blockSignals(False)
        self.low_only.blockSignals(False)
        self.reload_table()

    def filters_changed(self):
        category = self.category_filter.currentData()
        key = "low" if self.low_only.isChecked() else "all"
        self.nav_buttons[key].setChecked(True)
        self.page_title.setText(category or ("库存不足" if key == "low" else "我的元件"))
        self.reload_table()

    def refresh(self, select_id=None):
        if select_id:
            self.selected_id = select_id
        stats = self.db.statistics()
        self.stat_labels["count"].setText(f"{stats['count']:,}")
        self.stat_labels["quantity"].setText(f"{stats['quantity']:,}")
        self.stat_labels["low"].setText(str(stats["low"]))
        self.stat_labels["locations"].setText(f"{stats['used_locations']} / {stats['locations']}")
        self.nav_buttons["all"].setText(f"全部元件    {stats['count']}")
        self.nav_buttons["low"].setText(f"库存不足    {stats['low']}")
        components = self.db.list_components()
        for combo, entries in [
            (self.package_filter, [("封装：全部", "")] + [(p, p) for p in sorted({c["package"] for c in components if c["package"]})]),
            (self.location_filter, [("库位：全部", None)] + [(row["name"], row["id"]) for row in self.db.locations()]),
            (self.history_component_filter, [("全部元件", None)] + [(c["name"], c["id"]) for c in components]),
        ]:
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for title, data in entries:
                combo.addItem(title, data)
            index = combo.findData(previous)
            combo.setCurrentIndex(max(index, 0))
            combo.blockSignals(False)
        self.reload_table()
        self.reload_history()
        recent = self.db.history(limit=1)
        if recent:
            row = recent[0]
            self.recent_text.setText(f"{row['created_at'].replace('T', ' ')}    {row['name']}    {row['kind']} {row['delta']:+,} 件    {row['location']}    · 已保存到本地")
        else:
            self.recent_text.setText("还没有出入库记录。新增元件时可以填写初始库存。")
        backups = sorted((self.db.directory / "backups").glob("*.zip"), key=lambda p: p.stat().st_mtime) if (self.db.directory / "backups").exists() else []
        if backups:
            self.backup_label.setText("最近备份：" + datetime.fromtimestamp(backups[-1].stat().st_mtime).strftime("%m-%d %H:%M"))
        else:
            self.backup_label.setText("尚未创建备份")

    def reload_table(self):
        items = self.db.list_components(
            self.search.text(), self.category_filter.currentData() or "", self.package_filter.currentData() or "",
            self.location_filter.currentData(), self.low_only.isChecked(),
        )
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(items))
        for row, data in enumerate(items):
            locations = [s for s in data["stocks"] if s["quantity"] > 0]
            location_text = locations[0]["location"] if locations else "未存放"
            if len(locations) > 1:
                location_text += f"  +{len(locations) - 1}"
            cells = [data["name"], data["summary"], data["package"] or "—", data["total_quantity"], location_text,
                     "不足" if data["low"] else "无库存" if not data["total_quantity"] else "充足"]
            for col, text in enumerate(cells):
                cell = NumericItem(text) if col == 3 else QTableWidgetItem(str(text))
                cell.setData(Qt.ItemDataRole.UserRole, data if col == 0 else data["id"])
                cell.setToolTip(str(text) if col != 4 else "\n".join(f"{s['location']}：{s['quantity']:,} 件" for s in data["stocks"]))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 5 or col == 3 and data["low"]:
                    cell.setForeground(QColor("#B37B27" if data["low"] else "#4B8C77" if data["total_quantity"] else "#7B8DA2"))
                self.table.setItem(row, col, cell)
            self.table.setRowHeight(row, 64)
        self.table.setSortingEnabled(True)
        selected_row = next((row for row in range(self.table.rowCount()) if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)["id"] == self.selected_id), 0)
        if items:
            self.table.selectRow(selected_row)
        self.table.blockSignals(False)
        self.empty_table.setVisible(not items)
        self.empty_table.setText("没有符合条件的元件，请调整搜索或筛选条件。" if self.db.statistics()["count"] else "还没有元件，点击“新增元件”开始建立你的库存。")
        self.result_count.setText(f"当前显示 {len(items):,} 种 · 共 {self.db.statistics()['count']:,} 种元件")
        self.selection_changed()

    def selection_changed(self):
        row = self.table.currentRow()
        data = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 and self.table.item(row, 0) else None
        self.selected_id = data["id"] if data else None
        for widget in (self.in_button, self.out_button, self.edit_button, self.detail_in, self.detail_out):
            widget.setEnabled(data is not None)
        self.show_detail(data)

    def show_detail(self, data):
        clear_layout(self.detail_content)
        if not data:
            empty = label("选择一个元件，即可查看规格参数、库位库存和附件。")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.detail_content.addStretch()
            self.detail_content.addWidget(empty)
            self.detail_content.addStretch()
            return
        header = QHBoxLayout()
        photo = QLabel()
        photo.setObjectName("Photo")
        photo.setFixedSize(70, 70)
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(self.db.attachments / data["photo"])) if data["photo"] else QPixmap()
        photo.setPixmap(pixmap.scaled(66, 66, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) if not pixmap.isNull() else icon("chip", "#7FA69B", 40).pixmap(40, 40))
        header.addWidget(photo)
        titles = QVBoxLayout()
        name = label(data["name"], "Heading")
        name.setWordWrap(True)
        titles.addWidget(name)
        subtitle = label(" · ".join(filter(None, [data["manufacturer"] or data["category"], data["package"]])))
        subtitle.setWordWrap(True)
        titles.addWidget(subtitle)
        titles.addWidget(label("ID: " + data["id"][:8]))
        header.addLayout(titles, 1)
        self.detail_content.addLayout(header)
        stock = QFrame()
        stock.setObjectName("StockBox")
        stock_layout = QVBoxLayout(stock)
        stock_layout.setContentsMargins(16, 12, 16, 12)
        stock_layout.addWidget(label("当前库存"))
        value_row = QHBoxLayout()
        value_row.addWidget(label(f"{data['total_quantity']:,}", "StockValue"))
        value_row.addWidget(label("件"))
        value_row.addStretch()
        status = label("库存不足" if data["low"] else "库存充足" if data["total_quantity"] else "无库存")
        status.setStyleSheet("color: #B37B27;" if data["low"] else "color: #35886D;")
        value_row.addWidget(status)
        stock_layout.addLayout(value_row)
        self.detail_content.addWidget(stock)
        self.detail_content.addWidget(label("规格参数", "Heading"))
        params = data["parameters"]
        specs = QFormLayout()
        specs.setVerticalSpacing(9)
        specs.setHorizontalSpacing(22)
        specs.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        if data["model"]:
            value = label(data["model"], "")
            value.setWordWrap(True)
            specs.addRow(label("型号"), value)
        names = {"resistance_ohm": ("阻值", "Ω"), "tolerance_percent": ("精度", "%"), "power_w": ("功率", "W"),
                 "capacitance_f": ("容值", "F"), "voltage_v": ("额定电压", "V"), "dielectric": ("介质", ""),
                 "description": ("关键参数", "")}
        names.update({"temperature_coefficient": ("温度系数", ""), "operating_temperature": ("工作温度", "")})
        range_keys = set()
        definitions = {field.key: field for field in COMPONENT_SPECS.get(data["category"], ())}
        for definition in definitions.values():
            if definition.kind != "range":
                names[definition.key] = (definition.title, definition.unit)
                continue
            low, high = (f"{definition.key}_{endpoint}_v" for endpoint in ("min", "max"))
            range_keys.update((low, high))
            if low in params and high in params:
                field = label(f"{format_number(params[low])}～{format_number(params[high])} V", "")
                field.setWordWrap(True)
                specs.addRow(label(definition.title), field)
        ordered_keys = [key for key in names if key in params] + [key for key in params if key not in names and key not in range_keys]
        for key in ordered_keys:
            value = params[key]
            title, unit = names.get(key, (key, ""))
            if key in definitions and definitions[key].kind == "engineering":
                text = engineering(value, definitions[key].engineering_units)
            elif key == "resistance_ohm":
                text = engineering(value, [(1e6, "MΩ"), (1e3, "kΩ"), (1, "Ω")])
            elif key == "capacitance_f":
                text = engineering(value, [(1, "F"), (1e-3, "mF"), (1e-6, "µF"), (1e-9, "nF"), (1e-12, "pF")])
            elif key == "switching_frequency_khz":
                text = engineering(value, [(1e6, "GHz"), (1e3, "MHz"), (1, "kHz"), (1e-3, "Hz")])
            else:
                text = f"{format_number(value) if isinstance(value, (int, float)) else value} {unit}".strip()
                if key == "tolerance_percent":
                    text = "±" + text.replace(" %", "%")
            field = label(text, "")
            field.setWordWrap(True)
            specs.addRow(label(title), field)
        specs.addRow(label("封装"), label(data["package"] or "—", ""))
        specs.addRow(label("预警数量"), label(f"{data['warning_quantity']:,} 件", ""))
        self.detail_content.addLayout(specs)
        self.detail_content.addWidget(line())
        location_header = QHBoxLayout()
        location_header.addWidget(label("库位分布", "Heading"))
        location_header.addStretch()
        location_header.addWidget(button("盘点", "Link", callback=lambda: self.stock_action("盘点")))
        self.detail_content.addLayout(location_header)
        for item in data["stocks"]:
            row = QFrame()
            row.setObjectName("LocationRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 9, 10, 9)
            symbol = QLabel()
            symbol.setPixmap(icon("box", size=16).pixmap(16, 16))
            row_layout.addWidget(symbol)
            name = label(item["location"], "")
            name.setWordWrap(True)
            row_layout.addWidget(name, 1)
            value = label(f"{item['quantity']:,} 件", "")
            value.setStyleSheet("font-weight: 600;")
            row_layout.addWidget(value)
            self.detail_content.addWidget(row)
        if not data["stocks"]:
            self.detail_content.addWidget(label("尚未存放，入库时选择库位。"))
        self.detail_content.addWidget(label("备注与附件", "Heading"))
        notes = label(data["notes"] or "暂无备注", "Subtle")
        notes.setWordWrap(True)
        notes.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_content.addWidget(notes)
        if data["datasheet"]:
            self.detail_content.addWidget(button("打开数据手册 PDF", icon_name="folder", callback=lambda: self.open_attachment(data["datasheet"])))
        if data["photo"]:
            self.detail_content.addWidget(button("查看元件照片", icon_name="folder", callback=lambda: self.open_attachment(data["photo"])))
        self.detail_content.addWidget(button("查看此元件出入库记录 →", "Link", callback=lambda: self.show_component_history(data["id"])))
        self.detail_content.addStretch()

    def selected_component(self):
        return self.db.get_component(self.selected_id) if self.selected_id else None

    def add_component(self):
        dialog = ComponentDialog(self.db, parent=self)
        category = self.category_filter.currentData()
        if category in dialog.SUPPORTED_CATEGORIES:
            dialog.category.setCurrentText(category)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.search.clear()
            self.package_filter.setCurrentIndex(0)
            self.location_filter.setCurrentIndex(0)
            self.navigate("all")
            self.refresh(dialog.saved_id)

    def edit_component(self):
        component = self.selected_component()
        if component:
            dialog = ComponentDialog(self.db, component, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh(dialog.saved_id)

    def remove_component(self):
        component = self.selected_component()
        if not component:
            return
        answer = QMessageBox.question(
            self, "移除元件",
            f"确定移除元件“{component['name']}”吗？\n\n"
            f"当前库存：{component['total_quantity']:,} 件。\n"
            "该元件的资料、各库位库存和全部出入库记录将一并删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.remove_component(component["id"])
            self.selected_id = None
            self.refresh()
        except Exception as exc:
            error(self, exc)

    def stock_action(self, kind):
        component = self.selected_component()
        if component:
            dialog = StockDialog(self.db, component, kind, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh(component["id"])
            else:
                # A location can be created even if the inventory dialog is cancelled.
                self.refresh(component["id"])

    def table_menu(self, point):
        item = self.table.itemAt(point)
        if item is None:
            return
        self.table.selectRow(item.row())
        if not self.selected_id:
            return
        menu = QMenu(self)
        menu.addAction("编辑资料", self.edit_component)
        for kind in ("入库", "领用", "盘点"):
            menu.addAction(kind, lambda checked=False, k=kind: self.stock_action(k))
        menu.addSeparator()
        menu.addAction("查看出入库记录", lambda: self.show_component_history(self.selected_id))
        menu.addSeparator()
        menu.addAction("移除元件", self.remove_component)
        menu.exec(self.table.viewport().mapToGlobal(point))

    def show_component_history(self, component_id):
        self.history_search.clear()
        self.history_component_filter.setCurrentIndex(self.history_component_filter.findData(component_id))
        self.navigate("history")

    def reload_history(self):
        rows = self.db.history(self.history_component_filter.currentData(), limit=5000)
        tokens = self.history_search.text().casefold().split()
        rows = [row for row in rows if all(token in " ".join(str(value) for value in row.values()).casefold() for token in tokens)]
        self.history_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            cells = [row["created_at"].replace("T", " "), row["name"], row["location"], row["kind"], f"{row['delta']:+,}", f"{row['balance']:,}", row["note"]]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col == 4:
                    item.setForeground(QColor("#359779" if row["delta"] >= 0 else "#BE8A49"))
                self.history_table.setItem(index, col, item)
            self.history_table.setRowHeight(index, 46)
        self.history_count.setText(f"显示 {len(rows):,} 条记录（最多显示最近 5,000 条；更早的记录仍保存在数据库中）。")

    def manage_locations(self):
        dialog = LocationDialog(self.db, self)
        dialog.exec()
        if dialog.changed:
            self.refresh()

    def open_attachment(self, filename):
        path = self.db.attachments / filename
        if not path.is_file():
            error(self, ValueError("附件文件不存在，请从备份恢复或重新添加。"))
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            error(self, ValueError("无法打开附件，请检查系统默认查看程序。"))

    def _tool_dialog(self, title, description, actions):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(500)
        root = QVBoxLayout(dialog)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(15)
        root.addWidget(label(title, "Title"))
        text = label(description)
        text.setWordWrap(True)
        root.addWidget(text)
        for title, subtitle, symbol, callback in actions:
            root.addWidget(button(title, icon_name=symbol, callback=callback))
            text = label(subtitle)
            text.setWordWrap(True)
            root.addWidget(text)
        root.addWidget(button("关闭", callback=dialog.accept))
        dialog.exec()

    def import_export_dialog(self):
        self._tool_dialog("导入 / 导出", "CSV 适合批量录入与整理；完整迁移请使用 ZIP 备份。", [
            ("导出元件与库存 CSV", "导出所有元件，每个库位一行，保留分类参数。CSV 不包含照片、PDF 和历史记录。", "download", self.export_csv),
            ("导入 CSV", "按导出格式填写。只新增元件，不覆盖现有 ID；新元件可留空 ID。文件全部验证通过后才保存。", "folder", self.import_csv),
        ])

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出元件库存", f"元件库存-{datetime.now():%Y%m%d}.csv", "CSV (*.csv)")
        if path:
            try:
                self.db.export_csv(path)
                QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")
            except Exception as exc:
                error(self, exc)

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入元件库存", "", "CSV (*.csv)")
        if path:
            try:
                count = self.db.import_csv(path)
                self.refresh()
                QMessageBox.information(self, "导入完成", f"已新增 {count} 种元件。")
            except Exception as exc:
                error(self, exc)

    def backup_dialog(self):
        self._tool_dialog("备份与恢复", "ZIP 备份包含数据库、出入库记录、元件照片和 PDF 手册。", [
            ("创建完整备份", "建议定期将备份复制到另一个磁盘。", "folder", self.backup),
            ("从备份恢复", "恢复前会自动备份当前数据，备份保存在数据目录的 backups 文件夹。", "history", self.restore),
        ])

    def backup(self):
        default = self.db.directory / "backups" / f"元件仓库-{datetime.now():%Y%m%d-%H%M%S}.zip"
        default.parent.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "创建完整备份", str(default), "ZIP (*.zip)")
        if path:
            try:
                self.db.backup(path)
                self.backup_label.setText("最近备份：" + datetime.now().strftime("%m-%d %H:%M"))
                QMessageBox.information(self, "备份完成", f"数据库和附件已备份到：\n{path}")
            except Exception as exc:
                error(self, exc)

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "从完整备份恢复", "", "ZIP (*.zip)")
        if not path:
            return
        answer = QMessageBox.question(self, "恢复备份", "恢复将用备份内容替换当前库存、资料和历史记录。\n\n程序会先自动保存当前数据的备份。是否继续？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            rollback = self.db.restore(path)
            self.selected_id = None
            self.search.clear()
            self.navigate("all")
            self.refresh()
            QMessageBox.information(self, "恢复完成", f"数据已恢复。恢复前的数据备份保存在：\n{rollback}")
        except Exception as exc:
            error(self, exc)

    def settings_dialog(self):
        dialog = self.make_settings_dialog()
        dialog.exec()

    def make_settings_dialog(self):
        return SettingsDialog(
            self.db, self.change_data_directory,
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.db.directory))),
            self.backup, self.demo, self.directory_override, self,
        )

    def change_data_directory(self, directory: Path) -> bool:
        changed = self.db.migrate_to(directory, lambda path: self.settings.save_data_directory(path, self.demo))
        self.refresh()
        return changed
