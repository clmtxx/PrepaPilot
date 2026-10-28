"""Verify real page navigation, snapshots and preserved study state with demo data."""
import argparse
from copy import deepcopy
from datetime import date, datetime, time as daytime, timedelta
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources' / 'PrepaPilot'))

from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QEnterEvent, QFont, QFontDatabase, QImage, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext
from mpsi_desktop.focus_session import FocusSession
from mpsi_desktop.i18n import set_language
from mpsi_desktop.theme import apply_theme
from mpsi_desktop.window import MainWindow
from verifier_finitions import seed


def png(widget, output, name, errors):
    if not widget.grab().save(str(output / name)):
        errors.append(dict(type='Capture', message=name))
    return name


def set_motion(window, allowed):
    window.ctx.db.set_setting('desktop_reduced_motion', not allowed)
    window.motion_updated()


def finish(window):
    window.transition.finish()


def trigger(window, target, timings, captures):
    """Use the actual navigation button; measure only this machine and process."""
    layer = window.transition
    original = layer.capture

    def measured(widget):
        start = time.perf_counter()
        image = original(widget)
        captures.append(dict(milliseconds=round((time.perf_counter() - start) * 1000, 3),
                             pixels=image.width() * image.height(), width=image.width(), height=image.height()))
        return image

    start = time.perf_counter()
    with patch.object(layer, 'capture', side_effect=measured):
        window.nav[target][0].click()
    timings.append(round((time.perf_counter() - start) * 1000, 3))
    if layer.animation.state() == QAbstractAnimation.Running:
        layer.animation.pause()


def route_frames(window, source, target, stamp, timings, captures, errors):
    window.navigate(source, animate=False)
    window.wrappers[source].verticalScrollBar().setValue(0)
    window.wrappers[target].verticalScrollBar().setValue(0)
    QApplication.processEvents()
    stack_bounds = window.stack.geometry()
    button_bounds = {key: value[0].geometry() for key, value in window.nav.items()}
    trigger(window, target, timings, captures)
    layer = window.transition
    if window.current_key != target or not layer.isVisible():
        errors.append(dict(type='TransitionMissing', message=stamp))
    frames = []
    # These are visual progress samples. The GIF below samples animation time
    # instead, preserving the real easing used for an ordinary page change.
    with patch.object(layer, 'capture', side_effect=AssertionError('Snapshot recaptured during painting')):
        for progress in (0, .2, .5, .8, 1):
            layer.advance(progress)
            frames.append(window.grab())
            if window.stack.geometry() != stack_bounds:
                errors.append(dict(type='LiveStackMoved', message=stamp))
            if any(window.nav[key][0].geometry() != bounds for key, bounds in button_bounds.items()):
                errors.append(dict(type='NavigationMoved', message=stamp))
    layout = layer.frame_layout(0) if hasattr(layer, 'frame_layout') else {}
    distance = layout.get('distance')
    if distance is not None and not 80 <= abs(distance) <= 200:
        errors.append(dict(type='MotionDistance', message=f'{stamp}:{distance}'))
    duration = layer.animation.duration()
    finish(window)
    if not layer.before.isNull() or not layer.after.isNull() or layer.isVisible():
        errors.append(dict(type='SnapshotNotReleased', message=stamp))
    return frames, dict(duration_ms=duration, direction=layer.direction, distance=distance)


def frame_sheet(routes, output, stamp, errors):
    width, caption, image_height = 340, 30, 225
    sheet = QPixmap(width * 5, (caption + image_height) * len(routes))
    sheet.fill(QColor('#ECEFEF'))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setPen(QColor('#23343B'))
    painter.setFont(QFont('Segoe UI', 9))
    for row, (name, frames) in enumerate(routes):
        y = row * (caption + image_height)
        for column, (progress, frame) in enumerate(zip((0, .2, .5, .8, 1), frames)):
            x = column * width
            painter.drawText(QRectF(x + 10, y, width - 20, caption), Qt.AlignVCenter, f'{name} · {progress:g}')
            painter.drawPixmap(QRectF(x, y + caption, width, image_height), frame, QRectF(frame.rect()))
    painter.end()
    name = f'etapes-{stamp}.png'
    if not sheet.save(str(output / name)):
        errors.append(dict(type='Capture', message=name))
    return name


