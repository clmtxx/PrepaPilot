import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from mpsi_desktop.cloud_preferences import CloudPreferences, CATEGORY_IDS


class CloudPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.preferences = CloudPreferences(Path(self.temp.name))
        self.now = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def test_weekly_due_boundary_and_next_launch(self):
        self.preferences.ensure_started(self.now)
        self.assertFalse(self.preferences.due(self.now + timedelta(days=7, seconds=-1)))
        self.assertTrue(self.preferences.due(self.now + timedelta(days=7)))
        reopened = CloudPreferences(Path(self.temp.name))
        self.assertTrue(reopened.due(self.now + timedelta(days=15)))
        reopened.ensure_started(self.now + timedelta(days=15))
        self.assertEqual(reopened.read()['first_seen'], self.now.isoformat())

    def test_snooze_does_not_count_as_a_backup(self):
        self.preferences.ensure_started(self.now - timedelta(days=10))
        self.preferences.snooze(self.now)
        self.assertFalse(self.preferences.due(self.now + timedelta(hours=23)))
        self.assertTrue(self.preferences.due(self.now + timedelta(days=1)))
        self.assertIsNone(self.preferences.read()['last_success'])

    def test_verified_unchanged_snapshot_resets_reminder(self):
        self.preferences.ensure_started(self.now - timedelta(days=10))
        self.preferences.record_success(dict(snapshot_id='previous', verified_at=self.now.isoformat(), changed=False),
                                        'my_folder', 'Mes sauvegardes', ['grades'])
        self.assertFalse(self.preferences.due(self.now + timedelta(days=6)))
        self.assertTrue(self.preferences.due(self.now + timedelta(days=7)))
        self.assertEqual(self.preferences.read()['selection'], ['grades'])

    def test_missing_confirmation_never_marks_success(self):
        with self.assertRaises(ValueError):
            self.preferences.record_success({'snapshot_id': 'bad'}, 'folder', 'Test', ['grades'])
        self.assertIsNone(self.preferences.read()['last_success'])

    def test_invalid_preferences_and_interval_cannot_suppress_reminder(self):
        self.preferences.path.parent.mkdir()
        self.preferences.path.write_text(json.dumps(dict(reminder_days=30, reminders='no', selection=['bad'],
                                                        first_seen='2026-10-01T10:00:00', folder_id='../../escape')), encoding='utf-8')
        self.assertEqual(self.preferences.read()['reminder_days'], 7)
        self.assertTrue(self.preferences.read()['reminders'])
        self.assertEqual(self.preferences.read()['selection'], list(CATEGORY_IDS))
        self.assertEqual(self.preferences.read()['folder_id'], '')
        self.preferences.path.write_text('[' * 20000, encoding='utf-8')
        self.preferences.ensure_started(self.now)
        self.assertFalse(self.preferences.due(self.now))

    def test_reminder_frequency_and_opt_out(self):
        self.preferences.ensure_started(self.now)
        self.preferences.update(reminder_days=1)
        self.assertTrue(self.preferences.due(self.now + timedelta(days=1)))
        self.preferences.update(reminders=False)
        self.assertFalse(self.preferences.due(self.now + timedelta(days=50)))


if __name__ == '__main__':
    unittest.main()
