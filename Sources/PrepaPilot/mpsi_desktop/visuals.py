"""Quiet native illustrations and typography, with motion only on interaction."""
from __future__ import annotations
from .i18n import tr

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import (
    QAbstractTextDocumentLayout, QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
    QTextCharFormat, QTextCursor, QTextDocument, QTextOption, QTransform,
)
from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy, QStyle, QStyleOption, QWidget


def _theme():
    app = QApplication.instance()
    return "dark" if app is not None and app.property("visualTheme") == "dark" else "light"


def _motion_allowed():
    app = QApplication.instance()
    return app is None or not bool(app.property("reducedMotion"))


class _ArtworkCache:
    """One current resolution per illustration; parallax only moves its layers.

    Rasterize at the screen's actual pixel ratio, never at an assumed 1x size.
    Cache only the fitted artwork, not the potentially much wider widget. Old
    layers are discarded together on resize/theme/screen changes. The modest
    padding keeps shadows and displaced objects inside their transparent image.
    """

    def __init__(self):
        self.key = None
        self.layers = {}

    def prepare(self, widget, width, height, variant, padding=12):
        scale = min(widget.width() / width, widget.height() / height)
        ratio = widget.devicePixelRatioF()
        key = (scale, ratio, width, height, variant, padding)
        if key != self.key:
            self.key = key
            self.layers.clear()
        self.scale, self.ratio, self.padding = scale, ratio, padding
        self.width, self.height = width, height
        self.origin = QPointF((widget.width() - width * scale) / 2 - padding * scale,
                              (widget.height() - height * scale) / 2 - padding * scale)

    def draw(self, painter, name, render, offset=QPointF()):
        if self.scale <= 0:
            return
        if name not in self.layers:
            pixmap = QPixmap(max(1, math.ceil((self.width + self.padding * 2) * self.scale * self.ratio)),
                             max(1, math.ceil((self.height + self.padding * 2) * self.scale * self.ratio)))
            pixmap.setDevicePixelRatio(self.ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            layer_painter = QPainter(pixmap)
            try:
                layer_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                layer_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                layer_painter.scale(self.scale, self.scale)
                layer_painter.translate(self.padding, self.padding)
                render(layer_painter)
            finally:
                layer_painter.end()
            self.layers[name] = pixmap
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self.origin + offset * self.scale, self.layers[name])


class _VisualPreferences:
    """Share the application's single preference observer with other widgets."""

    def _watch_preferences(self):
        # widgets imports these illustrations for headings; defer this import.
        from .widgets import observe_visual_preferences
        observe_visual_preferences(self)

    def _reset_motion(self):
        self._rest()
        self.update()


