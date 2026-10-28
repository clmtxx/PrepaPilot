"""Shared coloured surfaces and sculpted headings for the study workspace."""
from math import cos, sin, pi, sqrt

from PySide6.QtCore import QRectF, QPointF, Qt, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout

from .page_figures import PageFigure, page_palette
from .theme import palette_for
from .visuals import ReflectiveTitle
from .widgets import Card, motion_enabled


class AccentTitle(ReflectiveTitle):
    """Keep native label sizing and accessibility with a page-coloured reflection."""

    def __init__(self, ctx, kind, text, parent=None):
        super().__init__(text, parent)
        self.ctx, self.kind = ctx, kind

    def _brush(self, rect):
        colors = page_palette(self.kind, self.ctx.theme)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base = QColor(colors['accent'])
        gradient.setColorAt(0, base)
        gradient.setColorAt(1, QColor(colors['light'] if self.ctx.theme == 'dark' else colors['dark']))
        if self._reflection is not None:
            for offset, color in ((-.13, base), (0, QColor(colors['light'])), (.13, base)):
                position = self._reflection + offset
                if 0 <= position <= 1:
                    gradient.setColorAt(position, color)
        return QBrush(gradient)


class AccentCard(Card):
    """A cached coloured surface; live text and controls stay at native resolution."""

    MAX_SURFACE_PIXELS = 220_000

    def __init__(self, ctx, kind, parent=None):
        self._surface_key = None
        self._surface = QPixmap()
        self._glint = 1.0
        self._light = QPointF(.82, .08)
        super().__init__(parent)
        self.ctx, self.kind = ctx, kind
        self.glint_animation = QVariantAnimation(self)
        self.glint_animation.setDuration(720)
        self.glint_animation.setStartValue(0.0)
        self.glint_animation.setEndValue(1.0)
        self.glint_animation.setEasingCurve(QEasingCurve.Linear)
        self.glint_animation.valueChanged.connect(self._advance_glint)
        self.setMouseTracking(True)
        self.setObjectName('AccentCard')
        self.body.setSizeConstraint(QLayout.SetMinimumSize)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ctx.theme_changed.connect(self._apply_palette)
        self._apply_palette()

    def _apply_palette(self, *_):
        self._surface_key = None
        self._surface = QPixmap()
        self._reset_motion()
        colors = page_palette(self.kind, self.ctx.theme)
        self.setProperty('materialAccent', colors['accent'])
        button_colors = page_palette(self.kind, 'light')
        neutral = palette_for(self.ctx.theme)
        button_start = (QColor(button_colors['accent']).darker(108).name()
                        if self.kind in ('time', 'settings') else button_colors['accent'])
        button_finish = button_colors['dark']
        button_text = '#FFFFFF'
        button_hover = QColor(button_start).lighter(106 if self.kind == 'documents' else 112).name()
        button_end = QColor(button_finish).lighter(115).name()
        self.setStyleSheet(f"""
            QLabel#colorEyebrow {{ color:{colors['accent']}; font-size:11px; font-weight:700; letter-spacing:1.2px; }}
            QLabel#statValue {{ color:{colors['accent']}; font-size:32px; font-weight:700; letter-spacing:-0.8px; }}
            QPushButton[role='primary'] {{
                background:qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {button_start}, stop:1 {button_finish});
                color:{button_text}; border:1px solid {button_start}; font-weight:600;
            }}
            QPushButton[role='primary']:hover {{
                background:qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {button_hover}, stop:1 {button_end}); color:{button_text};
            }}
            QPushButton[role='primary']:pressed {{ background:{button_finish}; color:{button_text}; }}
            QPushButton[role='primary']:focus {{ border-color:{colors['light']}; }}
            QPushButton[role='primary']:disabled {{ background:{neutral['surface2']}; color:{neutral['muted']}; border-color:{neutral['border']}; }}
        """)
        self.update()

    def _outline(self):
        outline = QPainterPath()
        radius = 18 if isinstance(self, PageHero) else 16
        outline.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -4), radius, radius)
        return outline

    def _advance_glint(self, value):
        self._glint = float(value) if motion_enabled() and self.isVisible() else 1.0
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._track_light(event.position())
        if motion_enabled() and self.isEnabled():
            self.glint_animation.stop()
            self.glint_animation.start()

    def leaveEvent(self, event):
        if hasattr(self, 'glint_animation'):
            self.glint_animation.stop()
            self._glint = 1.0
            self.light_animation.stop()
        super().leaveEvent(event)

    def _reset_motion(self):
        super()._reset_motion()
        if hasattr(self, 'glint_animation'):
            self.glint_animation.stop()
            self.light_animation.stop()
        self._glint = 1.0
        self._light = QPointF(.82, .08)
        self.update()

    def _paint_surface(self, painter):
        """Rasterized once per size/theme/screen, never once per motion frame."""
        colors = page_palette(self.kind, self.ctx.theme)
        neutral = palette_for(self.ctx.theme)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -4)
        outline = self._outline()
        # The lower contact and thin side wall live inside the widget. There is
        # no blurred graphics effect, offscreen shadow or moving layout margin.
        painter.setPen(Qt.NoPen)
        for drop, alpha in ((3, 12), (2, 17), (1, 22)):
            painter.setBrush(QColor(9, 20, 26, alpha if self.ctx.theme == 'dark' else alpha // 2))
            painter.drawRoundedRect(rect.translated(0, drop), 17, 17)
        painter.setClipPath(outline)
        base = QColor(neutral['surface'])
        painter.fillPath(outline, base)
        # Pigment belongs to the heading band and the trailing corner. The
        # central reading area deliberately retains the paper/graphite ground.
        band = QLinearGradient(0, 0, 0, min(70, self.height() * .32))
        color = QColor(colors['tint'])
        color.setAlphaF(.82 if self.ctx.theme == 'dark' else .88)
        band.setColorAt(0, color)
        color.setAlphaF(.54 if self.ctx.theme == 'dark' else .62)
        band.setColorAt(.40, color)
        color.setAlpha(0)
        band.setColorAt(1, color)
        painter.fillPath(outline, band)
        gradient = QLinearGradient(self.width() * .68, 0, self.width(), 0)
        gradient.setColorAt(0, color)
        color.setAlphaF(.54 if self.ctx.theme == 'dark' else .70)
        gradient.setColorAt(1, color)
        painter.fillPath(outline, gradient)
        # A small pigmented seam and a brushed corner give the paper a crafted
        # edge. The grain is deterministic and rasterized only with the surface.
        seam = QColor(colors['accent'])
        seam.setAlpha(160 if self.ctx.theme == 'dark' else 165)
        painter.setPen(QPen(seam, 2.5))
        painter.drawLine(QPointF(2.5, 31), QPointF(2.5, max(32, min(self.height() - 24, 78))))
        seam.setAlpha(70 if self.ctx.theme == 'dark' else 65)
        painter.setPen(QPen(seam, .8))
        painter.drawLine(QPointF(6, 34), QPointF(6, max(35, min(self.height() - 28, 75))))
        # A pair of short inlaid rules reads like the edge of a paper tab. It is
        # drawn into the material, without adding labels or covering controls.
        seam.setAlpha(155 if self.ctx.theme == 'dark' else 175)
        painter.setPen(QPen(seam, 1.2, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(20, 10.5), QPointF(60, 10.5))
        seam.setAlpha(65 if self.ctx.theme == 'dark' else 80)
        painter.setPen(QPen(seam, .8, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(20, 14), QPointF(40, 14))
        grain = QColor(neutral['text'])
        grain.setAlpha(8 if self.ctx.theme == 'dark' else 7)
        painter.setPen(QPen(grain, .7))
        right = self.width() - 21
        for column in range(13):
            for row in range(5):
                x, y = right - column * 11, 18 + row * 11
                if x > self.width() * .72 and y < self.height() - 15:
                    painter.drawPoint(QPointF(x, y))
        sheen = QLinearGradient(0, 0, 0, min(70, self.height() * .5))
        sheen.setColorAt(0, QColor(255, 255, 255, 15 if self.ctx.theme == 'dark' else 80))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(outline, sheen)
        inset = QPainterPath()
        inset.addRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), 15, 15)
        highlight = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        highlight.setColorAt(0, QColor(255, 255, 255, 38 if self.ctx.theme == 'dark' else 205))
        highlight.setColorAt(.48, QColor(255, 255, 255, 0))
        highlight.setColorAt(1, QColor(0, 0, 0, 20 if self.ctx.theme == 'dark' else 14))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QBrush(highlight), 1))
        painter.drawPath(inset)

    def _cached_surface(self):
        key = (self.size().width(), self.size().height(), self.devicePixelRatioF(),
               self.kind, self.ctx.theme)
        if key != self._surface_key:
            width, height = max(1, self.width()), max(1, self.height())
            ratio = min(self.devicePixelRatioF(), sqrt(self.MAX_SURFACE_PIXELS / (width * height)))
            surface = QPixmap(max(1, int(width * ratio)), max(1, int(height * ratio)))
            surface.setDevicePixelRatio(ratio)
            surface.fill(Qt.transparent)
            painter = QPainter(surface)
            try:
                painter.setRenderHint(QPainter.Antialiasing)
                self._paint_surface(painter)
            finally:
                painter.end()
            self._surface, self._surface_key = surface, key
        return self._surface

    def paintEvent(self, event):
        colors = page_palette(self.kind, self.ctx.theme)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            rect = QRectF(self.rect()).adjusted(1, 1, -1, -4)
            outline = self._outline()
            surface = self._cached_surface()
            painter.drawPixmap(QRectF(self.rect()), surface, QRectF(surface.rect()))
            painter.setClipPath(outline)
            hover = self._hover if motion_enabled() else 0
            if hover:
                glow = QRadialGradient(QPointF(self.width() * self._light.x(), self.height() * self._light.y()), max(80, min(220, self.width() * .38)))
                tint = QColor(colors['light'])
                tint.setAlphaF(hover * .12)
                glow.setColorAt(0, tint)
                tint.setAlpha(0)
                glow.setColorAt(1, tint)
                painter.fillPath(outline, glow)
            border = QColor(colors['accent'])
            border.setAlphaF(.54 if self.ctx.theme == 'dark' else .44)
            edge = QLinearGradient(rect.topLeft(), rect.bottomRight())
            edge.setColorAt(0, border)
            border = QColor(colors['accent'])
            border.setAlphaF(.28 + hover * .20)
            edge.setColorAt(.55, border)
            border.setAlphaF(.49 + hover * .22)
            edge.setColorAt(1, border)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QBrush(edge), 1.0))
            painter.drawPath(outline)
            self._paint_glint(painter, rect, colors)
        finally:
            painter.end()

    def _paint_glint(self, painter, rect, colors):
        if self._glint >= 1 or not motion_enabled():
            return
        pulse = sin(pi * self._glint) ** 2
        x = rect.left() + 19 + (rect.width() - 38) * self._glint
        color = QColor(colors['light'])
        color.setAlphaF(.84 * pulse)
        painter.setPen(QPen(color, 1.3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(max(rect.left() + 17, x - 23), rect.top() + 1),
                         QPointF(min(rect.right() - 17, x + 23), rect.top() + 1))
        # Two tiny specular crosses are attached to the rim, never floating over
        # content or reading as a stream of decorative particles.
        for location, offset in ((.29, 0), (.78, .16)):
            phase = max(0., min(1., (self._glint - offset) / .75))
            strength = sin(pi * phase) ** 6
            radius = 3.8 * strength
            if radius > .1:
                sx, sy = rect.left() + rect.width() * location, rect.top() + 2.5
                white = QColor('#FFF2D8')
                white.setAlphaF(strength * .9)
                painter.setPen(QPen(white, .9, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(sx - radius, sy), QPointF(sx + radius, sy))
                painter.drawLine(QPointF(sx, sy - radius), QPointF(sx, sy + radius))


class PageHero(AccentCard):
    """A compact introduction with a tangible object and the page's real actions."""

    def __init__(self, ctx, kind, eyebrow, title, subtitle, actions=(), parent=None):
        self._arrival = 1.0
        super().__init__(ctx, kind, parent)
        self.arrival_animation = QVariantAnimation(self)
        self.arrival_animation.setDuration(900)
        self.arrival_animation.setStartValue(0.0)
        self.arrival_animation.setEndValue(1.0)
        self.arrival_animation.setEasingCurve(QEasingCurve.InOutSine)
        self.arrival_animation.valueChanged.connect(self._advance_arrival)
        self.body.setContentsMargins(26, 20, 26, 20)
        self.body.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(20)
        copy = QVBoxLayout()
        copy.setSpacing(9)
        self.eyebrow_label = QLabel(eyebrow, objectName='colorEyebrow')
        self.eyebrow_label.setTextFormat(Qt.PlainText)
        self.eyebrow_label.setWordWrap(True)
        self.title_label = AccentTitle(ctx, kind, title)
        self.title_label.setObjectName('pageTitle')
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet('font-size:29px;font-weight:600;letter-spacing:-0.5px;')
        self.subtitle_label = QLabel(subtitle, objectName='pageSubtitle')
        self.subtitle_label.setTextFormat(Qt.PlainText)
        self.subtitle_label.setWordWrap(True)
        copy.addWidget(self.eyebrow_label)
        copy.addWidget(self.title_label)
        copy.addWidget(self.subtitle_label)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        for action in actions:
            controls.addWidget(action)
        controls.addStretch()
        if actions and len(actions) <= 1:
            copy.addSpacing(3)
            copy.addLayout(controls)
        row.addLayout(copy, 1)
        self.figure = PageFigure(kind)
        self.figure.setFixedSize(178, 142)
        self.bind_pointer_figure(self.figure)
        row.addWidget(self.figure, 0, Qt.AlignVCenter)
        self.body.addLayout(row)
        if len(actions) > 1:
            self.body.addLayout(controls)

    def _paint_surface(self, painter):
        super()._paint_surface(painter)
        colors = page_palette(self.kind, self.ctx.theme)
        # The object sits above a lightly tinted glass medallion. Its graduated
        # rim and inset highlights add detail while the reading area stays clear.
        painter.save()
        width, height = self.width(), self.height()
        pool = QRadialGradient(QPointF(width * .88, height * .50), max(100, min(150, height * .64)))
        pool_color = QColor(colors['accent'])
        pool_color.setAlphaF(.19 if self.ctx.theme == 'dark' else .12)
        pool.setColorAt(0, pool_color)
        pool_color.setAlpha(0)
        pool.setColorAt(1, pool_color)
        painter.fillPath(self._outline(), pool)
        painter.setClipRect(QRectF(self.width() * .64, 0, self.width() * .36, self.height()))
        center = QPointF(width - 115, (height - 4) * .50)
        radius = max(38, min(73, (height - 42) * .46))
        medal = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(9, 20, 26, 22 if self.ctx.theme == 'dark' else 10))
        painter.drawEllipse(medal.translated(0, 3))
        glass = QLinearGradient(medal.topLeft(), medal.bottomRight())
        ink = QColor(colors['light'])
        ink.setAlphaF(.28 if self.ctx.theme == 'dark' else .42)
        glass.setColorAt(0, ink)
        ink = QColor(colors['accent'])
        ink.setAlphaF(.12 if self.ctx.theme == 'dark' else .08)
        glass.setColorAt(.60, ink)
        ink.setAlphaF(.22 if self.ctx.theme == 'dark' else .15)
        glass.setColorAt(1, ink)
        painter.setBrush(glass)
        rim = QColor(colors['accent'])
        rim.setAlpha(90 if self.ctx.theme == 'dark' else 76)
        painter.setPen(QPen(rim, .9))
        painter.drawEllipse(medal)
        painter.setBrush(Qt.NoBrush)
        rim_light = QLinearGradient(medal.topLeft(), medal.bottomRight())
        rim_light.setColorAt(0, QColor(255, 255, 255, 95 if self.ctx.theme == 'dark' else 195))
        rim_light.setColorAt(.58, QColor(255, 255, 255, 0))
        rim_light.setColorAt(1, QColor(255, 255, 255, 15 if self.ctx.theme == 'dark' else 75))
        painter.setPen(QPen(QBrush(rim_light), 1))
        painter.drawEllipse(medal.adjusted(2, 2, -2, -2))
        tick = QColor(colors['accent'])
        tick.setAlpha(100 if self.ctx.theme == 'dark' else 85)
        painter.setPen(QPen(tick, .8, Qt.SolidLine, Qt.RoundCap))
        for index in range(13):
            angle = (-114 + index * 19) * pi / 180
            direction = QPointF(cos(angle), sin(angle))
            length = 6 if index % 3 == 0 else 3
            painter.drawLine(center + direction * (radius + 5),
                             center + direction * (radius + 5 + length))
        facet = QPainterPath(QPointF(width - 68, 2))
        facet.lineTo(width - 2, 2)
        facet.lineTo(width - 2, 53)
        facet.closeSubpath()
        facet_color = QColor(colors['accent'])
        facet_color.setAlpha(27 if self.ctx.theme == 'dark' else 22)
        painter.setPen(Qt.NoPen)
        painter.setBrush(facet_color)
        painter.drawPath(facet)
        edge = QColor(colors['light'])
        edge.setAlpha(80 if self.ctx.theme == 'dark' else 170)
        painter.setPen(QPen(edge, .8))
        painter.drawLine(QPointF(width - 68, 2), QPointF(width - 2, 53))
        painter.restore()

    def _arrival_area(self):
        return self.rect().adjusted(int(self.width() * .64), 0, 0, 0)

    def _advance_arrival(self, value):
        self._arrival = float(value) if motion_enabled() and self.isVisible() else 1.0
        self.update(self._arrival_area())

    def _reset_motion(self):
        super()._reset_motion()
        if hasattr(self, 'arrival_animation'):
            self.arrival_animation.stop()
        self._arrival = 1.0
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.arrival_animation.stop()
        if motion_enabled():
            self.arrival_animation.start()
        else:
            self._arrival = 1.0

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._arrival >= 1 or not motion_enabled():
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setClipPath(self._outline())
            painter.setClipRect(self._arrival_area(), Qt.IntersectClip)
            x = self.width() * (.64 + .46 * self._arrival)
            stripe = QLinearGradient(x - 40, 0, x + 40, 0)
            stripe.setColorAt(0, QColor(255, 255, 255, 0))
            stripe.setColorAt(.5, QColor(255, 255, 255, int(28 * (1 - self._arrival))))
            stripe.setColorAt(1, QColor(255, 255, 255, 0))
            painter.fillRect(self._arrival_area(), stripe)
            for fraction, delay in ((.81, .06), (.96, .26)):
                phase = max(0., min(1., (self._arrival - delay) / .64))
                light = sin(pi * phase) ** 6
                radius = 4.5 * light
                ink = QColor('#FFF2D8')
                ink.setAlphaF(.80 * light)
                painter.setPen(QPen(ink, .9, Qt.SolidLine, Qt.RoundCap))
                center = QPointF(self.width() * fraction, 24 + (self.height() - 56) * (1 - fraction))
                painter.drawLine(center + QPointF(-radius, 0), center + QPointF(radius, 0))
                painter.drawLine(center + QPointF(0, -radius), center + QPointF(0, radius))
        finally:
            painter.end()


def accent_stat_card(ctx, kind, title, value, subtitle=''):
    result = AccentCard(ctx, kind)
    result.body.setContentsMargins(22, 20, 22, 20)
    heading = QLabel(title, objectName='colorEyebrow')
    heading.setTextFormat(Qt.PlainText)
    heading.setWordWrap(True)
    result.value = QLabel(str(value), objectName='statValue')
    result.value.setTextFormat(Qt.PlainText)
    result.caption = QLabel(subtitle, objectName='muted')
    result.caption.setTextFormat(Qt.PlainText)
    result.caption.setWordWrap(True)
    result.body.addWidget(heading)
    result.body.addWidget(result.value)
    if subtitle:
        result.body.addWidget(result.caption)
    return result
