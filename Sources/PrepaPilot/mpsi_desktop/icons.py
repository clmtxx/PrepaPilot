from PySide6.QtCore import QByteArray, Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 8.5a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4M12 17h.01"/>',
    "pilot": '<circle cx="12" cy="12" r="9"/><path d="m16 7-2.5 6.5L7 16l2.5-6.5Z"/>',
    "home": '<path d="M3 11 12 4l9 7v10h-6v-7H9v7H3Z"/>',
    "tasks": '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="m7 9 2 2 3-4m1 9h4M7 16h2"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v5m10-5v5M3 11h18m-13 4h1m4 0h1m-6 3h1"/>',
    "chart": '<path d="M4 3v17h17M8 15l4-5 4 2 5-7"/>',
    "book": '<path d="M12 6C8 3 4 3 2 4v15c4-1 7 0 10 2 3-2 6-3 10-2V4c-3-1-7 0-10 2Zm0 0v15"/>',
    "memory": '<path d="M9 5a3 3 0 0 0-5 3 4 4 0 0 0-1 7 3 3 0 0 0 6 4M15 5a3 3 0 0 1 5 3 4 4 0 0 1 1 7 3 3 0 0 1-6 4M9 4v16m6-16v16M5 9l4 2m6 3 4-2"/>',
    "settings": '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    "moon": '<path d="M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12Z"/>',
    "expand": '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
    "collapse": '<path d="M3 8h5V3m8 0v5h5M8 21v-5H3m13 5v-5h5"/>',
    "spark": '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/>',
    "bolt": '<path d="m13 2-9 12h7l-1 8 10-13h-7Z"/>',
}


def icon(name, color="#0071E3", size=24):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{PATHS.get(name,PATHS["spark"])}</g></svg>'
    pix = QPixmap(size*2, size*2)
    pix.fill(Qt.transparent)
    pix.setDevicePixelRatio(2)
    painter = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0,0,size,size))
    painter.end()
    return QIcon(pix)
