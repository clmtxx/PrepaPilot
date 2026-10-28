"""Directional panel motion painted over immediately usable, stationary pages."""
from math import sin, pi, sqrt

from PySide6.QtCore import Qt, QVariantAnimation, QEasingCurve, QEvent, QRectF, QSize, QPoint, QPointF
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPixmap, QPolygonF, QTransform, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .theme import palette_for


class PageTransition(QWidget):
    # Only the decorative 540 ms layer needs these images. The live page remains
    # native-resolution. Bounding raster work keeps 4K/HiDPI navigation cheap.
    MAX_CAPTURE_PIXELS = 2_000_000

    def __init__(self, window):
        super().__init__(window.central)
        self.window = window
        self.before = QPixmap()
        self.after = QPixmap()
        self._light = QPixmap()
        self.progress = 1.0
        self.direction = 1
        self._accent_setting = None
        self._accent = QColor(palette_for(window.ctx.theme)['accent'])
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.NoFocus)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(540)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish)
        QApplication.instance().installEventFilter(self)
        self.hide()

    def capture(self, widget):
        if widget.width() <= 0 or widget.height() <= 0:
            return QPixmap()
        dpr = widget.devicePixelRatioF()
        scale = min(dpr, sqrt(self.MAX_CAPTURE_PIXELS / (widget.width() * widget.height())))
        size = QSize(max(1, int(widget.width() * scale)), max(1, int(widget.height() * scale)))
        image = QPixmap(size)
        image.fill(QColor(palette_for(self.window.ctx.theme)['bg']))
        painter = QPainter(image)
        try:
            painter.scale(size.width() / widget.width(), size.height() / widget.height())
            widget.render(painter, QPoint())
        finally:
            painter.end()
        return image

    def configure(self, *, accent=None):
        """Set the destination's trim colour without changing navigation state."""
        color = QColor(accent) if isinstance(accent, (str, QColor)) else QColor()
        self._accent_setting = color.name() if color.isValid() else None

    def _bounded_image(self, image):
        area = image.width() * image.height()
        if area <= self.MAX_CAPTURE_PIXELS:
            return image
        scale = sqrt(self.MAX_CAPTURE_PIXELS / area)
        return image.scaled(max(1, int(image.width() * scale)),
                            max(1, int(image.height() * scale)),
                            Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def start(self, before, after, rectangle, direction=1):
        self.finish()
        if (before.isNull() or after.isNull() or rectangle.isEmpty()
                or QApplication.instance().property('reducedMotion')):
            return
        self.before, self.after = self._bounded_image(before), self._bounded_image(after)
        self.direction = -1 if direction < 0 else 1
        self._accent = QColor(self._accent_setting or palette_for(self.window.ctx.theme)['accent'])
        self.progress = 0.0
        self._prepare_light()
        self.setGeometry(rectangle)
        self.show()
        self.raise_()
        self.animation.start()

    def _prepare_light(self):
        # The former full-page veil is now a reusable contact shadow attached to
        # the moving panel's leading edge. It never covers a reading area.
        self._light = QPixmap(48, 128)
        self._light.fill(Qt.transparent)
        painter = QPainter(self._light)
        try:
            gradient = QLinearGradient(0, 0, 48, 0)
            gradient.setColorAt(0, QColor(5, 13, 21, 0))
            gradient.setColorAt(.35, QColor(5, 13, 21, 6))
            gradient.setColorAt(.8, QColor(5, 13, 21, 30))
            gradient.setColorAt(1, QColor(5, 13, 21, 85 if self.window.ctx.theme == 'dark' else 58))
            painter.fillRect(self._light.rect(), gradient)
        finally:
            painter.end()

    def advance(self, value):
        self.progress = max(0.0, min(1.0, float(value)))
        self.update()

    def frame_layout(self, progress=None):
        """Deterministic panel geometry; no live control participates in motion."""
        p = self.progress if progress is None else max(0., min(1., float(progress)))
        bounds = QRectF(self.rect())
        distance = max(100., min(180., bounds.width() * .145))
        outgoing = bounds.adjusted(11 * p, 8 * p, -11 * p, -8 * p)
        outgoing.translate(-self.direction * distance * .30 * p, 1.5 * p)
        inset = 8 * (1 - p)
        incoming = bounds.adjusted(inset, inset, -inset, -inset)
        incoming.translate(self.direction * distance * (1 - p), 3 * (1 - p))
        # Become opaque early: the remainder is readable panel movement rather
        # than two sets of semi-transparent text crossing the reading area.
        alpha = min(1., p / .18)
        alpha = alpha * alpha * (3 - 2 * alpha)
        return dict(distance=distance, outgoing=outgoing, incoming=incoming,
                    tilt=min(10., bounds.height() * .018) * (1 - p), opacity=alpha)

    def _panel_transform(self, rect, tilt, *, incoming):
        width, height = self.width(), self.height()
        source = QPolygonF([QPointF(0, 0), QPointF(width, 0),
                            QPointF(width, height), QPointF(0, height)])
        # The far side is just a few pixels shorter, suggesting a panel turning
        # towards the viewer. There is no rotation of the application window.
        left_tilt = tilt if (self.direction < 0) == incoming else 0.
        right_tilt = tilt - left_tilt
        target = QPolygonF([QPointF(rect.left(), rect.top() + left_tilt),
                            QPointF(rect.right(), rect.top() + right_tilt),
                            QPointF(rect.right(), rect.bottom() - right_tilt),
                            QPointF(rect.left(), rect.bottom() - left_tilt)])
        transform = QTransform()
        if not QTransform.quadToQuad(source, target, transform):
            return QTransform()
        return transform

    def finish(self):
        self.animation.stop()
        self.progress = 1.0
        self.hide()
        self.before = QPixmap()
        self.after = QPixmap()
        self._light = QPixmap()

    def hideEvent(self, event):
        # Also release captures when the application is hidden externally.
        if hasattr(self, 'animation'):
            self.animation.stop()
            self.progress = 1.0
            self.before = QPixmap()
            self.after = QPixmap()
            self._light = QPixmap()
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.DynamicPropertyChange and watched is QApplication.instance():
            if bytes(event.propertyName()) in (b'reducedMotion', b'visualTheme'):
                self.finish()
        elif self.isVisible() and kind in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick,
                                           QEvent.KeyPress, QEvent.ShortcutOverride, QEvent.Wheel,
                                           QEvent.TouchBegin, QEvent.WindowDeactivate,
                                           QEvent.WindowStateChange):
            # Cancel the painted layer before the actual input reaches a control.
            self.finish()
        elif self.isVisible() and kind == QEvent.Resize and watched in (
                self.window, self.window.central, getattr(self.window, 'stack', None)):
            self.finish()
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.fillRect(self.rect(), QColor(palette_for(self.window.ctx.theme)['bg']))
            bounds = QRectF(self.rect())
            progress = self.progress
            # Exact endpoints avoid a one-pixel shift or duplicate text when the
            # painted layer hands back to the full-resolution native page.
            if progress <= 0:
                painter.drawPixmap(bounds, self.before, QRectF(self.before.rect()))
                return
            if progress >= 1:
                painter.drawPixmap(bounds, self.after, QRectF(self.after.rect()))
                return
            frame = self.frame_layout()
            painter.setWorldTransform(self._panel_transform(frame['outgoing'],
                                      5 * progress, incoming=False))
            painter.drawPixmap(bounds, self.before, QRectF(self.before.rect()))
            shade = QColor(4, 12, 20, round(20 * sin(pi * progress)))
            painter.fillRect(bounds, shade)
            painter.resetTransform()

            transform = self._panel_transform(frame['incoming'], frame['tilt'], incoming=True)
            painter.setWorldTransform(transform)
            painter.setOpacity(frame['opacity'] * sin(pi * progress) ** .5)
            painter.save()
            if self.direction > 0:
                painter.drawPixmap(QRectF(-30, 3, 30, self.height()), self._light, QRectF(self._light.rect()))
            else:
                painter.translate(self.width() * 2, 0)
                painter.scale(-1, 1)
                painter.drawPixmap(QRectF(self.width() - 30, 3, 30, self.height()),
                                   self._light, QRectF(self._light.rect()))
            painter.restore()
            painter.setOpacity(frame['opacity'])
            painter.drawPixmap(bounds, self.after, QRectF(self.after.rect()))
            # A thin page-coloured seam gives the moving panel a visible edge.
            # It fades away before the live page resumes, and has no timer.
            trim = QColor(self._accent)
            trim.setAlphaF(.48 * sin(pi * progress))
            painter.setPen(QPen(trim, 1.1))
            leading = 0.5 if self.direction > 0 else self.width() - .5
            painter.drawLine(QPointF(leading, 1), QPointF(leading, self.height() - 1))
        finally:
            painter.end()

    def shutdown(self):
        self.finish()
        QApplication.instance().removeEventFilter(self)
