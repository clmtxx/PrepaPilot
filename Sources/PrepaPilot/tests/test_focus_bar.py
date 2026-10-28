"""The persistent session controls mirror the real timer without owning it."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mpsi_desktop.context import AppContext
from mpsi_desktop.focus_bar import FocusSessionBar
from mpsi_desktop.focus_session import FocusSession

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class FocusSessionBarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.clock = [datetime.now().replace(second=0, microsecond=0) - timedelta(days=1), 1000.]
        self.session = FocusSession(self.ctx.db, now=lambda: self.clock[0], monotonic=lambda: self.clock[1])
        self.calls = []
        self.bar = FocusSessionBar(self.ctx, lambda: self.calls.append('return'), self.toggle, lambda: self.calls.append('review'))
        self.bar.resize(870, 58)

    def tearDown(self):
        self.bar.close()
        self.bar.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()

    def toggle(self):
        self.calls.append('toggle')
        if self.session.status == 'running':
            self.session.pause()
        else:
            self.session.resume()
        self.bar.refresh(self.session)

    def start(self, title='Exercices de démonstration'):
        self.session.start('maths', minutes=25, title=title)
        self.bar.refresh(self.session)
        APP.processEvents()

    def test_idle_and_saved_views_are_hidden_and_hiding_does_not_pause(self):
        self.bar.refresh(self.session)
        self.assertTrue(self.bar.isHidden())
        self.start()
        self.assertTrue(self.bar.has_session)
        self.bar.refresh(self.session, visible=False)
        self.assertTrue(self.bar.isHidden())
        self.assertEqual(self.session.status, 'running')
        self.session.discard()
        self.bar.refresh(self.session)
        self.assertFalse(self.bar.has_session)
        self.bar.refresh(SimpleNamespace(status='saved'))
        self.assertTrue(self.bar.isHidden())

    def test_refresh_is_read_only_and_countdown_uses_real_remaining_time(self):
        self.start()
        before = self.ctx.db._connection.total_changes
        with patch.object(self.ctx.db, 'category_labels', wraps=self.ctx.db.category_labels) as labels:
            for _ in range(4):
                self.clock[0] += timedelta(seconds=1)
                self.clock[1] += 1
                self.session.tick()
                self.bar.refresh(self.session)
        labels.assert_not_called()
        self.assertEqual(self.bar.time_label.text(), '24:56')
        self.assertEqual(self.ctx.db._connection.total_changes, before)
        self.assertEqual(self.bar.findChildren(QTimer), [])

    def test_return_keeps_work_running_and_pause_resume_uses_callbacks(self):
        self.start()
        QTest.mouseClick(self.bar.return_button, Qt.LeftButton)
        self.assertEqual(self.calls, ['return'])
        self.assertEqual(self.session.status, 'running')
        with patch('mpsi_desktop.focus_bar.time.monotonic', side_effect=[100., 100.1, 101.]):
            QTest.mouseClick(self.bar.toggle_button, Qt.LeftButton)
            self.assertEqual(self.session.status, 'paused')
            QTest.mouseClick(self.bar.toggle_button, Qt.LeftButton)
            self.assertEqual(self.session.status, 'paused')
            QTest.mouseClick(self.bar.toggle_button, Qt.LeftButton)
        self.assertEqual(self.session.status, 'running')
        self.assertEqual(self.calls, ['return', 'toggle', 'toggle'])

    def test_review_has_a_distinct_callback_and_never_logs_work(self):
        self.start()
        self.session.finish()
        self.bar.refresh(self.session)
        self.assertTrue(self.bar.toggle_button.isHidden())
        self.assertFalse(self.bar.review_button.isHidden())
        self.assertEqual(self.bar.time_label.text(), '00:00')
        self.assertIn('réalisé', self.bar.time_label.accessibleName())
        before = self.ctx.db._connection.total_changes
        QTest.mouseClick(self.bar.review_button, Qt.LeftButton)
        self.assertEqual(self.calls, ['review'])
        self.assertEqual(self.ctx.db._connection.total_changes, before)
        self.assertEqual(self.session.status, 'review')

    def test_long_personal_text_remains_plain_accessible_and_bounded(self):
        title = '<b>Un objectif personnel très long</b> ' * 6
        self.start(title=title)
        self.bar.resize(650, 58)
        APP.processEvents()
        self.assertIn('<b>', self.bar.context_label.full_text)
        self.assertEqual(self.bar.context_label.textFormat(), Qt.PlainText)
        self.assertEqual(self.bar.context_label.accessibleName(), self.bar.context_label.full_text)
        self.assertEqual(self.bar.context_label.toolTip(), self.bar.context_label.full_text)
        self.assertLess(self.bar.context_label.width(), self.bar.width())
        for action in (self.bar.return_button, self.bar.toggle_button, self.bar.review_button):
            self.assertLessEqual(action.height(), 40)

    def test_theme_changes_and_stale_actions_do_not_change_session(self):
        self.start()
        before = self.session.state
        self.ctx.set_theme('dark')
        self.assertEqual(self.session.state, before)
        self.session.discard()
        self.bar._return()
        self.bar._toggle()
        self.bar._review()
        self.assertEqual(self.calls, [])

    def test_renaming_a_subject_invalidates_only_cached_metadata(self):
        self.start()
        with patch.object(self.ctx.db, 'category_labels', return_value={'maths': 'Analyse renommée'}) as labels:
            self.ctx.mark_changed('subjects')
            self.bar.refresh(self.session)
            self.bar.refresh(self.session)
        labels.assert_called_once()
        self.assertIn('Analyse renommée', self.bar.context_label.full_text)


if __name__ == '__main__':
    unittest.main()
