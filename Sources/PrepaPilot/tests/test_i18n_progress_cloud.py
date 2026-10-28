"""Localized progress/backup interfaces retain canonical saved identities."""
from datetime import date, datetime
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QLabel
from mpsi_core.grades import format_stats
from mpsi_core.storage import Store
from mpsi_desktop import achievements, progression, transfers
from mpsi_desktop.achievement_panel import _amount, _date
from mpsi_desktop.achievement_visuals import BadgeFigure
from mpsi_desktop.cloud_dialog import CloudBackupDialog, display_date, folder_identifier
from mpsi_desktop.context import AppContext
from mpsi_desktop.google_drive import _file_id
from mpsi_desktop.google_auth import GoogleDriveError
from mpsi_desktop.i18n import language, set_language
from mpsi_desktop.progression_chart import AnnualProgressionChart, _number
from mpsi_desktop.progression_page import ProgressionTargetsDialog

APP = QApplication.instance() or QApplication([])


class Journal:
    def __init__(self):
        self.settings = {}

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = value

    def list_time_entries(self):
        return []

    def study_categories(self):
        return {'maths'}


class ProgressCloudTranslationTests(unittest.TestCase):
    def setUp(self):
        self.previous_language = language()
        set_language('en')

    def tearDown(self):
        set_language(self.previous_language)

    def test_achievement_report_translates_without_changing_catalog_or_ledger(self):
        db = Journal()
        state = {'version': 1, 'awards': {'work_total_v2:2': {'earned_at': '2026-10-12T12:00:00'}}}
        db.settings[achievements.SETTING] = state
        report = achievements.snapshot(db, now=datetime(2026, 10, 23, 12))
        family = next(item for item in report['families'] if item['id'] == 'work_total')
        self.assertEqual(family['title'], 'Every hour counts')
        self.assertEqual(family['tiers'][1]['name'], 'Silver')
        self.assertEqual(family['tiers'][1]['id'], 'work_total_v2:2')
        self.assertIn('Oct 2026', report['quests'][0]['period_label'])
        self.assertEqual(db.settings[achievements.SETTING], state)
        self.assertEqual(achievements.TIERS[1]['name'], 'Argent')
        self.assertEqual(achievements.FAMILIES[0]['title'], 'Chaque heure compte')

    def test_durations_dates_and_decimals_use_english(self):
        self.assertEqual(_amount(1, 'nights'), '1 night')
        self.assertEqual(_amount(3, 'weeks'), '3 weeks')
        self.assertEqual(_amount(2, 'days'), '2 days')
        self.assertEqual(_date('2026-10-23T12:00:00'), '23 Oct 2026')
        self.assertEqual(_number(1.5), '1.5')
        self.assertIn(' at ', display_date('2026-10-23T12:00:00+00:00'))
        self.assertEqual(display_date(None), 'Unknown date')
        set_language('fr')
        self.assertEqual(_amount(3, 'weeks'), '3 semaines')
        self.assertEqual(_number(1.5), '1,5')

    def test_validation_errors_are_localized(self):
        with self.assertRaisesRegex(ValueError, 'Targets must include'):
            progression.validate_targets({})
        with self.assertRaisesRegex(ValueError, 'achievement ledger'):
            achievements.validate_state({})
        with self.assertRaisesRegex(ValueError, 'folder link or ID is invalid'):
            folder_identifier('bad/link')
        with self.assertRaisesRegex(GoogleDriveError, 'file ID is invalid'):
            _file_id('bad/link')
        with self.assertRaisesRegex(ValueError, 'invalid file path'):
            transfers._safe_name('../data.sqlite3')
        store = Store(':memory:')
        try:
            with self.assertRaisesRegex(ValueError, 'The grade must be a number'):
                store.add_grade('maths', 'ds', True, 20, '2026-10-23')
        finally:
            store.close()

    def test_grade_summary_preserves_personal_labels_and_localizes_numbers(self):
        grades = [dict(subject='maths', kind='ds', score=12.5, scale=20,
                       coefficient=1, graded_on='2026-10-23', id=1)]
        summary = format_stats(grades, 'maths', subject_label='Mon cours personnel')
        self.assertIn('Mon cours personnel — 1 grade(s)', summary)
        self.assertIn('weighted average: 12.50/20', summary)
        self.assertIn('Written exam', summary)
        self.assertNotIn('Moyenne', summary)

    def test_native_progress_and_cloud_controls_use_english(self):
        with tempfile.TemporaryDirectory() as temp:
            ctx = AppContext(Path(temp) / 'data')
            ctx.set_language('en')
            targets = ProgressionTargetsDialog(ctx)
            cloud = CloudBackupDialog(ctx, connection=SimpleNamespace(configured=False, connected=False))
            chart = AnnualProgressionChart(ctx)
            badge = BadgeFigure(1, locked=True)
            try:
                self.assertEqual(ctx.achievement_report()['families'][0]['title'], 'Every hour counts')
                self.assertEqual(targets.windowTitle(), 'My personal targets')
                self.assertIn('Study', [label.text() for label in targets.findChildren(QLabel)])
                self.assertEqual(targets.inputs['sleep'].suffix(), ' h / day')
                self.assertEqual(cloud.connect_button.text(), 'Sign in with Google')
                self.assertEqual(cloud.choices['grades'].text(), 'Grades and assessments')
                self.assertEqual(set(cloud.choices), set(('documents', 'grades', 'sleep', 'activities', 'timetable', 'memories', 'preferences')))
                self.assertEqual(badge.accessibleName(), 'Silver medal: locked')
                chart.set_data([{'month': date(2026, 10, 1), 'future': True}], 'work')
                self.assertIn('October 2026 · Upcoming', chart.accessibleName())
            finally:
                for item in (targets, cloud, chart, badge):
                    item.close()
                    item.deleteLater()
                APP.processEvents()
                ctx.close()

    def test_full_import_keeps_current_language(self):
        with tempfile.TemporaryDirectory() as temp:
            ctx = AppContext(Path(temp) / 'data')
            archive = Path(temp) / 'fr.prepapilot'
            try:
                ctx.set_language('fr')
                transfers.export_archive(ctx, archive)
                ctx.set_language('en')
                with transfers.inspect_archive(archive, type(ctx.db)) as plan:
                    transfers.apply_import(ctx, plan)
                self.assertEqual(ctx.db.get_setting('desktop_language'), 'en')
                self.assertEqual(ctx.language, 'en')
                self.assertEqual(language(), 'en')
            finally:
                ctx.close()


if __name__ == '__main__':
    unittest.main()
