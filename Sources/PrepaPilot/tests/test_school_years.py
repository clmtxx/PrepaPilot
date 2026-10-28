"""School-year initialization, voluntary additions and calendar boundaries."""
from datetime import date
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext, current_school_year, school_year_bounds
from mpsi_desktop.window import MainWindow

APP=QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class CalendarTests(unittest.TestCase):
    def test_september_boundary_and_leap_day(self):
        self.assertEqual(current_school_year(date(2026,8,31)),2025)
        self.assertEqual(current_school_year(date(2026,9,1)),2026)
        self.assertEqual(current_school_year(date(2028,2,29)),2027)
        start,end=school_year_bounds(2027)
        self.assertLessEqual(start,date(2028,2,29))
        self.assertLess(date(2028,2,29),end)
        self.assertEqual((end-start).days,366)
        start,end=school_year_bounds(2099)
        self.assertEqual((end-start).days,365)  # 2100 is not a leap year.


class SchoolYearTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.current=patch('mpsi_desktop.context.current_school_year',return_value=2026)
        self.clock=self.current.start()
        self.ctx=AppContext(Path(self.temp.name)/'data')

    def tearDown(self):
        self.ctx.close()
        self.current.stop()
        self.temp.cleanup()

    def test_initial_year_and_voluntary_additions_persist(self):
        self.assertEqual(self.ctx.available_years,[2026])
        self.assertEqual(self.ctx.year,2026)
        self.assertEqual(self.ctx.db.get_setting('school_year_start'),2026)
        changes=QSignalSpy(self.ctx.data_changed)
        self.assertEqual(self.ctx.add_school_year(),2027)
        self.assertEqual(changes.count(),1)
        self.assertEqual(self.ctx.add_school_year(),2028)
        self.assertEqual(self.ctx.year,2028)
        self.ctx.close()
        self.ctx=AppContext(Path(self.temp.name)/'data')
        self.assertEqual(self.ctx.available_years,[2026,2027,2028])
        self.assertEqual(self.ctx.year,2028)

    def test_legacy_import_hides_past_without_removing_data(self):
        self.ctx.db.add_grade('maths','ds',15,20,'2025-11-03')
        self.ctx.db.set_setting('school_year_start',2025)
        self.ctx.db.set_setting('school_year',2025)
        self.ctx.db.set_setting('school_years',[2025,2027,2027,True,'2029',9999])
        self.ctx.reload_data()
        self.assertEqual(self.ctx.available_years,[2026,2027])
        self.assertEqual(self.ctx.year,2026)
        self.assertEqual(self.ctx.db.get_setting('school_years'),[2025,2026,2027])
        self.assertEqual(len(self.ctx.db.list_grades()),1)

    def test_older_archive_future_selection_is_retained(self):
        self.ctx.db.set_setting('school_year',2028)
        self.ctx.db.set_setting('school_years',None)
        self.ctx.reload_data()
        self.assertEqual(self.ctx.available_years,[2026,2028])
        self.assertEqual(self.ctx.year,2028)
        self.assertEqual(self.ctx.add_school_year(),2029)

    def test_new_term_updates_visible_floor_once_and_retains_origin(self):
        self.ctx.add_school_year()
        self.ctx.set_year(2026)
        changes=QSignalSpy(self.ctx.data_changed)
        self.clock.return_value=2027
        self.assertTrue(self.ctx.sync_school_years())
        self.assertEqual(self.ctx.available_years,[2027])
        self.assertEqual(self.ctx.year,2027)
        self.assertEqual(self.ctx.db.get_setting('school_year_start'),2026)
        self.assertEqual(self.ctx.db.get_setting('school_years'),[2026,2027])
        self.assertFalse(self.ctx.sync_school_years())
        self.assertEqual(changes.count(),1)

    def test_selection_only_accepts_registered_visible_years(self):
        changes=QSignalSpy(self.ctx.data_changed)
        self.ctx.set_year(2026)
        self.assertEqual(changes.count(),0)
        for invalid in (2025,2027,None,True,'2026'):
            with self.assertRaises(ValueError):self.ctx.set_year(invalid)
        self.assertEqual(self.ctx.year,2026)
        self.assertEqual(changes.count(),0)

    def test_grade_year_keeps_existing_august_boundary_and_leap_day(self):
        self.ctx.add_school_year()
        for stamp in ('2027-07-31','2027-08-01','2028-02-29','2028-07-31','2028-08-01'):
            self.ctx.db.add_grade('maths','ds',12,20,stamp)
        self.assertEqual([row['graded_on'] for row in self.ctx.grades()],
                         ['2027-08-01','2028-02-29','2028-07-31'])


class SchoolYearWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.current=patch('mpsi_desktop.context.current_school_year',return_value=2026)
        self.clock=self.current.start()
        self.ctx=AppContext(Path(self.temp.name)/'data')
        self.ctx.db.set_setting('desktop_reduced_motion',True)
        self.errors=[]
        self.previous_hook=sys.excepthook
        sys.excepthook=lambda kind,value,tb:self.errors.append((kind.__name__,str(value)))
        self.window=MainWindow(self.ctx,show_welcome=False)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.current.stop()
        self.temp.cleanup()
        sys.excepthook=self.previous_hook
        self.assertEqual(self.errors,[])

    def test_add_button_selects_next_year_without_feedback_signals(self):
        combo=self.window.year
        self.assertEqual([combo.itemText(i) for i in range(combo.count())],['2026–2027'])
        selection_changes=QSignalSpy(combo.currentIndexChanged)
        changes=QSignalSpy(self.ctx.data_changed)
        QTest.mouseClick(self.window.add_year_button,Qt.LeftButton)
        self.assertEqual(self.ctx.available_years,[2026,2027])
        self.assertEqual(combo.currentData(),2027)
        self.assertEqual(combo.currentText(),'2027–2028')
        self.assertEqual(selection_changes.count(),0)
        self.assertEqual(changes.count(),1)
        combo.setCurrentIndex(0)
        self.assertEqual(self.ctx.year,2026)
        self.assertEqual(changes.count(),2)

    def test_import_rebuilds_selector_and_term_sync_removes_past(self):
        combo=self.window.year
        selection_changes=QSignalSpy(combo.currentIndexChanged)
        self.ctx.db.set_setting('school_years',[2025,2026,2028])
        self.ctx.db.set_setting('school_year',2028)
        self.ctx.reload_data()
        self.assertEqual([combo.itemData(i) for i in range(combo.count())],[2026,2028])
        self.assertEqual(combo.currentData(),2028)
        self.assertEqual(selection_changes.count(),0)
        self.clock.return_value=2027
        self.ctx.sync_school_years()
        self.assertEqual([combo.itemData(i) for i in range(combo.count())],[2027,2028])
        self.assertEqual(combo.currentData(),2028)
        self.assertEqual(selection_changes.count(),0)


if __name__=='__main__':unittest.main()
