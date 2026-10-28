"""Adversarial data checks on synthetic, isolated SQLite databases."""
from datetime import date, datetime, timedelta
import math
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from mpsi_core.grades import plot_grades, stats
from mpsi_core.storage import Store
from mpsi_desktop.context import DesktopStore
from mpsi_desktop.time_store import period_bounds


def schedule():
    rows = [dict(id=f'day-{day}', weekday=day, start='09:00', end='10:00',
                 category='maths', title=f'Maths {day}', week='all') for day in (0, 1)]
    return dict(version=2, week_anchor='2026-08-31', semesters={
        'S1': rows, 'S2': [{**row, 'title': 'Second planning'} for row in rows]})


class GradeEdgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.temp.name) / 'grades.sqlite3')

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_all_finite_scale_extremes_normalize_and_weight_without_overflow(self):
        for scale in (math.ulp(0.0), 1e-300, 0.001, 1, 20, 1e300, 1.7976931348623157e308):
            for fraction in (0, 0.5, 1):
                with self.subTest(scale=scale, fraction=fraction):
                    score = scale * fraction
                    identity = self.db.add_grade('maths', 'ds', score, scale, '2026-10-01', coefficient=scale,
                                                 class_average=score, rank=1, class_size=2147483647)
                    row = next(row for row in self.db.list_grades() if row['id'] == identity)
                    expected = score / scale * 20
                    self.assertEqual(row['normalized_score'], expected)
                    self.assertEqual(row['normalized_class_average'], expected)
                    self.assertEqual(stats([row])['weighted_mean'], expected)
        combined = stats(self.db.list_grades())
        self.assertTrue(math.isfinite(combined['weighted_mean']))
        self.assertLessEqual(0, combined['weighted_mean'])
        self.assertLessEqual(combined['weighted_mean'], 20)

    def test_rejected_grade_mutations_leave_every_column_unchanged(self):
        valid = dict(subject='maths', kind='ds', score=12, scale=20, graded_on='2028-02-29',
                     class_average=0, rank=1, class_size=30)
        identity = self.db.add_grade(**valid)
        before = self.db.list_grades()
        invalids = [dict(score=value) for value in (None, True, False, float('nan'), float('inf'), -1, 21)]
        invalids += [dict(scale=value) for value in (None, True, False, 0, -1, float('nan'), float('inf'))]
        invalids += [dict(coefficient=value) for value in (None, True, False, 0, -1, float('nan'), float('inf'))]
        invalids += [dict(graded_on=value) for value in ('2027-02-29', '2100-02-29', '2026-2-01', '20261001', '2026-W40-4', '', None)]
        invalids += [dict(rank=2, class_size=1), dict(rank=1.1), dict(rank=True), dict(class_size=2147483648),
                     dict(class_average=float('nan')), dict(class_average=-1), dict(class_average=21),
                     dict(label='x\x00y'), dict(label='x\ny'), dict(kind='x\x7fy')]
        for fields in invalids:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    self.db.add_grade(**(valid | fields))
                with self.assertRaises(ValueError):
                    self.db.update_grade(identity, **(valid | fields))
                self.assertEqual(self.db.list_grades(), before)

    def test_nested_failure_rolls_back_notes_tasks_and_settings(self):
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            with self.db._atomic():
                self.db.add_grade('maths', 'ds', 10, 20, '2026-10-01')
                self.db.add_task('Synthetic task', 'maths', 'exo', None, 20)
                self.db.set_setting('synthetic', {'value': True})
                raise RuntimeError('synthetic failure')
        self.assertEqual(self.db.list_grades(), [])
        self.assertEqual(self.db.list_tasks(True), [])
        self.assertIsNone(self.db.get_setting('synthetic'))
        self.assertFalse(self.db._connection.in_transaction)
        self.db.add_grade('maths', 'ds', 12, 20, '2026-10-01')
        self.assertEqual(len(self.db.list_grades()), 1)

    def test_change_and_insert_preserve_an_explicit_outer_transaction(self):
        with self.assertRaisesRegex(RuntimeError, 'outer failure'):
            with self.db._connection:
                self.db._connection.execute('BEGIN IMMEDIATE')
                self.db.set_setting('synthetic', True)
                self.db.add_grade('maths', 'ds', 10, 20, '2026-10-01')
                self.assertTrue(self.db._connection.in_transaction)
                raise RuntimeError('outer failure')
        self.assertIsNone(self.db.get_setting('synthetic'))
        self.assertEqual(self.db.list_grades(), [])
        self.assertFalse(self.db._connection.in_transaction)

    def test_caught_inner_failure_retains_other_outer_mutations(self):
        with self.db._atomic():
            self.db.set_setting('before', True)
            with self.assertRaisesRegex(RuntimeError, 'inner failure'):
                with self.db._atomic():
                    self.db.set_setting('discarded', True)
                    raise RuntimeError('inner failure')
            self.db.set_setting('after', True)
        self.assertTrue(self.db.get_setting('before'))
        self.assertTrue(self.db.get_setting('after'))
        self.assertIsNone(self.db.get_setting('discarded'))
        self.assertFalse(self.db._connection.in_transaction)

    def test_calendar_extremes_can_be_charted_with_one_or_many_dates(self):
        for dates in [('0001-01-01',), ('9999-12-31',), ('0001-01-01', '0001-01-02'),
                      ('9999-12-30', '9999-12-31'), ('0001-01-01', '9999-12-31')]:
            with self.subTest(dates=dates):
                rows = [dict(subject='maths', kind='ds', score=12, scale=20, graded_on=day) for day in dates]
                chart = plot_grades(rows, 'maths')
                self.assertEqual(chart.read(8), b'\x89PNG\r\n\x1a\n')

    def test_seeded_grade_roundtrip_matches_independent_weighted_reference(self):
        rng = random.Random(20261025)
        weighted_sum, total_weight = 0, 0
        for index in range(300):
            scale, score, weight = rng.choice((5, 10, 20, 50, 100)), rng.randrange(101), rng.randrange(1, 21)
            raw_score = score * scale / 100
            day = (date(2026, 1, 1) + timedelta(days=rng.randrange(366))).isoformat()
            self.db.add_grade('maths', rng.choice(('cours', 'ds', 'colle', 'Portfolio')), raw_score,
                              scale, day, coefficient=weight)
            weighted_sum += raw_score / scale * 20 * weight
            total_weight += weight
        before = self.db.list_grades()
        self.assertAlmostEqual(stats(before)['weighted_mean'], weighted_sum / total_weight, places=12)
        self.db.close()
        self.db = Store(Path(self.temp.name) / 'grades.sqlite3')
        self.assertEqual(self.db.list_grades(), before)
        self.assertEqual(self.db._rows('PRAGMA integrity_check'), [{'integrity_check': 'ok'}])


class ScheduleAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DesktopStore(Path(self.temp.name) / 'journal.sqlite3')
        self.clock = patch.object(self.db, '_time_now', return_value=datetime(2026, 10, 4, 12))
        self.clock.start()
        self.db.save_setup(self.db.get_subjects(), schedule())
        self.db.ensure_range('2026-10-05', '2026-10-06')

    def tearDown(self):
        self.clock.stop()
        self.db.close()
        self.temp.cleanup()

    def snapshot(self):
        return {table: self.db._rows(f'SELECT * FROM {table} ORDER BY 1')
                for table in ('settings', 'time_entries', 'time_day_templates', 'sqlite_sequence')}

    def assert_refresh_failure_rolls_back(self, change):
        before = self.snapshot()
        # Fail on the second day, after a first snapshot and its sessions changed.
        with self.db._connection:
            self.db._connection.execute("""CREATE TRIGGER fail_second_day BEFORE UPDATE ON time_day_templates
                WHEN NEW.day='2026-10-06' BEGIN SELECT RAISE(ABORT,'synthetic refresh failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'synthetic refresh failure'):
            change()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.db._connection.in_transaction)
        with self.db._connection:
            self.db._connection.execute('DROP TRIGGER fail_second_day')
        change()
        self.assertNotEqual(self.snapshot(), before)

    def test_timetable_and_all_generated_days_roll_back_together(self):
        updated = self.db.get_timetable()
        for slot in updated['semesters']['S1']:
            slot['title'] = 'Updated title'
        self.assert_refresh_failure_rolls_back(lambda: self.db.save_timetable(updated))

    def test_subject_archival_and_all_generated_days_roll_back_together(self):
        updated = self.db.get_subjects()
        next(row for row in updated if row['id'] == 'maths')['active'] = False
        self.assert_refresh_failure_rolls_back(lambda: self.db.save_subjects(updated))

    def test_setup_settings_and_generated_days_roll_back_together(self):
        updated = self.db.get_timetable()
        updated['semesters']['S1'][0]['title'] = 'Updated setup'
        self.assert_refresh_failure_rolls_back(lambda: self.db.save_setup(
            self.db.get_subjects(), updated, schedule_labels={'S1': 'Classes', 'S2': 'Internship'}))

    def test_semester_transition_and_generated_days_roll_back_together(self):
        self.assert_refresh_failure_rolls_back(lambda: self.db.set_semester('S2', '2026-10-05'))

    def test_holiday_and_generated_days_roll_back_together(self):
        self.assert_refresh_failure_rolls_back(lambda: self.db.add_holiday('2026-10-05', '2026-10-06'))

    def test_holiday_resumption_and_generated_days_roll_back_together(self):
        self.db.add_holiday('2026-10-05', '2026-10-06')
        self.assert_refresh_failure_rolls_back(lambda: self.db.end_holiday('2026-10-05'))

    def test_invalid_timetable_never_changes_settings_or_snapshots(self):
        before = self.snapshot()
        for invalid in (None, [], {}, {'semesters': {}}, {'version': 3, 'semesters': {'S1': [], 'S2': []}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.db.save_timetable(invalid)
            self.assertEqual(self.snapshot(), before)

    def test_week_alternation_is_continuous_over_year_and_leap_boundaries(self):
        anchor = date.fromisoformat(self.db.get_timetable()['week_anchor'])
        for day in (date(2026, 12, 31), date(2027, 1, 1), date(2028, 2, 28), date(2028, 2, 29),
                    date(2028, 3, 1), date(2026, 8, 24)):
            with self.subTest(day=day):
                expected = 'A' if ((day - anchor).days // 7) % 2 == 0 else 'B'
                self.assertEqual(self.db.week_for_day(day.isoformat()), expected)
                self.assertEqual(self.db.week_for_day((day + timedelta(days=14)).isoformat()), expected)

    def test_calendar_last_day_can_be_listed_and_totalled(self):
        self.db.add_time_entry('maths', '9999-12-31T23:00', '9999-12-31T23:59', status='planned')
        lower, upper = period_bounds('9999-12-31', '9999-12-31')
        self.assertEqual(lower, datetime(9999, 12, 31))
        self.assertEqual(upper, datetime.max)
        self.assertEqual(len(self.db.list_time_entries('9999-12-31', '9999-12-31')), 1)
        self.assertEqual(self.db.time_totals('9999-12-31', '9999-12-31', status='planned'), {'maths': 59})

    def test_extreme_activity_durations_and_future_updates_are_atomic(self):
        identity = self.db.add_time_entry('maths', '2026-09-01T09:00', '2026-09-01T10:00')
        before = self.db.list_time_entries()
        for fields in ({'end_at': '2026-09-01T09:00'}, {'end_at': '2026-08-31T10:00'},
                       {'end_at': '2026-09-08T09:01'}, {'end_at': '2026-10-05T10:00'},
                       {'start_at': '2026-09-01T09:00+02:00'}, {'status': 'invalid'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.db.update_time_entry(identity, **fields)
            self.assertEqual(self.db.list_time_entries(), before)

    def test_range_generation_rolls_back_earlier_days_if_later_insert_fails(self):
        before = self.snapshot()
        with self.db._connection:
            self.db._connection.execute("""CREATE TRIGGER fail_new_day BEFORE INSERT ON time_day_templates
                WHEN NEW.day='2026-10-13' BEGIN SELECT RAISE(ABORT,'synthetic range failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'synthetic range failure'):
            self.db.ensure_range('2026-10-12', '2026-10-13')
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.db._connection.in_transaction)

    def test_seeded_overnight_entries_have_additive_daily_totals(self):
        rng = random.Random(20261025)
        expected = 0
        for offset in range(40):
            day = date(2026, 1, 1) + timedelta(days=offset * 2)
            start = datetime.combine(day, datetime.min.time()) + timedelta(minutes=rng.randrange(24 * 60))
            duration = rng.randrange(1, 24 * 60)
            end = start + timedelta(minutes=duration)
            self.db.add_time_entry('sommeil', start, end)
            expected += duration
        daily = sum(sum(self.db.time_totals(day.isoformat(), day.isoformat()).values())
                    for day in (date(2026, 1, 1) + timedelta(days=offset) for offset in range(82)))
        self.assertEqual(daily, expected)
        self.assertEqual(self.db.time_totals(), {'sommeil': expected})
        self.assertEqual(self.db._rows('PRAGMA integrity_check'), [{'integrity_check': 'ok'}])


if __name__ == '__main__':
    unittest.main()
