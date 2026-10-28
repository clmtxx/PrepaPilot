"""Visual QA with fictitious data, never the user's portable database."""
import os
import sys
import tempfile
from pathlib import Path
from datetime import date, datetime, timedelta
from unittest.mock import patch
from chemins import local_root

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources' / 'PrepaPilot'))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QLocale, QEvent, QTime, QPoint, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from mpsi_desktop.context import AppContext, prepare_data
from mpsi_desktop.window import MainWindow
from mpsi_desktop.time_tracking import ActivityDialog, SemesterDialog, TimetableDialog, HolidayDialog
from mpsi_desktop.schedule_setup import SetupDialog
from mpsi_desktop.study_profile import example_profile
from mpsi_desktop.visuals import ReflectiveTitle
from mpsi_desktop.progression import save_targets
from mpsi_desktop.progression_page import ProgressionTargetsDialog

app = QApplication([])
app.setStyle('Fusion')
app.setQuitOnLastWindowClosed(False)
QLocale.setDefault(QLocale('fr_FR'))
for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf', 'seguiemj.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
errors = []
def capture_error(kind, value, tb):
    errors.append((kind.__name__, str(value)))
    print('Qt:', kind.__name__, str(value), flush=True)
sys.excepthook = capture_error
out = local_root() / 'Verification' / 'Interface-2.16'
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as temporary:
    data, _ = prepare_data(temporary, migrate=False)
    ctx = AppContext(data)
    ctx.db.set_setting('desktop_name', 'Camille')
    ctx.db.set_setting('desktop_program', 'Licence de droit')
    ctx.db.set_setting('desktop_reduced_motion', True)
    subjects, timetable = example_profile('2026-09-28')
    names = ('Droit civil', 'Histoire du droit', 'Anglais', 'Méthodologie juridique', 'Économie')
    for subject, name in zip(subjects, names):
        subject['name'] = name
    ctx.db.save_setup(subjects, timetable, schedule_labels={'S1': 'Cours à l’université', 'S2': 'Stage en cabinet'})
    for day, score in ((3, 12), (10, 14), (17, 13), (24, 16)):
        ctx.db.add_grade('maths', 'Cas pratique', score, 20, f'2026-09-{day:02d}', 'Introduction au droit civil')
    sample = Path(temporary)/'Introduction au droit civil.txt'
    sample.write_text('Introduction au droit civil\n\nFiche de révision personnelle.\n\nDocument de démonstration.', encoding='utf-8')
    ctx.db.import_document(sample, 'maths', 'cours')
    ctx.db.remember('Objectif de la semaine', 'Préparer la présentation du projet de groupe.')
    past = (date.today() - timedelta(days=1)).isoformat()
    ctx.db.add_time_entry('maths', past+'T20:00', past+'T21:00', title='Réviser le droit civil', status='completed')
    # Six weeks of fictitious journal entries exercise comparisons and annual trends.
    for offset in range(45, 0, -1):
        day = date.today() - timedelta(days=offset)
        stamp = day.isoformat()
        ctx.db.add_time_entry('sommeil', stamp+'T00:00', stamp+'T07:30', 'Nuit de démonstration')
        ctx.db.add_time_entry('detente', stamp+'T19:00', stamp+'T20:00', 'Lecture et repos')
        if day.weekday() < 5:
            end = '12:00' if offset < 7 else '14:00'
            ctx.db.add_time_entry('maths', stamp+'T09:00', stamp+'T'+end, 'Travail de démonstration')
        if offset % 3 == 0:
            ctx.db.add_time_entry('sport', stamp+'T17:00', stamp+'T18:00', 'Sport de démonstration')
    save_targets(ctx.db, dict(work=2100, sleep=3360, sport=150, rest=420))
    window = MainWindow(ctx, show_welcome=False)
    window.show()
    for width,height in ((1360,900),(1024,680)):
        window.resize(width,height)
        for theme in ('light','dark'):
            ctx.set_theme(theme)
            for key in window.pages:
                window.navigate(key, animate=False)
                wrapper = window.wrappers[key]
                wrapper.verticalScrollBar().setValue(0)
                QTest.qWait(60)
                overflow = max(0, window.pages[key].width()-wrapper.viewport().width())
                if overflow:
                    errors.append(('LayoutOverflow',f'{key}/{width}/{theme}: {overflow}px'))
                hero = getattr(window.pages[key], 'hero', None)
                if hero is not None:
                    for label in (hero.title_label, hero.subtitle_label):
                        needed = label.heightForWidth(label.width())
                        if label.height() < needed:
                            errors.append(('HeroTextClipped', f'{key}/{width}/{theme}: {label.height()} < {needed}'))
                    if not hero.rect().contains(hero.figure.geometry()):
                        errors.append(('HeroFigureClipped', f'{key}/{width}/{theme}'))
                window.grab().save(str(out/f'{key}-{theme}-{width}.png'))
                if width==1024 and wrapper.verticalScrollBar().maximum():
                    wrapper.verticalScrollBar().setValue(wrapper.verticalScrollBar().maximum())
                    QTest.qWait(30)
                    window.grab().save(str(out/f'{key}-{theme}-{width}-bas.png'))
    window.resize(1360,900)
    # Exercise each period, the acknowledgement, annual values and target editor.
    progress = window.pages['progression']
    for theme in ('light', 'dark'):
        ctx.set_theme(theme)
        window.navigate('progression', animate=False)
        for mode in ('week', 'month', 'quarter'):
            progress.mode_buttons[mode].click()
            window.wrappers['progression'].verticalScrollBar().setValue(0)
            QTest.qWait(60)
            for axis, value in progress.metric_values.items():
                if value.height() < value.fontMetrics().height():
                    errors.append(('ProgressionClipped', f'{mode}/{theme}/{axis}'))
            window.grab().save(str(out/f'progression-{mode}-{theme}.png'))
        progress.mode_buttons['week'].click()
        if 'work' in progress.ack_buttons:
            # Hold the clock still: scores otherwise evolve with elapsed time.
            with patch('mpsi_desktop.progression_page.datetime', wraps=datetime) as clock:
                clock.now.return_value = datetime.now()
                progress.refresh()
                before = (dict(progress.report['totals']), dict(progress.report['scores']))
                progress.ack_buttons['work'].click()
                if before != (progress.report['totals'], progress.report['scores']):
                    errors.append(('ProgressionMutation', 'Acknowledgement changed statistics'))
            if not progress.details_toggle.isChecked():
                progress.details_toggle.click()
            window.wrappers['progression'].ensureWidgetVisible(progress.delta_labels['work'])
            QTest.qWait(60)
            window.grab().save(str(out/f'progression-acceptation-{theme}.png'))
        progress.history_axis.setCurrentIndex(progress.history_axis.findData('sleep'))
        if not progress.history_toggle.isChecked():
            progress.history_toggle.click()
        window.wrappers['progression'].verticalScrollBar().setValue(window.wrappers['progression'].verticalScrollBar().maximum())
        QTest.qWait(60)
        window.grab().save(str(out/f'progression-historique-{theme}.png'))
        targets = ProgressionTargetsDialog(ctx, window)
        targets.show()
        QTest.qWait(80)
        targets.grab().save(str(out/f'dialogue-objectifs-{theme}.png'))
        targets.reject()
        targets.deleteLater()
    progress.mode_buttons['summary'].click()
    if progress.details_toggle.isChecked():
        progress.details_toggle.click()
    # The visual identity must also work before the user chooses targets.
    configured_targets = dict(progress.report['targets'])
    save_targets(ctx.db, dict(work=0, sleep=0, sport=0, rest=0))
    ctx.mark_changed()
    for theme in ('light', 'dark'):
        ctx.set_theme(theme)
        window.navigate('progression', animate=False)
        window.wrappers['progression'].verticalScrollBar().setValue(0)
        QTest.qWait(80)
        window.grab().save(str(out/f'progression-sans-objectifs-{theme}.png'))
    save_targets(ctx.db, configured_targets)
    ctx.mark_changed()
    for theme in ('light', 'dark'):
        ctx.set_theme(theme)
        for name, dialog in (
            ('activite', ActivityDialog(ctx, day=past, parent=window)),
            ('semestre', SemesterDialog(ctx, date.today().isoformat(), window)),
            ('emploi-du-temps', TimetableDialog(ctx, window)),
            ('vacances', HolidayDialog(ctx, date.today().isoformat(), window)),
        ):
            dialog.show()
            QTest.qWait(200)
            dialog.grab().save(str(out/f'dialogue-{name}-{theme}.png'))
            if isinstance(dialog, SetupDialog):
                dialog.go_back()
                QTest.qWait(80)
                dialog.grab().save(str(out/f'dialogue-matieres-{theme}.png'))
            dialog.close()
        setup = SetupDialog(ctx, first_run=True)
        setup.show()
        QTest.qWait(80)
        setup.grab().save(str(out/f'premier-lancement-{theme}.png'))
        setup.start_empty()
        setup.subject_table.item(0,0).setText('Biologie')
        setup.paint_color_button(setup.subject_table.cellWidget(0,1), '#B4327A')
        setup.next_step()
        setup.day_filter.setCurrentIndex(setup.day_filter.findData(6))
        setup.week_filter.setCurrentIndex(setup.week_filter.findData('B'))
        setup.add_slot()
        setup.table.cellWidget(0,1).setTime(QTime(10,0))
        setup.table.cellWidget(0,2).setTime(QTime(12,0))
        QTest.qWait(80)
        setup.grab().save(str(out/f'premier-lancement-personnalise-{theme}.png'))
        setup.reject()
        setup.close()
        ctx.db.add_holiday(date.today().isoformat(), (date.today()+timedelta(days=6)).isoformat())
        ctx.mark_changed()
        window.navigate('home', animate=False)
        window.wrappers['home'].verticalScrollBar().setValue(0)
        QTest.qWait(60)
        window.grab().save(str(out/f'home-vacances-{theme}.png'))
        ctx.db.end_holiday(date.today().isoformat())
        ctx.mark_changed()
    # Interactive states complement static screenshots: preview, transition,
    # reflection and parallax are exercised with the user's motion setting on.
    ctx.db.set_setting('desktop_reduced_motion', False)
    ctx.mark_changed()
    window.activateWindow()
    for theme in ('light', 'dark'):
        ctx.set_theme(theme)
        for key, page in window.pages.items():
            hero = getattr(page, 'hero', None)
            if hero is None:
                continue
            window.navigate(key, animate=False)
            window.wrappers[key].verticalScrollBar().setValue(0)
            QTest.mouseMove(hero.figure, QPoint(hero.figure.width()-8, 16))
            QTest.qWait(220)
            hero.grab().save(str(out/f'page-hero-{key}-{theme}.png'))
        window.navigate('home', animate=False)
        window.wrappers['home'].verticalScrollBar().setValue(0)
        QTest.mouseMove(window.central, QPoint(5, window.central.height()-5))
        QTest.qWait(40)
        target = window.nav['notes'][0]
        QTest.mouseMove(target, target.rect().center())
        QTest.qWait(760)
        if not window.navigation_preview.popup.isVisible():
            errors.append(('MissingPreview', theme))
        window.grab().save(str(out/f'apercu-navigation-{theme}.png'))
        window.navigate('notes')
        window.animation.setCurrentTime(100)
        window.grab().save(str(out/f'transition-{theme}.png'))
        window.transition.finish()
        window.navigate('home', animate=False)
        sculpture = window.pages['home'].sculpture
        QTest.mouseMove(sculpture, QPoint(sculpture.width()-8, 12))
        QTest.qWait(200)
        window.grab().save(str(out/f'accueil-relief-{theme}.png'))
        title = window.pages['home'].findChild(ReflectiveTitle)
        QTest.mouseMove(title, title.rect().center())
        title.reflection_animation.setCurrentTime(320)
        window.grab().save(str(out/f'accueil-reflet-{theme}.png'))
        window.navigate('progression', animate=False)
        for axis, figure in progress.figures.items():
            window.wrappers['progression'].ensureWidgetVisible(figure)
            QTest.qWait(40)
            QTest.mouseMove(figure, QPoint(figure.width()-12, 16))
            QTest.qWait(240)
            figure.grab().save(str(out/f'progression-figure-{axis}-{theme}.png'))
        window.wrappers['progression'].ensureWidgetVisible(progress.metric_values['sleep'])
        window.grab().save(str(out/f'progression-relief-{theme}.png'))
        window.wrappers['progression'].ensureWidgetVisible(progress.chart)
        progress.chart.setFocus()
        QTest.keyClick(progress.chart, Qt.Key_Home)
        QTest.qWait(80)
        window.grab().save(str(out/f'progression-graphique-selection-{theme}.png'))
    ctx.db.set_setting('desktop_reduced_motion', True)
    ctx.mark_changed()
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    ctx.close()
print('Qt/layout errors:', errors)
raise SystemExit(bool(errors))
