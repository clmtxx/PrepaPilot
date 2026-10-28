from .i18n import tr
from math import hypot, sin, pi
from weakref import WeakSet

from PySide6.QtCore import Qt, QObject, QEvent, QAbstractAnimation, QVariantAnimation, QEasingCurve, QPropertyAnimation, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPainterPath, QLinearGradient, QRadialGradient, QPen, QBrush
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QWidget, QMessageBox, QScrollArea, QSizePolicy, QDialog, QApplication)
from .theme import palette_for
from shiboken6 import isValid


def motion_enabled(ctx=None):
    app = QApplication.instance()
    allowed = app is None or not app.property("reducedMotion")
    return allowed and (ctx is None or not ctx.db.get_setting("desktop_reduced_motion", False))


def _visual_palette():
    app = QApplication.instance()
    return palette_for(app.property("visualTheme") if app is not None else "light")


class _PreferenceObserver(QObject):
    """One application filter, regardless of how many cards and buttons exist."""

    def __init__(self, app):
        super().__init__(app)
        self.widgets = WeakSet()
        app.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is QApplication.instance() and event.type() == QEvent.DynamicPropertyChange:
            name = bytes(event.propertyName())
            reset = name == b"reducedMotion" and not motion_enabled()
            if reset or name == b"visualTheme":
                for widget in tuple(self.widgets):
                    if not isValid(widget):
                        self.widgets.discard(widget)
                    elif reset:
                        widget._reset_motion()
                    else:
                        widget.update()
        return super().eventFilter(watched, event)


def observe_visual_preferences(widget):
    """Register a QWidget implementing _reset_motion; theme changes repaint it."""
    app = QApplication.instance()
    if app is not None:
        if not hasattr(app, "_prepapilot_visual_observer"):
            app._prepapilot_visual_observer = _PreferenceObserver(app)
        app._prepapilot_visual_observer.widgets.add(widget)


class _VisualPreferences:
    def _watch_preferences(self):
        observe_visual_preferences(self)


