"""A quiet glass instrument for the focus session's real remaining time."""
from .i18n import tr
import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from .theme import palette_for
from .visuals import _ArtworkCache
from .widgets import motion_enabled, observe_visual_preferences


def _ink(value, alpha=255):
    color = QColor(value)
    color.setAlpha(alpha)
    return color


class FocusDial(QWidget):
    """Cache the sculpted face; animate only the arc and a finite light sweep.

    The numeral always uses ``seconds``. ``display_seconds`` is solely the
    interpolated position of the arc, never the time shown to the student.
    """

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.seconds = 25 * 60
        self.total_seconds = 25 * 60
        self.display_seconds = float(self.seconds)
        self._artwork = _ArtworkCache()
        self._sheen = 1.0
        self._completion = False
        # Read the preference at explicit changes, never during painting.
        self._local_motion = not ctx.db.get_setting("desktop_reduced_motion", False)
        self.setFixedSize(168, 168)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(360)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._advance)
        self.sheen_animation = QVariantAnimation(self)
        self.sheen_animation.setDuration(850)
        self.sheen_animation.setStartValue(0.0)
        self.sheen_animation.setEndValue(1.0)
        self.sheen_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.sheen_animation.valueChanged.connect(self._advance_sheen)
        ctx.theme_changed.connect(self._theme_changed)
        ctx.data_changed.connect(self._motion_changed)
        self._set_accessibility()
        observe_visual_preferences(self)

    @property
    def time_text(self):
        return f"{self.seconds // 60:02}:{self.seconds % 60:02}"

    def _set_accessibility(self):
        self.setAccessibleName(tr("Temps restant : {time}", time=self.time_text))
        self.setAccessibleDescription(tr("Minuteur de la séance de concentration"))

    def _can_animate(self):
        return self._local_motion and motion_enabled() and self.isVisible()

    def _reset_motion(self):
        self.animation.stop()
        self.sheen_animation.stop()
        self.display_seconds = float(self.seconds)
        self._sheen = 1.0
        self._completion = False
        self.update()

    def _theme_changed(self, *_):
        self._reset_motion()

    def _motion_changed(self, *_):
        self._local_motion = not self.ctx.db.get_setting("desktop_reduced_motion", False)
        if not self._can_animate():
            self._reset_motion()

    def _advance(self, value):
        if not self._can_animate():
            self._reset_motion()
            return
        self.display_seconds = float(value)
        self.update()

    def _advance_sheen(self, value):
        if not self._can_animate():
            self._reset_motion()
            return
        self._sheen = float(value)
        self.update()

    def _shine(self, completed=False):
        if not self._can_animate():
            return
        self.sheen_animation.stop()
        self._completion = completed
        self._sheen = 0.0
        self.sheen_animation.start()

    def set_seconds(self, seconds):
        previous = self.seconds
        self.seconds = max(0, int(seconds))
        self._set_accessibility()
        self.animation.stop()
        if self._can_animate() and self.display_seconds != self.seconds:
            self.animation.setStartValue(self.display_seconds)
            self.animation.setEndValue(float(self.seconds))
            self.animation.start()
        else:
            self.display_seconds = float(self.seconds)
        if previous > 0 and self.seconds == 0:
            self._shine(completed=True)
        self.update()

    def enterEvent(self, event):
        self._shine()
        super().enterEvent(event)

    def hideEvent(self, event):
        self._reset_motion()
        super().hideEvent(event)

    def _paint_face(self, p):
        colors = palette_for(self.ctx.theme)
        dark = self.ctx.theme == "dark"
        p.setPen(Qt.PenStyle.NoPen)
        # A compact cast shadow and a polished rim ground the glass lens.
        shadow = QRadialGradient(QPointF(84, 89), 79)
        shadow.setColorAt(.72, _ink("#243C81", 65 if dark else 30))
        shadow.setColorAt(1, _ink("#243C81", 0))
        p.setBrush(shadow)
        p.drawEllipse(QRectF(5, 10, 158, 158))
        bezel = QLinearGradient(30, 8, 138, 161)
        for position, color in ((0, "#C1D9FF" if dark else "#FFFFFF"),
                                (.28, "#394A72" if dark else "#DEE8FF"),
                                (.65, "#151E36" if dark else "#C6D1F0"),
                                (1, "#7D76A4" if dark else "#FAF6FF")):
            bezel.setColorAt(position, QColor(color))
        p.setBrush(bezel)
        p.drawEllipse(QRectF(7, 7, 154, 154))
        lens = QRadialGradient(QPointF(60, 41), 137)
        lens.setColorAt(0, QColor("#333D5C" if dark else "#FFFFFF"))
        lens.setColorAt(.55, QColor("#222A42" if dark else "#F1F5FF"))
        lens.setColorAt(1, QColor("#171B2B" if dark else "#DFE4F5"))
        p.setBrush(lens)
        p.setPen(QPen(_ink("#FFFFFF", 24 if dark else 170), .9))
        p.drawEllipse(QRectF(12, 12, 144, 144))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_ink("#8CA1D3", 52 if dark else 62), 4.2))
        p.drawEllipse(QRectF(12, 12, 144, 144))
        p.setPen(QPen(_ink("#FFFFFF", 21 if dark else 190), 1))
        p.drawArc(QRectF(20, 20, 128, 128), 24 * 16, 125 * 16)
        p.setPen(QPen(_ink("#606DB2", 35 if dark else 26), 1))
        p.drawArc(QRectF(22, 22, 124, 124), 201 * 16, 116 * 16)
        for index in range(60):
            angle = math.radians(index * 6 - 90)
            major = index % 5 == 0
            start = 58.7 if major else 62
            p.setPen(QPen(_ink(colors["muted"], 160 if major else 67), 1.3 if major else .8))
            p.drawLine(QPointF(84 + math.cos(angle) * start, 84 + math.sin(angle) * start),
                       QPointF(84 + math.cos(angle) * 65, 84 + math.sin(angle) * 65))
        # A small faceted blue crystal marks the top of the instrument.
        facet = QLinearGradient(76, 36, 92, 52)
        facet.setColorAt(0, QColor("#C5ECFF"))
        facet.setColorAt(.5, QColor("#638DEB"))
        facet.setColorAt(1, QColor("#876DD5"))
        p.setBrush(facet)
        p.setPen(QPen(_ink("#FFFFFF", 110), .6))
        p.drawPolygon(QPolygonF([QPointF(84, 35), QPointF(92, 43), QPointF(84, 51), QPointF(76, 43)]))
        p.setBrush(_ink("#FFFFFF", 95))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(84, 35), QPointF(84, 43), QPointF(76, 43)]))

    def _paint_progress(self, p):
        fraction = max(0., min(1., self.display_seconds / max(1, self.total_seconds)))
        gradient = QLinearGradient(14, 20, 149, 145)
        gradient.setColorAt(0, QColor("#51B9F3"))
        gradient.setColorAt(.45, QColor("#537FEA"))
        gradient.setColorAt(1, QColor("#AD7CDB"))
        pen = QPen(QBrush(gradient), 4.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if fraction > 0:
            p.drawArc(QRectF(12, 12, 144, 144), 90 * 16, -round(fraction * 360 * 16))
        angle = math.radians(360 * fraction - 90)
        tip = QPointF(84 + math.cos(angle) * 72, 84 + math.sin(angle) * 72)
        pearl = QRadialGradient(tip - QPointF(1.4, 1.7), 6.2)
        pearl.setColorAt(0, QColor("#FFFFFF"))
        pearl.setColorAt(.35, QColor("#D5E9FF"))
        pearl.setColorAt(.7, QColor("#86AAE9"))
        pearl.setColorAt(1, QColor("#5D67B2"))
        p.setPen(QPen(_ink("#FFFFFF", 180), .7))
        p.setBrush(pearl)
        p.drawEllipse(tip, 4.6, 4.6)

    def _paint_sheen(self, p):
        if self._sheen >= 1 or not self._can_animate():
            return
        phase = self._sheen
        strength = math.sin(math.pi * phase)
        if self._completion:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(_ink("#8CA9FF", round(120 * strength)), 1.5))
            radius = 72 + phase * 9
            p.drawEllipse(QPointF(84, 84), radius, radius)
        p.save()
        clip = QPainterPath()
        clip.addEllipse(QRectF(24, 24, 120, 120))
        p.setClipPath(clip)
        x = -65 + phase * 250
        gloss = QLinearGradient(x, 0, x + 65, 35)
        gloss.setColorAt(0, _ink("#FFFFFF", 0))
        gloss.setColorAt(.45, _ink("#FFFFFF", round((22 if self.ctx.theme == "dark" else 95) * strength)))
        gloss.setColorAt(1, _ink("#FFFFFF", 0))
        p.fillRect(QRectF(24, 24, 120, 120), gloss)
        p.restore()

    def paintEvent(self, event):
        colors = palette_for(self.ctx.theme)
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._artwork.prepare(self, 168, 168, self.ctx.theme, padding=0)
            self._artwork.draw(p, "face", self._paint_face)
            self._paint_progress(p)
            self._paint_sheen(p)
            p.setPen(QColor(colors["text"]))
            font = QFont("Segoe UI")
            font.setPixelSize(30 if len(self.time_text) < 6 else 27)
            font.setWeight(QFont.Weight.DemiBold)
            p.setFont(font)
            p.drawText(QRectF(27, 62, 114, 40), Qt.AlignmentFlag.AlignCenter, self.time_text)
            font.setPixelSize(9)
            font.setWeight(QFont.Weight.Medium)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, .7)
            p.setFont(font)
            p.setPen(QColor(colors["muted"]))
            p.drawText(QRectF(29, 102, 110, 15), Qt.AlignmentFlag.AlignCenter, tr("MINUTES POUR TOI"))
        finally:
            p.end()
