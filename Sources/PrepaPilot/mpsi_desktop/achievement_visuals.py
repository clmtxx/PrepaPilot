"""Small, cached metal trophies with motion only on hover or an unlock.

The five silhouettes grow from a simple bronze seal to a faceted diamond
medallion. Painting and animations stay local; there are no image downloads,
render loops or timers while the collection is idle.
"""
from __future__ import annotations
from .i18n import tr

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import (
    QBrush, QColor, QConicalGradient, QLinearGradient, QPainter, QPainterPath,
    QPen, QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from .visuals import _ArtworkCache
from .widgets import motion_enabled, observe_visual_preferences


TIER_NAMES = ("Bronze", "Argent", "Or", "Platine", "Diamant")
METALS = (
    ("#FFE3BE", "#CE8B53", "#714328", "#C27C42"),
    ("#F8FDFF", "#B5C5D7", "#536D8E", "#789DBE"),
    ("#FFF1AF", "#ECC154", "#996520", "#D19A2D"),
    ("#E8FFF9", "#83D1CB", "#377582", "#53B1AE"),
    ("#F7EEFF", "#B2B7FF", "#6660B6", "#9A8FF0"),
)


def _theme():
    app = QApplication.instance()
    return "dark" if app is not None and app.property("visualTheme") == "dark" else "light"


def _color(value, alpha=255):
    result = QColor(value)
    result.setAlpha(alpha)
    return result


def _gradient(rect, *colors):
    result = QLinearGradient(rect.topLeft(), rect.bottomRight())
    for i, color in enumerate(colors):
        result.setColorAt(i / max(1, len(colors) - 1), QColor(color))
    return QBrush(result)


def _star(cx, cy, outer, inner=None, points=5, rotation=-90):
    inner = outer * .45 if inner is None else inner
    vertices = []
    for i in range(points * 2):
        angle = math.radians(rotation + i * 180 / points)
        radius = outer if i % 2 == 0 else inner
        vertices.append(QPointF(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    return QPolygonF(vertices)


def _polygon(cx, cy, radius, points, rotation=-90):
    return QPolygonF([
        QPointF(cx + math.cos(math.radians(rotation + i * 360 / points)) * radius,
                cy + math.sin(math.radians(rotation + i * 360 / points)) * radius)
        for i in range(points)
    ])


class BadgeFigure(QWidget):
    """A studio trophy, with a cached body and a short optional particle reveal."""

    def __init__(self, tier=0, family="work_total", locked=False, parent=None):
        super().__init__(parent)
        self.tier = max(0, min(4, int(tier)))
        self.family, self.locked = family, bool(locked)
        self._artwork = _ArtworkCache()
        self._offset = QPointF()
        self._target = QPointF()
        self._reveal = 1.0
        self.parallax_animation = QVariantAnimation(self)
        self.parallax_animation.setDuration(180)
        self.parallax_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.parallax_animation.valueChanged.connect(self._set_offset)
        self.reveal_animation = QVariantAnimation(self)
        self.reveal_animation.setDuration(1250)
        self.reveal_animation.setStartValue(0.0)
        self.reveal_animation.setEndValue(1.0)
        self.reveal_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.reveal_animation.valueChanged.connect(self._set_reveal)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._set_accessibility()
        observe_visual_preferences(self)

    def sizeHint(self):
        return QSize(220, 200)

    def minimumSizeHint(self):
        return QSize(64, 64)

    def _set_accessibility(self):
        self.setAccessibleName(tr('Médaille {v0} : {v1}', v0=tr(TIER_NAMES[self.tier]), v1=tr('à débloquer') if self.locked else tr('obtenue')))
        self.setAccessibleDescription(tr('Illustration en relief du palier'))

    def set_badge(self, tier=0, family="work_total", locked=False):
        state = max(0, min(4, int(tier))), family, bool(locked)
        if state != (self.tier, self.family, self.locked):
            self.tier, self.family, self.locked = state
            self._set_accessibility()
            self.update()

    def _reset_motion(self):
        self.parallax_animation.stop()
        self.reveal_animation.stop()
        self._offset = QPointF()
        self._target = QPointF()
        self._reveal = 1.0
        self.update()

    def _set_offset(self, value):
        if not motion_enabled() or not self.isVisible():
            self._reset_motion()
            return
        self._offset = QPointF(value)
        self.update()

    def _set_reveal(self, value):
        if not motion_enabled() or not self.isVisible():
            self._reset_motion()
            return
        self._reveal = float(value)
        self.update()

    def celebrate(self):
        if self.locked or not self.isVisible() or not motion_enabled():
            self._reset_motion()
            return
        self.reveal_animation.stop()
        self.reveal_animation.start()

    def _move_to(self, target):
        if not motion_enabled() or not self.isVisible():
            self._reset_motion()
            return
        if target == self._target:
            return
        self._target = QPointF(target)
        self.parallax_animation.stop()
        self.parallax_animation.setStartValue(self._offset)
        self.parallax_animation.setEndValue(target)
        self.parallax_animation.start()

    def mouseMoveEvent(self, event):
        point = event.position()
        x = max(-1., min(1., point.x() / max(1, self.width()) * 2 - 1))
        y = max(-1., min(1., point.y() / max(1, self.height()) * 2 - 1))
        self._move_to(QPointF(x, y))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._move_to(QPointF())
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._reset_motion()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._artwork.prepare(self, 220, 200, (_theme(), self.tier, self.family, self.locked))
            self._artwork.draw(painter, "studio", self._paint_studio)
            self._artwork.draw(painter, "medal", self._paint_medal,
                               QPointF(self._offset.x() * 4, self._offset.y() * 3))
            if self._reveal < 1 and motion_enabled():
                self._paint_reveal(painter)
        finally:
            painter.end()

    def _paint_studio(self, p):
        light, middle, shadow, _ = METALS[self.tier]
        halo = QRadialGradient(QPointF(110, 89), 95)
        halo.setColorAt(0, _color(middle, 28 if self.locked else 68))
        halo.setColorAt(.6, _color(light, 12 if _theme() == "dark" else 28))
        halo.setColorAt(1, _color(middle, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(15, -6, 190, 190))
        p.save()
        p.translate(110, 176)
        p.scale(1, .12)
        shade = QRadialGradient(QPointF(), 78)
        shade.setColorAt(0, _color(shadow, 60 if self.locked else 100))
        shade.setColorAt(1, _color(shadow, 0))
        p.setBrush(shade)
        p.drawEllipse(QPointF(), 78, 78)
        p.restore()

    def _paint_medal(self, p):
        light, middle, shadow, accent = METALS[self.tier]
        p.save()
        if self.locked:
            p.setOpacity(.52 if _theme() == "dark" else .58)
        # Satin ribbon, folded behind the cast metal.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(QRectF(70, 115, 40, 61), shadow, accent, middle))
        p.drawPolygon(QPolygonF([QPointF(77, 116), QPointF(109, 129), QPointF(91, 178),
                                 QPointF(78, 160), QPointF(58, 167)]))
        p.setBrush(_gradient(QRectF(110, 115, 43, 62), middle, shadow))
        p.drawPolygon(QPolygonF([QPointF(111, 129), QPointF(143, 116), QPointF(163, 167),
                                 QPointF(143, 160), QPointF(129, 178)]))
        p.setPen(QPen(_color(light, 170), 1.3))
        p.drawLine(QPointF(76, 139), QPointF(67, 158))
        p.drawLine(QPointF(144, 139), QPointF(154, 158))
        if self.tier >= 3:
            self._paint_laurels(p, light, middle, shadow)
        # A small extrusion is a separate shaded solid below the front face.
        p.setPen(QPen(_color(shadow, 190), .8))
        p.setBrush(_gradient(QRectF(49, 41, 122, 112), accent, shadow))
        self._shape(p, 110, 95, 58)
        metal = QConicalGradient(QPointF(105, 85), 35)
        for position, color in ((0, light), (.16, middle), (.28, shadow), (.43, light),
                                (.57, middle), (.72, light), (.88, shadow), (1, light)):
            metal.setColorAt(position, QColor(color))
        p.setBrush(metal)
        p.setPen(QPen(QColor(light), .7))
        self._shape(p, 110, 89, 58)
        # The raised rim and inset enamel catch different lighting directions.
        p.setPen(QPen(_color(shadow, 135), 1.3))
        p.setBrush(_gradient(QRectF(64, 42, 92, 92), light, middle, accent))
        p.drawEllipse(QRectF(64, 43, 92, 92))
        p.setPen(QPen(_color(light, 220), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(68, 47, 84, 84))
        inner = QRadialGradient(QPointF(92, 64), 87)
        inner.setColorAt(0, QColor(light))
        inner.setColorAt(.53, QColor(middle))
        inner.setColorAt(1, QColor(shadow))
        p.setBrush(inner)
        p.setPen(QPen(_color(shadow, 90), .7))
        p.drawEllipse(QRectF(74, 53, 72, 72))
        if self.tier >= 1:
            p.setPen(QPen(_color(light, 165), 1.1))
            for i in range(24 if self.tier < 4 else 32):
                angle = i * math.tau / (24 if self.tier < 4 else 32)
                p.drawLine(QPointF(110 + math.cos(angle) * 48, 89 + math.sin(angle) * 48),
                           QPointF(110 + math.cos(angle) * 51, 89 + math.sin(angle) * 51))
        if self.tier == 4:
            self._paint_prism(p, light, middle, shadow)
        elif self.locked:
            self._paint_lock(p, shadow, light)
        else:
            self._paint_symbol(p, shadow, light)
        # Richer tiers earn a crown of stars, with increasingly large jewels.
        if self.tier >= 2:
            for x, y, radius in ((91, 26, 5), (110, 18, 7), (129, 26, 5)):
                p.setPen(QPen(_color(shadow, 90), .5))
                p.setBrush(_gradient(QRectF(x - radius, y - radius, radius * 2, radius * 2), light, middle, shadow))
                p.drawPolygon(_star(x, y, radius))
        if self.tier >= 3:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(light))
            for x, y, radius in ((38, 49, 4.5), (180, 76, 4), (167, 29, 3)):
                p.drawPolygon(_star(x, y, radius, radius * .22, points=4))
        # A reflection strip is baked into the medal rather than animated idle.
        shine = QPainterPath()
        shine.addEllipse(QRectF(67, 46, 87, 87))
        p.setClipPath(shine)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_color("#FFFFFF", 53))
        p.drawPolygon(QPolygonF([QPointF(50, 72), QPointF(134, 36), QPointF(145, 45), QPointF(61, 88)]))
        p.restore()

    def _shape(self, p, cx, cy, radius):
        if self.tier == 4:
            p.drawPolygon(_polygon(cx, cy, radius, 8, -67.5))
        elif self.tier >= 2:
            p.drawPolygon(_star(cx, cy, radius, radius * .9, points=16))
        else:
            p.drawEllipse(QPointF(cx, cy), radius, radius)

    @staticmethod
    def _paint_laurels(p, light, middle, shadow):
        for side in (-1, 1):
            p.save()
            p.translate(110, 96)
            p.scale(side, 1)
            path = QPainterPath(QPointF(24, 59))
            path.cubicTo(67, 45, 83, 7, 61, -34)
            p.setPen(QPen(QColor(middle), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            for i in range(6):
                angle = math.radians(67 - i * 19)
                x, y = 13 + math.cos(angle) * 57, math.sin(angle) * 58
                p.save()
                p.translate(x, y)
                p.rotate(20 - i * 18)
                leaf = QPainterPath(QPointF())
                leaf.cubicTo(5, -17, 16, -18, 20, -15)
                leaf.cubicTo(20, -7, 8, 0, 0, 0)
                p.setBrush(_gradient(QRectF(0, -18, 20, 18), light, middle, shadow))
                p.setPen(QPen(_color(light, 165), .5))
                p.drawPath(leaf)
                p.restore()
            p.restore()

    def _paint_symbol(self, p, shadow, light):
        # Simple embossed silhouettes remain recognizable even at thumbnail size.
        p.save()
        p.translate(.7, 1.5)
        self._symbol_path(p, _color(light, 210))
        p.restore()
        self._symbol_path(p, QColor(shadow))

    def _symbol_path(self, p, color):
        p.setPen(QPen(color, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.family == "sport_total":
            # The diagonal bar and paired plates read as an embossed dumbbell.
            p.save()
            p.translate(110, 89)
            p.rotate(-32)
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(-13, -2, 26, 4), 2, 2)
            for x in (-19, 13):
                p.drawRoundedRect(QRectF(x, -12, 6, 24), 2, 2)
            for x in (-24, 20):
                p.drawRoundedRect(QRectF(x, -7, 4, 14), 1.5, 1.5)
            p.restore()
        elif self.family == "sport_streak":
            # A flame represents continuity; its cut-out keeps the relief light.
            flame = QPainterPath(QPointF(111, 66))
            flame.cubicTo(114, 78, 124, 78, 125, 90)
            flame.cubicTo(129, 105, 116, 112, 106, 108)
            flame.cubicTo(94, 105, 92, 93, 101, 84)
            flame.cubicTo(102, 90, 104, 93, 106, 92)
            flame.cubicTo(111, 85, 106, 77, 111, 66)
            cut = QPainterPath(QPointF(112, 88))
            cut.cubicTo(120, 97, 119, 104, 112, 104)
            cut.cubicTo(106, 104, 104, 98, 112, 88)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPath(flame.subtracted(cut))
        elif self.family == "sleep_streak":
            moon = QPainterPath()
            moon.addEllipse(QRectF(92, 70, 35, 37))
            cut = QPainterPath()
            cut.addEllipse(QRectF(106, 64, 31, 35))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPath(moon.subtracted(cut))
            p.drawPolygon(_star(127, 76, 4.5))
        elif self.family in ("work_week", "work_month"):
            p.drawRoundedRect(QRectF(92, 72, 36, 34), 4, 4)
            p.drawLine(QPointF(92, 82), QPointF(128, 82))
            p.drawLine(QPointF(101, 68), QPointF(101, 76))
            p.drawLine(QPointF(119, 68), QPointF(119, 76))
            if self.family == "work_month":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                for x in (101, 110, 119):
                    for y in (90, 98):
                        p.drawEllipse(QPointF(x, y), 1.8, 1.8)
            else:
                p.drawPolyline(QPolygonF([QPointF(101, 94), QPointF(107, 99), QPointF(120, 88)]))
        else:
            path = QPainterPath(QPointF(110, 78))
            path.cubicTo(102, 72, 94, 73, 90, 75)
            path.lineTo(90, 102)
            path.cubicTo(98, 100, 105, 101, 110, 106)
            path.cubicTo(115, 101, 122, 100, 130, 102)
            path.lineTo(130, 75)
            path.cubicTo(126, 73, 118, 72, 110, 78)
            p.drawPath(path)
            p.drawLine(QPointF(110, 78), QPointF(110, 106))

    @staticmethod
    def _paint_lock(p, shadow, light):
        p.setPen(QPen(_color(shadow, 165), 2.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(102, 75, 16, 17), 8, 8)
        p.setBrush(_color(shadow, 190))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(98, 87, 24, 20), 4, 4)
        p.setPen(QPen(_color(light, 210), 2.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(110, 94), QPointF(110, 99))

    def _paint_prism(self, p, light, middle, shadow):
        faces = (
            ([(88, 82), (98, 70), (110, 82)], "#DDF9FF"),
            ([(98, 70), (122, 70), (110, 82)], "#FFFFFF"),
            ([(122, 70), (132, 82), (110, 82)], "#B1BCFF"),
            ([(88, 82), (110, 112), (110, 82)], "#88A6EB"),
            ([(110, 82), (110, 112), (132, 82)], "#CEC0FF"),
        )
        for vertices, color in faces:
            p.setPen(QPen(_color(light, 200), .65))
            p.setBrush(QColor(color))
            p.drawPolygon(QPolygonF([QPointF(*point) for point in vertices]))
        if self.locked:
            # The silhouette is still visible as a preview; the UI labels it locked.
            p.setPen(QPen(_color(shadow, 150), 1.2))
            p.drawLine(QPointF(110, 82), QPointF(110, 112))

    def _paint_reveal(self, p):
        progress = self._reveal
        scale = min(self.width() / 220, self.height() / 200)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2 - 10 * scale)
        p.scale(scale, scale)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(18):
            angle = i * math.tau / 18 + .15
            radius = 46 + progress * (37 + i % 3 * 7)
            color = _color(METALS[self.tier][i % 2], round(230 * (1 - progress)))
            p.setBrush(color)
            x, y = math.cos(angle) * radius, math.sin(angle) * radius
            p.drawPolygon(_star(x, y, (2.5 + i % 3) * (1 - progress * .5), points=4,
                                rotation=progress * 70 + i * 25))
        p.restore()