class AnimatedButton(_VisualPreferences, QPushButton):
    """An enamel-like native control with finite glints and a small spring lip."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._hover = 0.0
        self._ripple = 1.0
        self._sheen = 1.0
        self._origin = QPointF()
        self._light = QPointF(0.5, 0.2)
        self._sparkle = 1.0
        self._depth = 0.0
        self.hover_animation = QVariantAnimation(self)
        self.hover_animation.setDuration(180)
        self.hover_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.hover_animation.valueChanged.connect(self._set_hover)
        self.press_animation = QVariantAnimation(self)
        self.press_animation.setDuration(460)
        self.press_animation.setStartValue(0.0)
        self.press_animation.setEndValue(1.0)
        self.press_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.press_animation.valueChanged.connect(self._set_ripple)
        self.sheen_animation = QVariantAnimation(self)
        self.sheen_animation.setDuration(620)
        self.sheen_animation.setStartValue(0.0)
        self.sheen_animation.setEndValue(1.0)
        self.sheen_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.sheen_animation.valueChanged.connect(self._set_sheen)
        self.light_animation = QVariantAnimation(self)
        self.light_animation.setDuration(140)
        self.light_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.light_animation.valueChanged.connect(self._set_light)
        self.sparkle_animation = QVariantAnimation(self)
        self.sparkle_animation.setDuration(660)
        self.sparkle_animation.setStartValue(0.0)
        self.sparkle_animation.setEndValue(1.0)
        self.sparkle_animation.setEasingCurve(QEasingCurve.Linear)
        self.sparkle_animation.valueChanged.connect(self._set_sparkle)
        self.depth_animation = QVariantAnimation(self)
        self.depth_animation.setDuration(120)
        self.depth_animation.valueChanged.connect(self._set_depth)
        self.setMouseTracking(True)
        self.setMinimumHeight(40)
        self._watch_preferences()

    def _set_hover(self, value):
        if self._hover != float(value):
            self._hover = float(value)
            self.update()

    def _set_ripple(self, value):
        self._ripple = float(value)
        self.update()

    def _set_sheen(self, value):
        self._sheen = float(value)
        self.update()

    def _set_light(self, value):
        if self._light != value:
            self._light = QPointF(value)
            self.update()

    def _set_sparkle(self, value):
        self._sparkle = float(value)
        self.update()

    def _set_depth(self, value):
        self._depth = max(-0.22, min(1.0, float(value)))
        self.update()

    def _animate_depth(self, pressed):
        if not motion_enabled() or not self.isEnabled():
            return
        self.depth_animation.stop()
        self.depth_animation.setDuration(110 if pressed else 290)
        self.depth_animation.setEasingCurve(QEasingCurve.OutCubic if pressed else QEasingCurve.OutBack)
        # Fast clicks still show a short release from a compressed surface.
        self.depth_animation.setStartValue(self._depth if pressed else max(0.72, self._depth))
        self.depth_animation.setEndValue(1.0 if pressed else 0.0)
        self.depth_animation.start()

    def _track_light(self, position):
        if not motion_enabled() or not self.isEnabled():
            return
        # Normalized and clamped: the lens stays on the button, even during a drag.
        target = QPointF(max(0.15, min(0.85, position.x() / max(1, self.width()))),
                         max(0.2, min(0.8, position.y() / max(1, self.height()))))
        running = self.light_animation.state() == QAbstractAnimation.Running
        if (running and self.light_animation.endValue() == target) or (not running and self._light == target):
            return
        self.light_animation.stop()
        self.light_animation.setStartValue(self._light)
        self.light_animation.setEndValue(target)
        self.light_animation.start()

    def _reset_motion(self):
        # Qt can dispatch a hide/change event while constructing a styled button.
        for name in ('hover_animation', 'press_animation', 'sheen_animation',
                     'light_animation', 'sparkle_animation', 'depth_animation'):
            animation = getattr(self, name, None)
            if animation is not None:
                animation.stop()
        self._hover, self._ripple, self._sheen = 0.0, 1.0, 1.0
        self._light = QPointF(0.5, 0.2)
        self._sparkle, self._depth = 1.0, 0.0
        self.update()

    def _animate_hover(self, target):
        running = self.hover_animation.state() == QAbstractAnimation.Running
        if (not running and self._hover == target) or (running and self.hover_animation.endValue() == target):
            return
        self.hover_animation.stop()
        if motion_enabled() and self.isEnabled():
            self.hover_animation.setStartValue(self._hover)
            self.hover_animation.setEndValue(target)
            self.hover_animation.start()
        else:
            self._set_hover(0.0)

    def enterEvent(self, event):
        self._animate_hover(1.0)
        self._track_light(event.position())
        if motion_enabled() and self.isEnabled():
            self.sparkle_animation.stop()
            self.sparkle_animation.start()
        if motion_enabled() and self.isEnabled() and self.property("role") == "primary":
            self.sheen_animation.stop()
            self.sheen_animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_hover(0.0)
        self.sheen_animation.stop()
        self._set_sheen(1.0)
        self.light_animation.stop()
        self.sparkle_animation.stop()
        self._set_sparkle(1.0)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._reset_motion()
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.EnabledChange and not self.isEnabled():
            self._reset_motion()
        super().changeEvent(event)

    def _press_at(self, position):
        if motion_enabled() and self.isEnabled():
            self._origin = QPointF(position)
            self.press_animation.stop()
            self.press_animation.start()
            self.sparkle_animation.stop()
            self.sparkle_animation.start()
            self._animate_depth(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_at(event.position())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._track_light(event.position())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self._animate_depth(False)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter) and not event.isAutoRepeat():
            self._press_at(QPointF(self.rect().center()))
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter) and not event.isAutoRepeat():
            self._animate_depth(False)

    def _material_accent(self):
        """Read the nearest surface pigment; no data access during painting."""
        owner = self
        while owner is not None:
            value = owner.property('materialAccent')
            if isinstance(value, (str, QColor)):
                color = QColor(value)
                if color.isValid():
                    return color.name()
            owner = owner.parentWidget()
        return None

    def paintEvent(self, event):
        super().paintEvent(event)
        from .button_material import button_radius, paint_rim, paint_sparkles
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        role = self.property("role")
        radius = button_radius(role)
        clip.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), radius, radius)
        p.setClipPath(clip)
        primary = role == "primary"
        material_accent = self._material_accent()
        palette = dict(_visual_palette())
        if material_accent is not None:
            palette['accent'] = material_accent
        allowed = motion_enabled() and self.isEnabled()
        app = QApplication.instance()
        dark = app is not None and app.property('visualTheme') == 'dark'
        paint_rim(p, self.rect(), palette, role, dark=dark,
                  hover=self._hover if allowed else 0,
                  depth=self._depth if allowed else float(self.isDown()),
                  light=self._light, enabled=self.isEnabled(), checked=self.isChecked(),
                  material_accent=material_accent)
        if not allowed:
            p.end()
            return
        color = QColor("#ffffff" if primary else palette["danger" if role == "danger" else "accent"])
        color.setAlphaF(self._hover * 0.055)
        p.fillPath(clip, color)
        if self._hover > 0:
            # A small elliptical reflection gives the surface depth. It is painted
            # directly and settles after pointer movement: no shadow, timer or blur.
            lens_radius = max(24.0, min(96.0, self.width() * 0.42))
            lens = QRadialGradient(QPointF(), lens_radius)
            light = QColor("#ffffff" if primary else color)
            light.setAlphaF(self._hover * (0.15 if primary else 0.075))
            lens.setColorAt(0, light)
            light.setAlphaF(self._hover * (0.055 if primary else 0.025))
            lens.setColorAt(0.48, light)
            light.setAlpha(0)
            lens.setColorAt(1, light)
            p.save()
            p.translate(self._light.x() * self.width(), self._light.y() * self.height())
            p.scale(1, 0.54)
            p.setPen(Qt.NoPen)
            p.setBrush(lens)
            p.drawEllipse(QPointF(), lens_radius, lens_radius)
            p.restore()

            # Two restrained edge lights read as a bevel without shifting text.
            bevel = QLinearGradient(0, 1, 0, self.height() - 1)
            edge = QColor("#ffffff" if primary else color)
            edge.setAlphaF(self._hover * (0.42 if primary else 0.22))
            bevel.setColorAt(0, edge)
            edge.setAlphaF(self._hover * 0.025)
            bevel.setColorAt(0.48, edge)
            edge.setAlphaF(self._hover * (0.15 if primary else 0.12))
            bevel.setColorAt(1, edge)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QBrush(bevel), 1.0))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), radius, radius)
        if primary and self._sheen < 1:
            # The stripe crosses once per entry. Neither geometry nor hit testing changes.
            band = max(28.0, self.width() * 0.28)
            center = -band - self.height() + (self.width() + 2 * band + 2 * self.height()) * self._sheen
            stripe = QLinearGradient(-band / 2, 0, band / 2, 0)
            stripe.setColorAt(0, QColor(255, 255, 255, 0))
            stripe.setColorAt(0.5, QColor(255, 255, 255, 44))
            stripe.setColorAt(1, QColor(255, 255, 255, 0))
            p.save()
            p.translate(center, self.height() / 2)
            p.rotate(-22)
            p.fillRect(QRectF(-band / 2, -self.height() * 2, band, self.height() * 4), stripe)
            p.restore()
        if self._ripple < 1:
            reach = hypot(max(self._origin.x(), self.width() - self._origin.x()),
                          max(self._origin.y(), self.height() - self._origin.y()))
            radius = max(3.0, reach * self._ripple)
            halo = QRadialGradient(self._origin, radius)
            color.setAlphaF((1 - self._ripple) * 0.24)
            halo.setColorAt(0, color)
            color.setAlphaF((1 - self._ripple) * 0.10)
            halo.setColorAt(0.65, color)
            color.setAlpha(0)
            halo.setColorAt(1, color)
            p.setBrush(halo)
            p.setPen(Qt.NoPen)
            p.drawEllipse(self._origin, radius, radius)
            color.setAlphaF((1 - self._ripple) * 0.20)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(color, 1.25))
            p.drawEllipse(self._origin, radius, radius)
            # The inset edge compresses and releases once, with the native button
            # and its focus ring left intact. Reuse the ripple's finite animation.
            pressure = sin(pi * self._ripple)
            inset = 2.0 + 1.7 * pressure
            edge = QColor("#ffffff" if primary else color)
            edge.setAlphaF(pressure * (0.32 if primary else 0.22))
            p.setPen(QPen(edge, 1.0))
            corner = button_radius(role)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(inset, inset, -inset, -inset),
                              max(2, corner - inset), max(2, corner - inset))
        paint_sparkles(p, self.rect(), role, self._sparkle, dark=dark,
                       material_accent=material_accent)
        p.end()


class AnimatedDialog(_VisualPreferences, QDialog):
    """Native dialog focus and modality, with a brief entrance when permitted."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._watch_preferences()

    def _reset_motion(self):
        if hasattr(self, "_entrance"):
            self._entrance.stop()
        self.setWindowOpacity(1.0)

    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, "_entrance"):
            self._entrance = QPropertyAnimation(self, b"windowOpacity", self)
            self._entrance.setDuration(200)
            self._entrance.setEasingCurve(QEasingCurve.OutCubic)
        self._entrance.stop()
        if motion_enabled(getattr(self, "ctx", None)) and QApplication.platformName() != "offscreen":
            self.setWindowOpacity(0.0)
            self._entrance.setStartValue(0.0)
            self._entrance.setEndValue(1.0)
            self._entrance.start()
        else:
            self.setWindowOpacity(1.0)

    def hideEvent(self, event):
        if hasattr(self, "_entrance"):
            self._entrance.stop()
        self.setWindowOpacity(1.0)
        super().hideEvent(event)


