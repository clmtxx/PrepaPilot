"""Calendar, declared-time and personal-target contracts for Progression."""
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mpsi_desktop.progression import (
    ACKNOWLEDGEMENTS_SETTING, TARGETS_SETTING, acknowledge, annual_history,
    build_report, clear_acknowledgement, format_duration, load_targets,
    save_targets, validate_acknowledgements, validate_targets,
)
from mpsi_desktop.time_store import local_stamp


def activity(category, start, end, *, status='completed', source='manual', deleted=0):
    return dict(category=category, start_at=start, end_at=end, status=status,
                source=source, deleted=deleted)


class Journal:
    """An unfiltered reader also exercises rejection of future/deleted rows."""
    def __init__(self, entries=()):
        self.entries = list(entries)
        self.settings = {}
        self.writes = 0

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.writes += 1
        self.settings[key] = value

    def _time_now(self):
        return datetime(2026, 10, 6, 12)

    def list_time_entries(self, *args):
        return self.entries

    def study_categories(self):
        return {'maths', 'archived-law'}

    def category_labels(self, **kwargs):
        return {'maths': 'Mathématiques', 'archived-law': 'Droit ancien',
                'permanence': 'Travail autonome', 'ds': 'Évaluation', 'cpge': 'Temps collectif'}


class ProgressionTests(unittest.TestCase):
    def test_annual_history_splits_long_entries_and_matches_monthly_reports(self):
        db = Journal([
            activity('sommeil', '2025-08-31T23:00', '2025-09-01T07:00'),
            activity('maths', '2025-09-30T23:00', '2025-10-02T01:00'),
            activity('sport', '2025-12-31T23:30', '2026-01-01T00:30'),
            activity('detente', '2026-08-31T23:30', '2026-09-01T00:30'),
            activity('repas', '2026-04-01T12:00', '2026-04-01T13:00'),
            activity('maths', '2026-04-01T13:00', '2026-04-01T14:00', deleted=1),
            activity('sport', '2026-04-01T14:00', '2026-04-01T15:00', status='planned'),
        ])
        now = datetime(2026, 9, 2)
        history = annual_history(db, 2025, now)
        for row in history:
            report = build_report(db, 'month', row['month'], now)
            self.assertEqual(row['totals'], report['totals'])
            self.assertEqual(row['has_data'], report['has_data'])
        self.assertEqual(history[0]['totals']['sleep'], 420)
        self.assertEqual(history[0]['totals']['work'], 60)
        self.assertEqual(history[1]['totals']['work'], 1500)
        self.assertEqual(history[-1]['totals']['rest'], 30)

    def test_each_report_reads_and_parses_entries_once(self):
        db = Journal([
            activity('maths', '2026-09-29T09:00', '2026-09-29T10:00'),
            activity('sommeil', '2026-10-05T23:00', '2026-10-06T07:00'),
        ])
        for calculate in (lambda: annual_history(db, 2026), lambda: build_report(db)):
            with (patch.object(db, 'list_time_entries', wraps=db.list_time_entries) as read,
                  patch.object(db, 'category_labels', wraps=db.category_labels) as labels,
                  patch('mpsi_desktop.progression.local_stamp', wraps=local_stamp) as parse):
                calculate()
            self.assertEqual(read.call_count, 1)
            self.assertEqual(labels.call_count, 1)
            self.assertEqual(parse.call_count, 2 * len(db.entries))

    def test_reads_do_not_create_defaults_or_change_the_journal(self):
        db = Journal()
        report = build_report(db)
        history = annual_history(db, 2026)
        self.assertEqual(db.settings, {})
        self.assertEqual(db.writes, 0)
        self.assertFalse(report['has_data'])
        self.assertTrue(all(value is None for value in report['scores'].values()))
        self.assertTrue(all(row['averages'] is None for row in history))

    def test_week_and_previous_week_share_elapsed_time(self):
        db = Journal([
            activity('maths', '2026-10-05T09:00', '2026-10-05T11:00'),
            activity('maths', '2026-09-28T09:00', '2026-09-28T10:00'),
            activity('maths', '2026-09-30T09:00', '2026-09-30T14:00'),
        ])
        report = build_report(db)
        comparison = report['comparison']
        self.assertEqual(report['period_start'], date(2026, 10, 5))
        self.assertEqual(report['period_end'], date(2026, 10, 12))
        self.assertEqual(comparison['current_end'], datetime(2026, 10, 6, 12))
        self.assertEqual(comparison['previous_end'], datetime(2026, 9, 29, 12))
        self.assertEqual(comparison['duration_days'], 1.5)
        self.assertEqual(comparison['deltas']['work'], 60)
        self.assertEqual(comparison['percentages']['work'], 100)
        self.assertTrue(comparison['has_data'])

    def test_short_previous_month_uses_common_duration_not_full_current_totals(self):
        db = Journal([
            activity('maths', '2024-02-28T09:00', '2024-02-28T10:00'),
            activity('maths', '2024-03-28T09:00', '2024-03-28T11:00'),
            activity('maths', '2024-03-30T09:00', '2024-03-30T12:00'),
        ])
        report = build_report(db, 'month', date(2024, 3, 31), datetime(2024, 4, 2))
        comparison = report['comparison']
        self.assertEqual(report['totals']['work'], 300)
        self.assertEqual(report['elapsed_days'], 31)
        self.assertEqual(comparison['duration_days'], 29)
        self.assertEqual(comparison['current_end'], datetime(2024, 3, 30))
        self.assertEqual(comparison['previous_end'], datetime(2024, 3, 1))
        self.assertEqual(comparison['current_totals']['work'], 120)
        self.assertEqual(comparison['previous_totals']['work'], 60)

    def test_overnight_entry_is_split_at_month_and_year_boundaries(self):
        db = Journal([activity('sommeil', '2025-12-31T23:00', '2026-01-01T07:00')])
        december = build_report(db, 'month', date(2025, 12, 1))
        january = build_report(db, 'month', date(2026, 1, 1))
        self.assertEqual(december['totals']['sleep'], 60)
        self.assertEqual(january['totals']['sleep'], 420)
        self.assertEqual(december['totals']['sleep'] + january['totals']['sleep'], 480)

    def test_quarter_is_three_calendar_months_across_year_change(self):
        report = build_report(Journal(), 'quarter', date(2026, 1, 6), datetime(2026, 1, 6, 12))
        self.assertEqual(report['period_start'], date(2025, 11, 1))
        self.assertEqual(report['period_end'], date(2026, 2, 1))
        self.assertEqual(report['comparison']['previous_start'], datetime(2025, 8, 1))
        self.assertEqual(report['end'], datetime(2026, 1, 6, 12))

    def test_planned_deleted_future_and_unrelated_categories_are_excluded(self):
        db = Journal([
            activity('maths', '2026-10-05T09:00', '2026-10-05T10:00', status='planned'),
            activity('maths', '2026-10-05T10:00', '2026-10-05T11:00', deleted=1),
            activity('maths', '2026-10-06T11:00', '2026-10-06T13:00'),
            activity('repas', '2026-10-05T12:00', '2026-10-05T13:00'),
        ])
        report = build_report(db)
        self.assertFalse(report['has_data'])
        self.assertEqual(report['recorded_minutes'], 60)
        self.assertEqual(report['entries_count'], 1)
        self.assertEqual(sum(report['totals'].values()), 0)

    def test_archived_subject_and_legacy_work_remain_grouped_with_source_breakdown(self):
        db = Journal([
            activity('archived-law', '2026-10-05T08:00', '2026-10-05T09:00', source='timetable'),
            activity('permanence', '2026-10-05T09:00', '2026-10-05T10:00'),
            activity('ds', '2026-10-05T10:00', '2026-10-05T11:00'),
            activity('cpge', '2026-10-05T11:00', '2026-10-05T12:00'),
            activity('eps', '2026-10-05T13:00', '2026-10-05T14:00'),
            activity('sport', '2026-10-05T14:00', '2026-10-05T15:00'),
        ])
        report = build_report(db)
        self.assertEqual(report['totals']['work'], 240)
        self.assertEqual(report['totals']['sport'], 120)
        self.assertEqual(report['work_sources'], {'courses': 60, 'personal': 180})
        self.assertIn('Droit ancien', [row['label'] for row in report['work_by_subject']])

    def test_score_uses_personal_targets_and_caps_extra_work(self):
        db = Journal([
            activity('sommeil', '2026-10-05T00:00', '2026-10-05T08:00'),
            activity('maths', '2026-10-05T08:00', '2026-10-05T12:00'),
            activity('detente', '2026-10-05T12:00', '2026-10-05T13:00'),
        ])
        save_targets(db, {'work': 840, 'sleep': 3360, 'sport': 210, 'rest': 420})
        scores = build_report(db, now=datetime(2026, 10, 6))['scores']
        self.assertEqual(scores['work'], 100)
        self.assertEqual(scores['sleep'], 100)
        self.assertEqual(scores['recovery'], 50)
        self.assertAlmostEqual(scores['global'], 250 / 3)
        self.assertEqual(build_report(db, anchor=date(2026, 11, 1))['scores']['global'], None)

    def test_disabled_targets_are_not_zero_components(self):
        db = Journal([activity('sport', '2026-10-05T10:00', '2026-10-05T10:30')])
        save_targets(db, {'work': 0, 'sleep': 0, 'sport': 420, 'rest': 0})
        scores = build_report(db, now=datetime(2026, 10, 6))['scores']
        self.assertIsNone(scores['work'])
        self.assertIsNone(scores['sleep'])
        self.assertEqual(scores['recovery'], 50)
        self.assertEqual(scores['global'], 50)

    def test_empty_previous_period_has_no_percentage_or_decline(self):
        db = Journal([activity('maths', '2026-10-05T09:00', '2026-10-05T10:00')])
        comparison = build_report(db)['comparison']
        self.assertTrue(comparison['current_has_data'])
        self.assertFalse(comparison['previous_has_data'])
        self.assertFalse(comparison['has_data'])
        self.assertTrue(all(value is None for value in comparison['percentages'].values()))

    def test_future_period_is_empty_and_not_negative(self):
        report = build_report(Journal(), 'month', date(2027, 2, 1))
        self.assertEqual(report['start'], report['end'])
        self.assertEqual(report['elapsed_days'], 0)
        self.assertFalse(report['has_data'])
        self.assertEqual(report['comparison']['duration_days'], 0)

    def test_year_history_includes_leap_day_and_marks_missing_or_future_months(self):
        db = Journal([activity('maths', '2024-02-29T09:00', '2024-02-29T10:00')])
        history = annual_history(db, 2023, datetime(2024, 3, 15))
        self.assertEqual(len(history), 12)
        self.assertEqual(history[0]['month'], date(2023, 9, 1))
        self.assertEqual(history[-1]['month'], date(2024, 8, 1))
        february = history[5]
        self.assertEqual(february['days'], 29)
        self.assertAlmostEqual(february['averages']['work'], 60 / 29)
        self.assertIsNone(history[4]['averages'])
        self.assertFalse(history[4]['future'])
        self.assertTrue(history[7]['future'])
        self.assertIsNone(history[7]['averages'])

    def test_acknowledgement_is_period_specific_reversible_and_does_not_change_score(self):
        db = Journal([activity('maths', '2026-10-05T09:00', '2026-10-05T10:00')])
        original = build_report(db)
        acknowledge(db, original['period_key'], 'work')
        acknowledge(db, original['period_key'], 'work')
        updated = build_report(db)
        self.assertEqual(updated['acknowledged'], ['work'])
        self.assertEqual(updated['scores'], original['scores'])
        self.assertEqual(updated['totals'], original['totals'])
        self.assertEqual(len(db.settings[ACKNOWLEDGEMENTS_SETTING]), 1)
        following = build_report(db, anchor=date(2026, 10, 12))
        self.assertEqual(following['acknowledged'], [])
        clear_acknowledgement(db, original['period_key'], 'work')
        self.assertEqual(build_report(db)['acknowledged'], [])

    def test_target_validation_rejects_non_integer_or_impossible_week(self):
        valid = {'work': 0, 'sleep': 0, 'sport': 0, 'rest': 0}
        self.assertEqual(validate_targets(valid), valid)
        for candidate in ({}, {**valid, 'work': True}, {**valid, 'work': -1},
                          {**valid, 'work': 1.5}, {**valid, 'work': 10081},
                          {**valid, 'work': 7000, 'sleep': 4000}, {**valid, 'unknown': 0}):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_targets(candidate)
        db = Journal()
        self.assertEqual(load_targets(db), valid)
        self.assertNotIn(TARGETS_SETTING, db.settings)

    def test_acknowledgement_validation_rejects_bad_periods_duplicates_and_unknown_metrics(self):
        valid = ['week:2026-10-05|work', 'month:2026-10-01|sleep', 'quarter:2026-08-01|recovery']
        self.assertEqual(validate_acknowledgements(valid), valid)
        for candidate in ({}, ['week:2026-10-06|work'], ['month:2026-10-02|sleep'],
                          ['week:2026-10-05|health'], ['week:2026-02-31|work'],
                          [valid[0], valid[0]], [5], [valid[0]] * 5001):
            with self.subTest(candidate=str(candidate)[:80]), self.assertRaises(ValueError):
                validate_acknowledgements(candidate)

    def test_duration_rounds_up_to_a_minute(self):
        self.assertEqual(format_duration(0), '0 min')
        self.assertEqual(format_duration(.01), '1 min')
        self.assertEqual(format_duration(60), '1 h 00')
        self.assertEqual(format_duration(60.01), '1 h 01')
        for value in (-1, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                format_duration(value)

    def test_earliest_supported_anchor_can_acknowledge_its_derived_1999_start(self):
        db = Journal()
        for kind in ('week', 'month', 'quarter'):
            report = build_report(db, kind, date(2000, 1, 1))
            acknowledge(db, report['period_key'], 'work')
            self.assertEqual(build_report(db, kind, date(2000, 1, 1))['acknowledged'], ['work'])
        with self.assertRaises(ValueError):
            validate_acknowledgements(['week:1999-09-06|work'])


class ProgressionStoreIntegrationTests(unittest.TestCase):
    def test_actual_store_reports_preserve_all_rows_and_settings(self):
        from mpsi_desktop.context import DesktopStore
        with tempfile.TemporaryDirectory() as folder:
            db = DesktopStore(Path(folder) / 'data.sqlite3')
            try:
                with patch.object(db, '_time_now', return_value=datetime(2026, 10, 6, 12)):
                    db.add_time_entry('maths', '2026-10-05T09:00', '2026-10-05T10:00')
                    rows = db._rows('SELECT * FROM time_entries')
                    settings = db._rows('SELECT * FROM settings')
                    snapshots = db._rows('SELECT * FROM time_day_templates')
                    self.assertEqual(build_report(db)['totals']['work'], 60)
                    annual_history(db, 2026)
                    self.assertEqual(rows, db._rows('SELECT * FROM time_entries'))
                    self.assertEqual(settings, db._rows('SELECT * FROM settings'))
                    self.assertEqual(snapshots, db._rows('SELECT * FROM time_day_templates'))
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
