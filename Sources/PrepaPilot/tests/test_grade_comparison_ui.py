"""Optional class context is editable without changing personal statistics."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
import tempfile
import unittest

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from mpsi_desktop.context import AppContext
from mpsi_desktop.notes import GradeDialog, NotesPage
from mpsi_desktop.theme import apply_theme

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
APP.setStyle("Fusion")


class GradeComparisonUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(self.temp.name)
        self.ctx.db.set_setting("desktop_reduced_motion", True)
        apply_theme(APP, "light")
        self.page = NotesPage(self.ctx)
        self.page.resize(940, 1100)
        self.page.show()
        APP.processEvents()

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()

    def dialog(self, grade=None):
        result = GradeDialog(self.ctx, subject="maths", grade=grade, parent=self.page)
        result.score.setValue(8)
        result.scale.setValue(10)
        return result

    def test_default_is_optional_and_known_zero_is_preserved(self):
        dialog = self.dialog()
        self.assertFalse(dialog.class_average_enabled.isChecked())
        self.assertFalse(dialog.rank_enabled.isChecked())
        dialog.save()
        row = self.ctx.db.list_grades()[0]
        self.assertIsNone(row["class_average"])
        self.assertIsNone(row["rank"])
        self.assertIsNone(row["class_size"])
        edit = self.dialog(row)
        edit.class_average_enabled.setChecked(True)
        edit.class_average.setValue(0)
        edit.save()
        row = self.ctx.db.list_grades()[0]
        self.assertEqual(row["class_average"], 0)
        reopen = self.dialog(row)
        self.assertTrue(reopen.class_average_enabled.isChecked())
        self.assertEqual(reopen.class_average.value(), 0)

    def test_comparisons_edit_and_clear_without_changing_personal_mean(self):
        dialog = self.dialog()
        dialog.class_average_enabled.setChecked(True)
        dialog.class_average.setValue(6.25)
        dialog.rank_enabled.setChecked(True)
        dialog.rank.setValue(5)
        dialog.class_size.setValue(32)
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.page.table.item(0, 6).text(), "12,5")
        self.assertEqual(self.page.table.item(0, 7).text(), "5 / 32")
        personal_mean = self.page.mean_stat.value.text()
        row = self.ctx.db.list_grades()[0]
        edit = self.dialog(row)
        self.assertEqual(edit.rank.value(), 5)
        self.assertEqual(edit.class_size.value(), 32)
        edit.class_average_enabled.setChecked(False)
        edit.rank_enabled.setChecked(False)
        edit.save()
        row = self.ctx.db.list_grades()[0]
        self.assertIsNone(row["class_average"])
        self.assertIsNone(row["rank"])
        self.assertIsNone(row["class_size"])
        self.assertEqual(self.page.mean_stat.value.text(), personal_mean)
        self.assertTrue(self.page.table.isColumnHidden(6))
        self.assertTrue(self.page.table.isColumnHidden(7))

    def test_rank_and_average_can_be_used_independently(self):
        ranking = self.dialog()
        ranking.rank_enabled.setChecked(True)
        ranking.rank.setValue(1)
        ranking.class_size.setValue(1)
        ranking.save()
        average = self.dialog()
        average.class_average_enabled.setChecked(True)
        average.class_average.setValue(5)
        average.save()
        rows = self.ctx.db.list_grades()
        self.assertEqual([(row['class_average'], row['rank'], row['class_size']) for row in rows],
                         [(None, 1, 1), (5, None, None)])

    def test_partial_or_out_of_range_class_values_do_not_save(self):
        dialog = self.dialog()
        dialog.class_average_enabled.setChecked(True)
        dialog.save()
        self.assertIsNone(dialog.saved_id)
        self.assertEqual(dialog.details_stack.currentIndex(), 1)
        dialog.class_average.setValue(7)
        dialog.scale.setValue(5)
        dialog.score.setValue(4)
        self.assertEqual(dialog.class_average.value(), 7)  # Never silently clamp after a scale change.
        dialog.save()
        self.assertIsNone(dialog.saved_id)
        self.assertIn("moyenne de classe", dialog.error.text())
        dialog.class_average_enabled.setChecked(False)
        dialog.rank_enabled.setChecked(True)
        dialog.rank.setValue(3)
        dialog.save()
        self.assertIsNone(dialog.saved_id)
        dialog.class_size.setValue(2)
        dialog.save()
        self.assertIsNone(dialog.saved_id)
        self.assertEqual(self.ctx.db.list_grades(), [])
        dialog.class_size.setValue(3)
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_mode_buttons_preserve_selection_data_and_personal_statistics(self):
        for score, average, rank, size in ((8, 5, 2, 30), (7, None, None, None), (9, 6, 1, 28)):
            self.ctx.db.add_grade('maths', 'ds', score, 10, date.today().isoformat(),
                                  class_average=average, rank=rank, class_size=size)
        self.ctx.mark_changed('grades')
        self.page.table.selectRow(1)
        selected = self.page.selected_grade()['id']
        mean = self.page.mean_stat.value.text()
        changes = self.ctx.db._connection.total_changes
        QTest.mouseClick(self.page.chart_mode_buttons['ranking'], Qt.MouseButton.LeftButton)
        self.assertEqual(self.page.chart.mode, 'ranking')
        self.assertIn('2 classements', self.page.details_label.text())
        self.assertTrue(self.page.chart_mode_buttons['ranking'].isChecked())
        self.assertFalse(self.page.chart_mode_buttons['grades'].isChecked())
        self.page.refresh()
        self.assertEqual(self.page.chart.mode, 'ranking')
        QTest.mouseClick(self.page.chart_mode_buttons['grades'], Qt.MouseButton.LeftButton)
        self.assertIn('pointillés', self.page.details_label.text())
        self.assertEqual(self.page.selected_grade()['id'], selected)
        self.assertEqual(self.page.mean_stat.value.text(), mean)
        self.assertEqual(self.ctx.db._connection.total_changes, changes)

    def test_subject_switch_drops_previous_class_context_and_keeps_mode(self):
        self.ctx.db.add_grade('maths', 'ds', 12, 20, date.today().isoformat(), rank=3, class_size=30)
        self.page.set_subject('maths')
        self.page.set_chart_mode('ranking')
        self.page.set_subject('anglais')
        self.assertEqual(self.page.chart.mode, 'ranking')
        self.assertEqual(self.page.chart._ranking_series, [])
        self.assertIn('facultatif', self.page.details_label.text())
        self.page.set_subject('maths')
        self.assertEqual(len(self.page.chart._ranking_series), 1)

    def test_class_tab_and_validation_fit_small_screen_in_both_themes(self):
        for theme in ('light', 'dark'):
            self.ctx.set_theme(theme)
            dialog = self.dialog()
            dialog.show()
            for index in (0, 1):
                QTest.mouseClick(dialog.detail_buttons[index], Qt.MouseButton.LeftButton)
                APP.processEvents()
                self.assertLessEqual(dialog.height(), 640)
                self.assertTrue(dialog.save_button.isVisible())
                self.assertLessEqual(dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()).y(), dialog.height())
            dialog.rank_enabled.setChecked(True)
            dialog.save()
            APP.processEvents()
            self.assertLessEqual(dialog.height(), 640)
            dialog.reject()


if __name__ == '__main__':
    unittest.main()
