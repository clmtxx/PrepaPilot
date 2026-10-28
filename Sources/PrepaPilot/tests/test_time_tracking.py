"""Regression coverage for actual time, dated schedules and UI persistence."""
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QDate, QDateTime, QEvent
from PySide6.QtWidgets import QApplication, QDialog
from mpsi_desktop.catalog import CATEGORIES
from mpsi_desktop.context import AppContext, DesktopStore, prepare_data
from mpsi_desktop.time_store import validate_timetable
from mpsi_desktop.time_tracking import ActivityDialog, TimeTrackingPage, TimetableDialog

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class TimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DesktopStore(Path(self.temp.name) / 'data.sqlite3')
        self.now = patch.object(self.db, "_time_now", return_value=datetime(2026, 10, 4, 20))
        self.now.start()

    def tearDown(self):
        self.now.stop()
        self.db.close()
        self.temp.cleanup()

    def test_default_left_group_sessions_are_exact_and_not_counted_until_confirmed(self):
        self.db.ensure_day("2026-09-28")
        rows = self.db.list_time_entries("2026-09-28", "2026-09-28")
        self.assertEqual(rows[0]["start_at"], "2026-09-28T09:30")
        self.assertEqual(rows[1]["start_at"], "2026-09-28T11:00")
        self.assertEqual(rows[2]["category"], "permanence")
        self.assertEqual(self.db.time_totals("2026-09-28", "2026-09-28"), {})
        self.assertEqual(self.db.complete_day("2026-09-28"), 5)
        self.assertEqual(self.db.time_totals("2026-09-28", "2026-09-28")["maths"], 180)
        self.assertEqual(self.db.complete_day("2026-09-28"), 0)

    def test_idempotent_autofill_retains_ids_including_future_sessions(self):
        first = self.db.ensure_day("2026-10-05")
        rows = self.db.list_time_entries("2026-10-05", "2026-10-05")
        second = self.db.ensure_day("2026-10-05")
        self.assertGreater(first["created"], 0)
        self.assertEqual(second["created"], 0)
        self.assertEqual(rows, self.db.list_time_entries("2026-10-05", "2026-10-05"))

    def test_absent_professor_cancellation_and_override_survive_regeneration(self):
        self.db.ensure_day("2026-10-05")
        rows = self.db.list_time_entries("2026-10-05", "2026-10-05")
        self.db.delete_time_entry(rows[0]["id"])
        self.db.update_time_entry(rows[-1]["id"], title="Maths · séance déplacée", start_at="2026-10-05T15:00")
        self.db.ensure_day("2026-10-05")
        updated = self.db.list_time_entries("2026-10-05", "2026-10-05")
        self.assertEqual(len(updated), len(rows) - 1)
        self.assertNotIn(rows[0]["id"], [row["id"] for row in updated])
        self.assertEqual(updated[-1]["start_at"], "2026-10-05T15:00")

    def test_semester_change_preserves_past_and_manual_future_overrides(self):
        self.db.ensure_day("2026-09-28")
        historical = self.db.list_time_entries("2026-09-28", "2026-09-28")
        self.db.ensure_day("2026-10-05")
        future = self.db.list_time_entries("2026-10-05", "2026-10-05")
        self.db.update_time_entry(future[-1]["id"], title="Maths · exception")
        self.db.set_semester("S2", "2026-10-05")
        self.assertEqual(self.db.semester_for_day("2026-10-04"), "S1")
        self.assertEqual(self.db.semester_for_day("2026-10-05"), "S2")
        self.assertEqual(historical, self.db.list_time_entries("2026-09-28", "2026-09-28"))
        future = self.db.list_time_entries("2026-10-05", "2026-10-05")
        self.assertEqual(future[0]["start_at"], "2026-10-05T08:00")
        self.assertEqual(future[1]["start_at"], "2026-10-05T09:00")
        self.assertEqual(future[-1]["title"], "Maths · exception")
        self.assertIn("tipe", [row["category"] for row in future])

    def test_retrospective_semester_change_keeps_snapshotted_day(self):
        self.db.ensure_day("2026-09-28")
        before = self.db.list_time_entries("2026-09-28", "2026-09-28")
        self.db.set_semester("S2", "2026-09-01")
        self.db.ensure_day("2026-09-28")
        self.assertEqual(before, self.db.list_time_entries("2026-09-28", "2026-09-28"))

    def test_overnight_sleep_is_split_by_day_without_double_count(self):
        self.db.add_time_entry("sommeil", "2026-09-28T23:00", "2026-09-29T07:00")
        self.assertEqual(self.db.time_totals("2026-09-28", "2026-09-28"), {"sommeil": 60})
        self.assertEqual(self.db.time_totals("2026-09-29", "2026-09-29"), {"sommeil": 420})
        self.assertEqual(self.db.time_totals("2026-09-28", "2026-09-29"), {"sommeil": 480})

    def test_future_work_cannot_be_completed_and_bulk_skips_it(self):
        with self.assertRaisesRegex(ValueError, "pas encore terminée"):
            self.db.add_time_entry("maths", "2026-10-05T18:00", "2026-10-05T19:00")
        self.db.ensure_day("2026-10-05")
        self.assertEqual(self.db.complete_day("2026-10-05"), 0)
        self.assertEqual(self.db.time_totals(), {})

    def test_overlap_prevention_covers_manual_and_timetable_entries_and_allows_boundaries(self):
        identity = self.db.add_time_entry("sport", "2026-09-28T18:00", "2026-09-28T19:00")
        with self.assertRaisesRegex(ValueError, "chevauche"):
            self.db.add_time_entry("detente", "2026-09-28T18:30", "2026-09-28T19:30")
        self.db.add_time_entry("repas", "2026-09-28T19:00", "2026-09-28T20:00")
        with self.assertRaisesRegex(ValueError, "chevauche"):
            self.db.update_time_entry(identity, end_at="2026-09-28T19:30")
        self.db.add_time_entry("trajet", "2026-09-28T09:00", "2026-09-28T10:00")
        result = self.db.ensure_day("2026-09-28")
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertFalse(any(row["start_at"] == "2026-09-28T09:30" for row in self.db.list_time_entries()))

    def test_personal_template_allows_other_languages_and_rejects_overlap(self):
        timetable = self.db.get_timetable()
        timetable["semesters"]["S1"].append(dict(id="personal-de", weekday=6, start="10:00", end="11:00", category="allemand", title="Allemand"))
        self.db.save_timetable(timetable)
        self.db.ensure_day("2026-10-04")
        self.assertEqual(self.db.list_time_entries("2026-10-04", "2026-10-04")[0]["category"], "allemand")
        timetable["semesters"]["S1"].append(dict(id="overlap", weekday=6, start="10:30", end="11:30", category="eps", title="EPS"))
        with self.assertRaisesRegex(ValueError, "chevauchent"):
            validate_timetable(timetable)

    def test_bulk_validation_includes_sleep_ending_on_selected_day(self):
        self.db.add_time_entry("sommeil", "2026-09-28T23:00", "2026-09-29T07:00", status="planned")
        self.assertEqual(self.db.complete_day("2026-09-29"), 1)
        self.assertEqual(self.db.time_totals("2026-09-29", "2026-09-29"), {"sommeil": 420})