def navigation_gif(window, output, timings, captures, errors):
    from PIL import Image
    frames, durations = [], []

    def sample(duration):
        image = window.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
        source = Image.frombytes('RGBA', (image.width(), image.height()), bytes(image.constBits())).convert('RGB')
        frames.append(source.resize((960, round(image.height() * 960 / image.width())), Image.Resampling.LANCZOS))
        durations.append(duration)

    window.navigate('home', animate=False)
    for key in ('home', 'notes', 'documents'):
        window.wrappers[key].verticalScrollBar().setValue(0)
    QApplication.processEvents()
    sample(400)
    for target in ('notes', 'documents', 'home'):
        trigger(window, target, timings, captures)
        layer = window.transition
        if not layer.isVisible():
            errors.append(dict(type='GIFTransitionMissing', message=target))
        duration = layer.animation.duration()
        for index in range(12):
            layer.animation.setCurrentTime(round(duration * index / 12))
            sample(max(20, round(duration / 12)))
        layer.animation.setCurrentTime(duration)
        finish(window)
        sample(360)
    name = 'navigation-reelle.gif'
    # No loop extension: this recorded demonstration plays once.
    frames[0].save(output / name, save_all=True, append_images=frames[1:],
                   duration=durations, disposal=2, optimize=False)
    return name


def behavior_checks(window, stamp, errors, timings, captures):
    ctx, layer = window.ctx, window.transition
    documents = window.pages['documents']
    window.navigate('home', animate=False)
    trigger(window, 'documents', timings, captures)
    documents.search.clear()
    QTest.mouseClick(documents.search, Qt.LeftButton, pos=documents.search.rect().center())
    QTest.keyClicks(documents.search, 'suite')
    if layer.isVisible() or documents.search.text() != 'suite' or not documents.search.hasFocus():
        errors.append(dict(type='ClickDuringTransition', message=stamp))
    documents.search.clear()
    documents.refresh()
    for target in ('notes', 'documents', 'home', 'notes', 'documents'):
        trigger(window, target, timings, captures)
    if window.current_key != 'documents':
        errors.append(dict(type='RapidNavigation', message=stamp))
    finish(window)

    home = window.pages['home']
    clock = [datetime.combine(date.today(), daytime(14)), 1000.0]
    session = FocusSession(ctx.db, now=lambda: clock[0], monotonic=lambda: clock[1])
    session.discard()
    home.focus_session = session
    ctx._live_focus_session = session
    session.start('maths', minutes=25, title='Séance fictive · navigation')
    for _ in range(3):
        clock[0] += timedelta(seconds=1)
        clock[1] += 1
        session.tick()
    home._sync_focus()
    window.sync_focus_bar()
    trigger(window, 'notes', timings, captures)
    window.focus_bar._last_action_at = float('-inf')
    QTest.mouseClick(window.focus_bar.toggle_button, Qt.LeftButton)
    if session.status != 'paused' or layer.isVisible():
        errors.append(dict(type='PauseDuringTransition', message=stamp))

    memory = window.pages['memory']
    window.navigate('memory', animate=False)
    memory.new_memory()
    memory.key_input.setText('Mon brouillon non enregistré')
    memory.value_input.setPlainText('Un exemple à compléter : ∑, accents et méthode personnelle.')
    for key in ('memory', 'documents', 'home'):
        scroll = window.wrappers[key].verticalScrollBar()
        scroll.setValue(min(130, scroll.maximum()))
    expected_scroll = {key: window.wrappers[key].verticalScrollBar().value() for key in ('memory', 'documents', 'home')}
    draft = (memory.key_input.text(), memory.value_input.toPlainText())
    focus_state = deepcopy(session.state)
    focus_remaining = session.remaining_seconds
    for target in ('home', 'notes', 'documents', 'memory'):
        trigger(window, target, timings, captures)
        finish(window)
    if draft != (memory.key_input.text(), memory.value_input.toPlainText()):
        errors.append(dict(type='DraftChanged', message=stamp))
    if ctx.db.memories().get(draft[0]) is not None:
        errors.append(dict(type='DraftWasSaved', message=stamp))
    if focus_state != session.state or focus_remaining != session.remaining_seconds:
        errors.append(dict(type='FocusStateChanged', message=stamp))
    for key, expected in expected_scroll.items():
        if window.wrappers[key].verticalScrollBar().value() != expected:
            errors.append(dict(type='ScrollChanged', message=f'{stamp}/{key}'))

    set_motion(window, False)
    with patch.object(layer, 'capture', side_effect=AssertionError('Reduced motion captured a page')):
        window.navigate('notes')
    if layer.isVisible() or layer.animation.state() != QAbstractAnimation.Stopped:
        errors.append(dict(type='ReducedMotion', message=stamp))
    session.discard()
    home._sync_focus()
    window.sync_focus_bar()
    set_motion(window, True)


