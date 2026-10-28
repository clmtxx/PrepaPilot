"""Readable notices with a compact glass seal and explicit, never guessed status."""
from math import isfinite, sin, pi

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal, QEvent, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QWidget, QFrame, QHBoxLayout, QVBoxLayout,
                               QLabel, QPushButton, QScrollArea, QSizePolicy)

from .i18n import tr
from .theme import palette_for
from .visuals import _ArtworkCache
from .widgets import motion_enabled, observe_visual_preferences


def _accent(theme, kind):
    colors = palette_for(theme)
    return QColor(colors[{'warning': 'orange', 'error': 'danger', 'success': 'green'}.get(kind, 'accent')])


def _mix(left, right, amount):
    left, right = QColor(left), QColor(right)
    return QColor.fromRgbF(*(a + (b - a) * amount for a, b in zip(left.getRgbF(), right.getRgbF())))


class NoticeOrb(QWidget):
    """Legacy attribute name retained; the artwork is now a neutral 32 px seal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme, self.kind = 'light', 'info'
        self._progress = 1.
        self._artwork = _ArtworkCache()
        self.setFixedSize(32, 32)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAccessibleDescription(tr('Illustration décorative'))
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(520)
        self.animation.setStartValue(0.)
        self.animation.setEndValue(1.)
        self.animation.setEasingCurve(QEasingCurve.InOutSine)
        self.animation.valueChanged.connect(self._advance)
        observe_visual_preferences(self)

    def sizeHint(self):
        return QSize(32, 32)

    def _advance(self, value):
        self._progress = float(value) if motion_enabled() and self.isVisible() else 1.
        self.update()

    def _reset_motion(self):
        self.animation.stop()
        self._progress = 1.
        self.update()

    def play(self):
        self._reset_motion()
        if motion_enabled() and self.isVisible():
            self.animation.start()

    def hideEvent(self, event):
        self._reset_motion()
        super().hideEvent(event)

    def _paint_base(self, painter):
        dark = self.theme == 'dark'
        colors = palette_for(self.theme)
        accent = _accent(self.theme, self.kind)
        rect = QRectF(3, 3, 26, 26)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 38 if dark else 16))
        painter.drawRoundedRect(rect.translated(0, 1), 8, 8)
        glass = QLinearGradient(rect.topLeft(), rect.bottomRight())
        glass.setColorAt(0, _mix(colors['surface'], accent, .14 if dark else .08))
        glass.setColorAt(1, _mix(colors['surface2'], accent, .26 if dark else .14))
        painter.setBrush(glass)
        rim = QColor(accent)
        rim.setAlpha(110 if dark else 76)
        painter.setPen(QPen(rim, .8))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 37 if dark else 155), .8))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 7, 7)
        painter.setPen(QPen(accent, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if self.kind == 'success':
            path = QPainterPath(QPointF(10, 16))
            path.lineTo(14, 20)
            path.lineTo(22, 11)
            painter.drawPath(path)
        elif self.kind == 'error':
            painter.drawLine(QPointF(11.5, 11.5), QPointF(20.5, 20.5))
            painter.drawLine(QPointF(20.5, 11.5), QPointF(11.5, 20.5))
        elif self.kind == 'warning':
            painter.drawLine(QPointF(16, 10), QPointF(16, 17))
            painter.drawPoint(QPointF(16, 22))
        else:
            painter.drawPoint(QPointF(16, 10.5))
            painter.drawLine(QPointF(16, 15), QPointF(16, 22))

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            self._artwork.prepare(self, 32, 32, (self.theme, self.kind), padding=0)
            self._artwork.draw(painter, 'seal', self._paint_base)
            if 0 < self._progress < 1 and motion_enabled():
                clip = QPainterPath()
                clip.addRoundedRect(QRectF(4, 4, 24, 24), 7, 7)
                painter.setClipPath(clip)
                center = -7 + 46 * self._progress
                sheen = QLinearGradient(center - 4, 0, center + 4, 0)
                sheen.setColorAt(0, QColor(255, 250, 232, 0))
                sheen.setColorAt(.5, QColor(255, 250, 232, round(90 * sin(pi * self._progress))))
                sheen.setColorAt(1, QColor(255, 250, 232, 0))
                painter.fillRect(QRectF(0, 0, 32, 32), sheen)
        finally:
            painter.end()


class _CopyButton(QPushButton):
    def paintEvent(self, event):
        super().paintEvent(event)
        parent = self.parentWidget()
        colors = palette_for(getattr(parent, 'theme', 'light'))
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(colors['muted']), 1.15, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            center = QPointF(self.rect().center())
            painter.drawRoundedRect(QRectF(center.x() - 2.5, center.y() - 6.5, 8, 10), 1.5, 1.5)
            painter.drawRoundedRect(QRectF(center.x() - 5.5, center.y() - 3.5, 8, 10), 1.5, 1.5)
        finally:
            painter.end()


class NoticeCard(QFrame):
    """Exact text and explicit status, with bounded reading space and no idle loop."""

    dismissed = Signal()
    interaction_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme, self.kind = 'light', 'info'
        self._remaining = 1.
        self._pointer_inside = False
        self._interacting = False
        self._fitting = False
        self._max_height = 240
        self.setObjectName('NoticeCard')
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 12, 15)
        row.setSpacing(10)
        self.orb = NoticeOrb(self)
        row.addWidget(self.orb, 0, Qt.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        self.heading = QLabel(tr('Information'), objectName='noticeHeading')
        self.heading.setTextFormat(Qt.PlainText)
        self.heading.setWordWrap(True)
        self.message = QLabel(objectName='noticeMessage')
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.PlainText)
        self.message.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.message.setFocusPolicy(Qt.StrongFocus)
        self.message.setMinimumWidth(0)
        self.message.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.message.setAutoFillBackground(False)
        self.message_area = QScrollArea(self)
        self.message_area.setObjectName('noticeMessageArea')
        self.message_area.setFrameShape(QFrame.NoFrame)
        self.message_area.setWidgetResizable(True)
        self.message_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.message_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.message_area.setFocusPolicy(Qt.NoFocus)
        self.message_area.viewport().setAutoFillBackground(False)
        self.message_area.setWidget(self.message)
        copy.addWidget(self.heading)
        copy.addWidget(self.message_area)
        row.addLayout(copy, 1)
        actions = QHBoxLayout()
        actions.setSpacing(3)
        self.copy_button = _CopyButton('', self)
        self.copy_button.setObjectName('noticeCopy')
        self.copy_button.setFixedSize(30, 30)
        self.copy_button.setAccessibleName(tr('Copier le message'))
        self.copy_button.setToolTip(tr('Copier le message'))
        self.copy_button.clicked.connect(self.copy_message)
        self.close_button = QPushButton('×', self)
        self.close_button.setObjectName('noticeClose')
        self.close_button.setFixedSize(30, 30)
        self.close_button.setAccessibleName(tr('Fermer le message'))
        self.close_button.setToolTip(tr('Fermer le message'))
        self.close_button.clicked.connect(self.dismissed)
        for control in (self.copy_button, self.close_button):
            control.setCursor(Qt.PointingHandCursor)
            control.setFocusPolicy(Qt.StrongFocus)
            control.setAutoDefault(False)
            actions.addWidget(control)
        row.addLayout(actions, 0)
        row.setAlignment(actions, Qt.AlignTop)
        self.lifetime_animation = QVariantAnimation(self)
        self.lifetime_animation.setDuration(4200)
        self.lifetime_animation.setStartValue(1.)
        self.lifetime_animation.setEndValue(0.)
        self.lifetime_animation.valueChanged.connect(self._advance)
        self._interaction_timer = QTimer(self)
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.timeout.connect(self._sync_interaction)
        for control in (self.message, self.copy_button, self.close_button):
            control.installEventFilter(self)
        observe_visual_preferences(self)
        self.apply_theme('light')
        self.fit_width(620)

    def text(self):
        return self.message.text()

    def setText(self, text, *, kind='info', title=None):
        self.stop_effects()
        self.message.setText(str(text))
        self.message.setAccessibleName(str(text))
        self.message_area.verticalScrollBar().setValue(0)
        self.setAccessibleName(str(text))
        self.set_kind(kind, title=title)
        self.fit_width(self.width(), self._max_height)
        self.updateGeometry()

    def set_kind(self, kind='info', *, title=None):
        self.kind = kind if kind in {'info', 'warning', 'error', 'success'} else 'info'
        self.orb.kind = self.kind
        labels = {'info': 'Information', 'warning': 'À vérifier', 'error': 'Erreur', 'success': 'Action confirmée'}
        self.heading.setText(str(title) if title is not None else tr(labels[self.kind]))
        self.setAccessibleDescription(self.heading.text())
        self.orb.update()
        self.update()

    def copy_message(self):
        QApplication.clipboard().setText(self.text())

    def set_duration(self, milliseconds):
        self.lifetime_animation.setDuration(max(1, int(milliseconds)))

    def set_remaining(self, value):
        value = float(value)
        self._remaining = max(0., min(1., value)) if isfinite(value) else 1.
        self.update(12, self.height() - 8, max(1, self.width() - 24), 6)

    def fit_width(self, width, max_height=240):
        """Keep dismissal visible; long plain messages remain scrollable in place."""
        if self._fitting:
            return
        self._fitting = True
        try:
            self._max_height = max(76, int(max_height))
            self.setFixedWidth(max(210, int(width)))
            self.ensurePolished()
            self.heading.ensurePolished()
            self.message.ensurePolished()
            self.message.setMinimumHeight(0)
            text_width = max(30, self.width() - 141)
            heading_height = max(self.heading.fontMetrics().height(), self.heading.heightForWidth(text_width))
            available = max(20, min(180, self._max_height - 27 - heading_height - 3))
            content_height = max(20, self.message.heightForWidth(text_width))
            if content_height > available:
                text_width -= self.message_area.verticalScrollBar().sizeHint().width()
                content_height = max(20, self.message.heightForWidth(max(24, text_width)))
            horizontal = self.message.minimumSizeHint().width() > text_width
            viewport_height = content_height + (self.message_area.horizontalScrollBar().sizeHint().height() if horizontal else 0)
            self.message.setMinimumHeight(content_height)
            self.message_area.setFixedHeight(min(viewport_height, available))
            body_height = max(32, heading_height + 3 + min(viewport_height, available))
            self.setFixedHeight(min(self._max_height, body_height + 27))
            self.layout().activate()
        finally:
            self._fitting = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'message_area'):
            self.fit_width(self.width(), self._max_height)

    def apply_theme(self, theme):
        self.theme = theme
        self.orb.theme = theme
        self.stop_effects()
        colors = palette_for(theme)
        self.setStyleSheet(
            f"QLabel#noticeHeading {{color:{colors['muted']};font-size:10px;font-weight:600;letter-spacing:.7px;background:transparent;}}"
            f"QLabel#noticeMessage {{color:{colors['text']};font-size:13px;background:transparent;border:none;padding:0;}}"
            "QScrollArea#noticeMessageArea {background:transparent;border:none;padding:0;}"
            f"QPushButton#noticeClose,QPushButton#noticeCopy {{color:{colors['muted']};background:transparent;border:1px solid transparent;border-radius:8px;padding:0;min-height:0;min-width:0;font-size:20px;}}"
            f"QPushButton#noticeClose:hover,QPushButton#noticeCopy:hover {{color:{colors['text']};background:{colors['surface2']};}}"
            f"QPushButton#noticeClose:focus,QPushButton#noticeCopy:focus {{border:1px solid {colors['accent']};background:{colors['accent_soft']};}}"
        )
        self.update()

    def restart(self):
        self.stop_effects()
        self._remaining = 1.
        if motion_enabled() and self.isVisible():
            self.orb.play()
            self.lifetime_animation.start()
        self.update()

    def _advance(self, value):
        self.set_remaining(float(value) if motion_enabled() else 1.)

    def _reset_motion(self):
        self.stop_effects()

    def stop_effects(self):
        self.lifetime_animation.stop()
        self.orb._reset_motion()
        self._remaining = 1.
        self.update()

    def _sync_interaction(self):
        focused = QApplication.focusWidget()
        interacting = self.isVisible() and (self._pointer_inside or focused is self or
                                           (focused is not None and self.isAncestorOf(focused)))
        if interacting != self._interacting:
            self._interacting = interacting
            self.interaction_changed.emit(interacting)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            self._interaction_timer.start(0)
        return super().eventFilter(watched, event)

    def enterEvent(self, event):
        self._pointer_inside = True
        self._sync_interaction()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._pointer_inside = False
        self._sync_interaction()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self.stop_effects()
        self._interaction_timer.stop()
        self._pointer_inside = False
        if self._interacting:
            self._interacting = False
            self.interaction_changed.emit(False)
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            rect = QRectF(self.rect()).adjusted(2, 2, -2, -3)
            colors = palette_for(self.theme)
            dark = self.theme == 'dark'
            accent = _accent(self.theme, self.kind)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 15 if not dark else 42))
            painter.drawRoundedRect(rect.translated(0, 2), 16, 16)
            surface = QLinearGradient(rect.topLeft(), rect.bottomRight())
            surface.setColorAt(0, QColor(colors['surface']))
            surface.setColorAt(1, _mix(colors['surface'], colors['surface2'], .36))
            painter.setBrush(QBrush(surface))
            painter.setPen(QPen(QColor(colors['border']), .9))
            painter.drawRoundedRect(rect, 16, 16)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 25 if dark else 150), .8))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 15, 15)
            inlay = QColor(accent)
            inlay.setAlpha(190 if dark else 170)
            painter.setPen(QPen(inlay, 1.7, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(6, 19), QPointF(6, min(self.height() - 19, 41)))
            # A quiet countdown trim concerns display time, never task progress.
            if motion_enabled() and self._remaining > 0:
                rail = QColor(accent)
                rail.setAlpha(92 if dark else 78)
                painter.setPen(QPen(rail, 1.2, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(18, self.height() - 6),
                                 QPointF(18 + (self.width() - 36) * self._remaining, self.height() - 6))
        finally:
            painter.end()
