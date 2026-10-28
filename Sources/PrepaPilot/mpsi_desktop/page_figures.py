"""Small sculpted illustrations that extend Progression's visual language.

The figures are drawn locally and share its bounded, interaction-only motion.
They are decorative: their shapes never stand for application data.
"""
from __future__ import annotations
from .i18n import tr

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen

from .progression_visuals import (
    ProgressionFigure, _color, _gradient, _halo, _polygon, _theme,
)


_AXES = {"home": "work", "notes": "sleep", "documents": "sport",
         "time": "sport", "memory": "sleep", "settings": "rest"}
_NAMES = {"home": "Agenda et soleil en relief", "notes": "Carnet et médaille en relief",
          "documents": "Dossier et feuilles en relief", "time": "Horloge en relief",
          "memory": "Cartes et étoile en relief", "settings": "Commandes en relief"}

# Pigment-like accents keep each subject distinct without turning every panel
# into a luminous colour block. Warm paper and ink do most of the work.
_PAGE_PALETTES = {
    "home": ("#2D62A0", "#B4D2EC", "#1E4678", "#D6E5F4", "#8FBAE2", "#233D53"),
    "notes": ("#A34469", "#E9BCD0", "#7F2F4E", "#F0DAE4", "#E5A4BD", "#49303F"),
    "documents": ("#238368", "#AFE0CB", "#175E4A", "#D7ECE2", "#8CD2B5", "#23483E"),
    "time": ("#AD6B2D", "#EDD0A5", "#7F4B1D", "#F2E2C9", "#E0B383", "#4A3A2A"),
    "memory": ("#7060A0", "#CFC3EB", "#51457D", "#E3DDF1", "#C0B3E4", "#3A3452"),
    "settings": ("#71833C", "#D0DEA9", "#4D5B28", "#E5EACD", "#C1D199", "#3E482B"),
}


def page_palette(kind, theme="light"):
    """Return the palette used by a page and its decorative illustration."""
    accent, light, dark, tint, dark_accent, dark_tint = _PAGE_PALETTES.get(kind, _PAGE_PALETTES["home"])
    return dict(accent=dark_accent if theme == "dark" else accent,
                light=light, dark=dark, tint=dark_tint if theme == "dark" else tint)


def _rounded(p, rect, colors, radius=10, outline=None):
    p.setPen(QPen(_color(outline, 170), .9) if outline else Qt.PenStyle.NoPen)
    p.setBrush(_gradient(rect, *colors))
    p.drawRoundedRect(rect, radius, radius)


def _line(p, a, b, color, width=2):
    p.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(*a), QPointF(*b))


def _spark(p, x, y, radius, colors):
    star = QPainterPath(); star.moveTo(x, y - radius)
    star.quadTo(x + radius * .2, y - radius * .2, x + radius, y)
    star.quadTo(x + radius * .2, y + radius * .2, x, y + radius)
    star.quadTo(x - radius * .2, y + radius * .2, x - radius, y)
    star.quadTo(x - radius * .2, y - radius * .2, x, y - radius)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_gradient(QRectF(x - radius, y - radius, radius * 2, radius * 2), *colors))
    p.drawPath(star)


