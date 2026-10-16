"""Desktop appearance and vector icons."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICONS = {
    "chip": '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4M18 9h4m-4 6h4"/><rect x="10" y="10" width="4" height="4" rx=".5"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "box": '<path d="m3 7 9-4 9 4v11l-9 4-9-4ZM3 7l9 4 9-4M12 11v11M7.5 5l9 4"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-up": '<path d="m6 15 6-6 6 6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "in": '<path d="M12 3v17m-5-5 5 5 5-5"/>',
    "out": '<path d="M12 21V4m-5 5 5-5 5 5"/>',
    "history": '<path d="M4 7a9 9 0 1 1-1 8M4 3v5h5M12 7v5l3 2"/>',
    "folder": '<path d="M3 7V4h7l2 3h9v13H3ZM3 7h18"/>',
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    "alert": '<path d="m12 3 10 18H2ZM12 9v5M12 17h.01"/>',
    "resistor": '<path d="M2 12h4m12 0h4"/><rect x="6" y="8" width="12" height="8" rx="1"/><path d="M9 8v8m6-8v8"/>',
    "capacitor": '<path d="M2 12h7m6 0h7M9 5v14m6-14v14"/>',
    "inductor": '<path d="M2 12h3c0-8 4-8 4 0 0-8 4-8 4 0 0-8 4-8 4 0h5"/>',
    "diode": '<path d="M2 12h5m10 0h5M7 6l10 6-10 6ZM17 5v14"/>',
    "crystal": '<path d="M2 12h5m10 0h5M6 5v14m12-14v14"/><rect x="9" y="7" width="6" height="10"/>',
    "mosfet": '<path d="M4 5v14m3-12v10m0-5H2M10 6h7V2m-7 16h7v4M10 6v12m0-6h7v6"/>',
    "battery": '<rect x="3" y="6" width="17" height="12" rx="2"/><path d="M20 10h2v4M7 10v4m-2-2h4m4 0h4"/>',
    "transistor": '<circle cx="13" cy="12" r="9"/><path d="M2 12h7m0-6v12m0-8 8-5V2M9 14l8 5v3m-5-7 4 1-1 4"/>',
    "connector": '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 2v3m8-3v3M8 19v3m8-3v3"/><circle cx="8" cy="10" r="1"/><circle cx="16" cy="10" r="1"/><circle cx="8" cy="14" r="1"/><circle cx="16" cy="14" r="1"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "settings": '<path d="m9 3-1 3-3 1-2 4 2 2v4l4 2 3-1 3 1 4-2v-4l2-2-2-4-3-1-1-3Z"/><circle cx="12" cy="12" r="3"/>',
}


def icon(name: str, color="#71859D", size=24) -> QIcon:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICONS.get(name, ICONS["chip"])}</g></svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


STYLESHEET = """
QMainWindow, QWidget#Workspace { background: #F4F7FB; }
QWidget { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI'; font-size: 13px; color: #33465C; }
QWidget#DetailBody { background: white; }
QWidget#FormBody { background: #F4F7FB; }
QLabel { background: transparent; }
QLabel#Title { font-size: 24px; font-weight: 700; color: #172B43; }
QLabel#Heading { font-size: 16px; font-weight: 700; color: #172B43; }
QLabel#Subtle { color: #7B8DA2; font-size: 12px; }
QLabel#StatValue { font-size: 29px; font-weight: 700; color: #172B43; }
QLabel#WarningValue { font-size: 29px; font-weight: 700; color: #C28A35; }
QFrame#Header { background: white; border-bottom: 1px solid #E4EAF1; }
QFrame#Card { background: white; border: 1px solid #E4EAF1; border-radius: 12px; }
QFrame#Sidebar { background: #17283E; }
QScrollArea#SidebarScroll { background: #17283E; }
QLabel#Brand { color: white; font-size: 18px; font-weight: 700; }
QLabel#BrandSub { color: #8195AF; font-size: 10px; letter-spacing: 1px; }
QLabel#NavSection { color: #7387A3; font-size: 11px; padding: 8px 12px; }
QPushButton { background: white; border: 1px solid #DDE5EE; border-radius: 7px; padding: 9px 14px; }
QPushButton:hover { background: #F0F7F5; border-color: #A9CEC4; }
QPushButton:pressed { background: #E2F0EB; }
QPushButton:disabled { color: #A8B3C2; background: #F5F7FA; border-color: #E8EDF3; }
QPushButton#Primary { background: #138E82; color: white; font-weight: 600; border: 1px solid #138E82; }
QPushButton#Primary:hover { background: #0D7E73; }
QPushButton#Primary:pressed { background: #096C63; }
QPushButton#Primary:disabled { background: #9EC5BF; border-color: #9EC5BF; color: white; }
QPushButton#Link { color: #138E82; border: none; background: transparent; padding: 3px; }
QPushButton#Link:hover { background: #EDF7F3; }
QPushButton#Nav { color: #A7B7CD; text-align: left; background: transparent; border: none; border-radius: 8px; padding: 12px; }
QPushButton#Nav:hover { background: #20364E; }
QPushButton#Nav:checked { color: white; background: #29435C; font-weight: 600; }
QFrame#LocalBadge { background: #20334B; border-radius: 9px; }
QLabel#LocalText { color: #C3D1E2; font-size: 11px; }
QLabel#Offline { background: #EAF6F2; color: #287C68; padding: 5px 12px; border-radius: 12px; font-size: 11px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit { background: white; border: 1px solid #DDE5EE; border-radius: 6px; padding: 7px 9px; min-height: 18px; selection-background-color: #138E82; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus { border-color: #138E82; }
QTextEdit#MultiLineSpecification { min-height: 90px; max-height: 90px; }
QLineEdit:disabled, QComboBox:disabled { background: #EEF2F6; color: #627083; border-color: #DDE5EE; }
QSpinBox#QuantityInput { padding-right: 36px; }
QSpinBox#QuantityInput::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 30px; background: #EDF3F8; border-left: 1px solid #CBD5E1; border-bottom: 1px solid #CBD5E1; border-top-right-radius: 6px; }
QSpinBox#QuantityInput::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 30px; background: #EDF3F8; border-left: 1px solid #CBD5E1; border-bottom-right-radius: 6px; }
QSpinBox#QuantityInput::up-button:hover, QSpinBox#QuantityInput::down-button:hover { background: #DCEFE9; }
QSpinBox#QuantityInput::up-button:pressed, QSpinBox#QuantityInput::down-button:pressed { background: #C4E3D9; }
QSpinBox#QuantityInput::up-button:disabled, QSpinBox#QuantityInput::down-button:disabled { background: #F5F7FA; }
QSpinBox#QuantityInput::up-arrow, QSpinBox#QuantityInput::down-arrow { image: none; }
QLineEdit#Search { background: #F7F9FC; padding: 10px; }
QComboBox { padding-right: 20px; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox#ComponentCategory { padding-right: 30px; }
QComboBox#ComponentCategory::drop-down { width: 28px; }
QComboBox#ComponentCategory::down-arrow { image: none; }
QComboBox QAbstractItemView { background: white; selection-background-color: #E4F3ED; selection-color: #172B43; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 15px; height: 15px; }
QCheckBox::indicator:unchecked { border: 1px solid #C9D5E3; border-radius: 3px; background: white; }
QCheckBox::indicator:checked { border: 1px solid #138E82; border-radius: 3px; background: #138E82; }
QTableWidget { background: white; border: none; gridline-color: #EDF1F6; selection-background-color: #EAF7F2; selection-color: #215E51; outline: none; }
QTableWidget::item { border-bottom: 1px solid #EDF1F6; padding: 8px; }
QTableWidget::item:selected { background: #EAF7F2; color: #215E51; }
QHeaderView::section { background: #F8FAFD; color: #7B8DA2; border: none; border-bottom: 1px solid #E7EDF4; padding: 12px 8px; font-size: 12px; }
QTableCornerButton::section { background: #F8FAFD; border: none; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 3px; }
QScrollBar::handle:vertical { background: #D0DCE6; border-radius: 3px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QFrame#StockBox { background: #F0F8F5; border: none; border-radius: 9px; }
QLabel#StockValue { font-size: 30px; font-weight: 700; color: #237463; }
QFrame#LocationRow { background: #F7F9FC; border: none; border-radius: 6px; }
QFrame#Line { background: #E8EDF3; min-height: 1px; max-height: 1px; border: none; }
QLabel#Photo { background: #F0F5F5; border-radius: 10px; }
QSplitter::handle { background: transparent; width: 16px; }
QStatusBar { background: #F4F7FB; color: #7B8DA2; font-size: 11px; border: none; }
QDialog { background: #F4F7FB; }
QMenu { background-color: #FFFFFF; color: #172B43; border: 1px solid #AAB8C8; padding: 5px; font-size: 14px; }
QMenu::item { background-color: transparent; color: #172B43; padding: 9px 22px; }
QMenu::item:selected { background-color: #096C63; color: #FFFFFF; border-radius: 4px; }
QMenu::item:disabled { color: #627083; }
QMenu::separator { background-color: #CBD5E1; height: 1px; margin: 5px 8px; }
QToolTip { background: #17283E; color: white; border: none; padding: 6px; }
"""
