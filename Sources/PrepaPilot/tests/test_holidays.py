"""Explicit holiday ranges preserve actual time and dated timetable exceptions."""
from datetime import date, datetime
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QDate, QEvent
from PySide6.QtWidgets import QApplication, QDialog
from mpsi_desktop.context import AppContext, DesktopStore, prepare_data
from mpsi_desktop.time_store import validate_holidays
from mpsi_desktop.time_tracking import HolidayDialog, TimeTrackingPage

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class HolidayStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DesktopStore(Path(self.temp.name) / 'data.sqlite3')
        self.clock = patch.object(self.db, "_time_now", return_value=datetime(2026, 10, 5, 12, 30))
        self.now = self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.db.close()
        self.temp.cleanup()

    def test_inclusive_dates_duplicates_and_overlap_validation(self):
        holiday = self.db.add_holiday("2026-10-12", "2026-10-18")
        self.db.add_holiday("2026-10-12", "2026-10-18")
        self.assertEqual(len(self.db.get_setting("time_holidays")), 1)
        self.assertEqual(self.db.holiday_for_day("2026-10-12"), holiday)
        self.assertEqual(self.db.holiday_for_day("2026-10-18"), holiday)
        self.assertIsNone(self.db.holiday_for_day("2026-10-11"))
        self.assertIsNone(self.db.holiday_for_day("2026-10-19"))
        with self.assertRaisesRegex(ValueError, "chevauche"):
            self.db.add_holiday("2026-10-18", "2026-10-25")
        self.assertEqual(len(self.db.get_setting("time_holidays")), 1)

    def test_holidays_remove_only_automatic_unmodified_upcoming_entries(self):
        self.db.ensure_day("2026-10-12")
        rows = self.db.list_time_entries("2026-10-12", "2026-10-12")
        corrected = rows[-1]["id"]
        self.db.update_time_entry(corrected, title="Mathématiques · exception conservée")
        personal = self.db.add_time_entry("sport", "2026-10-12T18:00", "2026-10-12T19:00", status="planned")
        self.db.add_holiday("2026-10-12", "2026-10-18")
        remaining = self.db.list_time_entries("2026-10-12", "2026-10-12")
        self.assertEqual({row["id"] for row in remaining}, {corrected, personal})
        self.assertEqual(self.db.ensure_day("2026-10-12")["created"], 0)
        self.assertEqual(remaining, self.db.list_time_entries("2026-10-12", "2026-10-12"))
        self.assertEqual(self.db.time_totals("2026-10-12", "2026-10-12"), {})

    def test_midday_holiday_preserves_finished_sessions_and_older_days(self):
        self.db.ensure_day("2026-10-02")
        old = self.db.list_time_entries("2026-10-02", "2026-10-02")
        self.db.ensure_day("2026-10-05")
        rows = self.db.list_time_entries("2026-10-05", "2026-10-05")
        self.db.update_time_entry(rows[0]["id"], status="completed")
        self.db.add_holiday("2026-10-01", "2026-10-11")
        remaining = self.db.list_time_entries("2026-10-05", "2026-10-05")
        self.assertEqual([row["end_at"] for row in remaining], ["2026-10-05T11:00", "2026-10-05T12:00"])
        self.assertEqual(remaining[0]["status"], "completed")
        self.db.ensure_day("2026-10-02")
        self.assertEqual(old, self.db.list_time_entries("2026-10-02", "2026-10-02"))

    def test_resuming_regenerates_empty_future_snapshots_and_preserves_other_holidays(self):
        self.db.add_holiday("2026-10-12", "2026-10-25")
        self.db.add_holiday("2026-12-21", "2027-01-03", "Vacances de Noël")
        self.db.ensure_day("2026-10-19")
        self.assertEqual(self.db.list_time_entries("2026-10-19", "2026-10-19"), [])
        self.assertTrue(self.db.end_holiday("2026-10-19"))
        self.assertEqual(self.db.holiday_for_day("2026-10-18")["end"], "2026-10-18")
        self.assertIsNone(self.db.holiday_for_day("2026-10-19"))
        self.assertEqual(self.db.holiday_for_day("2026-12-25")["label"], "Vacances de Noël")
        rows = self.db.list_time_entries("2026-10-19", "2026-10-19")
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["status"] == "planned" for row in rows))
        self.assertFalse(self.db.end_holiday("2026-10-19"))
        self.assertEqual(rows, self.db.list_time_entries("2026-10-19", "2026-10-19"))

    def test_resuming_on_first_day_removes_that_range_and_restores_cancellations_correctly(self):
        self.db.ensure_day("2026-10-12")
        original = self.db.list_time_entries("2026-10-12", "2026-10-12")
        self.db.delete_time_entry(original[0]["id"])
        self.db.add_holiday("2026-10-12", "2026-10-18")
        self.db.end_holiday("2026-10-12")
        rows = self.db.list_time_entries("2026-10-12", "2026-10-12")
        self.assertEqual(len(rows), 4)
        self.assertNotIn(original[0]["id"], [row["id"] for row in rows])
        self.assertEqual(self.db.get_setting("time_holidays"), [])

    def test_resuming_at_midday_does_not_invent_morning_courses(self):
        self.now.return_value = datetime(2026, 10, 5, 7)
        self.db.add_holiday("2026-10-05", "2026-10-11")
        self.db.ensure_day("2026-10-05")
        self.now.return_value = datetime(2026, 10, 5, 12, 30)
        self.db.end_holiday("2026-10-05")
        rows = self.db.list_time_entries("2026-10-05", "2026-10-05")
        self.assertEqual([row["start_at"] for row in rows], ["2026-10-05T12:00", "2026-10-05T13:00", "2026-10-05T14:00"])
        self.assertEqual(self.db.time_totals("2026-10-05", "2026-10-05"), {})

    def test_past_holiday_snapshot_stays_empty_after_timetable_changes(self):
        self.db.add_holiday("2026-10-12", "2026-10-18")
        self.db.ensure_day("2026-10-12")
        self.now.return_value = datetime(2026, 10, 20, 12)
        self.db.set_semester("S2", "2026-10-01")
        self.db.ensure_day("2026-10-12")
        self.assertEqual(self.db.list_time_entries("2026-10-12", "2026-10-12"), [])
        with self.assertRaisesRegex(ValueError, "historique"):
            self.db.end_holiday("2026-10-12")

    def test_leap_day_and_year_boundaries_use_inclusive_calendar_dates(self):
        self.db.add_holiday("2028-02-26", "2028-03-03")
        self.assertIsNotNone(self.db.holiday_for_day("2028-02-29"))
        self.db.add_holiday("2026-12-28", "2027-01-10")
        self.assertIsNotNone(self.db.holiday_for_day("2027-01-01"))
        with self.assertRaises(ValueError):
            self.db.add_holiday("2027-02-29", "2027-03-02")
        with self.assertRaises(ValueError):
            self.db.add_holiday("2026-11-02", "2026-11-01")
        with self.assertRaises(ValueError):
            validate_holidays([dict(start="20261012", end="2026-10-18", label="Test")])


class HolidayPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        data, _ = prepare_data(self.temp.name, migrate=False)
        self.ctx = AppContext(data)
        self.ctx.db.set_setting("desktop_reduced_motion", True)
        self.widgets = []
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append(str(value))

    def tearDown(self):
        for widget in reversed(self.widgets):
            widget.close(); widget.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def keep(self, widget):
        self.widgets.append(widget)
        return widget

    def test_presets_cross_leap_day_and_allow_manual_end_adjustment(self):
        dialog = self.keep(HolidayDialog(self.ctx, "2028-02-26"))
        self.assertEqual(dialog.end.date(), QDate(2028, 3, 3))
        dialog.preset.setCurrentIndex(dialog.preset.findData("fortnight"))
        self.assertEqual(dialog.end.date(), QDate(2028, 3, 10))
        dialog.end.setDate(QDate(2028, 3, 8))
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.ctx.db.holiday_for_day("2028-02-29")["end"], "2028-03-08")

    def test_summer_requires_explicit_last_day_and_does_not_assume_school_dates(self):
        dialog = self.keep(HolidayDialog(self.ctx, "2028-07-03"))
        dialog.preset.setCurrentIndex(dialog.preset.findData("summer"))
        self.assertEqual(dialog.start.date(), dialog.end.date())
        dialog.save()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertIn("date de fin", dialog.error.text())
        dialog.end.setDate(QDate(2028, 8, 20))
        dialog.save(); dialog.save()
        self.assertEqual(len(self.ctx.db.get_setting("time_holidays")), 1)
        self.assertEqual(self.ctx.db.holiday_for_day("2028-08-20")["label"], "Vacances d’été")
        self.assertIsNone(self.ctx.db.holiday_for_day("2028-08-21"))

    def test_page_status_and_resumption_preserve_future_holidays(self):
        page = self.keep(TimeTrackingPage(self.ctx))
        page.day.setDate(QDate(2028, 2, 28))
        self.ctx.db.add_holiday("2028-02-26", "2028-03-03")
        self.ctx.db.add_holiday("2028-07-03", "2028-08-20", "Été")
        self.ctx.mark_changed()
        self.assertIn("Vacances scolaires", page.holiday_status.text())
        self.assertEqual(page.rows, [])
        with patch("mpsi_desktop.time_tracking.confirm", return_value=True):
            page.resume_courses()
        self.assertIn("Les cours suivent ton emploi du temps", page.holiday_status.text())
        self.assertTrue(page.rows)
        self.assertIsNotNone(self.ctx.db.holiday_for_day("2028-07-03"))


if __name__ == "__main__":
    unittest.main()