class _RowFeedback(_VisualPreferences, QWidget):
    def __init__(self, table, row, ctx):
        super().__init__(table.viewport())
        self.ctx = ctx
        self.table, self.row, self.progress = table, row, 0.0
        self.identity = table.item(row, 0).data(Qt.UserRole)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(900)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self._reset_motion)
        self._watch_preferences()
        self._position()
        self.show()
        self.animation.start()

    def _reset_motion(self):
        self.animation.stop()
        self.progress = 1.0
        self.hide()
        self.deleteLater()

    def hideEvent(self, event):
        # Leaving the page ends feedback immediately, including before deferred deletion.
        self.animation.stop()
        self.progress = 1.0
        self.deleteLater()
        super().hideEvent(event)

    def advance(self, value):
        self.progress = value
        self._position()
        self.update()

    def _position(self):
        item = self.table.item(self.row, 0)
        if item is None or item.data(Qt.UserRole) != self.identity:
            self.hide()
            return
        rect = self.table.visualItemRect(item)
        rect.setLeft(0)
        rect.setRight(self.table.viewport().width() - 1)
        if self.geometry() != rect:
            self.setGeometry(rect)

    def paintEvent(self, event):
        # Context preferences were checked before creation; live changes arrive
        # through the shared observer. Never query SQLite on animation frames.
        if not motion_enabled():
            return
        item = self.table.item(self.row, 0)
        if item is None or item.data(Qt.UserRole) != self.identity:
            return
        color = QColor(_visual_palette()["accent"])
        color.setAlphaF(0.19 * (1 - self.progress))
        p = QPainter(self)
        p.fillRect(self.rect(), color)
        p.end()


