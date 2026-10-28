"""Contextual home actions use actual session state and saved journal data."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from mpsi_desktop.context import AppContext
from mpsi_desktop.focus_dialogs import FocusSetupDialog, FocusReviewDialog
from mpsi_desktop.i18n import set_language, tr
from mpsi_desktop.window import MainWindow
from mpsi_desktop.progression import save_targets

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class HomeExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.window = MainWindow(self.ctx, show_welcome=False)
        self.window.resize(1024, 680)
        self.window.show()
        APP.processEvents()
        self.home = self.window.pages['home']

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        set_language('fr')

    def test_running_session_shortcut_keeps_timer_running(self):
        self.home.focus_session.start('maths', minutes=25)
        self.home._sync_focus()
        self.assertIn('EN COURS', self.home.hero.eyebrow_label.text())
        QTest.mouseClick(self.home.next_step_button, Qt.LeftButton)
        self.assertEqual(self.home.focus_session.status, 'running')
        self.assertTrue(self.home.timer.isActive())
        self.assertEqual(self.window.current_key, 'home')

    def test_paused_session_shortcut_resumes_without_new_setup(self):
        self.home.focus_session.start('maths', minutes=25)
        self.home.focus_session.pause()
        self.home._sync_focus()
        self.assertEqual(self.home.next_step_button.text(), 'Reprendre ma séance  →')
        with patch.object(FocusSetupDialog, 'exec') as setup:
            self.home.open_next_step()
        setup.assert_not_called()
        self.assertEqual(self.home.focus_session.status, 'running')

    def test_review_shortcut_opens_review_and_keeps_unconfirmed_work(self):
        self.home.focus_session.start('maths', minutes=25)
        self.home.focus_session.finish()
        self.home._sync_focus()
        self.assertEqual(self.home.next_step_button.text(), 'Voir mon bilan  →')
        with patch.object(FocusReviewDialog, 'exec', return_value=QDialog.Rejected) as review:
            self.home.open_next_step()
        review.assert_called_once()
        self.assertEqual(self.home.focus_session.status, 'review')
        self.assertEqual(self.ctx.db._rows("SELECT COUNT(*) AS n FROM time_entries WHERE source='manual'")[0]['n'], 0)

    def test_discovery_ignores_planned_or_future_work_and_updates_from_real_data(self):
        card = self.home.getting_started
        self.assertEqual(card.completed, (False, False, False))
        now = self.ctx.db._time_now().replace(second=0, microsecond=0)
        past = now - timedelta(days=2)
        self.ctx.db.add_time_entry('maths', past.isoformat(timespec='minutes'),
                                   (past + timedelta(minutes=25)).isoformat(timespec='minutes'),
                                   'À faire', status='planned')
        future = now + timedelta(days=2)
        with patch.object(self.ctx.db, '_time_now', return_value=future + timedelta(hours=1)):
            self.ctx.db.add_time_entry('maths', future.isoformat(timespec='minutes'),
                                       (future + timedelta(minutes=25)).isoformat(timespec='minutes'), 'Futur')
        self.ctx.mark_changed('activities')
        self.assertFalse(card.completed[2])
        done = now - timedelta(days=1)
        self.ctx.db.add_time_entry('maths', done.isoformat(timespec='minutes'),
                                   (done + timedelta(minutes=25)).isoformat(timespec='minutes'), 'Réalisé')
        self.ctx.mark_changed('activities')
        self.assertTrue(card.completed[2])
        sample = Path(self.temp.name) / 'Ma fiche.txt'
        sample.write_text('Fiche de démonstration', encoding='utf-8')
        self.ctx.db.import_document(sample, 'maths', 'cours')
        self.ctx.db.add_grade('maths', 'cours', 14, 20, f'{self.ctx.year}-09-10')
        self.ctx.mark_changed('documents', 'grades')
        self.assertEqual(card.completed, (True, True, True))
        self.assertEqual(card.progress.value(), 3)
        self.assertEqual(card.title.text(), 'Ton espace est prêt.')
        card.activate(0)
        self.assertEqual(self.window.current_key, 'documents')

    def test_discovery_and_weekly_card_refresh_are_read_only(self):
        before = self.ctx.db._connection.total_changes
        for _ in range(3):
            self.home.getting_started.refresh(documents=0, grades=0)
            self.home.momentum_card.refresh()
        self.assertEqual(self.home.getting_started.progress.value(), 0)
        self.assertEqual(self.ctx.db._connection.total_changes, before)

    def test_autonomous_session_counts_toward_discovery(self):
        start = self.ctx.db._time_now().replace(second=0, microsecond=0) - timedelta(days=1)
        identity = self.ctx.db.add_time_entry('permanence', start.isoformat(timespec='minutes'),
                                            (start + timedelta(minutes=25)).isoformat(timespec='minutes'), 'Travail autonome')
        self.ctx.mark_changed('activities')
        self.assertTrue(self.home.getting_started.completed[2])
        self.ctx.db.delete_time_entry(identity)
        self.ctx.mark_changed('activities')
        self.assertFalse(self.home.getting_started.completed[2])

    def test_changing_target_refreshes_home_without_reopening_it(self):
        self.assertEqual(self.home.momentum_card.summary['target'], 0)
        save_targets(self.ctx.db, dict(work=600, sleep=0, sport=0, rest=0))
        self.ctx.mark_changed('progression')
        self.assertEqual(self.home.momentum_card.summary['target'], 600)
        self.assertFalse(self.home.momentum_card.goal_bar.isHidden())

    def test_first_grade_remains_discovered_in_an_empty_school_year(self):
        self.ctx.db.add_grade('maths', 'cours', 14, 20, f'{self.ctx.year-1}-09-10')
        self.ctx.mark_changed('grades')
        self.assertEqual(self.home.grade_stat.value.text(), '0')
        self.assertTrue(self.home.getting_started.completed[1])

    def test_contextual_copy_has_english_translation(self):
        set_language('en')
        for status in ('idle', 'running', 'paused', 'review', 'saved'):
            self.home._sync_next_step(status)
            self.assertNotIn('séance', self.home.next_step_button.text())
            self.assertNotEqual(self.home.hero.eyebrow_label.text(), 'TON PROCHAIN PAS')
        self.assertEqual(tr('Ton premier document'), 'Your first document')


if __name__ == '__main__':
    unittest.main()
