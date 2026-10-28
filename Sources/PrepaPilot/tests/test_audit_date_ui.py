"""Exercise the actual Qt date selector limits, including 31 December 9999."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QDate, QEvent
from PySide6.QtWidgets import QApplication, QDialog

from mpsi_desktop.context import AppContext, prepare_data
from mpsi_desktop.progression_page import ProgressionPage
from mpsi_desktop.time_tracking import ActivityDialog, HolidayDialog, TimeTrackingPage
from mpsi_desktop.window import MainWindow


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class DateSelectorAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        data, _ = prepare_data(self.temporary.name, migrate=False)
        self.ctx = AppContext(data)
        self.ctx.db.set_setting("desktop_reduced_motion", True)
        self.widgets = []

    def tearDown(self):
        for widget in reversed(self.widgets):
            if isinstance(widget, ProgressionPage):
                widget.shutdown()
            widget.close()
            widget.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temporary.cleanup()

    def keep(self, widget):
        self.widgets.append(widget)
        return widget

    def test_journal_all_filters_render_at_both_selector_limits(self):
        page = self.keep(TimeTrackingPage(self.ctx))
        for chosen in (page.day.minimumDate(), page.day.maximumDate()):
            page.day.blockSignals(True)
            page.day.setDate(chosen)
            page.day.blockSignals(False)
            page.from_date.blockSignals(True)
            page.to_date.blockSignals(True)
            page.from_date.setDate(chosen)
            page.to_date.setDate(chosen)
            page.from_date.blockSignals(False)
            page.to_date.blockSignals(False)
            for mode in ("day", "week", "all", "custom"):
                with self.subTest(date=chosen.toString("yyyy-MM-dd"), mode=mode):
                    page.period.blockSignals(True)
                    page.period.setCurrentIndex(page.period.findData(mode))
                    page.period.blockSignals(False)
                    page.refresh()
                    self.assertNotIn("invalide", page.total_summary.text())
                    self.assertNotEqual(page.completed_stat.value.text(), "—")

    def test_holiday_dialog_opens_and_saves_at_maximum_journal_date(self):
        page = self.keep(TimeTrackingPage(self.ctx))
        maximum = page.day.maximumDate()
        dialog = self.keep(HolidayDialog(self.ctx, maximum.toString("yyyy-MM-dd")))
        self.assertEqual(dialog.start.date(), maximum)
        self.assertEqual(dialog.end.date(), maximum)
        self.assertNotIn("10000", dialog.summary.text())
        self.assertIn("9999", dialog.summary.text())
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        holiday = self.ctx.db.holiday_for_day(maximum.toString("yyyy-MM-dd"))
        self.assertEqual(holiday["start"], "9999-12-31")
        self.assertEqual(holiday["end"], "9999-12-31")

    def test_holiday_presets_near_maximum_stay_in_selector_range(self):
        dialog = self.keep(HolidayDialog(self.ctx, "9999-12-29"))
        self.assertEqual(dialog.end.date(), dialog.end.maximumDate())
        for preset in ("fortnight", "week", "summer", "custom"):
            with self.subTest(preset=preset):
                dialog.preset.setCurrentIndex(dialog.preset.findData(preset))
                dialog.apply_preset()
                self.assertGreaterEqual(dialog.end.date(), dialog.start.date())
                self.assertLessEqual(dialog.end.date(), dialog.end.maximumDate())

    def test_activity_dialog_uses_both_journal_date_limits(self):
        page = self.keep(TimeTrackingPage(self.ctx))
        for chosen in (page.day.minimumDate(), page.day.maximumDate()):
            with self.subTest(date=chosen.toString("yyyy-MM-dd")):
                dialog = self.keep(ActivityDialog(self.ctx, chosen.toString("yyyy-MM-dd")))
                self.assertEqual(dialog.start.date(), chosen)
                self.assertEqual(dialog.end.date(), chosen)
                self.assertGreater(dialog.start.dateTime().secsTo(dialog.end.dateTime()), 0)

    def test_progression_modes_render_and_navigation_clamps_at_actual_limits(self):
        page = self.keep(ProgressionPage(self.ctx))
        for mode in ("week", "month", "quarter"):
            page.set_mode(mode)
            for chosen in (page.date_picker.minimumDate(), page.date_picker.maximumDate()):
                with self.subTest(mode=mode, date=chosen.toString("yyyy-MM-dd")):
                    page.date_picker.setDate(chosen)
                    page.refresh()
                    self.assertGreaterEqual(page.anchor, date(2000, 1, 1))
                    self.assertLessEqual(page.anchor, date.today())
                    self.assertEqual(len(page.history), 12)
            page.date_picker.setDate(page.date_picker.minimumDate())
            page.shift_period(-1)
            self.assertEqual(page.date_picker.date(), page.date_picker.minimumDate())
            page.date_picker.setDate(page.date_picker.maximumDate())
            page.shift_period(1)
            self.assertEqual(page.date_picker.date(), page.date_picker.maximumDate())

    def test_window_starts_and_all_pages_render_with_extreme_saved_dates(self):
        self.ctx.db.add_grade("maths", "DS", 10, 20, "1752-09-14")
        self.ctx.db.add_grade("maths", "DS", 15, 20, "9999-12-31")
        self.ctx.db.add_time_entry("maths", "1752-09-14T09:00", "1752-09-14T10:00")
        self.ctx.db.add_time_entry("maths", "9999-12-31T09:00", "9999-12-31T10:00", status="planned")
        with patch.object(MainWindow, "check_updates_automatically"):
            window = self.keep(MainWindow(self.ctx, show_welcome=False))
            for key in window.pages:
                window.navigate(key)
            APP.processEvents()
        self.assertEqual(len(self.ctx.db.list_grades()), 2)
        self.assertEqual(self.ctx.db.time_totals("1752-09-14", "1752-09-14"), {"maths": 60})


if __name__ == "__main__":
    unittest.main()