def animate_table_row(table, row, ctx):
    for feedback in table.viewport().findChildren(_RowFeedback):
        feedback._reset_motion()
    if 0 <= row < table.rowCount() and table.item(row, 0) and motion_enabled(ctx):
        _RowFeedback(table, row, ctx)


class Card(_VisualPreferences, QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(26, 24, 26, 24)
        self.body.setSpacing(14)
        self._hover = 0.0
        self._light = QPointF(.82, .08)
        self._pointer_figures = WeakSet()
        self.hover_animation = QVariantAnimation(self)
        self.hover_animation.setDuration(220)
        self.hover_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.hover_animation.valueChanged.connect(self._set_hover)
        self.light_animation = QVariantAnimation(self)
        self.light_animation.setDuration(210)
        self.light_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.light_animation.valueChanged.connect(self._advance_light)
        # HoverMove propagates through native child controls, including labels
        # and editors which handle ordinary MouseMove themselves.
        self.setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)
        self._watch_preferences()

    def bind_pointer_figure(self, figure):
        self._pointer_figures.add(figure)
        figure.bind_pointer_surface(self)

    def _advance_light(self, value):
        if motion_enabled() and self.isVisible() and self.isEnabled():
            self._light = QPointF(value)
            self.update()

    def _track_light(self, position):
        if not motion_enabled() or not self.isEnabled() or not self.isVisible():
            return
        target = QPointF(max(.05, min(.95, position.x() / max(1, self.width()))),
                         max(.02, min(.98, position.y() / max(1, self.height()))))
        running = self.light_animation.state() == QAbstractAnimation.Running
        if (running and self.light_animation.endValue() == target) or (not running and self._light == target):
            return
        self.light_animation.stop()
        self.light_animation.setStartValue(self._light)
        self.light_animation.setEndValue(target)
        self.light_animation.start()

    def _track_pointer(self, position):
        if not motion_enabled() or not self.isEnabled() or not self.isVisible():
            return
        self._track_light(position)
        target = QPointF(max(-1., min(1., position.x() / max(1, self.width()) * 2 - 1)),
                         max(-1., min(1., position.y() / max(1, self.height()) * 2 - 1)))
        for figure in tuple(self._pointer_figures):
            if isValid(figure) and figure.isVisible():
                figure._move_to(target)

    def event(self, event):
        if event.type() == QEvent.HoverMove and hasattr(self, 'light_animation'):
            self._track_pointer(event.position())
        return super().event(event)

    def _set_hover(self, value):
        if self._hover != float(value):
            self._hover = float(value)
            self.update()

    def _reset_motion(self):
        self.hover_animation.stop()
        self.light_animation.stop()
        self._light = QPointF(.82, .08)
        for figure in tuple(self._pointer_figures):
            if isValid(figure):
                figure._reset_motion()
        self._set_hover(0.0)

    def _animate_hover(self, target):
        running = self.hover_animation.state() == QAbstractAnimation.Running
        if (not running and self._hover == target) or (running and self.hover_animation.endValue() == target):
            return
        self.hover_animation.stop()
        if motion_enabled() and self.isEnabled():
            self.hover_animation.setStartValue(self._hover)
            self.hover_animation.setEndValue(target)
            self.hover_animation.start()
        else:
            self._set_hover(0.0)

    def enterEvent(self, event):
        self._animate_hover(1.0)
        self._track_pointer(event.position())
        for figure in tuple(self._pointer_figures):
            if isValid(figure):
                figure.pointer_entered()
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        self._track_pointer(event.position())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.light_animation.stop()
        for figure in tuple(self._pointer_figures):
            if isValid(figure):
                figure.pointer_left()
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._reset_motion()
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.EnabledChange and not self.isEnabled():
            self._reset_motion()
        super().changeEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        palette = _visual_palette()
        app = QApplication.instance()
        dark = app is not None and app.property("visualTheme") == "dark"
        hover = self._hover if motion_enabled() and self.isEnabled() else 0.0
        # Specialized cards keep their own colour family. Plain panels receive
        # their colour at rest as well, including when motion is reduced.
        plain = self.objectName() in ("Card", "HeroCard")
        if not plain and hover <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        outline = QPainterPath()
        radius = self.property('materialRadius') or (18 if self.objectName() == "HeroCard" else 16)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        outline.addRoundedRect(rect, radius, radius)
        p.setClipPath(outline)
        if plain:
            wash = QLinearGradient(rect.topLeft(), rect.bottomRight())
            tint = QColor(palette["accent"])
            tint.setAlphaF(.055 if dark else .025)
            wash.setColorAt(0, tint)
            tint.setAlphaF(.015 if dark else .006)
            wash.setColorAt(.58, tint)
            tint = QColor('#D3A16D' if dark else '#B57A43')
            tint.setAlphaF(.035 if dark else .015)
            wash.setColorAt(1, tint)
            p.fillPath(outline, wash)

            # An inset highlight separates the coloured panel from the page
            # without a shadow, extra widgets or changes to content geometry.
            sheen = QLinearGradient(0, 1, 0, min(100, self.height() * .65))
            sheen.setColorAt(0, QColor(255, 255, 255, 12 if dark else 62))
            sheen.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillPath(outline, sheen)
        light = QRadialGradient(QPointF(self.width() * self._light.x(), self.height() * self._light.y()),
                                max(80, min(260, self.width() * .42)))
        accent = self.property('materialAccent') or palette['accent']
        glow = QColor(accent)
        glow.setAlphaF(hover * (.10 if self.property('materialAccent') else .065))
        light.setColorAt(0, glow)
        glow.setAlpha(0)
        light.setColorAt(1, glow)
        p.fillPath(outline, light)
        edge = QLinearGradient(0, 0, self.width(), self.height())
        border = QColor(palette['border'] if plain else accent)
        border.setAlphaF((.68 if dark else .70) + hover * .18 if plain else hover * .38)
        edge.setColorAt(0, border)
        border.setAlphaF((.40 if dark else .46) + hover * .1 if plain else hover * .09)
        edge.setColorAt(.55, border)
        border = QColor('#11171C' if dark else '#B1A89A')
        border.setAlphaF((.72 if dark else .46) + hover * .13 if plain else hover * .18)
        edge.setColorAt(1, border)
        p.setPen(QPen(QBrush(edge), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(outline)
        p.end()


def button(text, callback=None, primary=False, danger=False):
    result = AnimatedButton(text)
    result.setCursor(Qt.PointingHandCursor)
    if primary:
        result.setProperty("role", "primary")
    elif danger:
        result.setProperty("role", "danger")
    if callback is not None:
        result.clicked.connect(callback)
    return result


def page_header(title, subtitle, actions=None):
    from .visuals import ReflectiveTitle
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 6, 0, 18)
    layout.setSpacing(24)
    labels = QVBoxLayout()
    labels.setSpacing(7)
    heading = ReflectiveTitle(title)
    heading.setTextFormat(Qt.PlainText)
    heading.setObjectName("pageTitle")
    sub = QLabel(subtitle)
    sub.setObjectName("pageSubtitle")
    sub.setWordWrap(True)
    labels.addWidget(heading)
    labels.addWidget(sub)
    layout.addLayout(labels, 1)
    for item in actions or []:
        layout.addWidget(item, 0, Qt.AlignVCenter)
    return widget


def stat_card(title, value, caption=""):
    result = Card()
    heading = QLabel(title)
    heading.setTextFormat(Qt.PlainText)
    heading.setObjectName("muted")
    result.value = QLabel(str(value))
    result.value.setObjectName("statValue")
    result.caption = QLabel(caption)
    result.caption.setObjectName("muted")
    result.caption.setWordWrap(True)
    result.body.addWidget(heading)
    result.body.addWidget(result.value)
    if caption:
        result.body.addWidget(result.caption)
    return result


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            widget = item.widget()
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def show_error(parent, text, detail=None):
    QMessageBox.warning(parent, str(text) if detail is not None else tr("À vérifier"), str(detail if detail is not None else text))


def confirm(parent, title, text):
    box = QMessageBox(QMessageBox.Question, title, text, parent=parent)
    yes = box.addButton(tr("Confirmer"), QMessageBox.AcceptRole)
    box.addButton(tr("Annuler"), QMessageBox.RejectRole)
    box.setDefaultButton(box.buttons()[-1])
    box.exec()
    return box.clickedButton() is yes


def empty_state(title, description, action_label=None, on_action=None):
    result = QWidget()
    layout = QVBoxLayout(result)
    layout.setContentsMargins(26, 36, 26, 36)
    layout.setSpacing(12)
    heading = QLabel(title)
    heading.setTextFormat(Qt.PlainText)
    heading.setObjectName("sectionTitle")
    heading.setAlignment(Qt.AlignCenter)
    sub = QLabel(description)
    sub.setObjectName("muted")
    sub.setWordWrap(True)
    sub.setAlignment(Qt.AlignCenter)
    layout.addWidget(heading)
    layout.addWidget(sub)
    if action_label:
        layout.addWidget(button(action_label, on_action, primary=True), 0, Qt.AlignCenter)
    return result


class SmoothScrollArea(_VisualPreferences, QScrollArea):
    """Ease stepped mouse wheels; retain native trackpad, keyboard and dragging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scroll_target = 0
        self._setting_scroll = False
        self.scroll_animation = QVariantAnimation(self)
        self.scroll_animation.setDuration(180)
        self.scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.scroll_animation.valueChanged.connect(self._advance_scroll)
        self.verticalScrollBar().valueChanged.connect(self._external_scroll)
        self.verticalScrollBar().sliderPressed.connect(self._reset_motion)
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self._watch_preferences()

    def _advance_scroll(self, value):
        self._setting_scroll = True
        try:
            self.verticalScrollBar().setValue(round(float(value)))
        finally:
            self._setting_scroll = False

    def _external_scroll(self, value):
        if not self._setting_scroll:
            self._reset_motion()

    def _range_changed(self, minimum, maximum):
        # A refreshed or resized page must not keep animating toward old bounds.
        self._reset_motion()

    def _reset_motion(self):
        self.scroll_animation.stop()
        self._scroll_target = self.verticalScrollBar().value()

    def hideEvent(self, event):
        self._reset_motion()
        super().hideEvent(event)

    def wheelEvent(self, event):
        if (not motion_enabled() or not event.pixelDelta().isNull()
                or event.phase() != Qt.NoScrollPhase or event.modifiers() != Qt.NoModifier
                or not event.angleDelta().y() or event.angleDelta().x()):
            self._reset_motion()
            super().wheelEvent(event)
            return
        bar = self.verticalScrollBar()
        delta = round(-event.angleDelta().y() / 120 * QApplication.wheelScrollLines() * bar.singleStep())
        delta = max(-bar.pageStep(), min(bar.pageStep(), delta))
        origin = self._scroll_target if self.scroll_animation.state() == QAbstractAnimation.Running else bar.value()
        target = max(bar.minimum(), min(bar.maximum(), origin + delta))
        if target == bar.value():
            self._reset_motion()
            event.ignore()
            return
        self.scroll_animation.stop()
        self._scroll_target = target
        self.scroll_animation.setStartValue(float(bar.value()))
        self.scroll_animation.setEndValue(float(target))
        self.scroll_animation.start()
        event.accept()


def scroll_page(content):
    area = SmoothScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area
