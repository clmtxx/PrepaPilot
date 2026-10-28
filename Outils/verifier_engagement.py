"""Capture home engagement and quick actions with disposable, fictional data."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import date, datetime, timedelta
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources' / 'PrepaPilot'))

from PySide6.QtCore import QEvent, Qt, qInstallMessageHandler
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from mpsi_desktop.context import AppContext
from mpsi_desktop.focus_session import FocusSession
from mpsi_desktop.i18n import set_language
from mpsi_desktop.progression import save_targets
from mpsi_desktop.quick_actions import QuickActionsDialog
from mpsi_desktop.study_profile import example_profile
from mpsi_desktop.theme import palette_for
from mpsi_desktop.window import MainWindow


def contrast_ratio(foreground, background):
    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        values = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                  for value in channels]
        return sum(value * weight for value, weight in zip(values, (.2126, .7152, .0722)))
    values = sorted((luminance(foreground), luminance(background)))
    return (values[1] + .05) / (values[0] + .05)


def seed(ctx, folder, populated):
    today = date.today()
    subjects, timetable = example_profile((today - timedelta(days=today.weekday())).isoformat())
    if not populated:
        subjects = []
        timetable['semesters'] = {'S1': [], 'S2': []}
    ctx.db.save_setup(subjects, timetable)
    ctx.db.set_setting('desktop_reduced_motion', True)
    ctx.db.set_setting('desktop_welcomed', True)
    if not populated:
        return
    ctx.db.set_setting('desktop_name', 'Camille')
    ctx.db.set_setting('desktop_program', 'Licence · parcours de démonstration')
    ctx.db.add_grade('maths', 'Évaluation', 15, 20, today.isoformat(), 'Fonctions et variations')
    sample = folder / 'Fiche de révision.txt'
    sample.write_text('Document fictif pour le contrôle visuel de PrépaPilot.', encoding='utf-8')
    ctx.db.import_document(sample, 'maths', 'cours')
    ctx.db.remember('Prochain objectif', 'Revoir une méthode, puis faire une pause.')
    ctx.db.add_time_entry('maths', today.isoformat() + 'T08:00', today.isoformat() + 'T08:40',
                          'Une première séance de démonstration')
    for offset in range(1, 8):
        stamp = (today - timedelta(days=offset)).isoformat()
        ctx.db.add_time_entry('maths', stamp + 'T17:00', stamp + 'T18:00', 'Révision de démonstration')
        ctx.db.add_time_entry('detente', stamp + 'T20:00', stamp + 'T20:30', 'Lecture et repos')
    save_targets(ctx.db, dict(work=600, sleep=0, sport=0, rest=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--small-only', action='store_true')
    parser.add_argument('--language', choices=('fr', 'en'), help='Both languages by default.')
    options = parser.parse_args()
    out = ROOT / '.local' / 'Verification' / 'Engagement'
    out.mkdir(parents=True, exist_ok=True)
    errors, warnings, captures, contrasts = [], [], [], []
    previous_hook = sys.excepthook

    def exception(kind, value, traceback):
        errors.append(dict(type=kind.__name__, message=str(value)))

    def qt_message(kind, context, message):
        warnings.append(message)
        if any(word in message for word in ('QPainter', 'paint device', 'PaintEngine', 'paintEngine')):
            errors.append(dict(type='QtPaint', message=message))

    sys.excepthook = exception
    previous_handler = qInstallMessageHandler(qt_message)
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)
    for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf', 'seguiemj.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
    sizes = ((1024, 680),) if options.small_only else ((1360, 900), (1024, 680))
    languages = (options.language,) if options.language else ('fr', 'en')

    def capture(widget, name):
        app.processEvents()
        if not widget.grab().save(str(out / name)):
            errors.append(dict(type='CaptureFailed', message=name))
        captures.append(name)

    def check_layout(window, stamp):
        home, wrapper = window.pages['home'], window.wrappers['home']
        overflow = max(0, home.width() - wrapper.viewport().width())
        if overflow or wrapper.horizontalScrollBar().maximum():
            errors.append(dict(type='LayoutOverflow', message=f'{stamp}: {overflow}px'))
        for control, _ in window.nav.values():
            if control.text() and control.width() < control.sizeHint().width():
                errors.append(dict(type='NavigationClipped', message=f'{stamp}: {control.text()}'))

    try:
        for language in languages:
            for populated in (False, True):
                with tempfile.TemporaryDirectory(prefix='base-fictive-', dir=out) as temporary:
                    folder = Path(temporary)
                    set_language(language)
                    ctx = None
                    window = None
                    try:
                        ctx = AppContext(folder / 'data')
                        ctx.update_checks_enabled = False
                        # Keep completed demo activities in the past in every run.
                        ctx.db._time_now = lambda: datetime.combine(date.today(), datetime.min.time()).replace(hour=18)
                        ctx.set_language(language)
                        seed(ctx, folder, populated)
                        window = MainWindow(ctx, show_welcome=False)
                        window.show()
                        app.processEvents()
                        home = window.pages['home']
                        wrapper = window.wrappers['home']
                        for width, height in sizes:
                            window.resize(width, height)
                            for theme in ('light', 'dark'):
                                ctx.set_theme(theme)
                                state = 'configure' if populated else 'vide'
                                stamp = f'{language}-{theme}-{width}-{state}'
                                home.focus_session.discard()
                                home._sync_focus()
                                home.refresh()
                                wrapper.verticalScrollBar().setValue(0)
                                QTest.qWait(35)
                                check_layout(window, stamp)
                                capture(window, f'accueil-{stamp}.png')
                                wrapper.verticalScrollBar().setValue(wrapper.verticalScrollBar().maximum())
                                QTest.qWait(15)
                                capture(window, f'accueil-{stamp}-bas.png')
                                colors = palette_for(theme)
                                ratios = {role: round(contrast_ratio(colors[role], colors['bg']), 2)
                                          for role in ('text', 'muted')}
                                contrasts.append(dict(state=stamp, **ratios))
                                if ratios['text'] < 4.5 or ratios['muted'] < 4.5:
                                    errors.append(dict(type='TextContrast', message=f'{stamp}: {ratios}'))
                                if not populated:
                                    continue

                                momentum = getattr(home, 'momentum_card', None)
                                if momentum is not None:
                                    wrapper.ensureWidgetVisible(momentum)
                                    app.processEvents()
                                    capture(window, f'accueil-{stamp}-elan.png')
                                    capture(momentum, f'elan-{stamp}.png')

                                clock = [datetime.combine(date.today(), datetime.min.time()).replace(hour=14), 1000.]
                                session = FocusSession(ctx.db, now=lambda: clock[0], monotonic=lambda: clock[1])
                                home.focus_session = session
                                ctx._live_focus_session = session
                                session.start('maths', minutes=25, title='Revoir une méthode et deux exercices')
                                for _ in range(120):
                                    clock[0] += timedelta(seconds=1)
                                    clock[1] += 1
                                    session.tick()
                                session.pause()
                                home._sync_focus()
                                wrapper.ensureWidgetVisible(home.focus_card)
                                QTest.qWait(15)
                                check_layout(window, stamp + '-pause')
                                capture(window, f'accueil-{stamp}-pause.png')
                                session.finish()
                                home._sync_focus()
                                QTest.qWait(15)
                                capture(window, f'accueil-{stamp}-bilan.png')
                                captured_palette = []

                                def palette_exec(dialog):
                                    dialog.show()
                                    app.processEvents()
                                    capture(dialog, f'actions-{stamp}.png')
                                    dialog.search.setText('note' if language == 'fr' else 'grade')
                                    app.processEvents()
                                    capture(dialog, f'actions-{stamp}-recherche.png')
                                    captured_palette.append(True)
                                    dialog.reject()
                                    return QDialog.Rejected

                                with patch.object(QuickActionsDialog, 'exec', new=palette_exec):
                                    window.activateWindow()
                                    window.setFocus()
                                    QTest.qWait(15)
                                    QTest.keyClick(window, Qt.Key_K, Qt.ControlModifier)
                                    app.processEvents()
                                    if not captured_palette:
                                        errors.append(dict(type='ShortcutNotTriggered', message=stamp))
                                        window.open_quick_actions()
                                session.discard()
                                home._sync_focus()
                    except Exception as exc:
                        errors.append(dict(type=type(exc).__name__, message=str(exc)))
                    finally:
                        if window is not None:
                            window.close()
                            window.deleteLater()
                        app.sendPostedEvents(None, QEvent.DeferredDelete)
                        app.processEvents()
                        if ctx is not None:
                            ctx.close()
    finally:
        sys.excepthook = previous_hook
        qInstallMessageHandler(previous_handler)
        set_language('fr')
    report = dict(languages=languages, sizes=sizes, captures=captures, errors=errors,
                  warnings=warnings, text_contrast=contrasts, fictional_data_only=True)
    (out / 'rapport.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(output=str(out), capture_count=len(captures), errors=errors,
                          warning_count=len(warnings)), ensure_ascii=False))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