def supporting_views(window, output, errors):
    window.navigate('memory', animate=False)
    editor = window.pages['memory'].value_input
    window.wrappers['memory'].ensureWidgetVisible(editor, 0, 30)
    QApplication.processEvents()
    original_geometry = editor.geometry()
    editor.setFocus(Qt.OtherFocusReason)
    QApplication.processEvents()
    if editor.geometry() != original_geometry:
        errors.append(dict(type='FocusedFieldMoved', message='Editor geometry changed on focus'))
    captures = [png(window, output, 'formulaire-focus-fr-light-1360.png', errors)]
    text = ('Un document de démonstration a été ajouté à la bibliothèque. '
            'Tu peux maintenant le ranger dans un dossier, modifier sa matière ou le retrouver avec la recherche. '
            'Ce long message sert uniquement à vérifier la lisibilité et les commandes de notification.')
    window.notify(text)
    window.toast_animation.setCurrentTime(window.toast_animation.duration())
    QApplication.processEvents()
    if window.toast.text() != text or not window.toast.isVisible():
        errors.append(dict(type='LongNotification', message='Text or visibility changed'))
    bounds = window.central.rect()
    if not bounds.contains(window.toast.geometry()):
        errors.append(dict(type='NotificationOverflow', message=str(window.toast.geometry())))
    for action in (window.toast.copy_button, window.toast.close_button):
        if not window.toast.rect().contains(action.geometry()) or action.y() > 22:
            errors.append(dict(type='NotificationActionPosition', message=str(action.geometry())))
    if window.toast_timer.interval() <= 4200:
        errors.append(dict(type='LongNotificationDuration', message=str(window.toast_timer.interval())))
    if not window.toast.message.textInteractionFlags() & Qt.TextSelectableByMouse:
        errors.append(dict(type='NotificationNotSelectable', message='Message cannot be selected'))
    point = QPointF(8, 8)
    QApplication.sendEvent(window.toast, QEnterEvent(point, point, point))
    QApplication.processEvents()
    if window.toast_timer.isActive():
        errors.append(dict(type='NotificationHoverNotPaused', message='Dismissal timer kept running'))
    window.toast.copy_button.setFocus(Qt.OtherFocusReason)
    QApplication.processEvents()
    QApplication.sendEvent(window.toast, QEvent(QEvent.Leave))
    QApplication.processEvents()
    if window.toast_timer.isActive():
        errors.append(dict(type='NotificationFocusNotPaused', message='Keyboard focus did not hold message'))
    clipboard = Mock()
    with patch('mpsi_desktop.notice_card.QApplication.clipboard', return_value=clipboard):
        window.toast.copy_button.click()
    if clipboard.setText.call_args_list != [((text,), {})]:
        errors.append(dict(type='NotificationCopy', message='Copied message differs'))
    captures.append(png(window, output, 'notification-longue-fr-light-1360.png', errors))
    editor.setFocus(Qt.OtherFocusReason)
    QApplication.processEvents()
    QApplication.processEvents()
    if not window.toast_timer.isActive():
        errors.append(dict(type='NotificationDidNotResume', message='Timer did not resume after interaction'))
    window.dismiss_notice()
    if hasattr(window, 'toast_exit'):
        window.toast_exit.setCurrentTime(window.toast_exit.duration())
    return captures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quick', action='store_true', help='Un seul thème/langue et une petite fenêtre pour contrôler le script.')
    options = parser.parse_args()
    output = ROOT / '.local' / 'Verification' / 'Navigation-2.24'
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)
    for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf', 'seguiemj.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
    app.setFont(QFont('Segoe UI', 10))
    errors, captures, timings, snapshots, geometry = [], [], [], [], []
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, value, traceback: errors.append(dict(type=kind.__name__, message=str(value)))
    try:
        for locale in (('fr',) if options.quick else ('fr', 'en')):
            with tempfile.TemporaryDirectory(prefix='navigation-', dir=output) as temporary:
                ctx = AppContext(Path(temporary) / 'data')
                seed(ctx, Path(temporary))
                ctx.db.set_setting('desktop_language', locale)
                ctx.language = locale
                set_language(locale)
                ctx.db.set_setting('desktop_reduced_motion', False)
                app.setProperty('reducedMotion', False)
                window = MainWindow(ctx, show_welcome=False)
                window.show()
                for theme in (('light',) if options.quick else ('light', 'dark')):
                    ctx.set_theme(theme)
                    apply_theme(app, theme)
                    for width, height in (((1024, 680),) if options.quick else ((1024, 680), (1360, 900))):
                        window.resize(width, height)
                        app.processEvents()
                        stamp = f'{locale}-{theme}-{width}'
                        forward, details = route_frames(window, 'home', 'notes', stamp, timings, snapshots, errors)
                        reverse, backward = route_frames(window, 'documents', 'home', stamp, timings, snapshots, errors)
                        geometry.append(dict(view=stamp, forward=details, backward=backward))
                        captures.append(frame_sheet((('Accueil → Notes', forward), ('Documents → Accueil', reverse)), output, stamp, errors))
                        for key in ('home', 'notes', 'documents'):
                            window.navigate(key, animate=False)
                            page, wrapper = window.pages[key], window.wrappers[key]
                            if page.width() > wrapper.viewport().width() or wrapper.horizontalScrollBar().maximum():
                                errors.append(dict(type='PageOverflow', message=f'{stamp}/{key}'))
                        behavior_checks(window, stamp, errors, timings, snapshots)
                        if locale == 'fr' and theme == 'light' and width == 1360:
                            captures.append(navigation_gif(window, output, timings, snapshots, errors))
                            captures.extend(supporting_views(window, output, errors))
                window.close()
                window.deleteLater()
                app.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
                ctx.close()
    finally:
        sys.excepthook = previous_hook
        set_language('fr')
    performance = dict(navigation_count=len(timings), navigation_median_ms=round(statistics.median(timings), 3) if timings else None,
        navigation_max_ms=max(timings) if timings else None, snapshot_count=len(snapshots),
        snapshot_median_ms=round(statistics.median(row['milliseconds'] for row in snapshots), 3) if snapshots else None,
        snapshot_max_pixels=max((row['pixels'] for row in snapshots), default=0),
        note='Measurements describe this process and machine; they are not a frame-rate guarantee.')
    report = dict(errors=errors, captures=captures, performance=performance, layouts=geometry)
    (output / 'rapport.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(output=str(output), captures=len(captures), errors=errors, performance=performance), ensure_ascii=False))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
