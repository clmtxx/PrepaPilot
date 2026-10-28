"""Profile and named timetable integration without imposing a course of study."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import date

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QDialog, QLabel
from mpsi_desktop.context import AppContext
from mpsi_desktop.window import WelcomeDialog
from mpsi_desktop.settings_page import SettingsPage
from mpsi_desktop.dashboard import DashboardPage
from mpsi_desktop.schedule_setup import SetupDialog
from mpsi_desktop.time_tracking import SemesterDialog, TimeTrackingPage
from mpsi_desktop.study_profile import validate_program, validate_schedule_labels, schedule_labels

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class StudyProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.widgets = []

    def tearDown(self):
        for widget in reversed(self.widgets):
            widget.close(); widget.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()

    def keep(self, widget):
        self.widgets.append(widget)
        return widget

    def test_welcome_optional_program_and_settings_updates_home_and_reloads(self):
        welcome = self.keep(WelcomeDialog(self.ctx))
        welcome.name.setText('Camille')
        welcome.program.setText('  Licence de droit  ')
        welcome.save()
        self.assertEqual(welcome.result(), QDialog.Accepted)
        self.assertEqual(self.ctx.db.get_setting('desktop_program'), 'Licence de droit')
        settings = self.keep(SettingsPage(self.ctx))
        home = self.keep(DashboardPage(self.ctx, lambda _: None))
        self.assertEqual(settings.program.text(), 'Licence de droit')
        settings.program.setText('Formation continue')
        settings.save_profile()
        self.assertIn('Formation continue', [label.text() for label in home.findChildren(QLabel)])
        self.ctx.db.set_setting('desktop_program', 'BTS')
        self.ctx.data_replaced.emit()
        self.assertEqual(settings.program.text(), 'BTS')
        settings.program.clear()
        settings.save_profile()
        self.assertEqual(self.ctx.db.get_setting('desktop_program'), '')

    def test_rename_is_a_draft_until_saved_and_views_show_names(self):
        original = schedule_labels(self.ctx.db)
        dialog = self.keep(SetupDialog(self.ctx, first_run=True))
        self.assertEqual(dialog.subject_table.rowCount(), 0)
        self.assertEqual(dialog.table.rowCount(), 0)
        dialog.start_empty()
        dialog.subject_table.item(0, 0).setText('Droit civil')
        dialog.next_step()
        with patch('mpsi_desktop.schedule_setup.QInputDialog.getText', return_value=('Cours à l’université', True)):
            dialog.rename_schedule()
        self.assertEqual(schedule_labels(self.ctx.db), original)
        dialog.semester.setCurrentIndex(dialog.semester.findData('S2'))
        with patch('mpsi_desktop.schedule_setup.QInputDialog.getText', return_value=('Stage', True)):
            dialog.rename_schedule()
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(schedule_labels(self.ctx.db), {'S1': 'Cours à l’université', 'S2': 'Stage'})
        picker = self.keep(SemesterDialog(self.ctx, date.today().isoformat()))
        self.assertEqual(picker.semester.itemText(1), 'Stage')
        page = self.keep(TimeTrackingPage(self.ctx))
        self.assertIn('Cours à l’université', page.semester_label.text())
        home = self.keep(DashboardPage(self.ctx, lambda _: None))
        self.assertIn('Cours à l’université', home.holiday_status.text())
        edit = self.keep(SetupDialog(self.ctx))
        with patch('mpsi_desktop.schedule_setup.QInputDialog.getText', return_value=('À annuler', True)):
            edit.rename_schedule()
        edit.reject()
        self.assertEqual(schedule_labels(self.ctx.db)['S1'], 'Cours à l’université')

    def test_invalid_or_cancelled_names_preserve_the_draft(self):
        dialog = self.keep(SetupDialog(self.ctx))
        original = dialog.schedule_names.copy()
        for answer in [('', True), ('a' * 41, True), ('Nom\n', True), ('Annulé', False)]:
            with patch('mpsi_desktop.schedule_setup.QInputDialog.getText', return_value=answer):
                dialog.rename_schedule()
            self.assertEqual(dialog.schedule_names, original)

    def test_profile_validation_accepts_optional_program_and_rejects_malformed_values(self):
        self.assertEqual(validate_program(''), '')
        self.assertEqual(validate_program(' Droit '), 'Droit')
        for value in (None, 'x' * 81, 'BTS\nCommerce'):
            with self.assertRaises(ValueError): validate_program(value)
        for value in ({}, {'S1': 'Cours'}, {'S1': 'Cours', 'S2': ''}, {'S1': 'Cours', 'S2': 'Stage\x00'}):
            with self.assertRaises(ValueError): validate_schedule_labels(value)

    def test_reopening_personal_catalogue_without_schedule_uses_empty_models(self):
        self.ctx.db.save_setup([dict(id='subject_' + 'e' * 32, name='Droit', color='#123456', active=True)],
                              dict(version=2, week_anchor='2026-09-28', semesters={'S1': [], 'S2': []}))
        self.ctx.db._change("DELETE FROM settings WHERE key='desktop_timetable'", ())
        from mpsi_desktop.context import DesktopStore
        with_store = DesktopStore(self.ctx.data_dir / 'mpsi.sqlite3')
        try:
            self.assertEqual(with_store.get_timetable()['semesters'], {'S1': [], 'S2': []})
            self.assertEqual(list(with_store.subject_labels().values()), ['Droit'])
        finally:
            with_store.close()


if __name__ == '__main__': unittest.main()
