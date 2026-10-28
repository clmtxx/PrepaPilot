"""Dated tomorrow timetable, exceptions, holidays and calendar rollovers."""
from datetime import date, datetime
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QLabel, QFrame
from mpsi_desktop.context import AppContext
from mpsi_desktop.dashboard import DashboardPage
from mpsi_desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class TomorrowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name)/'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.clock = patch.object(self.ctx.db, '_time_now', return_value=datetime(2026,9,30,20))
        self.clock.start()
        self.today = patch.object(DashboardPage, '_today', return_value=date(2026,9,30))
        self.calendar = self.today.start()
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind,value,tb:self.errors.append((kind.__name__,str(value)))
        self.window = MainWindow(self.ctx, show_welcome=False)
        self.window.show()
        APP.processEvents()
        self.home = self.window.pages['home']

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None,QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.today.stop()
        self.clock.stop()
        self.temp.cleanup()
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def test_month_change_shows_all_dated_slots_without_counting_them(self):
        self.assertEqual(self.home.tomorrow_title.text(), 'Jeudi 1 octobre')
        self.assertEqual(len(self.home.tomorrow_entries), 6)
        self.assertEqual(self.home.tomorrow_entries[0]['start_at'], '2026-10-01T08:00')
        self.assertEqual(self.home.tomorrow_entries[-1]['end_at'], '2026-10-01T17:00')
        self.assertTrue(all(row['status']=='planned' for row in self.home.tomorrow_entries))
        self.assertEqual(self.ctx.db.time_totals('2026-10-01','2026-10-01'), {})
        identities = [row['id'] for row in self.home.tomorrow_entries]
        self.home.refresh()
        self.assertEqual([row['id'] for row in self.home.tomorrow_entries], identities)

    def test_cancelled_and_corrected_lessons_use_tomorrow_exceptions(self):
        first, second = self.home.tomorrow_entries[:2]
        self.ctx.db.delete_time_entry(first['id'])
        self.ctx.db.update_time_entry(second['id'], start_at='2026-10-01T10:00', title='TP SI · exception <groupe>')
        self.ctx.mark_changed()
        self.assertEqual(len(self.home.tomorrow_entries), 5)
        self.assertEqual(self.home.tomorrow_entries[0]['start_at'], '2026-10-01T10:00')
        self.assertEqual(self.home.tomorrow_entries[0]['title'], 'TP SI · exception <groupe>')
        self.assertTrue(self.home.tomorrow_entries[0]['manual_override'])

    def test_semester_and_sunday_follow_calendar_without_manual_activities(self):
        self.ctx.db.set_semester('S2','2026-10-01')
        self.calendar.return_value = date(2026,10,1)
        self.home.refresh()
        self.assertIn('Semestre 2', self.home.holiday_status.text())
        self.assertEqual(self.home.tomorrow_entries[-1]['end_at'],'2026-10-02T16:30')
        self.calendar.return_value = date(2026,10,3)
        self.ctx.db.add_time_entry('sport','2026-10-04T10:00','2026-10-04T11:00',status='planned')
        self.home.refresh()
        self.assertEqual(self.home.tomorrow_title.text(),'Dimanche 4 octobre')
        self.assertEqual(self.home.tomorrow_entries, [])

    def test_holiday_pauses_template_and_keeps_personal_activity(self):
        self.ctx.db.add_time_entry('maths','2026-10-01T18:00','2026-10-01T19:00',status='planned')
        self.ctx.db.add_holiday('2026-10-01','2026-10-07','Vacances <personnelles>')
        self.ctx.mark_changed()
        self.assertEqual(self.home.tomorrow_entries, [])
        self.assertIn('Vacances <personnelles>',self.home.holiday_status.text())
        self.assertEqual(self.home.holiday_status.textFormat(),Qt.PlainText)
        self.assertEqual(len(self.ctx.db.list_time_entries('2026-10-01','2026-10-01')),1)
        self.ctx.db.end_holiday('2026-10-01')
        self.ctx.mark_changed()
        self.assertEqual(len(self.home.tomorrow_entries),6)

    def test_leap_year_century_and_year_end_rollovers(self):
        for today, expected in ((date(2028,2,28),date(2028,2,29)),
                                (date(2028,2,29),date(2028,3,1)),
                                (date(2100,2,28),date(2100,3,1)),
                                (date(2027,12,31),date(2028,1,1))):
            with self.subTest(today=today):
                self.calendar.return_value=today
                self.home.refresh()
                self.assertTrue(all(row['start_at'].startswith(expected.isoformat())
                                    for row in self.home.tomorrow_entries))
                self.home.open_day(expected)
                self.assertEqual(self.window.pages['time'].selected_day(),expected.isoformat())

    def test_midnight_refresh_and_open_tomorrow_journal(self):
        self.calendar.return_value=date(2026,10,1)
        self.home.refresh_if_new_day()
        self.assertEqual(self.home.tomorrow_title.text(),'Vendredi 2 octobre')
        self.home.open_day(date(2026,10,2))
        self.assertEqual(self.window.current_key,'time')
        self.assertEqual(self.window.pages['time'].selected_day(),'2026-10-02')

    def test_custom_subject_colors_and_week_b_sunday(self):
        key = 'subject_' + 'a' * 32
        subjects = self.ctx.db.get_subjects() + [dict(id=key, name='Biologie', color='#B4327A', active=True)]
        slot = dict(id='sunday-biology', weekday=6, start='09:00', end='10:30',
                    category=key, title='Révisions', week='B')
        self.ctx.db.save_setup(subjects, dict(version=2, week_anchor='2026-09-28',
                                              semesters={'S1': [slot], 'S2': []}))
        self.calendar.return_value = date(2026, 10, 10)
        self.home.refresh()
        self.assertIn('semaine B', self.home.holiday_status.text())
        self.assertEqual(len(self.home.tomorrow_entries), 1)
        self.assertEqual(self.home.tomorrow_entries[0]['category'], key)
        labels = self.home.tomorrow_card.findChildren(QLabel)
        self.assertTrue(any('Biologie' in label.text() for label in labels))
        self.assertTrue(any('#B4327A' in frame.styleSheet() for frame in
                            self.home.tomorrow_card.findChildren(QFrame)))
        self.calendar.return_value = date(2026, 10, 3)
        self.home.refresh()
        self.assertEqual(self.home.tomorrow_entries, [])


if __name__=='__main__':unittest.main()
