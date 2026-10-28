"""Capture achievement tiers with disposable data; no account or personal data."""
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile

from chemins import local_root


def main():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'Sources' / 'PrepaPilot'))
    from PySide6.QtCore import QEvent, QLocale
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget
    from mpsi_desktop.achievement_panel import AchievementDetailsDialog, AchievementHistoryDialog
    from mpsi_desktop.achievement_visuals import BadgeFigure, TIER_NAMES
    from mpsi_desktop.context import AppContext
    from mpsi_desktop.window import MainWindow

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    QLocale.setDefault(QLocale('fr_FR'))
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
    output = local_root() / 'Verification' / 'Succes-2.15.1'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, value, trace: errors.append((kind.__name__, str(value)))
    try:
        with tempfile.TemporaryDirectory(prefix='prepapilot-succes-qa-') as temporary:
            ctx = AppContext(Path(temporary) / 'data')
            now = datetime(2026, 10, 18, 18)
            ctx.db._time_now = lambda: now
            ctx.db.set_setting('desktop_reduced_motion', True)
            window = MainWindow(ctx, show_welcome=False)
            window.show()
            window.navigate('progression', animate=False)
            page = window.pages['progression']
            page.set_mode('achievements')
            wrapper = window.wrappers['progression']
            window.resize(1024, 680)
            QTest.qWait(30)
            window.grab().save(str(output / 'succces-vide.png'))
            ctx.db.set_setting('desktop_achievements', {'version': 1, 'awards': {
                'work_total:3': {'earned_at': '2026-10-10T18:00:00'},
                'work_week:5': {'earned_at': '2026-10-10T18:00:00'},
                'work_week_v2:5': {'earned_at': '2026-10-10T18:00:00'},
                'work_month_v2:5': {'earned_at': '2026-10-10T18:00:00'},
                'quest:work_week:2026-10-05': {'earned_at': '2026-10-10T18:00:00'},
            }})
            for offset in range(45):
                day = now.replace(hour=10) - timedelta(days=offset)
                if day.day in (12, 14, 16) or day < datetime(2026, 10, 12):
                    hours = 1 if day >= datetime(2026, 10, 12) else 3
                    ctx.db.add_time_entry('maths', day.isoformat(),
                                          (day + timedelta(hours=hours)).isoformat(), 'Travail fictif')
                if offset < 35 and day.date() not in (datetime(2026, 10, 13).date(), datetime(2026, 10, 16).date()):
                    wake = day.replace(hour=7)
                    ctx.db.add_time_entry('sommeil', (wake - timedelta(hours=8)).isoformat(),
                                          wake.isoformat(), 'Sommeil fictif')
                if day.weekday() in (1, 4):
                    sport_start = day.replace(hour=16)
                    ctx.db.add_time_entry('sport', sport_start.isoformat(),
                                          (sport_start + timedelta(minutes=45)).isoformat(), 'Sport fictif')
            ctx.mark_changed('activities')
            for width, height in ((1360, 900), (1024, 680)):
                window.resize(width, height)
                for theme in ('light', 'dark'):
                    ctx.set_theme(theme)
                    wrapper.verticalScrollBar().setValue(0)
                    QTest.qWait(40)
                    window.grab().save(str(output / f'succes-{theme}-{width}.png'))
                    if page.width() > wrapper.viewport().width():
                        errors.append(('PageOverflow', f'{theme}/{width}: {page.width()}/{wrapper.viewport().width()}'))
                    wrapper.verticalScrollBar().setValue(wrapper.verticalScrollBar().maximum())
                    QTest.qWait(20)
                    window.grab().save(str(output / f'collection-{theme}-{width}.png'))
                    if len(page.achievement_panel.report['families']) != 6 or len(page.achievement_panel.report['quests']) != 6:
                        errors.append(('MissingSports', f'{theme}/{width}'))
                    for key in ('work_total', 'work_week', 'work_month', 'sleep_streak', 'sport_total', 'sport_streak'):
                        family = next(f for f in page.achievement_panel.report['families'] if f['id'] == key)
                        dialog = AchievementDetailsDialog(family, theme, window)
                        dialog.show()
                        QTest.qWait(25)
                        dialog.grab().save(str(output / f'paliers-{key}-{theme}-{width}.png'))
                        scroll = dialog.findChild(QScrollArea)
                        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                        QTest.qWait(15)
                        dialog.grab().save(str(output / f'paliers-fin-{key}-{theme}-{width}.png'))
                        if dialog.height() > 640 or dialog.width() > 1024:
                            errors.append(('DialogOverflow', f'{key}/{theme}: {dialog.width()}x{dialog.height()}'))
                        dialog.reject()
                        dialog.deleteLater()
                    history = AchievementHistoryDialog(page.achievement_panel.report, theme, window)
                    history.show()
                    QTest.qWait(25)
                    history.grab().save(str(output / f'historique-{theme}-{width}.png'))
                    if history.height() > 640 or history.width() > 1024 or history.table.rowCount() != 5:
                        errors.append(('HistoryLayout', f'{theme}/{width}'))
                    history.reject()
                    history.deleteLater()
            gallery = QWidget()
            gallery.setWindowTitle('Les cinq paliers — aperçu de contrôle')
            gallery.setStyleSheet('background:#192335;color:#EDF2FF;')
            row = QHBoxLayout(gallery)
            for index, name in enumerate(TIER_NAMES):
                column = QVBoxLayout()
                figure = BadgeFigure(index, 'sport_total' if index % 2 == 0 else 'sport_streak', False)
                figure.setFixedSize(200, 185)
                column.addWidget(figure)
                column.addWidget(QLabel(name))
                row.addLayout(column)
            gallery.show()
            QTest.qWait(30)
            gallery.grab().save(str(output / 'cinq-paliers.png'))
            gallery.close()
            gallery.deleteLater()
            window.close()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
            ctx.close()
    finally:
        sys.excepthook = previous_hook
    print('Captures :', output)
    print('Qt/layout errors:', errors)
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
