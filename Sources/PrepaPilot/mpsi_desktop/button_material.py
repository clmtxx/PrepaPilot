"""Small vector finishes for native controls; the text and hit target stay native."""
from math import sin, pi

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPen, QBrush


def button_radius(role):
    return 8 if role == 'nav' else 6 if role == 'link' else 10


def _pigment(value, fallback):
    """Accept an optional page colour without trusting arbitrary Qt properties."""
    try:
        color = QColor(value) if value is not None else QColor()
    except (TypeError, ValueError):
        color = QColor()
    return color if color.isValid() else QColor(fallback)


def paint_rim(painter, bounds, palette, role, *, dark=False, hover=0.0,
              depth=0.0, light=QPointF(0.5, 0.2), enabled=True, checked=False,
              material_accent=None):
    """A machined lip and lower edge, restricted to the control's perimeter."""
    radius = button_radius(role)
    rect = QRectF(bounds).adjusted(1.5, 1.5, -1.5, -1.5)
    if rect.width() <= 3 or rect.height() <= 3:
        return
    primary = role == 'primary' or (role == 'tab' and checked)
    quiet = role in {'link', 'danger'} or (role == 'nav' and not checked)
    # Links and unselected navigation remain typographic; their glint is transient.
    strength = (0.0 if quiet else 1.0) * (1.0 if enabled else 0.35)
    accent = (QColor(palette['danger']) if role == 'danger'
              else _pigment(material_accent, palette['accent']))
    copper = QColor('#D3A16D' if dark else '#B57A43')
    edge = QColor('#071A29' if primary else '#081118' if dark else '#51483A')
    # The apparent lower thickness compresses; no child geometry is animated.
    thickness = max(0.5, 2.2 - 1.45 * depth)
    painter.save()
    try:
        painter.setBrush(Qt.NoBrush)
        lower = QLinearGradient(0, rect.top(), 0, rect.bottom())
        edge.setAlphaF(0)
        lower.setColorAt(0, edge)
        lower.setColorAt(0.60, edge)
        edge.setAlphaF(strength * (0.60 if primary else 0.23 if dark else 0.19))
        lower.setColorAt(1, edge)
        painter.setPen(QPen(QBrush(lower), thickness))
        painter.drawRoundedRect(rect.adjusted(0.1, 0, -0.1, -0.15), radius, radius)

        upper = QLinearGradient(rect.topLeft(), rect.bottomRight())
        white = QColor('#FFFFFF' if primary or dark else '#FFFEF8')
        white.setAlphaF(strength * (0.38 if primary else 0.23 if dark else 0.92) * (1 - 0.3 * depth))
        upper.setColorAt(0, white)
        white.setAlphaF(strength * 0.05)
        upper.setColorAt(0.6, white)
        white.setAlpha(0)
        upper.setColorAt(1, white)
        painter.setPen(QPen(QBrush(upper), 1))
        painter.drawRoundedRect(rect.adjusted(0.8, 0.4 + max(0, depth) * 0.7, -0.8, -0.8), max(2, radius - 1), max(2, radius - 1))

        if primary and enabled:
            # A second, pigmented seam and short side inlay suggest enamel set
            # into a warm metal rim. Both stay clear of the native label area.
            inlay = rect.adjusted(2.3, 2.1 + max(0, depth) * .35, -2.3, -2.1)
            seam = QLinearGradient(inlay.topLeft(), inlay.bottomRight())
            pigment = accent.lighter(158 if dark else 182)
            pigment.setAlphaF(.48 if dark else .42)
            seam.setColorAt(0, pigment)
            pigment.setAlphaF(.055)
            seam.setColorAt(.52, pigment)
            warm = QColor(copper)
            warm.setAlphaF(.27 if dark else .22)
            seam.setColorAt(1, warm)
            painter.setPen(QPen(QBrush(seam), .85))
            painter.drawRoundedRect(inlay, max(2, radius - 2), max(2, radius - 2))
            side = accent.lighter(185 if dark else 205)
            side.setAlphaF(.76 if dark else .67)
            painter.setPen(QPen(side, 1.35, Qt.SolidLine, Qt.RoundCap))
            half = min(6.5, max(3, inlay.height() * .17))
            middle = inlay.center().y() + max(0, depth) * .25
            painter.drawLine(QPointF(inlay.left() + .7, middle - half),
                             QPointF(inlay.left() + .7, middle + half))

        if enabled and hover > 0:
            # A narrow, asymmetric edge reflection follows the pointer like enamel.
            position = rect.left() + rect.width() * light.x()
            glint = QLinearGradient(position - 60, 0, position + 60, 0)
            highlight = (accent.lighter(185) if primary else QColor(accent)
                         if material_accent is not None or role == 'danger' else QColor(copper))
            highlight.setAlpha(0)
            glint.setColorAt(0, highlight)
            glint.setColorAt(1, highlight)
            highlight.setAlphaF(hover * (0.67 if primary else 0.49))
            glint.setColorAt(0.5, highlight)
            painter.setPen(QPen(QBrush(glint), 1.25))
            painter.drawLine(QPointF(rect.left() + radius, rect.top() + 0.8),
                             QPointF(rect.right() - radius, rect.top() + 0.8))
            # An oblique side seam supplies depth without tinting the text area.
            accent.setAlphaF(hover * 0.20)
            painter.setPen(QPen(accent, 1))
            side = rect.left() + 1.5 if light.x() < 0.5 else rect.right() - 1.5
            painter.drawLine(QPointF(side, rect.top() + radius), QPointF(side, rect.bottom() - radius))
    finally:
        painter.restore()


def paint_sparkles(painter, bounds, role, progress, *, dark=False, material_accent=None):
    """Three brief specular glints, timed once per interaction, never random."""
    if not 0 < progress < 1:
        return
    rect = QRectF(bounds).adjusted(3, 3, -3, -3)
    if rect.width() < 20 or rect.height() < 12:
        return
    primary = role == 'primary'
    if role == 'danger':
        color = QColor('#F09687' if dark else '#B34239').lighter(120)
    elif primary or material_accent is not None:
        color = _pigment(material_accent, '#86B6DD' if dark else '#2E6289').lighter(150 if primary else 125)
    else:
        color = QColor('#D3A16D' if dark else '#A56934')
    painter.save()
    try:
        painter.setBrush(Qt.NoBrush)
        for delay, x, bottom, reach in ((0.0, .19, False, 3.7), (.16, .68, False, 2.8), (.32, .87, True, 3.2)):
            phase = (progress - delay) / (1 - delay)
            if not 0 < phase < 1:
                continue
            pulse = sin(pi * phase) ** 2
            point = QPointF(rect.left() + rect.width() * (x + .045 * (phase - .5)),
                            rect.bottom() - .5 if bottom else rect.top() + .5)
            color.setAlphaF(pulse * (.88 if primary else .72))
            painter.setPen(QPen(color, .9, Qt.SolidLine, Qt.RoundCap))
            size = .7 + reach * pulse
            painter.drawLine(point - QPointF(size, 0), point + QPointF(size, 0))
            painter.drawLine(point - QPointF(0, size * .7), point + QPointF(0, size * .7))
            core = QColor('#FFFFFF' if primary or dark else '#FFF7DF')
            core.setAlphaF(pulse * .95)
            painter.setPen(QPen(core, 1.2))
            painter.drawPoint(point)
    finally:
        painter.restore()
