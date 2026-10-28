"""Configuration UI: draft isolation, alternating weeks and stable subjects."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QDate, QEvent, QTime, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog
from mpsi_desktop.context import AppContext, prepare_data
from mpsi_desktop.schedule_setup import SetupDialog
from mpsi_desktop.time_tracking import ActivityDialog, TimeTrackingPage, TimetableDialog

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class SetupDialogTests(unittest.TestCase):
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

    def empty_setup(self):
        dialog = self.keep(SetupDialog(self.ctx, first_run=True))
        today = QDate.currentDate()
        self.assertEqual(dialog.anchor.date(), today.addDays(1 - today.dayOfWeek()))
        dialog.start_empty()
        dialog.subject_table.item(0, 0).setText("Biologie")
        return dialog

    def test_first_run_requires_choice_and_cancel_does_not_write(self):
        subjects = self.ctx.db.get_subjects()
        timetable = self.ctx.db.get_timetable()
        dialog = self.keep(SetupDialog(self.ctx, first_run=True))
        dialog.next_step()
        self.assertEqual(dialog.steps.currentIndex(), 0)
        self.assertIn("Choisis", dialog.error.text())
        dialog.start_empty()
        dialog.subject_table.item(0, 0).setText("Biologie")
        dialog.reject()
        self.assertEqual(subjects, self.ctx.db.get_subjects())
        self.assertEqual(timetable, self.ctx.db.get_timetable())
        self.assertFalse(self.ctx.db.get_setting("setup_completed", False))

    def test_blank_setup_saves_personal_subject_color_and_sunday_week_a(self):
        dialog = self.empty_setup()
        identity = dialog.subject_table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        color_button = dialog.subject_table.cellWidget(0, 1)
        with patch("mpsi_desktop.schedule_setup.QColorDialog.getColor", return_value=QColor("#9f268d")):
            dialog.choose_color(color_button)
        dialog.next_step()
        self.assertEqual(dialog.steps.currentIndex(), 1)
        self.assertEqual(dialog.table.rowCount(), 0)
        dialog.day_filter.setCurrentIndex(dialog.day_filter.findData(6))
        dialog.week_filter.setCurrentIndex(dialog.week_filter.findData("A"))
        dialog.add_slot()
        dialog.anchor.setDate(QDate(2028, 3, 1))
        self.assertEqual(dialog.anchor.date(), QDate(2028, 2, 28))
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(self.ctx.db.get_setting("setup_completed"))
        self.assertEqual(self.ctx.db.subject_labels(), {identity: "Biologie"})
        self.assertEqual(self.ctx.db.category_color(identity), "#9F268D")
        slot = self.ctx.db.get_timetable()["semesters"]["S1"][0]
        self.assertEqual((slot["weekday"], slot["week"], slot["category"]), (6, "A", identity))
        self.assertEqual(self.ctx.db.week_for_day("2028-03-05"), "A")
        self.assertEqual(self.ctx.db.week_for_day("2028-03-12"), "B")

    def test_explicit_example_keeps_sessions_and_is_only_saved_at_finish(self):
        dialog = self.keep(SetupDialog(self.ctx, first_run=True))
        dialog.use_example()
        self.assertEqual({row['name'] for row in dialog.subject_rows},
                         {'Mathématiques', 'Expression écrite', 'Anglais', 'Informatique', 'Méthodologie'})
        self.assertEqual(len(dialog.data['semesters']['S1']), 11)
        self.assertFalse(self.ctx.db.get_setting("setup_completed", False))
        dialog.next_step()
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(self.ctx.db.get_timetable()["semesters"]["S1"]), 11)

    def test_blank_setup_can_use_a_standard_subject_name(self):
        dialog = self.empty_setup()
        dialog.subject_table.item(0, 0).setText("Mathématiques")
        dialog.next_step()
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(list(self.ctx.db.subject_labels().values()), ["Mathématiques"])
        self.assertTrue(self.ctx.db.get_setting("setup_completed"))

    def test_filters_keep_hidden_days_semesters_and_opposite_week_slots(self):
        dialog = self.empty_setup()
        dialog.next_step()
        dialog.add_slot()  # Monday, every week.
        dialog.table.item(0, 4).setText("Lundi commun")
        dialog.day_filter.setCurrentIndex(dialog.day_filter.findData(6))
        dialog.week_filter.setCurrentIndex(dialog.week_filter.findData("B"))
        dialog.add_slot()
        dialog.table.item(0, 4).setText("Dimanche B")
        dialog.week_filter.setCurrentIndex(dialog.week_filter.findData("A"))
        self.assertEqual(dialog.table.rowCount(), 0)
        dialog.add_slot()
        dialog.table.item(0, 4).setText("Dimanche A")
        dialog.semester.setCurrentIndex(dialog.semester.findData("S2"))
        dialog.add_slot()
        dialog.table.item(0, 4).setText("Second semestre")
        dialog.semester.setCurrentIndex(dialog.semester.findData("S1"))
        dialog.week_filter.setCurrentIndex(dialog.week_filter.findData("any"))
        dialog.day_filter.setCurrentIndex(dialog.day_filter.findData(-1))
        self.assertEqual(dialog.table.rowCount(), 3)
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        timetable = self.ctx.db.get_timetable()
        self.assertEqual({row["title"] for row in timetable["semesters"]["S1"]}, {"Lundi commun", "Dimanche A", "Dimanche B"})
        self.assertEqual(timetable["semesters"]["S2"][0]["title"], "Second semestre")

    def test_remove_filtered_slot_does_not_remove_other_days(self):
        dialog = self.empty_setup()
        dialog.next_step()
        dialog.add_slot()
        dialog.day_filter.setCurrentIndex(dialog.day_filter.findData(6))
        dialog.add_slot()
        dialog.table.selectRow(0)
        dialog.remove_slot()
        dialog.day_filter.setCurrentIndex(dialog.day_filter.findData(-1))
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertEqual(dialog.table.cellWidget(0, 0).currentData(), 0)

    def test_editing_keeps_existing_schedule_and_archives_without_deleting_history(self):
        before = self.ctx.db.get_timetable()
        identity = self.ctx.db.add_time_entry("maths", "2026-09-20T18:00", "2026-09-20T19:00")
        dialog = self.keep(TimetableDialog(self.ctx))
        self.assertEqual(dialog.steps.currentIndex(), 1)
        self.assertEqual(dialog.data["semesters"], before["semesters"])
        dialog.go_back()
        maths_row = next(index for index in range(dialog.subject_table.rowCount()) if dialog.subject_table.item(index, 0).data(Qt.ItemDataRole.UserRole) == "maths")
        dialog.subject_table.item(maths_row, 0).setText("Maths avancées")
        dialog.subject_table.cellWidget(maths_row, 2).setChecked(False)
        dialog.next_step()
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertNotIn("maths", self.ctx.db.subject_labels())
        self.assertEqual(self.ctx.db.subject_labels(include_archived=True)["maths"], "Maths avancées")
        self.assertEqual(self.ctx.db.list_time_entries()[0]["id"], identity)
        self.assertEqual(self.ctx.db.time_totals()["maths"], 60)

    def test_invalid_schedule_or_database_failure_keeps_draft_and_allows_retry(self):
        before = self.ctx.db.get_subjects()
        dialog = self.empty_setup()
        dialog.next_step()
        dialog.add_slot(); dialog.add_slot()
        dialog.save()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.ctx.db.get_subjects(), before)
        self.assertFalse(self.ctx.db.get_setting("setup_completed", False))
        dialog.table.selectRow(1)
        dialog.remove_slot()
        with patch.object(self.ctx.db, "save_setup", side_effect=sqlite3.OperationalError("Base occupée")):
            dialog.save()
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertIn("Base occupée", dialog.error.text())
        dialog.save(); dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(self.ctx.db.get_timetable()["semesters"]["S1"]), 1)

    def test_journal_uses_custom_labels_colors_and_archived_subject_in_editor(self):
        dialog = self.empty_setup()
        dialog.next_step(); dialog.save()
        subject = self.ctx.db.get_subjects(include_archived=False)[0]
        identity = self.ctx.db.add_time_entry(subject["id"], "2026-09-20T18:00", "2026-09-20T19:00")
        page = self.keep(TimeTrackingPage(self.ctx))
        page.day.setDate(QDate(2026, 9, 20))
        page.show_saved(identity)
        self.assertEqual(page.table.item(0, 2).text(), "Biologie")
        self.assertEqual(page.table.item(0, 2).foreground().color().name().upper(), subject["color"])
        self.ctx.db.save_subjects([{**row, "active": False} for row in self.ctx.db.get_subjects()])
        entry = self.ctx.db.list_time_entries("2026-09-20", "2026-09-20")[0]
        editor = self.keep(ActivityDialog(self.ctx, entry=entry))
        self.assertEqual(editor.category.currentData(), subject["id"])
        self.assertIn("archivée", editor.category.currentText())
        self.assertEqual(self.ctx.db.time_totals("2026-09-20", "2026-09-20")[subject["id"]], 60)


if __name__ == "__main__":
    unittest.main()
