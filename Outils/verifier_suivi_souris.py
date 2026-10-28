"""Exercise native descendant hover on all pages with disposable demonstration data."""
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources' / 'PrepaPilot'))

from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext
from mpsi_desktop.theme import apply_theme, palette_for
from mpsi_desktop.window import MainWindow
from verifier_finitions import seed


def settle(card):
    for animation in card.findChildren(QAbstractAnimation):
        if animation.duration() > 0:
            animation.setCurrentTime(animation.duration())


def surface(window, key, axis='work'):
    page = window.pages[key]
    if key == 'progression':
        return page.metric_cards[axis], page.metric_titles[axis], page.figures[axis]
    return page.hero, page.hero.title_label, page.hero.figure


def follow(window, key, fraction, axis='work'):
    window.navigate(key, animate=False)
    card, title, figure = surface(window, key, axis)
    window.wrappers[key].ensureWidgetVisible(card, 0, 15)
    QApplication.processEvents()
    point = QPoint(round(max(2, min(title.width() - 2, title.width() * fraction))), max(2, title.height() // 2))
    QTest.mouseMove(title, point)
    QApplication.processEvents()
    settle(card)
    return card, title.mapTo(card, point), figure


def add_pointer(frame, point):
    image = QPixmap(frame)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#173F62'), 1.4))
    painter.setBrush(QColor(255, 255, 255, 220))
    painter.drawEllipse(point, 4, 4)
    painter.end()
    return image


def make_sheet(rows, output, theme):
    width, height, caption = 560, 190, 26
    sheet = QPixmap(width * 2, len(rows) * (height + caption))
    colors = palette_for(theme)
    sheet.fill(QColor(colors['bg']))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setFont(QFont('Segoe UI', 10))
    painter.setPen(QColor(colors['text']))
    for row, (key, left, right) in enumerate(rows):
        y = row * (height + caption)
        for column, (label, image) in enumerate((('Pointeur à gauche', left), ('Pointeur à droite', right))):
            x = column * width
            painter.drawText(QRectF(x + 12, y, width - 24, caption), Qt.AlignVCenter, f'{key} · {label}')
            target = QRectF(x + 8, y + caption, width - 16, height - 8)
            scale = min(target.width() / image.width(), target.height() / image.height())
            target.setSize(image.size().toSizeF() * scale)
            painter.drawPixmap(target, image, QRectF(image.rect()))
    painter.end()
    name = f'suivi-sept-pages-{theme}.png'
    sheet.save(str(output / name))
    return name


def make_gif(window, output):
    from PIL import Image
    window.ctx.set_theme('light')
    apply_theme(QApplication.instance(), 'light')
    window.resize(1360, 900)
    QApplication.processEvents()
    frames = []
    path = (.12, .22, .34, .46, .60, .74, .86, .92, .86, .74, .60, .46, .34, .22, .12, .08)
    for fraction in path:
        samples = []
        for key, axis in (('documents', 'work'), ('progression', 'work'), ('progression', 'sleep')):
            card, point, _ = follow(window, key, fraction, axis)
            samples.append(add_pointer(card.grab(), point))
        canvas = QPixmap(1120, 470)
        canvas.fill(QColor(palette_for('light')['bg']))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setFont(QFont('Segoe UI', 11))
        painter.setPen(QColor('#25343D'))
        painter.drawText(QRectF(16, 0, 1088, 30), Qt.AlignVCenter, 'Documents · déplacement sur le texte')
        painter.drawPixmap(QRectF(0, 30, 1120, 160), samples[0], QRectF(samples[0].rect()))
        for index, label in enumerate(('Progression · Travail', 'Progression · Sommeil')):
            painter.drawText(QRectF(index * 560 + 16, 195, 528, 30), Qt.AlignVCenter, label)
            painter.drawPixmap(QRectF(index * 560, 225, 560, 245), samples[index + 1], QRectF(samples[index + 1].rect()))
        painter.end()
        image = canvas.toImage().convertToFormat(QImage.Format_RGBA8888)
        frames.append(Image.frombytes('RGBA', (image.width(), image.height()), bytes(image.constBits())).convert('RGB'))
    name = 'suivi-sur-les-textes.gif'
    frames[0].save(output / name, save_all=True, append_images=frames[1:], duration=125, disposal=2, optimize=False)
    return name


def main():
    output = ROOT / '.local' / 'Verification' / 'Suivi-souris-2.26'
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
    app.setFont(QFont('Segoe UI', 10))
    errors, captures, tracking, colors = [], [], [], {}
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, value, trace: errors.append(dict(type=kind.__name__, message=str(value)))
    try:
        with tempfile.TemporaryDirectory(prefix='suivi-', dir=output) as temporary:
            ctx = AppContext(Path(temporary) / 'data')
            seed(ctx, Path(temporary))
            ctx.db.set_setting('desktop_reduced_motion', False)
            app.setProperty('reducedMotion', False)
            window = MainWindow(ctx, show_welcome=False)
            window.show()
            for theme in ('light', 'dark'):
                ctx.set_theme(theme)
                apply_theme(app, theme)
                rows = []
                for width, height in ((1360, 900), (1024, 680)):
                    window.resize(width, height)
                    app.processEvents()
                    for key in window.pages:
                        card, point, figure = follow(window, key, .15)
                        left = add_pointer(card.grab(), point)
                        left_light = (card._light.x(), card._light.y())
                        left_target = (figure._target.x(), figure._target.y())
                        style = card.styleSheet()
                        bounds = card.geometry()
                        card, point, figure = follow(window, key, .85)
                        right = add_pointer(card.grab(), point)
                        if card._light.x() <= left_light[0] or figure._target.x() <= left_target[0]:
                            errors.append(dict(type='PointerNotFollowing', message=f'{key}/{theme}/{width}'))
                        if card.geometry() != bounds:
                            errors.append(dict(type='CardMoved', message=f'{key}/{theme}/{width}'))
                        if card.styleSheet() != style:
                            errors.append(dict(type='CardColorChanged', message=f'{key}/{theme}/{width}'))
                        wrapper = window.wrappers[key]
                        if window.pages[key].width() > wrapper.viewport().width() or wrapper.horizontalScrollBar().maximum():
                            errors.append(dict(type='PageOverflow', message=f'{key}/{theme}/{width}'))
                        tracking.append(dict(page=key, theme=theme, width=width, light_left=left_light,
                                             light_right=(card._light.x(), card._light.y()),
                                             parallax_left=left_target, parallax_right=(figure._target.x(), figure._target.y())))
                        if width == 1360:
                            rows.append((key, left, right))
                        if key in ('documents', 'progression'):
                            name = f'{key}-{theme}-{width}.png'
                            window.grab().save(str(output / name))
                            captures.append(name)
                    progression = window.pages['progression']
                    colors[theme] = dict(hero=progression.hero_card.styleSheet(),
                        metrics={axis: metric.styleSheet() for axis, metric in progression.metric_cards.items()})
                captures.append(make_sheet(rows, output, theme))
            captures.append(make_gif(window, output))
            window.navigate('documents', animate=False)
            ctx.db.set_setting('desktop_reduced_motion', True)
            window.motion_updated()
            card, _, figure = follow(window, 'documents', .75)
            if figure._offset.x() or figure._offset.y() or any(animation.state() != QAbstractAnimation.Stopped
                    for animation in card.findChildren(QAbstractAnimation)):
                errors.append(dict(type='ReducedMotion', message='Pointer effects restarted'))
            window.close()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
            ctx.close()
    finally:
        sys.excepthook = previous_hook
    report = dict(captures=captures, errors=errors, tracking=tracking, progression_colors=colors)
    (output / 'rapport.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(output=str(output), captures=len(captures), pointer_checks=len(tracking), errors=errors), ensure_ascii=False))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
