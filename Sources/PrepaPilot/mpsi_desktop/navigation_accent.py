"""A small moving light under the current page, with no effect on hit targets."""
from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QRect, QVariantAnimation, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from .page_figures import page_palette
from .widgets import motion_enabled, observe_visual_preferences


class NavigationAccent(QWidget):
    """Decorative, bounded navigation feedback; all resting states are timer-free."""

    def __init__(self, sidebar, buttons, current="home"):
        super().__init__(sidebar)
        self.buttons = dict(buttons)
        self.current = current
        self._closed = False
        self._target = QRect()
        self._origin = QRect()
        self._color = self._page_color()
        self._from_color = QColor(self._color)
        self._to_color = QColor(self._color)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(260)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self._advance)
        self.animation.finished.connect(self._snap_geometry)
        observe_visual_preferences(self)
        sidebar.installEventFilter(self)
        for control in self.buttons.values():
            control.installEventFilter(self)
        self.sync()

    def _page_color(self):
        app = QApplication.instance()
        theme = app.property("visualTheme") if app is not None else "light"
        return QColor(page_palette(self.current, theme or "light")["accent"])

    def _target_rect(self):
        control = self.buttons.get(self.current)
        sidebar = self.parentWidget()
        if control is None or control.isHidden() or sidebar.width() < 12 or sidebar.height() < 10:
            return QRect()
        bounds = control.geometry()
        width = min(66, max(22, bounds.width() - 24), sidebar.width() - 8)
        left = max(4, min(sidebar.width() - width - 4, round(bounds.center().x() - width / 2)))
        top = max(0, min(sidebar.height() - 9, bounds.bottom() + 1))
        return QRect(left, top, width, 9)

    def _snap_geometry(self):
        self._target = self._target_rect()
        self._color = self._page_color()
        if self._target.isValid():
            self.setGeometry(self._target)
        self.update()

    def sync(self):
        """Immediately align after layout, theme or accessibility changes."""
        self.animation.stop()
        self._snap_geometry()
        self.setVisible(not self._closed and self._target.isValid())
        if self.isVisible():
            self.raise_()

    def _reset_motion(self):
        self.animation.stop()
        self._snap_geometry()

    def select(self, key, *, animate=True):
        if self._closed or key not in self.buttons:
            return
        previous = self.current
        self.current = key
        destination = self._target_rect()
        if (key == previous or not animate or not motion_enabled() or not self.isVisible()
                or not destination.isValid()):
            self.sync()
            return
        self.animation.stop()
        self._origin = QRect(self.geometry())
        self._target = destination
        self._from_color = QColor(self._color)
        self._to_color = self._page_color()
        self.raise_()
        self.animation.start()

    def _advance(self, value):
        fraction = float(value)
        origin, target = self._origin, self._target
        # Only this small child moves. Text, layouts and interactive bounds stay still.
        self.setGeometry(QRect(
            round(origin.x() + (target.x() - origin.x()) * fraction),
            round(origin.y() + (target.y() - origin.y()) * fraction),
            round(origin.width() + (target.width() - origin.width()) * fraction),
            9,
        ))
        self._color = QColor.fromRgbF(*(
            a + (b - a) * fraction
            for a, b in zip(self._from_color.getRgbF(), self._to_color.getRgbF())
        ))
        self.update()

    def eventFilter(self, watched, event):
        if not self._closed:
            kind = event.type()
            if watched is self.parentWidget() and kind in (QEvent.Resize, QEvent.Show, QEvent.Hide):
                self.sync()
            elif kind in (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.Hide, QEvent.LayoutRequest):
                if self._target_rect() != self._target:
                    self.sync()
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        self._reset_motion()
        super().showEvent(event)

    def hideEvent(self, event):
        self._reset_motion()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            # Three tiny translucent bands form a satin highlight without a blur effect.
            for inset, alpha, height in ((0, 18, 8), (3, 35, 5), (6, 220, 2)):
                rect = self.rect().adjusted(inset, 0, -inset, 0)
                rect.setTop((self.height() - height) // 2)
                rect.setHeight(height)
                gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
                edge = QColor(self._color)
                edge.setAlpha(0)
                middle = QColor(self._color)
                middle.setAlpha(alpha)
                gradient.setColorAt(0, edge)
                gradient.setColorAt(.25, middle)
                gradient.setColorAt(.75, middle)
                gradient.setColorAt(1, edge)
                painter.setBrush(gradient)
                painter.drawRoundedRect(rect, height / 2, height / 2)
        finally:
            painter.end()

    def shutdown(self):
        self._closed = True
        self.animation.stop()
        self.hide()
