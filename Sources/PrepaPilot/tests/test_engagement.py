"""Weekly attention cues stay factual, accessible and connected to real actions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mpsi_desktop.context import AppContext
from mpsi_desktop.engagement import MomentumCard, weekly_momentum
from mpsi_desktop.i18n import set_language
from mpsi_desktop.progression import build_report, save_targets
from mpsi_desktop.theme import apply_theme


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
NOW = datetime(2026, 10, 28, 12)


def activity(category, start, end, **fields):
    return dict(category=category, start_at=start, end_at=end,
                status=fields.get('status', 'completed'),
                source=fields.get('source', 'manual'), deleted=fields.get('deleted', 0))


class Journal:
    def __init__(self, rows):
        self.rows = rows
        self.reads = 0

    def _time_now(self):
        return NOW

    def study_categories(self):
        return {'maths', 'old-subject'}

    def category_labels(self, **_):
        return {'maths': 'Mathématiques', 'old-subject': 'Ancienne matière'}

    def list_time_entries(self, *_):
        self.reads += 1
        return self.rows

    def get_setting(self, key, default=None):
        return default


class WeeklyMomentumTests(unittest.TestCase):
    def test_actual_completed_work_matches_progression_and_splits_midnight(self):
        db = Journal([
            activity('maths', '2026-10-25T23:00', '2026-10-26T01:00'),
            activity('old-subject', '2026-10-27T22:00', '2026-10-28T01:00'),
            activity('permanence', '2026-10-28T08:00', '2026-10-28T08:30'),
            activity('sport', '2026-10-28T09:00', '2026-10-28T09:30'),
            activity('maths', '2026-10-27T10:00', '2026-10-27T11:00', status='planned'),
            activity('maths', '2026-10-26T10:00', '2026-10-26T11:00', deleted=1),
            activity('maths', '2026-10-28T18:00', '2026-10-28T19:00'),
            activity('maths', '2026-10-29T10:00', '2026-10-29T11:00'),
            activity('repas', '2026-10-26T12:00', '2026-10-26T13:00'),
        ])
        result = weekly_momentum(db)
        self.assertEqual(db.reads, 1)
        self.assertEqual(result['work_minutes'], 270)
        self.assertEqual(result['active_days'], 3)
        self.assertEqual(result['sessions'], 3)
        self.assertEqual([day['work_minutes'] for day in result['days']], [60, 120, 90, 0, 0, 0, 0])
        self.assertEqual(result['days'][2]['recovery_minutes'], 30)
        self.assertEqual([day['future'] for day in result['days']], [False, False, False, True, True, True, True])
        self.assertEqual(result['work_minutes'], build_report(db, now=NOW)['totals']['work'])

    def test_selected_historical_day_excludes_later_days_and_counts_no_activity(self):
        db = Journal([activity('maths', '2026-10-27T10:00', '2026-10-27T11:00')])
        result = weekly_momentum(db, date(2026, 10, 26))
        self.assertEqual(result['work_minutes'], 0)
        self.assertEqual(result['active_days'], 0)
        self.assertEqual(result['target'], 0)
        self.assertEqual(len(result['days']), 7)

    def test_future_week_never_implies_work_has_happened(self):
        db = Journal([activity('maths', '2026-11-02T10:00', '2026-11-02T11:00')])
        result = weekly_momentum(db, date(2026, 11, 2))
        self.assertEqual(result['work_minutes'], 0)
        self.assertTrue(all(day['future'] for day in result['days']))


class MomentumCardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.clock = patch.object(self.ctx.db, '_time_now', return_value=NOW)
        self.clock.start()
        self.navigation = []
        self.focus = []
        apply_theme(APP, 'light')
        self.card = MomentumCard(self.ctx, self.navigation.append, lambda: self.focus.append(True))

    def tearDown(self):
        self.card.close()
        self.card.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.clock.stop()
        self.ctx.close()
        self.temp.cleanup()
        set_language('fr')

    def test_refresh_uses_journal_corrections_and_optional_target(self):
        self.assertTrue(self.card.goal_bar.isHidden())
        self.assertEqual(self.card.total_label.text(), '0 min')
        identity = self.ctx.db.add_time_entry('maths', '2026-10-26T10:00', '2026-10-26T11:00')
        save_targets(self.ctx.db, dict(work=120, sleep=0, sport=0, rest=0))
        self.card.refresh()
        self.assertEqual(self.card.summary['work_minutes'], 60)
        self.assertEqual(self.card.goal_bar.value(), 500)
        self.assertFalse(self.card.goal_bar.isHidden())
        self.ctx.db.delete_time_entry(identity)
        self.card.refresh()
        self.assertEqual(self.card.summary['work_minutes'], 0)
        self.assertEqual(self.card.goal_bar.value(), 0)

    def test_goal_completion_is_capped_and_does_not_erase_real_total(self):
        self.ctx.db.add_time_entry('maths', '2026-10-26T10:00', '2026-10-26T12:00')
        save_targets(self.ctx.db, dict(work=60, sleep=0, sport=0, rest=0))
        self.card.refresh()
        self.assertEqual(self.card.goal_bar.value(), 1000)
        self.assertEqual(self.card.summary['work_minutes'], 120)
        self.assertIn('souffler', self.card.encouragement.text())

    def test_display_and_theme_are_read_only_and_actions_are_connected(self):
        with patch.object(self.ctx.db, 'set_setting') as write, patch.object(self.ctx.db, 'ensure_day') as ensure:
            self.card.refresh()
            self.ctx.theme = 'dark'
            apply_theme(APP, 'dark')
            self.ctx.theme_changed.emit('dark')
            write.assert_not_called()
            ensure.assert_not_called()
        self.card.resize(870, 260)
        self.card.show()
        APP.processEvents()
        self.assertLessEqual(self.card.minimumSizeHint().width(), 870)
        self.assertTrue(all(cell.accessibleName() for cell, *_ in self.card.day_cells))
        QTest.mouseClick(self.card.progression_button, Qt.LeftButton)
        QTest.mouseClick(self.card.focus_action, Qt.LeftButton)
        self.assertEqual(self.navigation, ['progression'])
        self.assertEqual(self.focus, [True])

    def test_focus_action_tracks_session_state_without_starting_a_timer(self):
        self.ctx._live_focus_session = SimpleNamespace(status='running')
        self.card.sync_focus_state()
        self.assertEqual(self.card.focus_action.text(), 'Retrouver ma séance')
        self.ctx._live_focus_session.status = 'paused'
        self.card.sync_focus_state()
        self.assertEqual(self.card.focus_action.text(), 'Reprendre')
        self.ctx._live_focus_session.status = 'review'
        self.card.sync_focus_state()
        self.assertEqual(self.card.focus_action.text(), 'Voir le bilan')
        self.ctx._live_focus_session.status = 'saved'
        self.card.sync_focus_state()
        self.assertEqual(self.card.focus_action.text(), 'Commencer une séance')


if __name__ == '__main__':
    unittest.main()
