"""User-facing progression controls, persistence and read-only rendering."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime, timedelta
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QDate, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from mpsi_desktop.context import AppContext, prepare_data
from mpsi_desktop.progression import load_targets, save_targets
from mpsi_desktop.progression_page import ProgressionPage, ProgressionTargetsDialog
from mpsi_desktop.theme import apply_theme
from mpsi_desktop.widgets import scroll_page


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ProgressionPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        data, _ = prepare_data(self.temp.name, migrate=False)
        self.ctx = AppContext(data)
        self.ctx.db.set_setting("desktop_reduced_motion", True)
        self.page = None
        self.dialogs = []
        apply_theme(APP, "light")

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        if self.page:
            self.page.shutdown()
            self.page.close()
            self.page.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()

    def page_with_history(self):
        self.ctx.db.add_time_entry("maths", "2026-09-21T09:00", "2026-09-21T12:00")
        self.ctx.db.add_time_entry("maths", "2026-09-28T09:00", "2026-09-28T10:00")
        self.page = ProgressionPage(self.ctx)
        self.page.set_mode("week")
        self.page.date_picker.setDate(QDate(2026, 9, 29))
        return self.page

    def test_construction_refresh_and_theme_do_not_write_or_create_activities(self):
        with patch.object(self.ctx.db, "set_setting") as write, patch.object(self.ctx.db, "ensure_day") as ensure:
            self.page = ProgressionPage(self.ctx)
            self.page.refresh()
            self.page._theme_changed()
            write.assert_not_called()
            ensure.assert_not_called()
        self.assertEqual(load_targets(self.ctx.db), dict(work=0, sleep=0, sport=0, rest=0))
        self.assertFalse(self.page.report["has_data"])
        self.assertFalse(self.page.empty_card.isHidden())
        self.assertFalse(self.page.targets_prompt.isHidden())
        self.assertTrue(self.page.scores_container.isHidden())

    def test_annual_history_reused_for_navigation_and_refreshed_on_write_or_clock(self):
        from mpsi_desktop import progression
        now = datetime.now().replace(second=10, microsecond=0)
        with (patch('mpsi_desktop.progression_page.datetime') as clock,
              patch('mpsi_desktop.progression_page.progression.annual_history', wraps=progression.annual_history) as history):
            clock.now.return_value = now
            clock.combine.side_effect = datetime.combine
            clock.min = datetime.min
            self.page = ProgressionPage(self.ctx)
            self.page.set_mode('month')
            self.page.set_mode('quarter')
            self.page._theme_changed()
            self.assertEqual(history.call_count, 1)
            self.ctx.db.add_time_entry('maths', '2026-09-21T09:00', '2026-09-21T10:00')
            self.page.refresh()
            self.assertEqual(history.call_count, 2)
            clock.now.return_value = now + timedelta(minutes=1)
            self.page.refresh()
            self.assertEqual(history.call_count, 3)

    def test_unchanged_refresh_preserves_table_items_and_avoids_theme_repolishing(self):
        page = self.page_with_history()
        subject = page.subjects.item(0, 0)
        history = page.history_table.item(0, 0)
        with patch.object(page.hero_card, 'setStyleSheet') as style:
            page.refresh()
            style.assert_not_called()
        self.assertIs(page.subjects.item(0, 0), subject)
        self.assertIs(page.history_table.item(0, 0), history)

    def test_personal_targets_save_in_selected_units_and_cancel_has_no_effect(self):
        cancelled = ProgressionTargetsDialog(self.ctx)
        self.dialogs.append(cancelled)
        cancelled.inputs["work"].setValue(18)
        cancelled.reject()
        self.assertEqual(load_targets(self.ctx.db)["work"], 0)
        dialog = ProgressionTargetsDialog(self.ctx)
        self.dialogs.append(dialog)
        for key, value in dict(work=20, sleep=8, sport=2.5, rest=1.25).items():
            dialog.inputs[key].setValue(value)
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(load_targets(self.ctx.db), dict(work=1200, sleep=3360, sport=150, rest=525))
        reread = ProgressionTargetsDialog(self.ctx)
        self.dialogs.append(reread)
        self.assertEqual(reread.inputs["sleep"].value(), 8)
        self.assertEqual(reread.inputs["rest"].value(), 1.25)

    def test_invalid_target_budget_can_be_corrected_without_losing_old_values(self):
        save_targets(self.ctx.db, dict(work=1200, sleep=0, sport=0, rest=0))
        dialog = ProgressionTargetsDialog(self.ctx)
        self.dialogs.append(dialog)
        dialog.inputs["work"].setValue(168)
        dialog.inputs["sleep"].setValue(10)
        dialog.save()
        self.assertFalse(dialog.saved)
        self.assertEqual(load_targets(self.ctx.db)["work"], 1200)
        self.assertIn("168", dialog.error.text())
        dialog.inputs["work"].setValue(20)
        dialog.save()
        self.assertTrue(dialog.saved)
        self.assertEqual(load_targets(self.ctx.db)["sleep"], 4200)

    def test_decline_acknowledgement_is_reversible_and_scoped_to_period(self):
        page = self.page_with_history()
        before = page.report["totals"].copy(), page.report["scores"].copy()
        self.assertIn("🙁", page.delta_labels["work"].text())
        self.assertIn("work", page.ack_buttons)
        page.ack_buttons["work"].click()
        self.assertIn("neutralisée", page.delta_labels["work"].text())
        self.assertEqual((page.report["totals"], page.report["scores"]), before)
        page.date_picker.setDate(QDate(2026, 9, 22))
        self.assertNotIn("work", page.report["acknowledged"])
        page.date_picker.setDate(QDate(2026, 9, 29))
        self.assertIn("work", page.report["acknowledged"])
        page.ack_buttons["work"].click()
        self.assertNotIn("work", page.report["acknowledged"])
        self.assertIn("🙁", page.delta_labels["work"].text())

    def test_period_navigation_summary_and_incomplete_comparison(self):
        page = self.page_with_history()
        self.assertEqual(page.report["period_start"], date(2026, 9, 28))
        page.previous_button.click()
        self.assertEqual(page.report["period_start"], date(2026, 9, 21))
        self.assertIn("indisponible", page.delta_labels["work"].text())
        self.assertNotIn("work", page.ack_buttons)
        page.mode_buttons["month"].click()
        self.assertEqual(page.report["kind"], "month")
        self.assertEqual(page.report["period_start"], date(2026, 9, 1))
        page.mode_buttons["quarter"].click()
        self.assertEqual(page.report["period_start"], date(2026, 7, 1))
        page.mode_buttons["summary"].click()
        self.assertTrue(page.period_controls.isHidden())
        self.assertEqual(page.report["period_start"], date.today() - __import__("datetime").timedelta(days=date.today().weekday()))
        page.mode_buttons["month"].click()
        page.current_period()
        self.assertFalse(page.next_button.isEnabled())
        self.assertLessEqual(page.date_picker.date(), QDate.currentDate())

    def test_annual_chart_axis_text_and_keyboard_accessible_table(self):
        page = self.page_with_history()
        self.assertEqual(page.history[0]["month"], date(self.ctx.year, 9, 1))
        page.history_axis.setCurrentIndex(page.history_axis.findData("sleep"))
        self.assertEqual(page.chart.axis, "sleep")
        self.assertIn("sommeil", page.chart.accessibleName())
        page.history_toggle.click()
        self.assertFalse(page.history_table.isHidden())
        self.assertEqual(page.history_table.rowCount(), 12)
        self.assertEqual(page.history_table.item(0, 0).text(), f"Septembre {self.ctx.year}")
        page.history_toggle.click()
        self.assertTrue(page.history_table.isHidden())

    def test_missing_journal_is_not_labelled_as_missing_objectives(self):
        save_targets(self.ctx.db, dict(work=1200, sleep=0, sport=0, rest=0))
        self.page = ProgressionPage(self.ctx)
        text = [label.text() for label in self.page.scores_container.findChildren(QLabel)]
        self.assertIn("Journal à compléter", text)
        self.assertNotIn("Aucun objectif actif", text)

    def test_resizing_modes_theme_and_acknowledgement_keep_cards_legible(self):
        save_targets(self.ctx.db, dict(work=1200, sleep=3360, sport=180, rest=420))
        page = self.page_with_history()
        wrapper = scroll_page(page)
        controls = dict(page.metric_values)
        score_controls = dict(page.score_values)
        acknowledgement = page._ack_controls["work"]
        try:
            wrapper.resize(1360, 900)
            wrapper.show()
            QTest.qWait(50)
            for width, height, theme in ((1360, 900, "dark"), (1024, 680, "light"),
                                          (1024, 680, "dark"), (1360, 900, "light")):
                wrapper.resize(width, height)
                self.ctx.set_theme(theme)
                apply_theme(APP, theme)
                for mode in ("month", "quarter", "week"):
                    page.mode_buttons[mode].click()
                    QTest.qWait(30)
                    self.assertEqual(page.metric_values, controls)
                    self.assertEqual(page.score_values, score_controls)
                    self.assertGreaterEqual(page.height(), page.minimumSizeHint().height())
                    self.assertGreaterEqual(page.metrics_container.height(), page.metrics_container.minimumSizeHint().height())
                    for key, card in page.metric_cards.items():
                        self.assertGreaterEqual(card.height(), card.minimumSizeHint().height())
                        self.assertGreaterEqual(page.metric_values[key].height(), page.metric_values[key].minimumSizeHint().height())
                        self.assertTrue(card.rect().contains(page.metric_values[key].geometry()))
            wrapper.ensureWidgetVisible(acknowledgement)
            acknowledgement.click()
            QTest.qWait(30)
            self.assertIs(page.ack_buttons["work"], acknowledgement)
            self.assertIn("neutralisée", page.delta_labels["work"].text())
            self.assertGreaterEqual(page.height(), page.minimumSizeHint().height())
            self.assertGreaterEqual(page.metric_cards["work"].height(), page.metric_cards["work"].minimumSizeHint().height())
        finally:
            wrapper.takeWidget()
            page.hide()
            wrapper.close()
            wrapper.deleteLater()

    def test_visible_timer_stops_on_hide_and_shutdown_and_empty_cta_navigates(self):
        visited = []
        self.page = ProgressionPage(self.ctx, visited.append)
        self.page.resize(900, 700)
        self.page.show()
        APP.processEvents()
        self.assertTrue(self.page.timer.isActive())
        self.page.open_time()
        self.assertEqual(visited, ["time"])
        self.page.hide()
        APP.processEvents()
        self.assertFalse(self.page.timer.isActive())
        self.page.show()
        APP.processEvents()
        self.page.shutdown()
        self.assertFalse(self.page.timer.isActive())
        with patch.object(self.page, "_render") as render:
            self.ctx.mark_changed()
            self.assertFalse(render.called)

    def test_details_keep_comparison_explanations_without_changing_the_report(self):
        page = self.page_with_history()
        before = page.report.copy()
        self.assertTrue(page.details_body.isHidden())
        self.assertIn("période précédente", page.delta_badges["work"].text())
        with patch.object(self.ctx.db, "set_setting") as write:
            page.details_toggle.click()
            self.assertFalse(page.details_body.isHidden())
            self.assertIn("Fenêtres comparées", page.comparison_caption.text())
            self.assertIn("journal incomplet", page.delta_labels["work"].text())
            page.details_toggle.click()
            self.assertTrue(page.details_body.isHidden())
            write.assert_not_called()
        self.assertEqual(page.report, before)

    def test_figures_persist_and_target_bars_use_elapsed_period_targets(self):
        save_targets(self.ctx.db, dict(work=1200, sleep=0, sport=0, rest=0))
        page = self.page_with_history()
        figures = dict(page.figures)
        target = 1200 * page.report["elapsed_days"] / 7
        expected = round(min(1, page.report["totals"]["work"] / target) * 1000)
        self.assertEqual(page.target_bars["work"].value(), expected)
        self.assertFalse(page.target_bars["work"].isHidden())
        self.assertTrue(page.target_bars["sleep"].isHidden())
        self.assertEqual(set(figures), {"work", "sleep", "sport", "rest"})
        save_targets(self.ctx.db, dict(work=0, sleep=0, sport=0, rest=0))
        page.refresh()
        self.assertEqual(page.figures, figures)
        self.assertFalse(page.score_orb.isHidden())
        self.assertFalse(page.targets_prompt.isHidden())
        self.assertTrue(all(bar.isHidden() for bar in page.target_bars.values()))


if __name__ == "__main__":
    unittest.main()
