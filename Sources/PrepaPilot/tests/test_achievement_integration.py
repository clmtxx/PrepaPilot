"""Achievements follow journal changes without disturbing unrelated pages."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QAbstractAnimation, QEvent
from PySide6.QtWidgets import QApplication

from mpsi_desktop import achievements
from mpsi_desktop.context import AppContext
from mpsi_desktop.progression_page import ProgressionPage
from mpsi_desktop.theme import apply_theme


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class AchievementIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.previous_motion = APP.property('reducedMotion')
        self.temporary = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temporary.name) / 'data')
        self.ctx.db._time_now = lambda: datetime(2026, 10, 18, 19)
        self.page = None

    def tearDown(self):
        if self.page:
            self.page.shutdown()
            self.page.close()
            self.page.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temporary.cleanup()
        APP.setProperty('reducedMotion', self.previous_motion)

    def add_sport(self):
        return self.ctx.db.add_time_entry('sport', '2026-10-12T09:00', '2026-10-12T10:00')

    def test_validated_journal_unlocks_once_and_unrelated_changes_do_not_scan(self):
        notices, unlocked = [], []
        self.ctx.notice.connect(notices.append)
        self.ctx.achievements_unlocked.connect(unlocked.append)
        self.add_sport()
        self.ctx.mark_changed('activities')
        self.assertEqual(len(unlocked), 1)
        self.assertGreater(self.ctx.achievement_report()['earned_count'], 0)
        self.assertEqual(len(notices), 1)
        with patch('mpsi_desktop.achievements.reconcile', wraps=achievements.reconcile) as reconcile:
            self.ctx.mark_changed('activities')
            self.ctx.mark_changed('grades')
            self.ctx.achievement_report()
            reconcile.assert_not_called()
        self.assertEqual(len(unlocked), 1)

    def test_startup_recognises_existing_journal_and_preserves_awards(self):
        self.add_sport()
        directory = self.ctx.data_dir
        self.ctx.close()
        self.ctx = AppContext(directory)
        report = self.ctx.achievement_report()
        self.assertGreater(report['earned_count'], 0)
        self.assertIn('sport_total:1', self.ctx.db.get_setting(achievements.SETTING)['awards'])

    def test_study_requires_new_thresholds_and_never_awards_legacy_tiers(self):
        monday = datetime(2026, 10, 12, 9)
        for day in range(5):
            start = monday + timedelta(days=day)
            self.ctx.db.add_time_entry('maths', start.isoformat(), (start + timedelta(hours=5)).isoformat())
            self.ctx.mark_changed('activities')
            if day == 0:
                self.assertEqual(self.ctx.db.get_setting(achievements.SETTING, {'awards': {}})['awards'], {})
        awards = self.ctx.db.get_setting(achievements.SETTING)['awards']
        self.assertIn('work_week_v3:1', awards)
        self.assertIn('quest:work_week_v2:2026-10-12', awards)
        self.assertIn('quest:study_days_v2:2026-10-12', awards)
        self.assertNotIn('work_total_v2:1', awards)  # Lifetime bronze starts at 50 h.
        self.assertNotIn('work_total:1', awards)
        self.assertNotIn('work_week:1', awards)
        self.assertNotIn('work_week_v2:1', awards)

    def test_success_mode_restores_period_modes_and_reduced_motion(self):
        self.add_sport()
        self.ctx.mark_changed('activities')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        APP.setProperty('reducedMotion', True)
        self.page = ProgressionPage(self.ctx)
        for theme in ('light', 'dark'):
            self.ctx.set_theme(theme)
            apply_theme(APP, theme)
            self.page.set_mode('achievements')
            self.page.show()
            APP.processEvents()
            self.assertTrue(self.page.achievement_panel.isVisible())
            self.assertEqual(len(self.page.achievement_panel.family_cards), 6)
            self.assertTrue(self.page.hero_card.isHidden())
            self.assertTrue(self.page.period_controls.isHidden())
            self.assertFalse(self.page.achievement_panel.grab().isNull())
            self.page.achievement_panel.celebrate(self.ctx.achievement_report()['recent_awards'])
            self.assertFalse(any(animation.state() == QAbstractAnimation.Running
                                 for animation in self.page.achievement_panel.findChildren(QAbstractAnimation)))
            self.page.set_mode('week')
            self.assertTrue(self.page.achievement_panel.isHidden())
            self.assertFalse(self.page.hero_card.isHidden())
            self.assertFalse(self.page.period_controls.isHidden())


if __name__ == '__main__':
    unittest.main()