class PageFigure(ProgressionFigure):
    """A transparent, accessible 220 × 160 studio illustration for one page."""

    def __init__(self, kind, parent=None):
        self.kind = kind if kind in _AXES else "home"
        super().__init__(_AXES[self.kind], parent)
        self.setAccessibleName(tr(_NAMES[self.kind]))

    def _figure_variant(self):
        return self.kind

    def _orbit_angle(self):
        return {"home": -22, "notes": 19, "documents": -12,
                "time": -32, "memory": 24, "settings": -18}[self.kind]

    def _satellite_layout(self):
        # Distinct compositions frame the useful object without covering it.
        return {"home": ((34, 43, 9), (183, 118, 8)),
                "notes": ((35, 112, 9), (183, 36, 7)),
                "documents": ((187, 93, 9), (39, 30, 7)),
                "time": ((33, 46, 10), (181, 121, 7)),
                "memory": ((31, 43, 9), (183, 116, 8)),
                "settings": ((33, 117, 9), (183, 29, 8))}[self.kind]

    def _paint_studio(self, p):
        colors = page_palette(self.kind, _theme())
        _halo(p, QRectF(18, 13, 185, 128), colors["light"], 34 if _theme() == "dark" else 62)
        _halo(p, QRectF(39, 129, 147, 20), colors["dark"], 73 if _theme() == "dark" else 49)

    def _paint_figure(self, p):
        getattr(self, "_paint_" + self.kind)(p, page_palette(self.kind, _theme()))

    def _paint_home(self, p, c):
        # A pearl agenda with a blue enamel top, in front of a warm sunrise.
        _halo(p, QRectF(130, 6, 71, 71), "#FFCC6A", 75)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(QRectF(144, 17, 42, 43), "#FFF5C9", "#FFDA89", "#E9A548"))
        p.drawEllipse(QRectF(144, 17, 42, 43))
        p.setPen(QPen(_color("#FFFFFF", 180), 1.3))
        p.drawArc(QRectF(145, 18, 40, 41), 20 * 16, 132 * 16)
        p.save(); p.translate(111, 81); p.rotate(-10)
        _rounded(p, QRectF(-53, -44, 107, 100), ("#B7D7EE", "#6394C4"), 15)
        _rounded(p, QRectF(-56, -49, 106, 100), ("#FFFFFF", "#F0F7FF", "#DCEAF7"), 15, "#FFFFFF")
        top = QPainterPath(); top.addRoundedRect(QRectF(-56, -49, 106, 37), 15, 15)
        top.addRect(QRectF(-56, -34, 106, 22)); top.setFillRule(Qt.FillRule.WindingFill)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(QRectF(-56, -49, 106, 37), "#A4DDFF", "#4A9DF5", "#2B69C7")); p.drawPath(top)
        for x in (-31, 24):
            _rounded(p, QRectF(x, -56, 8, 22), ("#D6E4F5", "#FFFFFF", "#849FBE"), 4)
        for row in range(3):
            for column in range(4):
                x, y = -37 + column * 21, -1 + row * 17
                _rounded(p, QRectF(x, y, 10, 7), ("#C0D3E7", "#ABBFDC"), 2)
        _rounded(p, QRectF(1, 12, 20, 18), ("#83C5FF", "#367EDD", "#1C58B3"), 6)
        _line(p, (6, 21), (9, 24), "#FFFFFF", 1.7)
        _line(p, (9, 24), (15, 18), "#FFFFFF", 1.7)
        p.restore()
        cloud = QPainterPath(); cloud.setFillRule(Qt.FillRule.WindingFill)
        cloud.addRoundedRect(QRectF(133, 62, 59, 17), 9, 9)
        cloud.addEllipse(QRectF(142, 47, 28, 28)); cloud.addEllipse(QRectF(163, 55, 23, 24))
        p.setPen(Qt.PenStyle.NoPen)
        p.save(); p.translate(0, 3); p.setBrush(QColor("#B8CDDF")); p.drawPath(cloud); p.restore()
        p.setBrush(_gradient(QRectF(139, 48, 54, 33), "#FFFFFF", "#F6FAFF", "#D7E5F0")); p.drawPath(cloud)

    def _paint_notes(self, p, c):
        p.save(); p.translate(97, 78); p.rotate(-9)
        _rounded(p, QRectF(-43, -50, 90, 112), ("#B19DCF", "#66568C"), 11)
        _rounded(p, QRectF(-47, -54, 90, 112), ("#FDFBFF", "#EAE2FA", "#CFC0E9"), 11, "#FFFFFF")
        _rounded(p, QRectF(-36, -41, 48, 6), ("#B8A1DD", "#9072BE"), 3)
        _line(p, (-36, -26), (22, -26), "#C4B5DE", 2)
        for x, y, h, colors in ((-32, 17, 26, ("#E1CFFF", "#B498DE")),
                                (-10, 3, 40, ("#D4BBFF", "#946DCF")),
                                (12, -10, 53, ("#BEA0F4", "#7955B7"))):
            _rounded(p, QRectF(x + 3, y + 3, 14, h), ("#9270B7", "#715095"), 4)
            _rounded(p, QRectF(x, y, 14, h), colors, 4, "#EEE3FF")
        p.restore()
        # Enamel award with bevel and folded blue ribbons.
        _polygon(p, [(148, 93), (167, 98), (163, 137), (153, 129), (144, 134)],
                 _gradient(QRectF(144, 93, 23, 44), "#9BAAEF", "#5062AE"))
        _polygon(p, [(151, 96), (173, 90), (184, 125), (173, 122), (167, 133)],
                 _gradient(QRectF(151, 90, 33, 43), "#BCCAFE", "#6F80CE"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(QRectF(131, 65, 51, 51), "#F4CB85", "#A76D2E")); p.drawEllipse(QRectF(134, 68, 51, 51))
        p.setBrush(_gradient(QRectF(131, 65, 51, 51), "#FFF4CF", "#EDC27B", "#CC9448")); p.drawEllipse(QRectF(131, 65, 51, 51))
        p.setBrush(_gradient(QRectF(137, 71, 39, 39), "#FFDFA2", "#EABA69")); p.drawEllipse(QRectF(137, 71, 39, 39))
        p.setPen(QPen(_color("#FFFFFF", 175), 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(136, 70, 41, 41))
        _spark(p, 156.5, 91, 12, ("#FFFCDF", "#FFF0BD", "#D89C4D"))

    def _paint_documents(self, p, c):
        p.save(); p.translate(110, 84); p.rotate(-7)
        back = QPainterPath(); back.moveTo(-68, -25); back.quadTo(-68, -36, -57, -36)
        back.lineTo(-30, -36); back.lineTo(-18, -25); back.lineTo(55, -25)
        back.quadTo(66, -25, 66, -14); back.lineTo(63, 42)
        back.quadTo(62, 52, 52, 52); back.lineTo(-56, 52); back.quadTo(-67, 52, -68, 40); back.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(_gradient(QRectF(-68, -36, 134, 88), "#A7EDDD", "#63C3A9", "#32836D")); p.drawPath(back)
        p.save(); p.rotate(8)
        _rounded(p, QRectF(-42, -61, 81, 100), ("#CBDFF0", "#F4FAFF", "#B9D1E0"), 7)
        p.restore()
        _rounded(p, QRectF(-44, -53, 84, 97), ("#FFFFFF", "#EEF8F4", "#D5E7E2"), 7, "#FFFFFF")
        _rounded(p, QRectF(-32, -39, 30, 5), ("#8FCFBD", "#65AA99"), 2)
        for y, end in ((-25, 27), (-15, 22), (-5, 28)):
            _line(p, (-32, y), (end, y), "#B3CEC5", 2)
        front = QPainterPath(); front.moveTo(-71, -4); front.quadTo(-73, -14, -61, -14)
        front.lineTo(65, -14); front.quadTo(76, -14, 72, -3)
        front.lineTo(59, 44); front.quadTo(57, 54, 45, 54)
        front.lineTo(-50, 54); front.quadTo(-61, 54, -63, 44); front.closeSubpath()
        p.save(); p.translate(1, 4)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#378A78")); p.drawPath(front); p.restore()
        p.setBrush(_gradient(QRectF(-71, -14, 143, 68), "#C6F8E9", "#7DD8BD", "#4BAB92"))
        p.setPen(QPen(_color("#E8FFF7", 185), 1)); p.drawPath(front)
        _rounded(p, QRectF(-21, 9, 46, 17), ("#E2FFF3", "#B0EAD6", "#80CEB4"), 5)
        _line(p, (-10, 17), (14, 17), "#6FAF9F", 2)
        p.restore()
        _spark(p, 181, 34, 7, ("#D7FFF2", "#5BBAA1"))

    def _paint_time(self, p, c):
        # Offset rings supply depth; highlights make the rim feel glazed.
        _rounded(p, QRectF(96, 12, 32, 14), ("#F9E2B0", "#D3AC69"), 5)
        _rounded(p, QRectF(102, 23, 19, 11), ("#D0EEE4", "#77B5A5"), 3)
        _rounded(p, QRectF(73, 125, 16, 13), ("#C4ECDD", "#71AFA1"), 5)
        _rounded(p, QRectF(140, 123, 16, 14), ("#C4ECDD", "#71AFA1"), 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(QRectF(58, 29, 114, 111), "#B2F2DE", "#3E9685", "#286C66"))
        p.drawEllipse(QRectF(58, 29, 114, 111))
        p.setBrush(_gradient(QRectF(51, 24, 114, 111), "#DEFFF4", "#93DCC6", "#4DA38F"))
        p.drawEllipse(QRectF(51, 24, 114, 111))
        p.setBrush(_gradient(QRectF(59, 32, 98, 95), "#81BDAF", "#DEF3EC")); p.drawEllipse(QRectF(59, 32, 98, 95))
        p.setBrush(_gradient(QRectF(63, 36, 91, 87), "#FFFFFF", "#F0FAF6", "#D9EEE7")); p.drawEllipse(QRectF(63, 36, 91, 87))
        p.setPen(QPen(_color("#FFFFFF", 180), 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(52, 25, 112, 109), 22 * 16, 152 * 16)
        for a, b in (((108, 44), (108, 50)), ((108, 109), (108, 115)), ((71, 80), (77, 80)), ((140, 80), (146, 80))):
            _line(p, a, b, "#97B8AC", 2.3)
        _line(p, (109, 81), (109, 58), "#438D82", 4)
        _line(p, (109, 81), (132, 92), "#567FC0", 3.5)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(_gradient(QRectF(103, 74, 12, 12), "#C1E9DE", "#4A9182"))
        p.drawEllipse(QRectF(103, 74, 12, 12))
        p.setBrush(QColor("#F3FFF9")); p.drawEllipse(QRectF(106, 77, 4, 4))
        _spark(p, 176, 46, 8, ("#D9EFFF", "#6AA4E5"))

    def _paint_memory(self, p, c):
        p.save(); p.translate(103, 81); p.rotate(-20)
        _rounded(p, QRectF(-46, -48, 89, 109), ("#B9CDF4", "#8CA9DC", "#6184BB"), 12, "#E1EBFF")
        p.restore()
        p.save(); p.translate(115, 81); p.rotate(12)
        _rounded(p, QRectF(-42, -48, 90, 109), ("#CCB4EF", "#A88AD6", "#7C63A6"), 12)
        p.restore()
        p.save(); p.translate(109, 77); p.rotate(-3)
        _rounded(p, QRectF(-42, -49, 89, 109), ("#BBAAD6", "#8B74AB"), 12)
        _rounded(p, QRectF(-46, -53, 89, 109), ("#FFFFFF", "#F5EFFF", "#DACBED"), 12, "#FFFFFF")
        _rounded(p, QRectF(-30, -40, 19, 5), ("#DDC8F8", "#BA9AD9"), 2)
        _line(p, (-28, 28), (22, 28), "#C8B6DE", 2.5)
        _line(p, (-20, 38), (15, 38), "#D4C3E7", 2.5)
        _spark(p, 1, -3, 25, ("#A38BD0", "#7655A2"))
        _spark(p, -2, -7, 25, ("#E8D5FF", "#B995E4", "#926BC4"))
        _spark(p, -6, -13, 6, ("#FFFFFF", "#E2CBFB"))
        p.restore()
        _spark(p, 179, 47, 9, ("#EFDFFF", "#A987D4"))
        _spark(p, 43, 104, 5, ("#DBC7FA", "#A686D5"))

    def _paint_settings(self, p, c):
        p.save(); p.translate(110, 79); p.rotate(-10)
        _rounded(p, QRectF(-57, -46, 120, 111), ("#C5D7E8", "#809CAF", "#648599"), 19)
        _rounded(p, QRectF(-63, -52, 120, 111), ("#FFFFFF", "#EDF4FA", "#CEDDE9"), 19, "#FFFFFF")
        # Recessed tracks, colored inlays and rounded metal knobs.
        for y, x, colors in ((-27, -3, ("#AAD6FF", "#598BD5", "#365EAE")),
                             (1, 22, ("#FFEBC0", "#F1CB82", "#BF8B42")),
                             (29, -17, ("#B5EBDB", "#7BC3AD", "#45927E"))):
            _rounded(p, QRectF(-40, y - 3, 70, 8), ("#AEBFCC", "#D3E0E8"), 4)
            _rounded(p, QRectF(-39, y - 2, x + 40, 5), colors[:2], 2.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_gradient(QRectF(x - 9, y - 8, 21, 21), colors[1], colors[2]))
            p.drawEllipse(QRectF(x - 9, y - 8, 21, 21))
            p.setBrush(_gradient(QRectF(x - 11, y - 11, 21, 21), "#FFFFFF", colors[0], colors[1]))
            p.drawEllipse(QRectF(x - 11, y - 11, 21, 21))
            p.setPen(QPen(_color("#FFFFFF", 185), 1.1)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(x - 10, y - 10, 19, 19), 22 * 16, 151 * 16)
        p.restore()
        _spark(p, 182, 42, 7, ("#FFF1C5", "#DAB16D"))
