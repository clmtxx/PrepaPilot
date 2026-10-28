"""English timetable, activity journal and first-run setup integration."""
from datetime import date, datetime
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QDate, QEvent, QLocale
from PySide6.QtWidgets import QApplication, QLabel

from mpsi_desktop.catalog import SUBJECTS, duration_text
from mpsi_desktop.context import AppContext
from mpsi_desktop.dashboard import DashboardPage
from mpsi_desktop.i18n import set_language
from mpsi_desktop.schedule_setup import SetupDialog
from mpsi_desktop.study_profile import example_profile, new_schedule_labels, schedule_labels
from mpsi_desktop.time_store import local_stamp, validate_holidays, validate_timetable
from mpsi_desktop.time_tracking import ActivityDialog, HolidayDialog, TimeTrackingPage

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ScheduleLanguageTests(unittest.TestCase):
    def setUp(self):
        set_language("fr")
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / "data")
        self.ctx.db.set_setting("desktop_reduced_motion", True)
        self.widgets = []
        self.clock = patch.object(self.ctx.db, "_time_now", return_value=datetime(2026, 9, 30, 20))
        self.clock.start()
        set_language("en")

    def tearDown(self):
        for widget in reversed(self.widgets):
            if isinstance(widget, DashboardPage):
                widget.timer.stop()
                widget.day_timer.stop()
            widget.close()
            widget.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.clock.stop()
        self.ctx.close()
        self.temp.cleanup()
        set_language("fr")

    def keep(self, widget):
        self.widgets.append(widget)
        return widget

    def test_new_examples_are_english_but_identifiers_and_original_catalogue_stay_stable(self):
        subjects, timetable = example_profile("2026-08-31")
        self.assertEqual([row["name"] for row in subjects],
                         ["Mathematics", "Writing skills", "English", "Computer science", "Study skills"])
        self.assertEqual(timetable["semesters"]["S1"][-1]["title"], "Workshop")
        self.assertEqual(new_schedule_labels(), {"S1": "Main schedule", "S2": "Alternative schedule"})
        self.assertEqual(SUBJECTS["maths"], "Mathématiques")
        set_language("fr")
        french_subjects, french_timetable = example_profile("2026-08-31")
        self.assertEqual([row["id"] for row in subjects], [row["id"] for row in french_subjects])
        self.assertEqual([row["id"] for row in timetable["semesters"]["S1"]],
                         [row["id"] for row in french_timetable["semesters"]["S1"]])
        self.assertEqual(duration_text(65), "1 h 05")
        set_language("en")
        self.assertEqual(duration_text(65), "1 hr 05 min")

    def test_english_validation_preserves_personal_titles_in_errors(self):
        with self.assertRaisesRegex(ValueError, "Choose a valid local date and time"):
            local_stamp("invalid")
        with self.assertRaisesRegex(ValueError, "on or after"):
            validate_holidays([dict(start="2026-10-05", end="2026-10-01", label="Mes vacances")])
        with self.assertRaisesRegex(ValueError, "reference date.*Monday"):
            validate_timetable(dict(version=2, week_anchor="2026-09-01", semesters={"S1": [], "S2": []}))
        self.ctx.db.add_time_entry("sport", "2026-10-04T10:00", "2026-10-04T11:00", title="Mon entraînement", status="planned")
        with self.assertRaisesRegex(ValueError, "overlaps.*Mon entraînement"):
            self.ctx.db.add_time_entry("sport", "2026-10-04T10:30", "2026-10-04T11:30", status="planned")
        with self.assertRaisesRegex(ValueError, "Keep it marked as Planned"):
            self.ctx.db.add_time_entry("sport", "2026-10-05T10:00", "2026-10-05T11:00", status="completed")

    def test_first_run_editor_has_english_controls_days_and_examples(self):
        dialog = self.keep(SetupDialog(self.ctx, first_run=True))
        self.assertEqual(dialog.windowTitle(), "Set up PrépaPilot")
        self.assertEqual(dialog.day_filter.itemText(1), "Monday")
        self.assertEqual(dialog.subject_table.horizontalHeaderItem(0).text(), "Subject")
        self.assertEqual(dialog.table.horizontalHeaderItem(5).text(), "Repeats")
        self.assertEqual(dialog.anchor.locale().language(), QLocale.English)
        dialog.next_step()
        self.assertEqual(dialog.error.text(), "Choose “Start from scratch” or “Use an example”.")
        dialog.use_example()
        self.assertEqual(dialog.subject_table.item(0, 0).text(), "Mathematics")
        self.assertIn("Monday", dialog.preview.accessibleDescription())
        self.assertIn("week", dialog.preview.accessibleDescription())
        self.assertIn("week of", dialog.anchor_hint.text())

    def test_holiday_dialog_uses_english_dates_and_requires_explicit_summer_end(self):
        dialog = self.keep(HolidayDialog(self.ctx, "2026-10-01"))
        self.assertEqual(dialog.windowTitle(), "Holidays and breaks")
        self.assertEqual(dialog.name.text(), "Class break")
        self.assertIn("7 days", dialog.summary.text())
        self.assertIn("October", dialog.summary.text())
        dialog.preset.setCurrentIndex(dialog.preset.findData("summer"))
        self.assertEqual(dialog.name.text(), "Summer holiday")
        dialog.save()
        self.assertIn("Choose the last day", dialog.error.text())
        dialog.end.setDate(dialog.start.date().addDays(10))
        self.assertIn("11 days", dialog.summary.text())
        dialog.save()
        self.assertEqual(self.ctx.db.get_setting("time_holidays")[0]["label"], "Summer holiday")

    def test_activity_editor_translates_controls_and_preserves_existing_title(self):
        identity = self.ctx.db.add_time_entry("sport", "2026-10-04T10:00", "2026-10-04T11:05",
                                              title="Révisions à moi", status="planned")
        entry = next(row for row in self.ctx.db.list_time_entries("2026-10-04", "2026-10-04") if row["id"] == identity)
        dialog = self.keep(ActivityDialog(self.ctx, entry=entry))
        self.assertEqual(dialog.windowTitle(), "Edit activity")
        self.assertEqual(dialog.title.text(), "Révisions à moi")
        self.assertEqual(dialog.duration.text(), "Duration: 1 hr 05 min")
        self.assertEqual(dialog.start.locale().language(), QLocale.English)
        self.assertEqual(dialog.status.currentData(), "planned")
        self.assertEqual(dialog.status.itemText(0), "Completed · include in my totals")

    def test_journal_recreation_changes_copy_without_changing_stored_data(self):
        self.ctx.db.set_setting("desktop_schedule_labels", {"S1": "Mes cours", "S2": "Mes stages"})
        self.ctx.db.add_time_entry("sport", "2026-09-30T18:00", "2026-09-30T19:00", title="Séance personnelle")
        set_language("fr")
        page = self.keep(TimeTrackingPage(self.ctx))
        page.day.setDate(QDate(2026, 9, 30))
        before = (self.ctx.db.get_timetable(), self.ctx.db.get_subjects(include_archived=True),
                  self.ctx.db.list_time_entries("2026-09-30", "2026-09-30"))
        set_language("en")
        english = self.keep(TimeTrackingPage(self.ctx))
        english.day.setDate(QDate(2026, 9, 30))
        after = (self.ctx.db.get_timetable(), self.ctx.db.get_subjects(include_archived=True),
                 self.ctx.db.list_time_entries("2026-09-30", "2026-09-30"))
        self.assertEqual(after, before)
        self.assertEqual(schedule_labels(self.ctx.db), {"S1": "Mes cours", "S2": "Mes stages"})
        self.assertIn("Wednesday", english.journal_title.text())
        self.assertIn("September", english.journal_title.text())
        self.assertIn("Mes cours · week", english.semester_label.text())
        self.assertEqual(english.table.horizontalHeaderItem(2).text(), "Category")
        self.assertIn("Séance personnelle", [english.table.item(row, 1).text() for row in range(english.table.rowCount())])

    def test_dashboard_uses_english_dates_and_reuses_running_session(self):
        with patch.object(DashboardPage, "_today", return_value=date(2026, 9, 30)):
            home = self.keep(DashboardPage(self.ctx, lambda _: None))
            self.assertEqual(home.tomorrow_title.text(), "Thursday 1 October")
            self.assertEqual(home.focus_button.text(), "Start")
            self.assertIn("TOMORROW", [label.text() for label in home.findChildren(QLabel)])
            home.focus_session.start(category="maths", title="Mon objectif", minutes=25)
            home._sync_focus()
            replacement = self.keep(DashboardPage(self.ctx, lambda _: None))
            self.assertIs(replacement.focus_session, home.focus_session)
            self.assertEqual(replacement.focus_session.status, "running")
            self.assertIn("Mon objectif", replacement.focus_caption.text())


if __name__ == "__main__":
    unittest.main()
