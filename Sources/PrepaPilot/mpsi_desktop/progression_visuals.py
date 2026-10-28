"""Native sculpted illustrations and a score dial for the Progression page.

Everything is painted locally. Motion is short, interaction-driven and stopped
when a widget is hidden or the application's reduced-motion setting is enabled.
"""
from __future__ import annotations
from .i18n import tr

import math
from weakref import ref

from PySide6.QtCore import QEasingCurve, QEvent, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import (
    QBrush, QColor, QConicalGradient, QFont, QLinearGradient, QPainter,
    QPainterPath, QPen, QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from .visuals import _ArtworkCache
from shiboken6 import isValid

_PALETTES = {
    "work": ("#0755CA", "#81CDFF", "#1748AA", "#D7E9FF", "#7AC8FF", "#133B70"),
    "sleep": ("#7131CA", "#D7B0FF", "#6827AD", "#EADCFF", "#D6AEFF", "#432769"),
    "sport": ("#006D64", "#84EED0", "#006A61", "#CAF3E7", "#6CE6C5", "#104C46"),
    "rest": ("#914900", "#FFD175", "#A75A0B", "#FFE5BA", "#FFD078", "#573717"),
}


def axis_palette(axis, theme="light"):
    """Return independent, readable hex colours for an activity axis."""
    accent, light, dark, tint, dark_accent, dark_tint = _PALETTES.get(axis, _PALETTES["work"])
    return dict(accent=dark_accent if theme == "dark" else accent,
                light=light, dark=dark, tint=dark_tint if theme == "dark" else tint)


def _theme():
    app = QApplication.instance()
    return "dark" if app is not None and app.property("visualTheme") == "dark" else "light"


def _motion_allowed():
    app = QApplication.instance()
    return app is None or not bool(app.property("reducedMotion"))


def _color(value, alpha=None):
    color = QColor(value)
    if alpha is not None:
        color.setAlpha(alpha)
    return color


def _gradient(rect, *colors):
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    for index, color in enumerate(colors):
        gradient.setColorAt(index / max(1, len(colors) - 1), QColor(color))
    return QBrush(gradient)


def _polygon(painter, points, brush, outline=None):
    painter.setPen(QPen(QColor(outline), .7) if outline else Qt.PenStyle.NoPen)
    painter.setBrush(brush)
    painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))


def _halo(painter, rect, color, opacity=65):
    gradient = QRadialGradient(rect.center(), max(rect.width(), rect.height()) / 2)
    gradient.setColorAt(0, _color(color, opacity))
    gradient.setColorAt(.5, _color(color, int(opacity * .46)))
    gradient.setColorAt(1, _color(color, 0))
    painter.save()
    painter.translate(rect.center())
    painter.scale(1, rect.height() / max(1, rect.width()))
    painter.setPen(Qt.PenStyle.NoPen)
    gradient.setCenter(QPointF())
    gradient.setFocalPoint(QPointF())
    painter.setBrush(gradient)
    radius = rect.width() / 2
    painter.drawEllipse(QRectF(-radius, -radius, radius * 2, radius * 2))
    painter.restore()


def _glass_crystal(painter, x, y, size, colors):
    """A little cut-glass solid: three shaded faces and an etched bright edge."""
    light, middle, dark = colors
    top = (x, y - size)
    left = (x - size * .78, y - size * .25)
    center = (x, y + size * .2)
    right = (x + size * .78, y - size * .25)
    bottom = (x, y + size)
    _polygon(painter, [top, right, center, left],
             _gradient(QRectF(x - size, y - size, size * 2, size), "#FFFFFF", light, middle))
    _polygon(painter, [left, center, bottom, (x - size * .78, y + size * .48)],
             _gradient(QRectF(x - size, y, size, size), light, middle))
    _polygon(painter, [center, right, (x + size * .78, y + size * .48), bottom],
             _gradient(QRectF(x, y, size, size), middle, dark))
    painter.setPen(QPen(_color("#FFFFFF", 205), .9))
    painter.drawLine(QPointF(*left), QPointF(*center))
    painter.drawLine(QPointF(*center), QPointF(*right))
    painter.drawLine(QPointF(*center), QPointF(*bottom))