class ReflectiveTitle(_VisualPreferences, QLabel):
    """A QLabel with blue typography and one short reflection on pointer entry.

    QLabel retains its text, accessible role, sizing, font, alignment and wrapping.
    Set the usual ``objectName`` (for example ``pageTitle``) before styling it.
    ``QApplication.reducedMotion`` disables the reflection immediately.
    """

    def __init__(self, text="", parent=None, **kwargs):
        # Names and other user content stay literal unless markup is requested.
        kwargs.setdefault("textFormat", Qt.TextFormat.PlainText)
        super().__init__(text, parent, **kwargs)
        self._reflection = None
        self._document_key = None
        self._document = None
        self.reflection_animation = QVariantAnimation(self)
        self.reflection_animation.setDuration(720)
        self.reflection_animation.setStartValue(-0.18)
        self.reflection_animation.setEndValue(1.18)
        self.reflection_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.reflection_animation.valueChanged.connect(self._set_reflection)
        self.reflection_animation.finished.connect(self._finish_reflection)
        self._watch_preferences()

    def _set_reflection(self, value):
        if not _motion_allowed():
            self._rest()
            return
        self._reflection = float(value)
        self.update()

    def _finish_reflection(self):
        self._reflection = None
        self.update()

    def _rest(self):
        self.reflection_animation.stop()
        self._reflection = None

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.isVisible() and _motion_allowed():
            self.reflection_animation.stop()
            self.reflection_animation.start()

    def leaveEvent(self, event):
        self._rest()
        self.update()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._rest()
        super().hideEvent(event)

    def _text_rectangle(self):
        rect = QRectF(self.contentsRect())
        margin = self.margin()
        rect.adjust(margin, margin, -margin, -margin)
        indent = self.indent()
        if indent < 0:
            indent = self.fontMetrics().horizontalAdvance("x") / 2 if self.frameWidth() else 0
        alignment = QStyle.visualAlignment(self.layoutDirection(), self.alignment())
        if alignment & Qt.AlignmentFlag.AlignLeft:
            rect.adjust(indent, 0, 0, 0)
        elif alignment & Qt.AlignmentFlag.AlignRight:
            rect.adjust(0, 0, -indent, 0)
        if alignment & Qt.AlignmentFlag.AlignTop:
            rect.adjust(0, indent, 0, 0)
        elif alignment & Qt.AlignmentFlag.AlignBottom:
            rect.adjust(0, 0, 0, -indent)
        return rect

    def _brush(self, rect):
        dark = _theme() == "dark"
        base = QColor("#69B3FF" if dark else "#0071E3")
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor("#B2D9FF" if dark else "#0756B1"))
        gradient.setColorAt(0.55, base)
        gradient.setColorAt(1, QColor("#3999F5" if dark else "#087ACB"))
        if self._reflection is not None:
            center = self._reflection
            for offset, color in ((-0.13, base), (-0.035, QColor("#B6DBFF")),
                                  (0.0, QColor("#E8F4FF")), (0.035, QColor("#B6DBFF")), (0.13, base)):
                position = center + offset
                if 0 <= position <= 1:
                    gradient.setColorAt(position, color)
        return QBrush(gradient)

    def paintEvent(self, event):
        # Let the style draw any explicitly configured QLabel background/border.
        painter = QPainter(self)
        try:
            self._paint_title(painter)
        finally:
            painter.end()

    def _paint_title(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)
        if self.frameWidth():
            self.drawFrame(painter)
        rect = self._text_rectangle()
        if rect.width() <= 0 or rect.height() <= 0 or not self.text():
            return

        document = self._text_document(rect.width())
        height = document.size().height()
        y = rect.top()
        if self.alignment() & Qt.AlignmentFlag.AlignVCenter:
            y += (rect.height() - height) / 2
        elif self.alignment() & Qt.AlignmentFlag.AlignBottom:
            y += rect.height() - height
        local_rect = QRectF(0, 0, rect.width(), max(1, height))
        # A paint selection applies the changing brush without editing the
        # document: reflection frames reuse shaping, wrapping and glyph layout.
        selection = QAbstractTextDocumentLayout.Selection()
        selection.cursor = QTextCursor(document)
        selection.cursor.select(QTextCursor.SelectionType.Document)
        char_format = QTextCharFormat()
        char_format.setForeground(self._brush(local_rect))
        selection.format = char_format
        context = QAbstractTextDocumentLayout.PaintContext()
        context.selections = [selection]
        painter.setClipRect(rect)
        painter.translate(rect.left(), y)
        document.documentLayout().draw(painter, context)

    def _text_document(self, width):
        key = (self.text(), self.textFormat(), QFont(self.font()),
               self.layoutDirection(), self.alignment(), self.wordWrap(), width)
        if key == self._document_key:
            return self._document
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(self.font())
        text_option = QTextOption()
        text_option.setTextDirection(self.layoutDirection())
        text_option.setAlignment(self.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask)
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere if self.wordWrap() else QTextOption.WrapMode.NoWrap)
        document.setDefaultTextOption(text_option)
        text_format = self.textFormat()
        if text_format == Qt.TextFormat.RichText:
            document.setHtml(self.text())
        elif text_format == Qt.TextFormat.MarkdownText:
            document.setMarkdown(self.text())
        else:
            document.setPlainText(self.text())
        document.setTextWidth(width)
        self._document_key, self._document = key, document
        return document


