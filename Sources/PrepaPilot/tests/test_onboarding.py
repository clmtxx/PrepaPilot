"""The initial profile is saved before any page materializes example lessons."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog
from mpsi_desktop.context import AppContext
from mpsi_desktop.onboarding import run_initial_setup, tutorial_needed, complete_tutorial

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')

    def tearDown(self):
        self.ctx.close()
        self.temp.cleanup()

    def test_first_setup_runs_before_any_example_lesson_and_does_not_repeat(self):
        calls = []
        def welcome(*args, **kwargs):
            calls.append('welcome')
            self.assertEqual(self.ctx.db.list_time_entries('2026-01-01', '2027-12-31'), [])
            self.ctx.db.set_setting('desktop_welcomed', True)
            class Dialog:
                def exec(self): return QDialog.Accepted
            return Dialog()
        def setup(*args, **kwargs):
            calls.append('schedule')
            self.assertTrue(kwargs['first_run'])
            self.assertEqual(self.ctx.db.list_time_entries('2026-01-01', '2027-12-31'), [])
            self.ctx.db.save_setup(self.ctx.db.get_subjects(), {
                'version': 2, 'week_anchor': '2026-09-28',
                'semesters': {'S1': [], 'S2': []}})
            class Dialog:
                def exec(self): return QDialog.Accepted
            return Dialog()
        with patch('mpsi_desktop.window.WelcomeDialog', side_effect=welcome), \
                patch('mpsi_desktop.schedule_setup.SetupDialog', side_effect=setup):
            self.assertTrue(run_initial_setup(self.ctx))
            self.assertTrue(run_initial_setup(self.ctx))
        self.assertEqual(calls, ['welcome', 'schedule'])
        self.assertEqual(self.ctx.db.ensure_day('2026-10-01')['created'], 0)

    def test_cancelling_welcome_does_not_open_setup_or_complete_profile(self):
        with patch('mpsi_desktop.window.WelcomeDialog') as welcome, \
                patch('mpsi_desktop.schedule_setup.SetupDialog') as setup:
            welcome.return_value.exec.return_value = QDialog.Rejected
            self.assertFalse(run_initial_setup(self.ctx))
            setup.assert_not_called()
        self.assertFalse(self.ctx.db.get_setting('setup_completed'))
        self.assertFalse(APP.quitOnLastWindowClosed())

    def test_cancelling_schedule_resumes_it_on_next_launch_without_repeating_name(self):
        self.ctx.db.set_setting('desktop_welcomed', True)
        with patch('mpsi_desktop.window.WelcomeDialog') as welcome, \
                patch('mpsi_desktop.schedule_setup.SetupDialog') as setup:
            setup.return_value.exec.return_value = QDialog.Rejected
            self.assertFalse(run_initial_setup(self.ctx))
            self.assertFalse(run_initial_setup(self.ctx))
            welcome.assert_not_called()
            self.assertEqual(setup.call_count, 2)
        self.assertFalse(self.ctx.db.get_setting('setup_completed'))

    def test_future_tutorial_progress_is_independent_of_configuration(self):
        self.ctx.db.save_setup(self.ctx.db.get_subjects(), self.ctx.db.get_timetable())
        self.assertFalse(tutorial_needed(self.ctx.db, 0))
        self.assertTrue(tutorial_needed(self.ctx.db, 1))
        complete_tutorial(self.ctx.db, 1)
        self.assertFalse(tutorial_needed(self.ctx.db, 1))
        self.assertTrue(tutorial_needed(self.ctx.db, 2))
        self.assertTrue(self.ctx.db.get_setting('setup_completed'))
        with self.assertRaises(ValueError): complete_tutorial(self.ctx.db, True)


if __name__ == '__main__': unittest.main()
