"""Small independent startup window, displayed while the main process loads.

Keep this module independent of the application, its database and its assets.
The helper receives JSON lines on stdin; closing that pipe always dismisses it.
"""
from __future__ import annotations
from .i18n import tr, set_language

import json
import math
import os
import sys
import threading

from PySide6.QtCore import QElapsedTimer, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget


def _color(value, alpha=255):
    color = QColor(value)
    color.setAlpha(alpha)
    return color


class StartupSplash(QWidget):
    """A quiet, non-activating loading card with a sculpted compass."""

    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("PrépaPilot")
        self.setAccessibleName("PrépaPilot")
        self.setFixedSize(440, 300)
        self._theme = "light"
        self._reduced_motion = False
        self._closed = False
        self._phase = 0.0
        self._status = "PrépaPilot"
        self._language_ready = False
        self._clock = QElapsedTimer()
        self._clock.start()
        self.animation_timer = QTimer(self)
        self.animation_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.animation_timer.setInterval(30)
        self.animation_timer.timeout.connect(self._advance)
        self.set_status(self._status)

    def set_status(self, text):
        if not isinstance(text, str):
            return
        self._status = " ".join(text.split())[:200]
        self.setAccessibleDescription(self._status)
        self.update()

    def set_preferences(self, theme="light", reduced_motion=False):
        self._theme = "dark" if theme == "dark" else "light"
        self._reduced_motion = bool(reduced_motion)
        if self._reduced_motion:
            self.animation_timer.stop()
            self._phase = 0.0
        elif self.isVisible() and not self._closed:
            self.animation_timer.start()
        self.update()

    def _advance(self):
        if self._closed or self._reduced_motion or not self.isVisible():
            self.animation_timer.stop()
            return
        self._phase = self._clock.elapsed() / 1000.0
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())
        if not self._reduced_motion and not self._closed:
            self.animation_timer.start()

    def hideEvent(self, event):
        self.animation_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.animation_timer.stop()
        if not self._closed:
            self._closed = True
            self.closed.emit()
        super().closeEvent(event)

    def shutdown(self):
        """Dismiss immediately, including before show; safe to call repeatedly."""
        if self._closed:
            return
        self.animation_timer.stop()
        self.close()

    def _text(self, painter, rect, text, size, color, weight=QFont.Weight.Normal):
        font = QFont("Segoe UI")
        font.setPixelSize(size)
        font.setWeight(weight)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def paintEvent(self, event):
        dark = self._theme == "dark"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        panel = QRectF(10, 9, 420, 280)

        # A soft window edge without a native title bar or an intrusive shadow.
        for spread, alpha in ((5, 4), (3, 8), (1, 13)):
            painter.setBrush(_color("#0B1733", alpha))
            painter.drawRoundedRect(panel.adjusted(-spread, -spread + 2, spread, spread + 2),
                                    29 + spread, 29 + spread)
        surface = QLinearGradient(panel.topLeft(), panel.bottomRight())
        surface.setColorAt(0, QColor("#20273B" if dark else "#FFFFFF"))
        surface.setColorAt(1, QColor("#181D30" if dark else "#F2F4FD"))
        painter.setBrush(surface)
        painter.setPen(QPen(_color("#B4C6EF" if dark else "#FFFFFF", 85 if dark else 230), 1))
        painter.drawRoundedRect(panel, 29, 29)
        clip = QPainterPath()
        clip.addRoundedRect(panel, 29, 29)
        painter.setClipPath(clip)
        painter.setPen(Qt.PenStyle.NoPen)
        for center, radius, color in ((QPointF(96, 51), 156, "#559AFF"),
                                      (QPointF(353, 162), 151, "#B595EF")):
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0, _color(color, 25 if dark else 31))
            glow.setColorAt(1, _color(color, 0))
            painter.setBrush(glow)
            painter.drawEllipse(center, radius, radius)

        drift = 0 if self._reduced_motion else math.sin(self._phase * 1.8) * 2.0
        painter.save()
        painter.translate(220, 91 + drift)
        shadow = QRadialGradient(QPointF(0, 44), 57)
        shadow.setColorAt(0, _color("#5260A6", 42 if dark else 30))
        shadow.setColorAt(1, _color("#5260A6", 0))
        painter.setBrush(shadow)
        painter.drawEllipse(QRectF(-58, 28, 116, 31))

        body = QLinearGradient(-36, -41, 42, 45)
        body.setColorAt(0, QColor("#FEFEFF"))
        body.setColorAt(.45, QColor("#D2E2FF"))
        body.setColorAt(1, QColor("#879BE1"))
        painter.setBrush(body)
        painter.drawEllipse(QRectF(-44, -42, 88, 88))
        face = QRadialGradient(QPointF(-17, -20), 85)
        face.setColorAt(0, QColor("#FFFFFF"))
        face.setColorAt(.54, QColor("#F2F5FF"))
        face.setColorAt(1, QColor("#BBCEF7"))
        painter.setBrush(face)
        painter.drawEllipse(QRectF(-40, -41, 80, 80))
        painter.setPen(QPen(_color("#FFFFFF", 200), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(-39, -40, 78, 78))
        painter.setPen(QPen(_color("#667CAE", 95), 1.6, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        for angle in (0, 90, 180, 270):
            painter.save()
            painter.rotate(angle)
            painter.drawLine(QPointF(0, -28), QPointF(0, -23))
            painter.restore()
        painter.rotate(31)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_color("#5369A3", 25))
        painter.drawPolygon(QPolygonF([QPointF(3, -25), QPointF(16, 4),
                                      QPointF(3, 32), QPointF(-10, 4)]))
        for points, top, bottom in (
            ((QPointF(0, -29), QPointF(0, 1), QPointF(-13, 1)), "#86C5FF", "#2576E3"),
            ((QPointF(0, -29), QPointF(13, 1), QPointF(0, 1)), "#518FF4", "#345DC5"),
            ((QPointF(-13, 1), QPointF(0, 1), QPointF(0, 29)), "#E9E0FF", "#A38BCD"),
            ((QPointF(0, 1), QPointF(13, 1), QPointF(0, 29)), "#BFB0EB", "#7B66AB"),
        ):
            shade = QLinearGradient(0, -29, 0, 29)
            shade.setColorAt(0, QColor(top))
            shade.setColorAt(1, QColor(bottom))
            painter.setBrush(shade)
            painter.drawPolygon(QPolygonF(points))
        painter.setBrush(QColor("#FDFEFF"))
        painter.drawEllipse(QPointF(0, 1), 3, 3)
        painter.restore()

        # Small glossy satellites echo the illustrations in the main pages.
        for x, y, radius, light, base in ((151, 77, 7, "#D9EAFF", "#6D9BE9"),
                                         (286, 112, 9, "#EADFFF", "#A48ACF")):
            sphere = QRadialGradient(QPointF(x - radius * .4, y - radius * .45), radius * 1.9)
            sphere.setColorAt(0, QColor(light))
            sphere.setColorAt(1, QColor(base))
            painter.setBrush(sphere)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(x, y), radius, radius)

        foreground = "#F2F5FF" if dark else "#202B45"
        secondary = "#BCC8E1" if dark else "#69748C"
        self._text(painter, QRectF(30, 153, 380, 38), "PrépaPilot", 31, foreground,
                   QFont.Weight.DemiBold)
        self._text(painter, QRectF(30, 194, 380, 24), tr("Ton espace prend forme.") if self._language_ready else "…", 14, secondary)
        status_font = QFont("Segoe UI")
        status_font.setPixelSize(12)
        painter.setFont(status_font)
        status = painter.fontMetrics().elidedText(self._status, Qt.TextElideMode.ElideRight, 356)
        self._text(painter, QRectF(40, 233, 360, 20), status, 12, secondary)
        painter.setPen(Qt.PenStyle.NoPen)
        for index, color in enumerate(("#518CEE", "#7B86E7", "#A18ADD")):
            pulse = .55 if self._reduced_motion else (.55 + .45 * math.sin(self._phase * 3.4 - index * .8))
            painter.setBrush(_color(color, int(100 + 155 * pulse)))
            radius = 2.7 if self._reduced_motion else 2.5 + pulse * .65
            painter.drawEllipse(QPointF(208 + 12 * index, 268), radius, radius)
        painter.end()


class _CommandBridge(QObject):
    command = Signal(object)
    finished = Signal()


def _read_commands(stream, bridge, closing):
    """Read on a daemon thread; communicate exclusively through Qt signals."""
    try:
        for line in stream:
            try:
                message = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(message, dict):
                continue
            if message.get("close") is True:
                break
            bridge.command.emit(message)
    except (OSError, ValueError):
        pass
    finally:
        closing.set()
        bridge.finished.emit()


def _input_stream():
    """Recover the inherited pipe in a Windows ``--windowed`` executable."""
    if sys.stdin is not None:
        return sys.stdin
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
        kernel.GetStdHandle.restype = ctypes.c_void_p
        kernel.GetFileType.argtypes = [ctypes.c_void_p]
        kernel.GetFileType.restype = ctypes.c_uint32
        handle = kernel.GetStdHandle(ctypes.c_uint32(-10))
        if not handle or handle == ctypes.c_void_p(-1).value or kernel.GetFileType(handle) != 3:
            return None
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        return os.fdopen(descriptor, "r", encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def run_splash():
    """Run the isolated loading helper until a close message or parent EOF."""
    stream = _input_stream()
    if stream is None:
        return 0
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(True)
    bridge = _CommandBridge()
    closing = threading.Event()
    splash = None

    def receive(message):
        if closing.is_set():
            return
        if message.get('language') in ('fr', 'en'):
            set_language(message['language'])
            splash._language_ready = True
            splash.setWindowTitle(tr('PrépaPilot — Ouverture'))
            splash.setAccessibleName(tr('Ouverture de PrépaPilot'))
        if isinstance(message.get("status"), str):
            splash.set_status(message["status"])
        theme = message.get("theme", splash._theme)
        reduced = message.get("reduced_motion", splash._reduced_motion)
        if theme not in ("light", "dark"):
            theme = splash._theme
        if not isinstance(reduced, bool):
            reduced = splash._reduced_motion
        splash.set_preferences(theme, reduced)

    def finish():
        if splash is not None:
            splash.shutdown()
        app.quit()

    bridge.command.connect(receive, Qt.ConnectionType.QueuedConnection)
    bridge.finished.connect(finish, Qt.ConnectionType.QueuedConnection)
    reader = threading.Thread(target=_read_commands, args=(stream, bridge, closing), daemon=True)
    reader.start()
    # An already closed parent must never produce a late loading-card flash.
    if closing.is_set():
        return 0
    splash = StartupSplash()
    splash.closed.connect(app.quit)

    def show_when_ready():
        if closing.is_set():
            finish()
        else:
            splash.show()

    QTimer.singleShot(0, show_when_ready)
    result = app.exec()
    splash.shutdown()
    return result