class TimePageTests(unittest.TestCase):
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

    def test_activity_dialog_can_retry_failed_save_and_never_duplicate_success(self):
        dialog = self.keep(ActivityDialog(self.ctx, day="2026-09-20"))
        dialog.start.setDateTime(QDateTime.fromString("2026-09-20T18:00", "yyyy-MM-ddTHH:mm"))
        dialog.end.setDateTime(QDateTime.fromString("2026-09-20T19:00", "yyyy-MM-ddTHH:mm"))
        with patch.object(self.ctx.db, "add_time_entry", side_effect=sqlite3.OperationalError("Base occupée")):
            dialog.save()
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.save(); dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(self.ctx.db.list_time_entries()), 1)
        self.assertEqual(dialog.category.count(), len(CATEGORIES))

    def test_page_bulk_validation_totals_and_saved_selection(self):
        page = self.keep(TimeTrackingPage(self.ctx))
        page.day.setDate(QDate(2026, 9, 21))
        self.assertIn("0 min réalisées", page.total_summary.text())
        with patch("mpsi_desktop.time_tracking.confirm", return_value=True):
            page.complete_day()
        self.assertTrue(all(row["status"] == "completed" for row in page.rows))
        identity = self.ctx.db.add_time_entry("sport", "2026-09-21T18:00", "2026-09-21T19:00")
        page.show_saved(identity)
        self.assertEqual(page.selected_entry()["id"], identity)
        page.period.setCurrentIndex(page.period.findData("week"))
        self.assertNotIn("0 min réalisées", page.total_summary.text())
        page.period.setCurrentIndex(page.period.findData("custom"))
        page.from_date.setDate(QDate(2026, 9, 25))
        page.to_date.setDate(QDate(2026, 9, 20))
        self.assertIn("fin de la période", page.total_summary.text())

    def test_timetable_editor_preserves_edits_while_switching_semesters(self):
        dialog = self.keep(TimetableDialog(self.ctx))
        dialog.table.item(0, 4).setText("Cours personnalisé")
        dialog.semester.setCurrentIndex(1)
        dialog.semester.setCurrentIndex(0)
        self.assertEqual(dialog.table.item(0, 4).text(), "Cours personnalisé")
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.ctx.db.get_timetable()["semesters"]["S1"][0]["title"], "Cours personnalisé")


if __name__ == "__main__":
    unittest.main()
