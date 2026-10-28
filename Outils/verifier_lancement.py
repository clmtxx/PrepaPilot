"""Exercise launch-ready help, search and cross-page sessions with fictional data."""
import argparse
from datetime import date, datetime, time, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources' / 'PrepaPilot'))

from PySide6.QtCore import QEvent, Qt, qInstallMessageHandler
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from mpsi_desktop.context import AppContext
from mpsi_desktop.focus_session import FocusSession
from mpsi_desktop.global_search import GlobalSearchDialog
from mpsi_desktop.help_center import HelpCenterDialog
from mpsi_desktop.i18n import set_language
from mpsi_desktop.study_profile import example_profile
from mpsi_desktop.window import MainWindow


def seed(ctx, folder):
    today = date.today()
    subjects, timetable = example_profile((today - timedelta(days=today.weekday())).isoformat())
    ctx.db.save_setup(subjects, timetable)
    ctx.db.set_setting('desktop_reduced_motion', True)
    ctx.db.set_setting('desktop_welcomed', True)
    ctx.db.set_setting('desktop_name', 'Camille')
    ctx.db.set_setting('desktop_program', 'Parcours de démonstration')
    ctx.db.add_grade('maths', 'Évaluation', 15, 20, today.isoformat(), 'Projet · analyse de données')
    sample = folder / 'Projet de démonstration.txt'
    sample.write_text('Un document fictif pour le contrôle de la recherche locale.', encoding='utf-8')
    ctx.db.import_document(sample, 'maths', 'cours', title='Projet de démonstration', description='Projet de groupe · méthode et exercices')
    ctx.db.remember('Projet de groupe', 'Préparer le projet puis garder du temps pour une pause.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--small-only', action='store_true')
    parser.add_argument('--language', choices=('fr', 'en'))
    options = parser.parse_args()
    out = ROOT / '.local' / 'Verification' / 'Lancement'
    out.mkdir(parents=True, exist_ok=True)
    errors, warnings, captures = [], [], []
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
    app.setFont(QFont('Segoe UI', 10))
    languages = (options.language,) if options.language else ('fr', 'en')
    sizes = ((1024, 680),) if options.small_only else ((1360, 900), (1024, 680))

    def capture(widget, name):
        app.processEvents()
        if not widget.grab().save(str(out / name)):
            errors.append(dict(type='CaptureFailed', message=name))
        captures.append(name)

    def check_window(window, stamp):
        app.processEvents()
        page = window.pages[window.current_key]
        wrapper = window.wrappers[window.current_key]
        if page.width() > wrapper.viewport().width() or wrapper.horizontalScrollBar().maximum():
            errors.append(dict(type='PageOverflow', message=stamp))
        for control in (window.year, window.add_year_button, window.quick_actions_button,
                        window.search_button, window.help_button, window.theme_button,
                        window.fullscreen_button):
            if (not window.central.rect().contains(control.mapTo(window.central, control.rect().topLeft()))
                    or not window.central.rect().contains(control.mapTo(window.central, control.rect().bottomRight()))):
                errors.append(dict(type='TopbarOverflow', message=stamp))
            if (hasattr(control, 'text') and control.text()
                    and control.width() < control.fontMetrics().horizontalAdvance(control.text()) + 16):
                errors.append(dict(type='TopbarClipped', message=f'{stamp}: {control.accessibleName() or control.text()}'))
        if window.focus_bar.isVisible():
            bar = window.focus_bar
            if bar.minimumSizeHint().width() > bar.width():
                errors.append(dict(type='FocusBarOverflow', message=stamp))
            for action in (bar.return_button, bar.toggle_button, bar.review_button):
                if action.isVisible() and not bar.rect().contains(action.geometry()):
                    errors.append(dict(type='FocusBarControlClipped', message=stamp))

    def check_help(dialog, stamp):
        for index, (key, scroll) in enumerate(dialog.pages.items()):
            dialog.tabs.setCurrentIndex(index)
            app.processEvents()
            if scroll.horizontalScrollBar().maximum() or scroll.widget().width() > scroll.viewport().width():
                errors.append(dict(type='HelpOverflow', message=f'{stamp}: {key}'))
            capture(dialog, f'aide-{stamp}-{key}.png')

    try:
        for language in languages:
            with tempfile.TemporaryDirectory(prefix='base-fictive-', dir=out) as temporary:
                folder = Path(temporary)
                ctx, window = None, None
                try:
                    set_language(language)
                    ctx = AppContext(folder / 'data')
                    ctx.update_checks_enabled = False
                    ctx.db._time_now = lambda: datetime.combine(date.today(), time(18))
                    ctx.set_language(language)
                    seed(ctx, folder)
                    window = MainWindow(ctx, show_welcome=False)
                    window.show()
                    app.processEvents()
                    home = window.pages['home']
                    clock = [datetime.combine(date.today(), time(14)), 1000.]
                    session = FocusSession(ctx.db, now=lambda: clock[0], monotonic=lambda: clock[1])
                    home.focus_session = session
                    ctx._live_focus_session = session
                    for width, height in sizes:
                        window.resize(width, height)
                        for theme in ('light', 'dark'):
                            ctx.set_theme(theme)
                            stamp = f'{language}-{theme}-{width}'
                            session.discard()
                            session.start('maths', minutes=25,
                                          title='Projet · démonstration avec un objectif volontairement long pour contrôler la lisibilité des boutons de séance')
                            home._sync_focus()
                            for status in ('running', 'paused', 'review'):
                                if status == 'paused':
                                    for _ in range(120):
                                        clock[0] += timedelta(seconds=1)
                                        clock[1] += 1
                                        session.tick()
                                    session.pause()
                                elif status == 'review':
                                    session.finish()
                                home._sync_focus()
                                for key in ('documents', 'notes'):
                                    window.navigate(key, animate=False)
                                    app.processEvents()
                                    QTest.qWait(15)
                                    check_window(window, f'{stamp}-{key}-{status}')
                                    if not window.focus_bar.isVisible():
                                        errors.append(dict(type='MissingFocusBar', message=f'{stamp}-{key}-{status}'))
                                    capture(window, f'seance-{stamp}-{key}-{status}.png')

                            help_opened = []

                            def help_exec(dialog):
                                dialog.resize(min(740, width - 80), min(570, height - 80))
                                dialog.show()
                                check_help(dialog, stamp)
                                help_opened.append(True)
                                dialog.reject()
                                return QDialog.Rejected

                            with patch.object(HelpCenterDialog, 'exec', new=help_exec):
                                window.activateWindow()
                                window.setFocus()
                                QTest.qWait(15)
                                QTest.keyClick(window, Qt.Key_F1)
                                app.processEvents()
                                if not help_opened:
                                    errors.append(dict(type='HelpShortcutNotTriggered', message=stamp))

                            search_opened = []

                            def search_exec(dialog):
                                dialog.show()
                                app.processEvents()
                                capture(dialog, f'recherche-{stamp}-vide.png')
                                dialog.search.setText('projet')
                                dialog.run_search()
                                app.processEvents()
                                if dialog.results.count() != 3:
                                    errors.append(dict(type='GlobalSearchResults', message=f'{stamp}: {dialog.results.count()}'))
                                if dialog.results.horizontalScrollBar().maximum():
                                    errors.append(dict(type='SearchOverflow', message=stamp))
                                capture(dialog, f'recherche-{stamp}-projet.png')
                                dialog.search.setText('introuvablepourletest')
                                dialog.run_search()
                                app.processEvents()
                                capture(dialog, f'recherche-{stamp}-aucun.png')
                                search_opened.append(True)
                                dialog.reject()
                                return QDialog.Rejected

                            with patch.object(GlobalSearchDialog, 'exec', new=search_exec):
                                window.activateWindow()
                                window.setFocus()
                                QTest.qWait(15)
                                QTest.keyClick(window, Qt.Key_F, Qt.ControlModifier)
                                app.processEvents()
                                if not search_opened:
                                    errors.append(dict(type='SearchShortcutNotTriggered', message=stamp))
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
                  warnings=warnings, fictional_data_only=True)
    (out / 'rapport.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(output=str(out), capture_count=len(captures), errors=errors,
                          warning_count=len(warnings)), ensure_ascii=False))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