class StudySculpture(_VisualPreferences, QWidget):
    """A small blue notebook and silver cards, painted in layered perspective.

    Preferred size is 330 × 230. It scales to its available rectangle, without
    forcing its parent to grow. Hover motion is bounded to a few pixels and
    stops entirely at rest; there are no timers, files or graphics effects.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = QPointF()
        self._target = QPointF()
        self._artwork = _ArtworkCache()
        self.parallax_animation = QVariantAnimation(self)
        self.parallax_animation.setDuration(180)
        self.parallax_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.parallax_animation.valueChanged.connect(self._set_offset)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(tr("Carnet bleu et cartes d’étude en relief"))
        self.setAccessibleDescription(tr("Illustration décorative"))
        self._watch_preferences()

    def sizeHint(self):
        return QSize(330, 230)

    def minimumSizeHint(self):
        return QSize(150, 105)

    def _rest(self):
        self.parallax_animation.stop()
        self._offset = QPointF()
        self._target = QPointF()

    def _set_offset(self, value):
        if not _motion_allowed() or not self.isVisible():
            self._rest()
        else:
            self._offset = QPointF(value)
        self.update()

    def _move_to(self, target, duration=180):
        if not _motion_allowed() or not self.isVisible():
            self._rest()
            return
        if target == self._target:
            return
        self._target = QPointF(target)
        self.parallax_animation.stop()
        self.parallax_animation.setDuration(duration)
        self.parallax_animation.setStartValue(self._offset)
        self.parallax_animation.setEndValue(self._target)
        self.parallax_animation.start()

    def mouseMoveEvent(self, event):
        position = event.position()
        x = max(-1, min(1, position.x() / max(1, self.width()) * 2 - 1))
        y = max(-1, min(1, position.y() / max(1, self.height()) * 2 - 1))
        self._move_to(QPointF(x, y))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._move_to(QPointF(), 260)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._rest()
        super().hideEvent(event)

    @staticmethod
    def _shadow(painter, rect, strength=1.0):
        painter.setPen(Qt.PenStyle.NoPen)
        for spread in range(12, 0, -1):
            painter.setBrush(QColor(10, 37, 67, round((1.8 if _theme() == "light" else 3.2) * strength)))
            painter.drawEllipse(rect.adjusted(-spread, -spread / 2, spread, spread / 2))

    @staticmethod
    def _plane(painter, origin, across, down, width, height):
        painter.setTransform(QTransform(across.x() / width, across.y() / width,
                                        down.x() / height, down.y() / height,
                                        origin.x(), origin.y()), True)

    @staticmethod
    def _side(painter, points, first, last):
        gradient = QLinearGradient(points[0], points[-1])
        gradient.setColorAt(0, QColor(first))
        gradient.setColorAt(1, QColor(last))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPolygon(QPolygonF(points))

    def _notebook(self, painter):
        origin, across, down = QPointF(74, 105), QPointF(133, -36), QPointF(58, 85)
        a, b, c, d = origin, origin + across, origin + across + down, origin + down
        depth = QPointF(0, 9)
        self._side(painter, [d, c, c + depth, d + depth], "#C9D4E1", "#F0F5FA")
        self._side(painter, [a, d, d + depth, a + depth], "#1255A1", "#073A7F")
        painter.setPen(QPen(QColor("#A5B3C5"), 0.7))
        for dy in (3, 5, 7):
            painter.drawLine(d + QPointF(1, dy), c + QPointF(-1, dy))
        painter.setPen(QPen(QColor("#1263BF"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(d + depth, c + depth)
        painter.save()
        self._plane(painter, origin, across, down, 144, 106)
        surface = QLinearGradient(0, 0, 144, 106)
        surface.setColorAt(0, QColor("#83BDFF"))
        surface.setColorAt(0.28, QColor("#348DF0"))
        surface.setColorAt(0.75, QColor("#0969D9"))
        surface.setColorAt(1, QColor("#0456B9"))
        painter.setBrush(surface)
        painter.setPen(QPen(QColor(195, 224, 255, 170), 0.8))
        painter.drawRoundedRect(QRectF(0, 0, 144, 106), 6, 6)
        painter.setPen(QPen(QColor(10, 76, 160, 125), 2))
        painter.drawLine(QPointF(12, 3), QPointF(12, 103))
        painter.setPen(QPen(QColor(211, 237, 255, 105), 0.7))
        painter.drawLine(QPointF(15, 3), QPointF(15, 103))
        painter.setPen(QPen(QColor(240, 248, 255, 175), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(38, 68), QPointF(101, 68))
        painter.setPen(QPen(QColor(211, 234, 255, 125), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(38, 76), QPointF(83, 76))
        painter.restore()

    def _card(self, painter, origin, across, down, *, compact=False):
        a, b, c, d = origin, origin + across, origin + across + down, origin + down
        depth = QPointF(0, 4 if compact else 5)
        self._side(painter, [d, c, c + depth, d + depth], "#ACB9CA", "#D5E0EC")
        self._side(painter, [a, d, d + depth, a + depth], "#D1DCE8", "#B2C0D2")
        painter.save()
        width, height = (76, 54) if compact else (114, 78)
        self._plane(painter, origin, across, down, width, height)
        silver = QLinearGradient(0, 0, width, height)
        silver.setColorAt(0, QColor("#FFFFFF"))
        silver.setColorAt(0.45, QColor("#F6F9FD"))
        silver.setColorAt(1, QColor("#DCE6F2"))
        painter.setBrush(silver)
        painter.setPen(QPen(QColor(255, 255, 255, 225), 1.1))
        painter.drawRoundedRect(QRectF(0, 0, width, height), 7, 7)
        if compact:
            for x, bar_height, color in ((17, 13, "#A4C8EF"), (31, 21, "#5FA6EF"), (45, 29, "#227ADB")):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(color))
                painter.drawRoundedRect(QRectF(x, 41 - bar_height, 8, bar_height), 3, 3)
        else:
            blue = QLinearGradient(14, 11, 43, 36)
            blue.setColorAt(0, QColor("#6AB5FF"))
            blue.setColorAt(1, QColor("#0769D7"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(blue)
            painter.drawRoundedRect(QRectF(15, 13, 28, 25), 6, 6)
            painter.setPen(QPen(QColor("#F9FCFF"), 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            tick = QPainterPath(QPointF(23, 25))
            tick.lineTo(28, 30)
            tick.lineTo(36, 21)
            painter.drawPath(tick)
            painter.setPen(QPen(QColor("#88A0BE"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(55, 22), QPointF(91, 22))
            painter.setPen(QPen(QColor("#C0CDDE"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(55, 31), QPointF(80, 31))
            painter.drawLine(QPointF(17, 52), QPointF(94, 52))
            painter.drawLine(QPointF(17, 61), QPointF(72, 61))
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._paint_sculpture(painter)
        finally:
            painter.end()

    def _paint_sculpture(self, painter):
        self._artwork.prepare(self, 330, 230, _theme())
        draw = self._artwork.draw
        x, y = self._offset.x(), self._offset.y()
        draw(painter, "notebook-shadow", lambda p: self._shadow(p, QRectF(91, 189, 170, 13), 1.2), QPointF(x, y))
        draw(painter, "notebook", self._notebook, QPointF(x * 2.5, y * 1.6))
        draw(painter, "card-shadow", lambda p: self._shadow(p, QRectF(124, 112, 93, 13), .7), QPointF(x * 2, y * 2))
        draw(painter, "card", lambda p: self._card(p, QPointF(88, 61), QPointF(91, -25), QPointF(36, 55)), QPointF(x * 6, y * 4))
        draw(painter, "chart-shadow", lambda p: self._shadow(p, QRectF(234, 107, 47, 8), .55), QPointF(x * 3, y * 2))
        draw(painter, "chart", lambda p: self._card(p, QPointF(219, 69), QPointF(54, -13), QPointF(26, 37), compact=True), QPointF(x * 8, y * 5))