def _pearl(painter, x, y, radius, colors):
    """The off-centre reflection stays baked into this miniature enamel orb."""
    light, middle, dark = colors
    reflection = QRadialGradient(QPointF(x - radius * .32, y - radius * .38), radius * 1.6)
    reflection.setColorAt(0, QColor("#FFFFFF"))
    reflection.setColorAt(.2, QColor(light))
    reflection.setColorAt(.57, QColor(middle))
    reflection.setColorAt(1, QColor(dark))
    painter.setPen(QPen(_color(light, 155), .65))
    painter.setBrush(QBrush(reflection))
    painter.drawEllipse(QPointF(x, y), radius, radius)
    painter.setPen(QPen(_color("#FFFFFF", 175), .8))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(x - radius + 1, y - radius + 1, radius * 2 - 2, radius * 2 - 2),
                    46 * 16, 105 * 16)


class ProgressionFigure(QWidget):
    """Cached sculpted layers with quiet parallax and one glint on pointer entry."""

    def __init__(self, axis, parent=None):
        super().__init__(parent)
        self.axis = axis if axis in _PALETTES else "work"
        self._offset = QPointF()
        self._target = QPointF()
        self._artwork = _ArtworkCache()
        self.parallax_animation = QVariantAnimation(self)
        self.parallax_animation.setDuration(180)
        self.parallax_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.parallax_animation.valueChanged.connect(self._set_offset)
        self._glint = 1.
        self.glint_animation = QVariantAnimation(self)
        self.glint_animation.setDuration(760)
        self.glint_animation.setStartValue(0.)
        self.glint_animation.setEndValue(1.)
        self.glint_animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.glint_animation.valueChanged.connect(self._set_glint)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName({"work": tr('Livres et crayon en relief'), "sleep": tr('Lune et nuage en relief'),
                                "sport": tr('Haltère en relief'), "rest": tr('Tasse et vapeur en relief')}[self.axis])
        self.setAccessibleDescription(tr('Illustration décorative'))
        from .widgets import observe_visual_preferences
        observe_visual_preferences(self)

    def sizeHint(self):
        return QSize(220, 160)

    def minimumSizeHint(self):
        return QSize(96, 96)

    def bind_pointer_surface(self, surface):
        self._pointer_surface = ref(surface)

    def _bound_surface(self):
        reference = getattr(self, '_pointer_surface', None)
        surface = reference() if reference is not None else None
        return surface if surface is not None and isValid(surface) else None

    def _reset_motion(self):
        self.parallax_animation.stop()
        self.glint_animation.stop()
        self._offset = QPointF()
        self._target = QPointF()
        self._glint = 1.
        self.update()

    def _set_glint(self, value):
        if not _motion_allowed() or not self.isVisible() or not self.isEnabled():
            self._reset_motion()
            return
        self._glint = float(value)
        self.update()

    def _set_offset(self, value):
        if not _motion_allowed() or not self.isVisible():
            self._reset_motion()
            return
        self._offset = QPointF(value)
        self.update()

    def _move_to(self, target, duration=180):
        if not _motion_allowed() or not self.isVisible() or not self.isEnabled():
            self._reset_motion()
            return
        if target == self._target:
            return
        self._target = QPointF(target)
        self.parallax_animation.stop()
        self.parallax_animation.setDuration(duration)
        self.parallax_animation.setStartValue(self._offset)
        self.parallax_animation.setEndValue(target)
        self.parallax_animation.start()

    def mouseMoveEvent(self, event):
        surface = self._bound_surface()
        if surface is not None:
            point = surface.mapFrom(self, event.position().toPoint())
            surface._track_pointer(QPointF(point))
            super().mouseMoveEvent(event)
            return
        point = event.position()
        x = max(-1., min(1., point.x() / max(1, self.width()) * 2 - 1))
        y = max(-1., min(1., point.y() / max(1, self.height()) * 2 - 1))
        self._move_to(QPointF(x, y))
        super().mouseMoveEvent(event)

    def enterEvent(self, event):
        if self._bound_surface() is None:
            self.pointer_entered()
        super().enterEvent(event)

    def pointer_entered(self):
        if _motion_allowed() and self.isVisible() and self.isEnabled():
            self.glint_animation.stop()
            self.glint_animation.start()

    def leaveEvent(self, event):
        if self._bound_surface() is None:
            self.pointer_left()
        super().leaveEvent(event)

    def pointer_left(self):
        self.glint_animation.stop()
        self._glint = 1.
        self._move_to(QPointF(), 240)
        self.update()

    def changeEvent(self, event):
        if event.type() == QEvent.EnabledChange and not self.isEnabled():
            self._reset_motion()
        super().changeEvent(event)

    def hideEvent(self, event):
        self._reset_motion()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._artwork.prepare(self, 220, 160, (_theme(), self._figure_variant()))
            self._artwork.draw(painter, "studio", self._paint_studio)
            self._artwork.draw(painter, "orbit", self._paint_orbit,
                               QPointF(-self._offset.x() * 1.2, -self._offset.y() * .8))
            self._artwork.draw(painter, "figure", self._paint_figure,
                               QPointF(self._offset.x() * 4, self._offset.y() * 3))
            pulse = math.sin(math.pi * self._glint) if 0. < self._glint < 1. else 0.
            satellite_offset = QPointF(-self._offset.x() * 5, -self._offset.y() * 3.5 - pulse * 3)
            self._artwork.draw(painter, "satellites", self._paint_satellites, satellite_offset)
            painter.save()
            painter.setOpacity(pulse * .8)
            # Rasterized even at rest, so the first hover never adds painting work.
            self._artwork.draw(painter, "glint", self._paint_glint, satellite_offset)
            painter.restore()
        finally:
            painter.end()

    def _figure_variant(self):
        return self.axis

    def _paint_studio(self, painter):
        colors = axis_palette(self.axis, _theme())
        _halo(painter, QRectF(21, 17, 180, 120), colors["light"], 35 if _theme() == "dark" else 65)
        _halo(painter, QRectF(31, 123, 159, 25), colors["dark"], 75 if _theme() == "dark" else 55)

    def _orbit_angle(self):
        return {"work": -24, "sleep": 22, "sport": -17, "rest": 14}[self.axis]

    def _paint_orbit(self, painter):
        colors = axis_palette(self.axis, _theme())
        painter.save()
        painter.translate(109, 82)
        painter.rotate(self._orbit_angle())
        ellipse = QRectF(-87, -47, 174, 94)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # A translucent enamel hoop. Its rear half is occluded by the sculpture.
        painter.setPen(QPen(_color(colors["dark"], 37 if _theme() == "dark" else 23), 4.3))
        painter.drawEllipse(ellipse.translated(0, 1.4))
        painter.setPen(QPen(_color(colors["light"], 108 if _theme() == "dark" else 130), 2.8))
        painter.drawEllipse(ellipse)
        painter.setPen(QPen(_color("#FFFFFF", 175 if _theme() == "dark" else 215), .9))
        painter.drawArc(ellipse.adjusted(-.7, -.7, .7, .7), 20 * 16, 139 * 16)
        painter.setPen(QPen(_color(colors["accent"], 75), .8))
        painter.drawArc(ellipse.adjusted(.9, .9, -.9, -.9), 195 * 16, 130 * 16)
        painter.restore()

    def _satellite_layout(self):
        return {"work": ((32, 45, 10), (179, 118, 8)),
                "sleep": ((34, 112, 9), (183, 96, 7)),
                "sport": ((36, 39, 9), (179, 122, 8)),
                "rest": ((36, 85, 9), (179, 38, 8))}[self.axis]

    def _paint_satellites(self, painter):
        colors = axis_palette(self.axis, _theme())
        crystal, pearl = self._satellite_layout()
        _glass_crystal(painter, *crystal, (colors["light"], colors["accent"], colors["dark"]))
        _pearl(painter, *pearl, ("#F9EAC9", "#EBC487", "#BA864C"))

    def _paint_glint(self, painter):
        for x, y, radius in self._satellite_layout():
            x, y = x - radius * .25, y - radius * .38
            _halo(painter, QRectF(x - 13, y - 13, 26, 26), "#FFFFFF", 120)
            painter.setPen(QPen(_color("#FFFFFF", 230), .9, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(x - 5, y), QPointF(x + 5, y))
            painter.drawLine(QPointF(x, y - 5), QPointF(x, y + 5))

    def _paint_figure(self, painter):
        {"work": self._paint_work, "sleep": self._paint_sleep,
         "sport": self._paint_sport, "rest": self._paint_rest}[self.axis](painter, axis_palette(self.axis, _theme()))

    @staticmethod
    def _book(painter, x, y, cover, thickness=15):
        # Three independently shaded planes make a real volume, including pages.
        painter.save()
        painter.translate(x, y)
        top = [(0, 0), (78, -24), (135, 5), (55, 32)]
        _polygon(painter, [(0, 0), (55, 32), (55, 32 + thickness), (0, thickness)],
                 _gradient(QRectF(0, 0, 55, 47), cover[1], cover[2]))
        _polygon(painter, [(55, 32), (135, 5), (135, 5 + thickness), (55, 32 + thickness)],
                 _gradient(QRectF(55, 10, 80, 32), "#FFFFFF", "#E1E6F3", "#B8C4DB"))
        for offset in (4, 7, 10):
            if offset < thickness:
                painter.setPen(QPen(_color("#8394B6", 80), .65))
                painter.drawLine(QPointF(59, 32 + offset), QPointF(130, 8 + offset))
        _polygon(painter, top, _gradient(QRectF(0, -24, 135, 56), *cover), cover[0])
        painter.setPen(QPen(_color("#FFFFFF", 135), 1.1))
        painter.drawLine(QPointF(1, .5), QPointF(55, 31))
        painter.drawLine(QPointF(55, 31), QPointF(133, 5))
        painter.restore()

    def _paint_work(self, p, c):
        self._book(p, 35, 84, ("#EDF2FF", "#ADBDDF", "#6B7CA6"), 11)
        self._book(p, 42, 60, ("#86C9FF", "#397DEE", "#1B4FB7"), 17)
        # Inset silver title label, foil rule, and rounded binding fasteners.
        _polygon(p, [(80, 52), (116, 41), (139, 52), (103, 64)],
                 _gradient(QRectF(80, 41, 59, 23), "#FFFFFF", "#D7E9FF"))
        p.setPen(QPen(_color("#FFFFFF", 155), 1.5))
        p.drawLine(QPointF(114, 78), QPointF(159, 64))
        p.setPen(Qt.PenStyle.NoPen)
        for x, y in ((54, 62), (67, 69), (80, 76), (93, 83)):
            p.setBrush(QColor("#2557A4")); p.drawEllipse(QPointF(x, y), 2.2, 1.8)
            p.setBrush(QColor("#BCDFFF")); p.drawEllipse(QPointF(x - .4, y - .5), 1.2, .7)
        # A hovering graphite pencil catches a narrow highlight.
        p.save(); p.translate(150, 74); p.rotate(-63)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(QRectF(-36, -4, 89, 10), "#F6F9FF", "#C7D6ED", "#718CA9"))
        p.drawRoundedRect(QRectF(-36, -4, 79, 9), 3, 3)
        p.setBrush(QColor("#7EA2D1")); p.drawRoundedRect(QRectF(34, -4, 10, 9), 2, 2)
        _polygon(p, [(-36, -4), (-48, .5), (-36, 5)], QColor("#DCC2A0"))
        _polygon(p, [(-48, .5), (-42, -1.8), (-42, 2.8)], QColor("#34476B"))
        p.setPen(QPen(_color("#FFFFFF", 210), 1)); p.drawLine(QPointF(-31, -2), QPointF(30, -2))
        p.restore()

    def _paint_sleep(self, p, c):
        crescent = QPainterPath(); crescent.addEllipse(QRectF(60, 19, 87, 93))
        cut = QPainterPath(); cut.addEllipse(QRectF(91, 7, 81, 88))
        crescent = crescent.subtracted(cut)
        p.save(); p.translate(5, 6)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(_gradient(QRectF(60, 19, 87, 93), "#AD8BD9", "#654594"))
        p.drawPath(crescent); p.restore()
        p.setBrush(_gradient(QRectF(60, 19, 87, 93), "#F4E7FF", "#C9A5F0", "#9566CD"))
        p.setPen(QPen(_color("#FFFFFF", 105), .9)); p.drawPath(crescent)
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, radius in ((147, 30, 5), (174, 55, 3.4), (52, 47, 2.8), (160, 86, 2.2)):
            _halo(p, QRectF(x - radius * 3, y - radius * 3, radius * 6, radius * 6), "#D3B7FF", 110)
            star = QPainterPath(); star.moveTo(x, y - radius)
            star.quadTo(x + 1.1, y - 1.1, x + radius, y)
            star.quadTo(x + 1.1, y + 1.1, x, y + radius)
            star.quadTo(x - 1.1, y + 1.1, x - radius, y)
            star.quadTo(x - 1.1, y - 1.1, x, y - radius)
            p.setBrush(QColor("#EBD5FF" if _theme() == "dark" else "#AD85DA")); p.drawPath(star)
        cloud = QPainterPath(); cloud.setFillRule(Qt.FillRule.WindingFill)
        cloud.addRoundedRect(QRectF(91, 108, 76, 23), 12, 12)
        cloud.addEllipse(QRectF(105, 88, 38, 40)); cloud.addEllipse(QRectF(133, 100, 33, 30))
        cloud.addEllipse(QRectF(87, 103, 28, 27)); cloud = cloud.simplified()
        p.save(); p.translate(1, 4); p.setBrush(QColor("#A09AB9")); p.drawPath(cloud); p.restore()
        p.setBrush(_gradient(QRectF(100, 90, 63, 43), "#FFFFFF", "#F0EBFC", "#C9C2E0"))
        p.drawPath(cloud)
        p.setPen(QPen(_color("#FFFFFF", 155), 1.2)); p.drawArc(QRectF(107, 89, 34, 36), 25 * 16, 128 * 16)

    def _paint_sport(self, p, c):
        p.save(); p.translate(111, 81); p.rotate(-24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(QRectF(-74, -7, 147, 15), "#DEFDF1", "#AADACD", "#408B83"))
        p.drawRoundedRect(QRectF(-75, -7, 151, 15), 6, 6)
        p.setBrush(_gradient(QRectF(-29, -6, 58, 14), "#F4FEFC", "#C9DFE0", "#7FABA8"))
        p.drawRoundedRect(QRectF(-29, -6, 58, 13), 3, 3)
        p.setPen(QPen(_color("#5B8F8B", 100), .7))
        for x in range(-23, 24, 5):
            p.drawLine(QPointF(x, -3), QPointF(x - 3, 4))
        for x in (-58, 37):
            # A wide cylindrical weight: convex front, beveled rim, shaded edge.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_gradient(QRectF(x, -36, 27, 72), "#A8EFDC", "#51BCA2", "#247E70"))
            p.drawRoundedRect(QRectF(x, -36, 25, 72), 10, 10)
            p.setBrush(_gradient(QRectF(x + 9, -36, 27, 72), "#C7FFE9", "#7BD5B8", "#42A18C"))
            p.drawEllipse(QRectF(x + 9, -36, 28, 72))
            p.setPen(QPen(_color("#FFFFFF", 150), 1.2))
            p.drawArc(QRectF(x + 10, -35, 26, 70), 58 * 16, 132 * 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_gradient(QRectF(x + 17, -27, 17, 54), "#98E7CB", "#439C88"))
            p.drawEllipse(QRectF(x + 17, -27, 17, 54))
            p.setBrush(QColor("#336F66")); p.drawEllipse(QRectF(x + 23, -6, 6, 12))
            p.setBrush(QColor("#A7D7CB")); p.drawEllipse(QRectF(x + 25, -5, 3, 8))
        for x in (-73, 62):
            p.setBrush(_gradient(QRectF(x, -23, 15, 46), "#CBF8E8", "#62BDA4", "#286F65"))
            p.drawRoundedRect(QRectF(x, -23, 12, 46), 5, 5)
        p.restore()

    def _paint_rest(self, p, c):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(QRectF(60, 113, 112, 24), "#FFF1D9", "#EAC99A", "#C89756"))
        p.drawEllipse(QRectF(60, 113, 112, 24))
        p.setBrush(_gradient(QRectF(68, 113, 95, 16), "#FFF7E9", "#E9CAA0"))
        p.drawEllipse(QRectF(68, 113, 95, 16))
        # Thick ceramic handle built from a ring, independent from the cup body.
        handle = QPainterPath(); handle.addEllipse(QRectF(135, 72, 42, 41))
        hole = QPainterPath(); hole.addEllipse(QRectF(141, 81, 25, 23))
        p.setBrush(_gradient(QRectF(138, 72, 37, 41), "#FFE8BD", "#C99A54"))
        p.drawPath(handle.subtracted(hole))
        cup = QPainterPath(); cup.moveTo(75, 73); cup.lineTo(82, 107)
        cup.cubicTo(89, 132, 132, 132, 143, 106); cup.lineTo(151, 73); cup.closeSubpath()
        p.setBrush(_gradient(QRectF(75, 70, 77, 56), "#FFF1CF", "#EFC77F", "#C48B3C")); p.drawPath(cup)
        p.setBrush(_gradient(QRectF(75, 59, 77, 28), "#FFF8E9", "#E5B76C")); p.drawEllipse(QRectF(75, 59, 77, 28))
        p.setBrush(_gradient(QRectF(81, 65, 65, 18), "#9A6437", "#C7955E", "#E7BD87")); p.drawEllipse(QRectF(81, 65, 65, 18))
        p.setPen(QPen(_color("#FFFFFF", 180), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(83, 85), QPointF(88, 105))
        # Delicate static steam ribbons; no perpetual motion.
        for x, y, alpha in ((100, 27, 115), (117, 19, 160), (134, 33, 100)):
            steam = QPainterPath(); steam.moveTo(x, 58)
            steam.cubicTo(x + 10, 47, x - 11, 42, x + 1, y)
            p.setPen(QPen(_color("#DEB57C", alpha), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(steam)


class ScoreOrb(QWidget):
    """Accessible score dial. The supplied value is displayed, never computed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._score = None
        self._display_score = 0.
        self._initialized = False
        self._artwork = _ArtworkCache()
        self.score_animation = QVariantAnimation(self)
        self.score_animation.setDuration(400)
        self.score_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.score_animation.valueChanged.connect(self._set_display_score)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setAccessibleName(tr('Score personnel non renseigné'))
        from .widgets import observe_visual_preferences
        observe_visual_preferences(self)

    def sizeHint(self):
        return QSize(180, 180)

    def minimumSizeHint(self):
        return QSize(130, 130)

    def set_score(self, value):
        score = None if value is None else float(value)
        if score is not None:
            if not math.isfinite(score):
                raise ValueError(tr('Le score doit être un nombre fini.'))
            score = max(0., min(100., score))
        previous = self._score
        self._score = score
        self.setAccessibleName(tr('Score personnel non renseigné') if score is None else
                               tr('Score personnel : {v0} sur 100', v0=format(score, '.0f')))
        target = score if score is not None else 0.
        animate = self._initialized and score is not None and score != previous and self.isVisible() and _motion_allowed()
        self._initialized = True
        self.score_animation.stop()
        if animate:
            self.score_animation.setStartValue(self._display_score)
            self.score_animation.setEndValue(target)
            self.score_animation.start()
        else:
            self._display_score = target
            self.update()

    def _set_display_score(self, value):
        if not _motion_allowed() or not self.isVisible():
            self._reset_motion()
            return
        self._display_score = float(value)
        self.update()

    def _reset_motion(self):
        self.score_animation.stop()
        self._display_score = self._score if self._score is not None else 0.
        self.update()

    def hideEvent(self, event):
        self._reset_motion()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            self._artwork.prepare(self, 180, 180, _theme())
            self._artwork.draw(p, "orb", self._paint_base)
            scale = min(self.width(), self.height()) / 180
            p.translate((self.width() - 180 * scale) / 2, (self.height() - 180 * scale) / 2)
            p.scale(scale, scale)
            dark = _theme() == "dark"
            p.setBrush(Qt.BrushStyle.NoBrush)
            if self._score is not None and self._display_score > 0:
                gradient = QConicalGradient(QPointF(90, 90), 90)
                gradient.setColorAt(0, QColor("#88CFFF")); gradient.setColorAt(.28, QColor("#BE9EF3"))
                gradient.setColorAt(.6, QColor("#766DEB")); gradient.setColorAt(1, QColor("#3589F2"))
                p.setPen(QPen(QBrush(gradient), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawArc(QRectF(18, 18, 144, 144), 90 * 16, -round(self._display_score * 3.6 * 16))
                p.setPen(QPen(_color("#FFFFFF", 65), 1.4))
                p.drawArc(QRectF(13.5, 13.5, 153, 153), 90 * 16, -round(self._display_score * 3.6 * 16))
                angle = math.radians(self._display_score * 3.6 - 90)
                end = QPointF(90 + 72 * math.cos(angle), 90 + 72 * math.sin(angle))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#E6F0FF")); p.drawEllipse(end, 3, 3)
            font = QFont(self.font()); font.setPixelSize(45); font.setWeight(QFont.Weight.DemiBold)
            p.setFont(font); p.setPen(QColor("#F3F6FF" if dark else "#253F69"))
            p.drawText(QRectF(24, 49, 132, 59), Qt.AlignmentFlag.AlignCenter,
                       "—" if self._score is None else f"{self._score:.0f}")
            font.setPixelSize(13); font.setWeight(QFont.Weight.Medium); p.setFont(font)
            p.setPen(QColor("#ADBDD9" if dark else "#70819E"))
            p.drawText(QRectF(40, 105, 100, 23), Qt.AlignmentFlag.AlignCenter,
                       tr('À DÉFINIR') if self._score is None else "/ 100")
        finally:
            p.end()

    def _paint_base(self, p):
        dark = _theme() == "dark"
        _halo(p, QRectF(1, 3, 178, 172), "#677EF1", 45 if dark else 35)
        _halo(p, QRectF(25, 145, 132, 25), "#233E78", 70 if dark else 38)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(QRectF(21, 24, 138, 138), "#36445D" if dark else "#FFFFFF",
                             "#252736" if dark else "#EDF0FA"))
        p.drawEllipse(QRectF(21, 24, 138, 138))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#303B52" if dark else "#DDE6F6"), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawEllipse(QRectF(18, 18, 144, 144))
        p.setPen(QPen(_color("#FFFFFF", 24 if dark else 170), 1.1))
        p.drawEllipse(QRectF(11, 11, 158, 158))
