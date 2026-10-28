"""An accessible, native annual chart with bounded, optional motion."""
from __future__ import annotations
from .i18n import tr, format_number

from copy import deepcopy
import math

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QSizePolicy, QToolTip, QWidget

from .progression_visuals import axis_palette
from .theme import palette_for
from .widgets import motion_enabled, observe_visual_preferences


AXES = {"work": "Travail", "sleep": "Sommeil", "sport": "Sport", "rest": "Détente"}
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
SHORT_MONTHS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")


def _number(value):
    return format_number(value, 1).rstrip("0").rstrip(",.")


class AnnualProgressionChart(QWidget):
    """Recorded hours per calendar day; missing months are never fabricated."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.rows = []
        self.axis = "work"
        self._hover_index = -1
        self._selected_index = -1
        self._progress = 1.0
        self._pending_reveal = False
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(450)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self._animate)
        observe_visual_preferences(self)
        self.setAccessibleDescription(tr('Flèches gauche et droite : parcourir les mois. Début et Fin : premier et dernier mois. Le tableau détaille les mêmes données.'))

    def sizeHint(self):
        return QSize(700, 260)

    def _theme(self):
        app = QApplication.instance()
        return app.property("visualTheme") or self.ctx.theme

    def set_data(self, rows, axis):
        if rows == self.rows and axis == self.axis:
            return
        self.animation.stop()
        self.rows, self.axis = deepcopy(rows), axis
        self._hover_index = -1
        self._selected_index = -1
        QToolTip.hideText()
        available = [self._detail(index) for index in range(len(self.rows))]
        self.setAccessibleName(tr('Historique {v0}. ', v0=tr(AXES[axis]).lower()) + "; ".join(available))
        self._set_description()
        self._pending_reveal = bool(rows) and motion_enabled()
        if self.isVisible() and not self.window().isMinimized():
            self._reveal()
        else:
            self._progress = 1.0
            self.update()

    def _reveal(self):
        if self._pending_reveal and motion_enabled() and not self.window().isMinimized():
            self._pending_reveal = False
            self._progress = 0.0
            self.animation.start()
        else:
            self._reset_motion()
        self.update()

    def _animate(self, value):
        if not motion_enabled() or not self.isVisible() or self.window().isMinimized():
            self._reset_motion()
            return
        self._progress = float(value)
        self.update()

    def _reset_motion(self):
        self.animation.stop()
        self._progress = 1.0
        self._pending_reveal = False
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._reveal()

    def hideEvent(self, event):
        self._reset_motion()
        self._hover_index = -1
        QToolTip.hideText()
        super().hideEvent(event)

    def _plot(self):
        return QRectF(43, 43, max(1, self.width() - 56), max(1, self.height() - 79))

    def _index_at(self, point):
        plot = self._plot()
        if not self.rows or not plot.adjusted(0, -5, 0, 27).contains(point):
            return -1
        return min(len(self.rows) - 1, max(0, int((point.x() - plot.left()) / plot.width() * len(self.rows))))

    def _detail(self, index):
        row = self.rows[index]
        title = f"{tr(MONTHS[row['month'].month - 1]).capitalize()} {row['month'].year}"
        if row.get("future"):
            return tr('{v0} · À venir', v0=title)
        if row.get("averages") is None:
            return tr('{v0} · Aucune activité renseignée', v0=title)
        mean = row["averages"][self.axis] / 60
        total = row["totals"][self.axis] / 60
        return tr('{v0} · {v1} h au total · {v2} h / jour', v0=title, v1=_number(total), v2=_number(mean))

    def _set_description(self):
        index = self._hover_index if self._hover_index >= 0 else self._selected_index
        instructions = tr('Flèches gauche et droite : parcourir les mois. Début et Fin : premier et dernier mois.')
        self.setAccessibleDescription((self._detail(index) + ". " if 0 <= index < len(self.rows) else "") + instructions)

    def mouseMoveEvent(self, event):
        index = self._index_at(event.position())
        if index != self._hover_index:
            self._hover_index = index
            if index >= 0:
                QToolTip.showText(event.globalPosition().toPoint() + QPoint(10, 15), self._detail(index), self)
            else:
                QToolTip.hideText()
            self._set_description()
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._selected_index = self._index_at(event.position())
            self.setFocus(Qt.MouseFocusReason)
            self._set_description()
            self.update()
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self._hover_index = -1
        QToolTip.hideText()
        self._set_description()
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if self.rows and key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End):
            index = self._selected_index
            if key == Qt.Key_Home:
                index = 0
            elif key == Qt.Key_End:
                index = len(self.rows) - 1
            elif key == Qt.Key_Right:
                index = min(len(self.rows) - 1, index + 1)
            else:
                index = max(0, index - 1) if index >= 0 else len(self.rows) - 1
            self._hover_index = -1
            self._selected_index = index
            QToolTip.hideText()
            self._set_description()
            self.update()
            event.accept()
            return
        if key == Qt.Key_Escape:
            self._selected_index = self._hover_index = -1
            QToolTip.hideText()
            self._set_description()
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        if self.rows and self._selected_index < 0:
            self._selected_index = 0
        self._set_description()
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._selected_index = -1
        self._set_description()
        self.update()
        super().focusOutEvent(event)

    def event(self, event):
        if event.type() == QEvent.ToolTip:
            # The per-month text is already positioned by mouseMoveEvent.
            event.accept()
            return True
        return super().event(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter):
        if not self.rows:
            return
        colors = palette_for(self._theme())
        accent = axis_palette(self.axis, self._theme())
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(QFont("Segoe UI", 9))
        plot = self._plot()
        values = [(row["averages"][self.axis] / 60) if row.get("averages") is not None else None for row in self.rows]
        maximum = max(1, math.ceil(max((value for value in values if value is not None), default=0)))
        selected = self._hover_index if self._hover_index >= 0 else self._selected_index
        painter.setPen(QColor(colors["muted"]))
        painter.drawText(QRectF(0, 3, 40, 22), Qt.AlignRight | Qt.AlignVCenter, tr("h / j"))
        if 0 <= selected < len(self.rows):
            detail_rect = QRectF(plot.left() + 8, 0, plot.width() - 8, 28)
            painter.setPen(Qt.NoPen)
            tint = QColor(accent["tint"])
            painter.setBrush(tint)
            painter.drawRoundedRect(detail_rect, 10, 10)
            painter.setPen(QColor(accent["accent"]))
            text = painter.fontMetrics().elidedText(self._detail(selected), Qt.ElideRight, int(detail_rect.width() - 20))
            painter.drawText(detail_rect.adjusted(10, 0, -10, 0), Qt.AlignVCenter, text)
        for step in range(5):
            y = plot.bottom() - plot.height() * step / 4
            grid = QColor(colors["border"])
            grid.setAlpha(180 if step == 0 else 100)
            painter.setPen(QPen(grid, 1, Qt.SolidLine if step == 0 else Qt.DotLine))
            painter.drawLine(plot.left(), y, plot.right(), y)
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(QRectF(0, y - 8, 33, 18), Qt.AlignRight | Qt.AlignVCenter, _number(maximum * step / 4))
        cell_width = plot.width() / len(self.rows)
        bar_width = min(34, cell_width * 0.48)
        for index, (row, value) in enumerate(zip(self.rows, values)):
            center = plot.left() + (index + 0.5) * cell_width
            if index == selected:
                painter.setPen(Qt.NoPen)
                hover = QColor(accent["tint"])
                hover.setAlpha(130)
                painter.setBrush(hover)
                painter.drawRoundedRect(QRectF(center - cell_width * 0.43, plot.top() - 6, cell_width * 0.86, plot.height() + 34), 10, 10)
            if value is not None and value > 0:
                height = max(0.5, plot.height() * value / maximum * self._progress)
                bar = QRectF(center - bar_width / 2, plot.bottom() - height, bar_width, height)
                painter.setPen(Qt.NoPen)
                glow = QRadialGradient(center, plot.bottom() - 2, bar_width * 0.9)
                glow_color = QColor(accent["accent"])
                glow_color.setAlpha(38)
                glow.setColorAt(0, glow_color)
                glow.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setBrush(glow)
                painter.drawEllipse(QRectF(center - bar_width, plot.bottom() - 8, bar_width * 2, 14))
                gradient = QLinearGradient(bar.topLeft(), bar.bottomRight())
                gradient.setColorAt(0, QColor(accent["light"]))
                gradient.setColorAt(0.35, QColor(accent["accent"]))
                gradient.setColorAt(1, QColor(accent["dark"]))
                painter.setBrush(gradient)
                painter.drawRoundedRect(bar, min(7, height / 2), min(7, height / 2))
                if height > 8:
                    sheen = QLinearGradient(bar.topLeft(), bar.topRight())
                    sheen.setColorAt(0, QColor(255, 255, 255, 90))
                    sheen.setColorAt(0.25, QColor(255, 255, 255, 24))
                    sheen.setColorAt(1, QColor(255, 255, 255, 0))
                    painter.setBrush(sheen)
                    painter.drawRoundedRect(bar.adjusted(1, 1, -1, -1), 6, 6)
            elif value is not None:
                # Zero is recorded data. An outlined marker never implies hours.
                painter.setBrush(QColor(colors["surface"]))
                painter.setPen(QPen(QColor(accent["accent"]), 1.8))
                painter.drawEllipse(QRectF(center - 3, plot.bottom() - 3, 6, 6))
            else:
                painter.setPen(QPen(QColor(colors["border"]), 2, Qt.DotLine if row.get("future") else Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(center - 5, plot.bottom(), center + 5, plot.bottom())
            painter.setPen(QColor(accent["accent"] if index == selected else colors["muted"]))
            painter.drawText(QRectF(center - cell_width / 2, plot.bottom() + 9, cell_width, 20), Qt.AlignHCenter | Qt.AlignTop, tr(SHORT_MONTHS[row["month"].month - 1]))
        if self.hasFocus():
            outline = QColor(accent["accent"])
            outline.setAlpha(150)
            painter.setPen(QPen(outline, 1, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)
