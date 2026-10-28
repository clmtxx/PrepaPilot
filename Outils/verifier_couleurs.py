"""Capture both UI themes with fictional data and report layout/paint issues."""
import argparse
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources' / 'PrepaPilot'))

from PySide6.QtCore import QEvent, QLocale, qInstallMessageHandler
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext, prepare_data
from mpsi_desktop.progression import save_targets
from mpsi_desktop.study_profile import example_profile
from mpsi_desktop.window import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='apres')
    parser.add_argument('--pages', nargs='*')
    parser.add_argument('--language', choices=('fr', 'en'), default='fr')
    parser.add_argument('--small-only', action='store_true')
    options = parser.parse_args()
    label = ''.join(c for c in options.label if c.isalnum() or c in '-_')
    out = ROOT / '.local' / 'Verification' / 'Couleurs' / (label or 'apres')
    out.mkdir(parents=True, exist_ok=True)
    errors, warnings, captures = [], [], []

    def exception(kind, value, tb):
        errors.append({'type': kind.__name__, 'message': str(value)})
        import traceback
        traceback.print_exception(kind, value, tb)

    def qt_message(kind, context, message):
        warnings.append(message)
        if any(word in message for word in ('QPainter', 'paint device', 'PaintEngine', 'paintEngine')):
            errors.append({'type': 'QtPaint', 'message': message})

    sys.excepthook = exception
    qInstallMessageHandler(qt_message)
    app = QApplication([])
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)
    QLocale.setDefault(QLocale('fr_FR'))
    for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf', 'seguiemj.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
    with tempfile.TemporaryDirectory(prefix='base-fictive-', dir=out) as temporary:
        data, _ = prepare_data(temporary, migrate=False)
        ctx = AppContext(data)
        ctx.set_language(options.language)
        ctx.db.set_setting('desktop_name', 'Camille')
        ctx.db.set_setting('desktop_program', 'Licence de droit')
        ctx.db.set_setting('desktop_reduced_motion', True)
        subjects, timetable = example_profile('2026-09-28')
        for subject, name in zip(subjects, ('Droit civil', 'Histoire du droit', 'Anglais', 'Méthodologie juridique', 'Économie')):
            subject['name'] = name
        ctx.db.save_setup(subjects, timetable, schedule_labels={'S1': 'Cours à l’université', 'S2': 'Stage en cabinet'})
        for day, score in ((3, 12), (10, 14), (17, 13), (24, 16)):
            ctx.db.add_grade('maths', 'Cas pratique', score, 20, f'2026-09-{day:02d}', 'Introduction au droit civil')
        sample = Path(temporary) / 'Introduction au droit civil.txt'
        sample.write_text('Introduction au droit civil\n\nFiche de révision personnelle.\n\nDocument de démonstration.', encoding='utf-8')
        ctx.db.import_document(sample, 'maths', 'cours')
        ctx.db.remember('Objectif de la semaine', 'Préparer la présentation du projet de groupe.')
        for offset in range(45, 0, -1):
            day = date.today() - timedelta(days=offset)
            stamp = day.isoformat()
            ctx.db.add_time_entry('sommeil', stamp+'T00:00', stamp+'T07:30', 'Nuit de démonstration')
            ctx.db.add_time_entry('detente', stamp+'T19:00', stamp+'T20:00', 'Lecture et repos')
            if day.weekday() < 5:
                ctx.db.add_time_entry('maths', stamp+'T09:00', stamp+('T12:00' if offset < 7 else 'T14:00'), 'Travail de démonstration')
            if offset % 3 == 0:
                ctx.db.add_time_entry('sport', stamp+'T17:00', stamp+'T18:00', 'Sport de démonstration')
        save_targets(ctx.db, dict(work=2100, sleep=3360, sport=150, rest=420))
        window = MainWindow(ctx, show_welcome=False)
        window.show()
        pages = options.pages or list(window.pages)
        sizes = ((1024, 680),) if options.small_only else ((1360, 900), (1024, 680))
        for width, height in sizes:
            window.resize(width, height)
            for theme in ('light', 'dark'):
                ctx.set_theme(theme)
                for key in pages:
                    window.navigate(key, animate=False)
                    wrapper = window.wrappers[key]
                    wrapper.verticalScrollBar().setValue(0)
                    QTest.qWait(80)
                    page = window.pages[key]
                    overflow = max(0, page.width()-wrapper.viewport().width())
                    if overflow:
                        errors.append({'type': 'LayoutOverflow', 'message': f'{key}/{width}/{theme}: {overflow}px'})
                    nav_controls = [item[0] for item in window.nav.values()]
                    for control in nav_controls:
                        if control.text() and control.width() < control.sizeHint().width():
                            errors.append({'type': 'NavigationClipped', 'message': f'{key}/{width}/{theme}: {control.text()}'})
                    hero = getattr(page, 'hero', None)
                    if hero is not None:
                        for text_label in (hero.title_label, hero.subtitle_label):
                            needed = text_label.heightForWidth(text_label.width())
                            if needed > text_label.height():
                                errors.append({'type': 'HeroTextClipped', 'message': f'{key}/{width}/{theme}: {text_label.height()} < {needed}'})
                        if not hero.rect().contains(hero.figure.geometry()):
                            errors.append({'type': 'HeroFigureClipped', 'message': f'{key}/{width}/{theme}'})
                    name = f'{key}-{theme}-{width}.png'
                    window.grab().save(str(out / name))
                    captures.append(name)
                    if width == 1024 and wrapper.verticalScrollBar().maximum():
                        wrapper.verticalScrollBar().setValue(wrapper.verticalScrollBar().maximum())
                        QTest.qWait(40)
                        name = f'{key}-{theme}-{width}-bas.png'
                        window.grab().save(str(out / name))
                        captures.append(name)
        if 'progression' in pages:
            progress = window.pages['progression']
            for width, height in sizes:
                window.resize(width, height)
                for theme in ('light', 'dark'):
                    ctx.set_theme(theme)
                    window.navigate('progression', animate=False)
                    progress.mode_buttons['achievements'].click()
                    wrapper = window.wrappers['progression']
                    wrapper.verticalScrollBar().setValue(0)
                    QTest.qWait(80)
                    overflow = max(0, progress.width()-wrapper.viewport().width())
                    if overflow:
                        errors.append({'type': 'LayoutOverflow', 'message': f'achievements/{width}/{theme}: {overflow}px'})
                    name = f'succes-{theme}-{width}.png'
                    window.grab().save(str(out / name))
                    captures.append(name)
                    if width == 1024 and wrapper.verticalScrollBar().maximum():
                        wrapper.verticalScrollBar().setValue(wrapper.verticalScrollBar().maximum())
                        QTest.qWait(40)
                        name = f'succes-{theme}-{width}-bas.png'
                        window.grab().save(str(out / name))
                        captures.append(name)
            progress.mode_buttons['summary'].click()
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        ctx.close()
    report = {'pages': pages, 'captures': captures, 'errors': errors, 'warnings': warnings}
    (out / 'rapport.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'pages': pages, 'capture_count': len(captures), 'errors': errors, 'warning_count': len(warnings)}, ensure_ascii=False))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
