"""Passive navigation previews painted inside the existing application window."""
from .i18n import tr
from math import sin, pi, sqrt

from PySide6.QtCore import QObject, QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QCursor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient, QRegion
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from .theme import palette_for
from .page_figures import page_palette


PAGE_COPY = {
    'home': ('Aujourd’hui', 'Ta journée et tes prochaines étapes.'),
    'time': ('Gestion du temps', 'Ton planning et le temps que tu y consacres.'),
    'progression': ('Progression', 'Tes bilans, ton équilibre et tes objectifs personnels.'),
    'notes': ('Notes', 'Tes évaluations, tes moyennes et tes progrès.'),
    'documents': ('Documents', 'Tes cours et tes fichiers, au même endroit.'),
    'memory': ('Mes repères', 'Tes idées et ce que tu veux garder en tête.'),
    'settings': ('Réglages', 'Ton profil, tes préférences et tes données.'),
}

PAGE_COLORS = {key: page_palette(key)['accent'] for key in PAGE_COPY}


class _PreviewCard(QWidget):
    """No popup window, graphics effect or interactive child can steal focus."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('NavigationPreviewCard')
        self.setFixedSize(320, 246)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(False)
        self.thumbnail = QPixmap()
        self.title = ''
        self.description = ''
        self.accent = PAGE_COLORS['home']
        self.theme = 'light'
        self.progress = 1.0
        self._surface = QPixmap()
        self._surface_key = None
        self._glint = QPixmap()
        self.hide()

    def set_progress(self, value):
        self.progress = float(value)
        self.update()

    def paintEvent(self, event):
        dpr = self.devicePixelRatioF()
        key = (self.thumbnail.cacheKey(), self.title, self.description, self.theme, self.accent,
               self.width(), self.height(), dpr, self.font().key())
        if key != self._surface_key:
            self._surface = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
            self._surface.setDevicePixelRatio(dpr)
            self._surface.fill(Qt.transparent)
            self._paint_surface(QPainter(self._surface))
            self._surface_key = key
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(self.progress)
        # Transform only the cached card; live widgets and their geometry stay
        # untouched, and the entire entrance finishes after a single pass.
        painter.translate(self.width() / 2, 154 + 7 * (1 - self.progress))
        scale = 0.97 + 0.03 * self.progress
        painter.scale(scale, scale)
        painter.translate(-self.width() / 2, -154)
        painter.drawPixmap(0, 0, self._surface)
        if 0 < self.progress < 1 and not self._glint.isNull():
            painter.setClipRect(QRectF(19, 19, 282, 130))
            painter.setOpacity(0.28 * sin(pi * self.progress))
            painter.drawPixmap(round(-76 + 410 * self.progress), 19, self._glint)
        painter.end()

    def _paint_surface(self, painter):
        # The appearance is static during its fade; compose shadow, text and
        # thumbnail once instead of repainting them at every animation tick.
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        colors = palette_for(self.theme)
        accent = QColor(self.accent)
        card = QRectF(7, 7, self.width() - 14, self.height() - 14)
        painter.setPen(Qt.NoPen)
        for spread in range(6, 0, -1):
            painter.setBrush(QColor(0, 0, 0, 4 if self.theme == 'light' else 9))
            painter.drawRoundedRect(card.adjusted(-spread, -spread + 2, spread, spread + 2), 18 + spread, 18 + spread)
        # A fine tinted edge gives the card depth without an expensive blur.
        edge = QColor(accent)
        edge.setAlpha(42 if self.theme == 'light' else 72)
        painter.setBrush(edge)
        painter.drawRoundedRect(card.translated(0, 3), 18, 18)
        painter.setPen(QPen(QColor(colors['border']), 1))
        painter.setBrush(QColor(colors['surface']))
        painter.drawRoundedRect(card, 18, 18)
        wash = QLinearGradient(card.topLeft(), card.bottomRight())
        tint = QColor(accent)
        tint.setAlpha(18 if self.theme == 'light' else 28)
        wash.setColorAt(0, QColor(255, 255, 255, 0))
        wash.setColorAt(1, tint)
        painter.setPen(Qt.NoPen)
        painter.setBrush(wash)
        painter.drawRoundedRect(card.adjusted(1, 1, -1, -1), 17, 17)

        frame = QRectF(18, 18, 284, 132)
        clip = QPainterPath()
        clip.addRoundedRect(frame, 10, 10)
        painter.save()
        painter.setClipPath(clip)
        painter.fillRect(frame, QColor(colors['bg']))
        if not self.thumbnail.isNull():
            painter.drawPixmap(frame, self.thumbnail, QRectF(self.thumbnail.rect()))
        painter.restore()
        painter.setPen(QPen(QColor(colors['border']), 0.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame, 10, 10)

        # One glossy bead echoes the larger page objects, drawn into the same
        # cached surface as the miniature and its text.
        sphere = QRectF(272, 162, 26, 26)
        bead = QRadialGradient(sphere.left() + 8, sphere.top() + 6, 26)
        bead.setColorAt(0, QColor('#FFFFFF'))
        bead.setColorAt(0.36, accent.lighter(150))
        bead.setColorAt(1, accent.darker(130))
        painter.setPen(Qt.NoPen)
        painter.setBrush(bead)
        painter.drawEllipse(sphere)
        painter.setPen(QPen(QColor(255, 255, 255, 210), 1.4))
        painter.drawLine(QPoint(281, 179), QPoint(289, 171))
        painter.drawLine(QPoint(283, 171), QPoint(289, 171))
        painter.drawLine(QPoint(289, 171), QPoint(289, 177))

        font = QFont(self.font())
        font.setPixelSize(16)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(colors['text']))
        painter.drawText(QRectF(20, 160, 244, 24), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        font.setPixelSize(12)
        font.setWeight(QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor(colors['muted']))
        description = painter.fontMetrics().elidedText(self.description, Qt.ElideRight, 280)
        painter.drawText(QRectF(20, 189, 280, 18), Qt.AlignLeft | Qt.AlignVCenter, description)
        font.setPixelSize(11)
        font.setWeight(QFont.Medium)
        painter.setFont(font)
        painter.setPen(QColor(colors['accent']))
        painter.drawText(QRectF(20, 215, 280, 16), Qt.AlignLeft | Qt.AlignVCenter, tr('Cliquer pour ouvrir  →'))
        painter.end()
        self._glint = QPixmap(76, 130)
        self._glint.fill(Qt.transparent)
        light = QPainter(self._glint)
        shine = QLinearGradient(0, 0, 76, 30)
        shine.setColorAt(0, QColor(255, 255, 255, 0))
        shine.setColorAt(0.5, QColor(255, 255, 255, 210))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        light.fillRect(self._glint.rect(), shine)
        light.end()


class NavigationPreview(QObject):
    """Hover an inactive navigation button for 550 ms to inspect its live page.

    Captures only existing page widgets in their current geometry. It never calls
    refresh(), show(), resize(), setCurrentWidget(), or any database mutation on
    a page. The crop follows its stored scroll position without moving a scrollbar.
    """
    DELAY_MS = 550
    MAX_CAPTURE_PIXELS = 500_000

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.ctx = window.ctx
        self.popup = _PreviewCard(window.central)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(self.DELAY_MS)
        self.timer.timeout.connect(self._show_preview)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(230)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self.popup.set_progress)
        self._pending_key = None
        self._stopped = False
        self._cache = {}
        self._buttons = {button: key for key, (button, _) in window.nav.items()}
        self._signals = []
        for name in ('theme_changed', 'data_changed', 'data_replaced'):
            signal = getattr(self.ctx, name, None)
            if signal is not None:
                signal.connect(self.invalidate)
                self._signals.append(signal)
        self._app = QApplication.instance()
        self._app.installEventFilter(self)

    def dismiss(self, *_):
        self._pending_key = None
        self.timer.stop()
        self.animation.stop()
        self.popup.hide()
        self.popup.thumbnail = QPixmap()

    def invalidate(self, key=None):
        """Discard images after a mutation, or a page's editable/scroll state."""
        self.dismiss()
        if isinstance(key, str):
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    def shutdown(self):
        if self._stopped:
            return
        self._stopped = True
        self.invalidate()
        self.popup._surface = QPixmap()
        self.popup._surface_key = None
        self.popup._glint = QPixmap()
        self._app.removeEventFilter(self)
        for signal in self._signals:
            try:
                signal.disconnect(self.invalidate)
            except (RuntimeError, TypeError):
                pass
        self._signals.clear()

    def _schedule(self, key):
        self.dismiss()
        if self._stopped or key == self.window.current_key:
            return
        button = self.window.nav[key][0]
        if button.isEnabled() and button.isVisible() and self._app.activeModalWidget() is None:
            self._pending_key = key
            self.timer.start()

    def _thumbnail(self, key):
        page = self.window.pages.get(key)
        wrapper = self.window.wrappers.get(key)
        if page is None or wrapper is None or page.width() <= 0 or page.height() <= 0:
            return QPixmap()
        top = max(0, min(wrapper.verticalScrollBar().value(), page.height() - 1))
        height = min(page.height() - top, max(1, round(page.width() * 132 / 284)))
        # Rasterize below the full page resolution. Native editable text can
        # disappear when Qt renders below half scale; a small intermediate
        # surface preserves those glyphs before the final smooth downsample.
        dpr = min(2.0, self.popup.devicePixelRatioF())
        size = QSize(round(284 * dpr), round(132 * dpr))
        scale = max(0.5, size.width() / page.width())
        render_size = QSize(max(size.width(), round(page.width() * scale)),
                            max(size.height(), round(height * scale)))
        pixels = render_size.width() * render_size.height()
        if pixels > self.MAX_CAPTURE_PIXELS:
            shrink = sqrt(self.MAX_CAPTURE_PIXELS / pixels)
            render_size = QSize(max(1, int(render_size.width() * shrink)),
                                max(1, int(render_size.height() * shrink)))
        image = QPixmap(render_size)
        image.fill(QColor(palette_for(self.ctx.theme)['bg']))
        painter = QPainter(image)
        painter.scale(render_size.width() / page.width(), render_size.height() / height)
        page.render(painter, QPoint(), QRegion(QRect(0, top, page.width(), height)))
        painter.end()
        return image if render_size == size else image.scaled(size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def _cached_thumbnail(self, key):
        page = self.window.pages.get(key)
        wrapper = self.window.wrappers.get(key)
        if page is None or wrapper is None:
            return QPixmap()
        signature = (page.width(), page.height(), wrapper.verticalScrollBar().value(),
                     self.ctx.theme, self.popup.devicePixelRatioF(),
                     getattr(page, 'preview_revision', 0))
        cached = self._cache.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]
        image = self._thumbnail(key)
        if not image.isNull():
            # One small image per existing page; repeated hovering performs no
            # widget-tree rendering until data, live state, theme or geometry changes.
            self._cache[key] = (signature, image)
        return image

    def _show_preview(self):
        key = self._pending_key
        if self._stopped or key is None or key == self.window.current_key:
            return
        button = self.window.nav[key][0]
        if (not self.window.isVisible() or not self.window.isActiveWindow()
                or not button.isEnabled() or self._app.activeModalWidget() is not None
                or not button.rect().contains(button.mapFromGlobal(QCursor.pos()))):
            self.dismiss()
            return
        try:
            thumbnail = self._cached_thumbnail(key)
        except RuntimeError:
            self.dismiss()
            return
        if thumbnail.isNull() or self._pending_key != key:
            return
        self.popup.thumbnail = thumbnail
        self.popup.title, self.popup.description = PAGE_COPY.get(key, (button.text(), tr('Un aperçu de cette page.')))
        self.popup.title, self.popup.description = tr(self.popup.title), tr(self.popup.description)
        self.popup.accent = page_palette(key, self.ctx.theme)['accent']
        self.popup.theme = self.ctx.theme
        self.popup.setAccessibleName(tr("Aperçu : {title}. {description}", title=self.popup.title, description=self.popup.description))
        self._position(button)
        self.popup.set_progress(1 if self._app.property('reducedMotion') else 0)
        self.popup.show()
        self.popup.raise_()
        if not self._app.property('reducedMotion'):
            self.animation.setStartValue(0.0)
            self.animation.setEndValue(1.0)
            self.animation.start()

    def _position(self, button):
        bounds = self.window.central.rect()
        origin = button.mapTo(self.window.central, QPoint(0, 0))
        x = origin.x() + button.width() // 2 - self.popup.width() // 2
        y = origin.y() + button.height() + 5
        if y + self.popup.height() > bounds.bottom() - 7:
            y = origin.y() - self.popup.height() - 5
        x = max(8, min(x, bounds.width() - self.popup.width() - 8))
        y = max(8, min(y, bounds.height() - self.popup.height() - 8))
        self.popup.move(x, y)

    def eventFilter(self, watched, event):
        if self._stopped:
            return False
        kind = event.type()
        if watched is self._app and kind == QEvent.DynamicPropertyChange:
            preference = bytes(event.propertyName())
            if preference == b'reducedMotion' and self._app.property('reducedMotion'):
                self.animation.stop()
                self.popup.set_progress(1)
            elif preference == b'visualTheme':
                self.invalidate()
        if watched in self._buttons:
            if kind == QEvent.Enter:
                self._schedule(self._buttons[watched])
            elif kind == QEvent.Leave:
                self.dismiss()
            elif kind == QEvent.ToolTip:
                # Keep accessible tooltips as metadata, without stacking two tips.
                return True
        if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.KeyPress,
                    QEvent.ShortcutOverride, QEvent.Wheel, QEvent.TouchBegin):
            if isinstance(watched, QWidget) and watched.window() is self.window:
                self.dismiss()
        elif watched is self.window and kind in (QEvent.WindowDeactivate, QEvent.WindowBlocked,
                                                  QEvent.Close, QEvent.Hide, QEvent.Move, QEvent.Resize):
            self.invalidate() if kind == QEvent.Resize else self.dismiss()
        elif watched is self.window.central and kind == QEvent.Resize:
            self.invalidate()
        elif kind == QEvent.Show and isinstance(watched, QDialog) and watched.isModal():
            self.dismiss()
        return False
