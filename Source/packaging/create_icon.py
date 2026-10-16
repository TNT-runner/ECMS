"""Create a multi-size Windows icon from the application's existing chip symbol."""

import os
from pathlib import Path
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from component_desk.style import ICONS


def main():
    application = QGuiApplication([])
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           '<rect width="32" height="32" rx="7" fill="#17283E"/>'
           '<g transform="translate(4 4)" fill="none" stroke="#60D0C0" '
           'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
           + ICONS["chip"] + '</g></svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    sizes = (16, 24, 32, 48, 64, 128, 256)
    pictures = []
    for size in sizes:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Unable to render application icon")
        pictures.append(bytes(buffer.data()))
    offset = 6 + 16 * len(sizes)
    entries = []
    for size, picture in zip(sizes, pictures):
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(picture), offset))
        offset += len(picture)
    target = Path(__file__).with_name("ComponentDesk.ico")
    target.write_bytes(struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries) + b"".join(pictures))
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
