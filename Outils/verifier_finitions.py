"""Render crafted controls, motion samples and comparable pages with fictional data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import date, timedelta

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources' / 'PrepaPilot'))

from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QEnterEvent, QFont, QFontDatabase, QImage, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from mpsi_desktop.context import AppContext
from mpsi_desktop.i18n import set_language
from mpsi_desktop.page_chrome import AccentCard, PageHero
from mpsi_desktop.progression import save_targets
from mpsi_desktop.study_profile import example_profile
from mpsi_desktop.theme import apply_theme, palette_for
from mpsi_desktop.widgets import button
from mpsi_desktop.window import MainWindow


def seed(ctx, temporary):
    subjects, timetable = example_profile('2026-09-28')
    ctx.db.save_setup(subjects, timetable)
    ctx.db.set_setting('desktop_name', 'Camille')
    ctx.db.set_setting('desktop_program', 'MPSI · Semestre 1')
    ctx.db.set_setting('desktop_welcomed', True)
    ctx.db.set_setting('desktop_reduced_motion', True)
    folder = ctx.db.create_document_folder('Analyse · Suites et limites')
    source = temporary / 'Suites et limites.txt'
    source.write_text('Cours fictif de contrôle : suites, limites et récurrence.', encoding='utf-8')
    ctx.db.import_document(source, 'maths', 'cours', folder_id=folder)
    for offset, score in ((3, 14), (10, 15.5), (17, 12)):
        ctx.db.add_grade('maths', 'Devoir surveillé', score, 20, (date.today() - timedelta(days=offset)).isoformat(), 'Analyse')
    for offset in range(1, 9):
        stamp = (date.today() - timedelta(days=offset)).isoformat()
        ctx.db.add_time_entry('sommeil', stamp + 'T00:00', stamp + 'T07:30', 'Nuit de démonstration')
        ctx.db.add_time_entry('maths', stamp + 'T17:00', stamp + 'T18:30', 'Travail de démonstration')
    save_targets(ctx.db, dict(work=1200, sleep=3360, sport=150, rest=420))


def image_digest(widget):
    image = widget.grab().toImage()
    return hashlib.sha256(bytes(image.constBits())).hexdigest()


def color_coverage(path):
    """Describe colour coverage; this is evidence, never a UI acceptance score."""
    try:
        from PIL import Image
    except ImportError:
        return None
    with Image.open(path) as image:
        saturation = image.convert('RGB').convert('HSV').getchannel('S')
        histogram = saturation.histogram()
        pixels = image.width * image.height
    return dict(pixels=pixels,
                saturation_over_006_pct=round(sum(histogram[16:]) * 100 / pixels, 3),
                saturation_over_015_pct=round(sum(histogram[39:]) * 100 / pixels, 3),
                saturation_over_065_pct=round(sum(histogram[166:]) * 100 / pixels, 3),
                mean_saturation=round(sum(index * count for index, count in enumerate(histogram)) / (255 * pixels), 4))


def compare_captures(before, after):
    measurements, sheets = [], []
    output = after.parent / 'Comparaisons'
    output.mkdir(parents=True, exist_ok=True)
    for name in ('home-fr-light-1360.png', 'documents-fr-light-1360.png', 'progression-fr-light-1360.png',
                 'home-fr-dark-1360.png', 'documents-fr-dark-1360.png', 'progression-fr-dark-1360.png',
                 'home-fr-light-1024.png', 'documents-fr-light-1024.png'):
        earlier, current = before / name, after / name
        if not earlier.is_file() or not current.is_file():
            continue
        previous, present = color_coverage(earlier), color_coverage(current)
        if previous is not None and present is not None:
            measurements.append(dict(capture=name, before=previous, after=present,
                coverage_change_percentage_points=round(present['saturation_over_015_pct'] - previous['saturation_over_015_pct'], 3),
                pastel_coverage_change_percentage_points=round(present['saturation_over_006_pct'] - previous['saturation_over_006_pct'], 3)))
        if '-light-1360' not in name:
            continue
        sheet = QPixmap(1360, 486)
        sheet.fill(QColor('#F3F1E9'))
        painter = QPainter(sheet)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setFont(QFont('Segoe UI', 11))
        painter.setPen(QColor('#25333A'))
        for index, (caption, source) in enumerate((('Avant · 2.22', earlier), ('Après · 2.23', current))):
            x = index * 680
            painter.drawText(QRectF(x + 16, 0, 648, 36), Qt.AlignVCenter, caption)
            frame = QPixmap(str(source))
            painter.drawPixmap(QRectF(x, 36, 680, 450), frame, QRectF(frame.rect()))
        painter.end()
        target = output / ('comparaison-' + name)
        if sheet.save(str(target)):
            sheets.append(str(target))
    result = dict(method='HSV saturation over 0.15 and 0.65 on the complete screenshot; 0.06 also describes pale tinted areas. Descriptive only, no automatic quality threshold.',
                  before=str(before), after=str(after), measurements=measurements, sheets=sheets)
    (output / 'couverture-couleur.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def seek_animations(widget, fraction):
    for animation in widget.findChildren(QAbstractAnimation):
        if animation.state() == QAbstractAnimation.Running and animation.duration() > 0:
            animation.pause()
        if animation.state() == QAbstractAnimation.Paused:
            animation.setCurrentTime(round(animation.duration() * fraction))


def settle(widget):
    for animation in widget.findChildren(QAbstractAnimation):
        if animation.duration() > 0:
            animation.setCurrentTime(animation.duration())
        animation.stop()
    for child in (widget, *widget.findChildren(QWidget)):
        reset = getattr(child, '_reset_motion', None)
        if reset is not None:
            reset()


def save_motion_preview(app, host, hero, card, primary, output):
    """A finite two-second UI recording, sampled without real-time waiting."""
    try:
        from PIL import Image
    except ImportError:
        return None
    frames = []

    def sample():
        image = host.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
        frames.append(Image.frombytes('RGBA', (image.width(), image.height()), bytes(image.constBits())).convert('RGB'))

    settle(host)
    sample()
    point = QPointF(primary.width() * .72, primary.height() * .28)
    for target in (primary, card):
        app.sendEvent(target, QEnterEvent(point, point, point))
    hero.arrival_animation.start()
    for fraction in (0, .15, .3, .45, .6, .8, .98):
        seek_animations(host, fraction)
        sample()
    QTest.mousePress(primary, Qt.LeftButton, pos=primary.rect().center())
    for fraction in (0, .25, .65):
        seek_animations(host, fraction)
        sample()
    QTest.mouseRelease(primary, Qt.LeftButton, pos=primary.rect().center())
    for fraction in (0, .2, .6, .98):
        seek_animations(host, fraction)
        sample()
    app.sendEvent(primary, QEvent(QEvent.Leave))
    app.sendEvent(card, QEvent(QEvent.Leave))
    settle(host)
    sample()
    name = 'apercu-mouvements.gif'
    # Omitting the GIF loop extension makes this recording play only once.
    frames[0].save(output / name, save_all=True, append_images=frames[1:],
                   duration=125, disposal=2, optimize=False)
    return name


def motion_sheet(app, ctx, output, theme, errors):
    host = QWidget()
    host.setObjectName('FinishingWorkbench')
    host.resize(760, 500)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(18)
    hero = PageHero(ctx, 'home', 'PRÉPAPILOT / FINITIONS', 'Une matière qui répond.',
                    'Reflets, lumière et profondeur : six instants d’une même interaction.')
    layout.addWidget(hero)
    card = AccentCard(ctx, 'documents')
    card.body.addWidget(QLabel('Commandes · surfaces et gestes', objectName='sectionTitle'))
    actions = QHBoxLayout()
    controls = [button('Commencer', primary=True), button('Enregistrer'), button('Supprimer', danger=True)]
    for control in controls:
        actions.addWidget(control)
    card.body.addLayout(actions)
    card.body.addWidget(QLabel('Le texte reste net et la zone de clic conserve sa position.', objectName='muted'))
    layout.addWidget(card)
    layout.addStretch()
    host.show()
    app.processEvents()
    for animation in host.findChildren(QAbstractAnimation):
        if animation.loopCount() != 1:
            errors.append(dict(type='RepeatedMotion', message=theme + ':' + type(animation).__name__))
    ctx.db.set_setting('desktop_reduced_motion', False)
    app.setProperty('reducedMotion', False)
    settle(host)
    primary = controls[0]
    bounds = primary.geometry()
    clicked = []
    primary.clicked.connect(lambda: clicked.append(True))
    frames, fingerprints = [], []

    def snapshot(caption):
        frames.append((caption, host.grab()))
        fingerprints.append(image_digest(primary))
        if primary.geometry() != bounds or not primary.hitButton(primary.rect().center()):
            errors.append(dict(type='ButtonGeometry', message=theme + '/' + caption))

    snapshot('01 · Repos')
    point = QPointF(primary.width() * .72, primary.height() * .28)
    for target in (primary, card):
        app.sendEvent(target, QEnterEvent(point, point, point))
    seek_animations(host, .24)
    snapshot('02 · Survol')
    seek_animations(host, .58)
    snapshot('03 · Reflet')
    QTest.mousePress(primary, Qt.LeftButton, pos=primary.rect().center())
    seek_animations(host, .32)
    snapshot('04 · Pression')
    QTest.mouseRelease(primary, Qt.LeftButton, pos=primary.rect().center())
    seek_animations(host, .62)
    snapshot('05 · Relâchement')
    app.sendEvent(primary, QEvent(QEvent.Leave))
    app.sendEvent(card, QEvent(QEvent.Leave))
    QTest.mouseMove(host, QPoint(4, 4))
    app.processEvents()
    # Let the final tick finish normally: do not mask a persistent loop by
    # forcibly stopping it before checking the resting state.
    for animation in host.findChildren(QAbstractAnimation):
        if animation.state() == QAbstractAnimation.Paused:
            animation.resume()
        if animation.state() == QAbstractAnimation.Running and animation.duration() > 0:
            animation.setCurrentTime(max(0, animation.duration() - 1))
    QTest.qWait(40)
    idle = [f'{type(animation.parent()).__name__}/{animation.parent().objectName()}:'
            f'{animation.currentTime()}/{animation.duration()}:{animation.state().name}'
            for animation in host.findChildren(QAbstractAnimation)
            if animation.state() != QAbstractAnimation.Stopped]
    if idle:
        errors.append(dict(type='IdleMotion', message=theme + ':' + ','.join(idle)))
    snapshot('06 · Retour au repos')
    if len(set(fingerprints[:5])) < 3:
        errors.append(dict(type='MotionInvisible', message=theme))
    if clicked != [True]:
        errors.append(dict(type='ButtonActivation', message=theme + ':' + str(clicked)))
    preview = save_motion_preview(app, host, hero, card, primary, output) if theme == 'light' else None

    # Reducing animation must stop even effects which are halfway through a gesture.
    app.sendEvent(primary, QEnterEvent(point, point, point))
    seek_animations(host, .3)
    app.setProperty('reducedMotion', True)
    running = [type(animation).__name__ for animation in host.findChildren(QAbstractAnimation)
               if animation.state() != QAbstractAnimation.Stopped]
    if running:
        errors.append(dict(type='ReducedMotion', message=theme + ':' + str(running)))
    host.hide()
    if any(animation.state() != QAbstractAnimation.Stopped for animation in host.findChildren(QAbstractAnimation)):
        errors.append(dict(type='HiddenMotion', message=theme))

    width, image_height, caption_height = 380, 250, 34
    sheet = QPixmap(width * 3, (image_height + caption_height) * 2)
    colors = palette_for(theme)
    sheet.fill(QColor(colors['bg']))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setFont(QFont('Segoe UI', 10))
    painter.setPen(QColor(colors['text']))
    for index, (caption, frame) in enumerate(frames):
        x, y = (index % 3) * width, (index // 3) * (image_height + caption_height)
        painter.drawText(QRectF(x + 12, y, width - 24, caption_height), Qt.AlignVCenter, caption)
        painter.drawPixmap(QRectF(x, y + caption_height, width, image_height), frame, QRectF(frame.rect()))
    painter.end()
    name = f'mouvements-{theme}.png'
    if not sheet.save(str(output / name)):
        errors.append(dict(type='Capture', message=name))
    host.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    ctx.db.set_setting('desktop_reduced_motion', True)
    return name, fingerprints, preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.local' / 'Verification' / 'Finitions')
    parser.add_argument('--compare-with', type=Path)
    parser.add_argument('--pages', nargs='+', choices=('home', 'documents', 'progression', 'notes'),
                        default=('home', 'documents', 'progression'))
    parser.add_argument('--notes-detail', action='store_true', help='Ajouter Notes en français à 1360 px, dans les deux thèmes.')
    options = parser.parse_args()
    output = options.output_dir.expanduser()
    if not output.is_absolute():
        output = ROOT / output
    output = output.resolve()
    if not output.is_relative_to(ROOT):
        parser.error('Les captures doivent rester dans le dossier du projet.')
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)
    for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf', 'seguiemj.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
    app.setFont(QFont('Segoe UI', 10))
    output.mkdir(parents=True, exist_ok=True)
    errors, captures, timelines = [], [], {}
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, error, traceback: errors.append(dict(type=kind.__name__, message=str(error)))
    try:
        for locale in ('fr', 'en'):
            with tempfile.TemporaryDirectory(prefix='finitions-', dir=output) as temporary:
                ctx = AppContext(Path(temporary) / 'data')
                seed(ctx, Path(temporary))
                ctx.db.set_setting('desktop_language', locale)
                ctx.language = locale
                set_language(locale)
                app.setProperty('reducedMotion', True)
                window = MainWindow(ctx, show_welcome=False)
                window.show()
                for theme in ('light', 'dark'):
                    ctx.set_theme(theme)
                    apply_theme(app, theme)
                    for width, height in ((1024, 680), (1360, 900)):
                        window.resize(width, height)
                        pages = list(options.pages)
                        if options.notes_detail and locale == 'fr' and width == 1360 and 'notes' not in pages:
                            pages.append('notes')
                        for key in pages:
                            window.navigate(key, animate=False)
                            app.processEvents()
                            wrapper, page = window.wrappers[key], window.pages[key]
                            wrapper.verticalScrollBar().setValue(0)
                            if page.width() > wrapper.viewport().width() or wrapper.horizontalScrollBar().maximum():
                                errors.append(dict(type='LayoutOverflow', message=f'{locale}/{theme}/{width}/{key}'))
                            hero = getattr(page, 'hero', None)
                            if hero is not None:
                                for text in (hero.title_label, hero.subtitle_label):
                                    if text.heightForWidth(text.width()) > text.height():
                                        errors.append(dict(type='HeroTextClipped', message=f'{locale}/{theme}/{width}/{key}'))
                            name = f'{key}-{locale}-{theme}-{width}.png'
                            if not window.grab().save(str(output / name)):
                                errors.append(dict(type='Capture', message=name))
                            captures.append(name)
                    if locale == 'fr':
                        name, fingerprints, preview = motion_sheet(app, ctx, output, theme, errors)
                        captures.append(name)
                        if preview:
                            captures.append(preview)
                        timelines[theme] = fingerprints
                window.close()
                window.deleteLater()
                app.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
                ctx.close()
    finally:
        sys.excepthook = previous_hook
        set_language('fr')
    comparison = compare_captures(options.compare_with.resolve(), output) if options.compare_with else None
    report = dict(captures=captures, timelines=timelines, errors=errors, comparison=comparison)
    (output / 'rapport.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(output=str(output), captures=len(captures), errors=errors), ensure_ascii=False))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
