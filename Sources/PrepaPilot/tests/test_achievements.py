"""Reward identity, calendar boundaries and durable journal-derived awards."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mpsi_desktop.achievements import FAMILIES, QUESTS, SETTING, reconcile, snapshot, validate_state
from mpsi_desktop.time_store import local_stamp


def activity(category, start, end, **changes):
    return dict(category=category, start_at=start, end_at=end,
                status=changes.get('status', 'completed'),
                source=changes.get('source', 'manual'), deleted=changes.get('deleted', 0))


class Journal:
    def __init__(self, entries=()):
        self.entries = list(entries)
        self.settings = {}
        self.writes = 0

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.writes += 1
        self.settings[key] = value

    def list_time_entries(self):
        return self.entries

    def study_categories(self):
        return {'maths', 'archived-law', 'user-architecture', 'eps'}

    def _time_now(self):
        return datetime(2026, 10, 18, 20)


def family(report, identity):
    return next(item for item in report['families'] if item['id'] == identity)


def quest(report, key):
    return next(item for item in report['quests'] if item['id'].startswith(f'quest:{key}:'))


class AchievementTests(unittest.TestCase):
    def test_old_easy_threshold_no_longer_awards_work_badges_or_quests(self):
        db = Journal([activity('maths', '2026-10-12T09:00', '2026-10-12T14:00')])
        report = reconcile(db)
        self.assertEqual(report['new_awards'], [])
        self.assertEqual(db.writes, 0)
        self.assertEqual(report['points'], 0)
        self.assertEqual(quest(report, 'work_week_v2')['target'], 1500)
        self.assertEqual(quest(report, 'study_days_v2')['target'], 5)
        self.assertEqual(quest(report, 'study_month_v2')['target'], 20)

    def test_every_harder_work_tier_requires_exact_new_threshold(self):
        expected = {
            'work_total': (50, 150, 400, 800, 1500),
            'work_week': (25, 40, 55, 65, 80),
            'work_month': (100, 160, 220, 260, 320),
        }
        start = datetime(2026, 6, 1)  # Monday and first day of the month.
        for identity, hours in expected.items():
            for index, threshold in enumerate(hours):
                for difference in (-1, 0):
                    minutes = threshold * 60 + difference
                    db = Journal([activity('maths', (start + timedelta(minutes=offset)).isoformat(),
                                           (start + timedelta(minutes=min(minutes, offset + 6000))).isoformat())
                                  for offset in range(0, minutes, 6000)])
                    with self.subTest(family=identity, hours=threshold, difference=difference):
                        report = reconcile(db)
                        tiers = family(report, identity)['tiers']
                        self.assertEqual(tuple(tier['target'] // 60 for tier in tiers), hours)
                        version = 2 if identity == 'work_total' else 3
                        self.assertEqual(tiers[index]['id'], f'{identity}_v{version}:{index + 1}')
                        self.assertEqual(tiers[index]['earned_at'] is not None, difference == 0)
                        self.assertEqual(report['legacy_count'], 0)

    def test_sport_and_eps_count_as_sport_only_and_merge_duplicate_minutes(self):
        db = Journal([
            activity('sport', '2026-10-12T09:00', '2026-10-12T09:45'),
            activity('eps', '2026-10-12T09:30', '2026-10-12T10:00', source='timetable'),
            activity('sport', '2026-10-12T09:00', '2026-10-12T09:45'),
        ])
        report = reconcile(db)
        self.assertEqual(family(report, 'sport_total')['current'], 60)
        self.assertEqual(family(report, 'work_total')['current'], 0)
        self.assertEqual(family(report, 'sport_streak')['current'], 1)
        self.assertEqual({award['id'] for award in report['new_awards']},
                         {'sport_total:1', 'quest:sport_week:2026-10-12'})
        self.assertEqual(report['points'], 220)
        self.assertEqual(report['legacy_count'], 0)

    def test_every_sport_total_tier_has_accessible_exact_threshold(self):
        start = datetime(2026, 10, 5, 9)
        for index, hours in enumerate((1, 5, 15, 30, 60)):
            for difference in (-1, 0):
                db = Journal([activity('sport', start.isoformat(),
                                       (start + timedelta(minutes=hours * 60 + difference)).isoformat())])
                with self.subTest(hours=hours, difference=difference):
                    report = reconcile(db)
                    self.assertEqual(family(report, 'sport_total')['tiers'][index]['earned_at'] is not None,
                                     difference == 0)

    def test_sport_week_crossing_midnight_uses_correct_monday_boundaries(self):
        db = Journal([activity('sport', '2026-10-11T23:30', '2026-10-12T00:30')])
        report = reconcile(db)
        self.assertEqual(family(report, 'sport_total')['current'], 60)
        self.assertEqual(family(report, 'sport_streak')['current'], 0)
        self.assertEqual(quest(report, 'sport_week')['current'], 30)
        self.assertIsNone(quest(report, 'sport_week')['earned_at'])
        db.entries.append(activity('eps', '2026-10-12T09:00', '2026-10-12T09:30'))
        self.assertEqual(family(reconcile(db), 'sport_streak')['current'], 1)
        db.entries.append(activity('sport', '2026-10-05T09:00', '2026-10-05T09:30'))
        report = reconcile(db)
        self.assertEqual(family(report, 'sport_streak')['current'], 2)
        self.assertIsNotNone(family(report, 'sport_streak')['tiers'][0]['earned_at'])

    def test_all_sport_streak_tiers_count_regular_weeks_including_current_week(self):
        start = datetime(2026, 4, 13, 9)
        db = Journal()
        for index in range(24):
            first = start + timedelta(weeks=index)
            db.entries.append(activity('sport', first.isoformat(), (first + timedelta(hours=1)).isoformat()))
            report = reconcile(db, first + timedelta(hours=2))
            expected = sum(target <= index + 1 for target in (2, 4, 8, 12, 24))
            self.assertEqual(family(report, 'sport_streak')['earned_count'], expected)
            self.assertEqual(family(report, 'sport_streak')['current'], index + 1)
            self.assertEqual(family(report, 'sport_streak')['unit'], 'weeks')

    def test_short_missing_and_future_sport_weeks_do_not_extend_best_streak(self):
        start = datetime(2026, 8, 17, 9)
        db = Journal([activity('sport', (start + timedelta(weeks=index)).isoformat(),
                               (start + timedelta(weeks=index, hours=1)).isoformat())
                      for index in (0, 1, 2, 3, 5, 6, 7, 8, 9)])
        db.entries.append(activity('sport', '2026-09-14T09:00', '2026-09-14T09:59'))
        report = reconcile(db)
        self.assertEqual(family(report, 'sport_streak')['current'], 4)
        self.assertEqual(family(report, 'sport_streak')['earned_count'], 2)
        db.entries = []
        corrected = reconcile(db)
        self.assertEqual(family(corrected, 'sport_streak')['current'], 0)
        self.assertEqual(family(corrected, 'sport_streak')['earned_count'], 2)

    def test_sport_day_quest_uses_twenty_minutes_aggregated_on_two_distinct_days(self):
        db = Journal([
            activity('sport', '2026-10-12T09:00', '2026-10-12T09:10'),
            activity('eps', '2026-10-12T17:00', '2026-10-12T17:10'),
            activity('sport', '2026-10-13T09:00', '2026-10-13T09:19'),
            activity('sport', '2026-10-14T09:00', '2026-10-14T09:20'),
            activity('sport', '2026-10-15T09:00', '2026-10-15T10:00', status='planned'),
            activity('sport', '2026-10-16T09:00', '2026-10-16T10:00', deleted=1),
        ])
        report = reconcile(db)
        self.assertEqual(quest(report, 'sport_days')['current'], 2)
        self.assertIsNotNone(quest(report, 'sport_days')['earned_at'])
        self.assertEqual(family(report, 'sport_total')['current'], 59)
        self.assertEqual(report['points'], 120)
        self.assertIsNone(quest(report, 'sport_week')['earned_at'])

    def test_sport_quests_are_renewed_once_per_calendar_week(self):
        db = Journal([activity('sport', f'2026-10-{day:02d}T09:00', f'2026-10-{day:02d}T09:30')
                      for day in (5, 6, 12, 13)])
        report = reconcile(db)
        self.assertEqual(report['quests_completed'], 4)
        self.assertIsNotNone(quest(report, 'sport_week')['earned_at'])
        self.assertIsNotNone(quest(report, 'sport_days')['earned_at'])
        self.assertEqual(reconcile(db)['new_awards'], [])
        next_week = snapshot(db, datetime(2026, 10, 19))
        self.assertEqual(quest(next_week, 'sport_days')['current'], 0)
        self.assertEqual(next_week['points'], report['points'])

    def test_legacy_awards_preserve_points_without_unlocking_harder_milestones(self):
        db = Journal([activity('maths', '2026-10-12T09:00', '2026-10-12T14:00')])
        old_ids = ('work_total:1', 'work_week:1', 'work_month:1',
                   'quest:work_week:2026-10-12', 'quest:study_days:2026-10-12',
                   'quest:study_month:2026-10-01')
        original = {'version': 1, 'awards': {
            identity: {'earned_at': '2026-10-18T19:00:00'} for identity in old_ids}}
        db.settings[SETTING] = deepcopy(original)
        report = reconcile(db)
        self.assertEqual(db.settings[SETTING], original)
        self.assertEqual(db.writes, 0)
        self.assertEqual(report['earned_count'], 0)
        self.assertEqual(report['quests_completed'], 0)
        self.assertEqual(report['legacy_count'], 6)
        self.assertEqual(report['legacy_points'], 820)
        self.assertEqual(report['points'], 820)
        self.assertEqual({award['id'] for award in report['legacy_awards']}, set(old_ids))
        self.assertTrue(all(award['legacy'] for award in report['legacy_awards']))
        self.assertTrue(all('target' in award and 'unit' in award for award in report['legacy_awards']))
        self.assertEqual(report['new_awards'], [])

    def test_new_work_awards_can_coexist_with_old_earned_points_without_double_awarding(self):
        db = Journal([activity('maths', '2026-10-12T09:00', '2026-10-14T11:00')])
        db.settings[SETTING] = {'version': 1, 'awards': {
            'work_total:1': {'earned_at': '2026-10-12T14:00:00'},
            'quest:work_week:2026-10-12': {'earned_at': '2026-10-12T14:00:00'}}}
        report = reconcile(db)
        self.assertEqual(report['legacy_points'], 200)
        self.assertIsNotNone(family(report, 'work_total')['tiers'][0]['earned_at'])
        self.assertEqual(family(report, 'work_total')['tiers'][0]['id'], 'work_total_v2:1')
        self.assertFalse(any(award['legacy'] for award in report['new_awards']))
        self.assertEqual(reconcile(db)['new_awards'], [])
        self.assertEqual(reconcile(db)['points'], report['points'])

    def test_previous_week_and_month_diamonds_keep_their_original_targets_and_points(self):
        db = Journal()
        original = {'version': 1, 'awards': {
            'work_week_v2:5': {'earned_at': '2026-10-18T19:00:00'},
            'work_month_v2:5': {'earned_at': '2026-10-18T19:00:00'},
            'work_total_v2:1': {'earned_at': '2026-10-18T19:00:00'},
            'quest:work_week_v2:2026-10-12': {'earned_at': '2026-10-18T19:00:00'}}}
        db.settings[SETTING] = deepcopy(original)
        report = reconcile(db)
        self.assertEqual(db.settings[SETTING], original)
        self.assertEqual(db.writes, 0)
        self.assertEqual(report['points'], 2200)
        self.assertEqual(report['legacy_count'], 2)
        self.assertEqual(report['legacy_points'], 2000)
        self.assertEqual({award['id']: award['target'] for award in report['legacy_awards']},
                         {'work_week_v2:5': 3600, 'work_month_v2:5': 15000})
        self.assertEqual(family(report, 'work_week')['earned_count'], 0)
        self.assertEqual(family(report, 'work_month')['earned_count'], 0)
        self.assertEqual(family(report, 'work_total')['earned_count'], 1)
        self.assertEqual(report['quests_completed'], 1)
        self.assertEqual(report['new_awards'], [])

    def test_sixty_hour_week_no_longer_earns_diamond_but_preserves_previous_diamond(self):
        db = Journal([activity('maths', '2026-10-12T00:00', '2026-10-14T12:00')])
        db.settings[SETTING] = {'version': 1, 'awards': {
            'work_week_v2:5': {'earned_at': '2026-10-14T12:00:00'}}}
        report = reconcile(db)
        week = family(report, 'work_week')
        self.assertEqual(week['current'], 3600)
        self.assertEqual(week['earned_count'], 3)
        self.assertIsNone(week['tiers'][3]['earned_at'])
        self.assertIsNone(week['tiers'][4]['earned_at'])
        self.assertEqual(report['legacy_points'], 1000)
        self.assertIn('work_week_v2:5', db.settings[SETTING]['awards'])
        self.assertEqual(reconcile(db)['new_awards'], [])

    def test_legacy_history_is_bounded_without_losing_points_or_persistent_awards(self):
        db = Journal()
        start = datetime(2020, 1, 6)
        db.settings[SETTING] = {'version': 1, 'awards': {
            f'quest:work_week:{(start + timedelta(weeks=index)).date().isoformat()}':
                {'earned_at': (start + timedelta(weeks=index, days=1)).isoformat()}
            for index in range(105)}}
        original = deepcopy(db.settings[SETTING])
        report = reconcile(db)
        self.assertEqual(report['legacy_count'], 105)
        self.assertEqual(report['legacy_points'], 10500)
        self.assertEqual(len(report['legacy_awards']), 100)
        self.assertEqual(report['legacy_awards'][0]['id'], 'quest:work_week:2022-01-03')
        self.assertEqual(db.settings[SETTING], original)
        self.assertEqual(db.writes, 0)

    def test_old_and_new_backup_ids_validate_but_unknown_new_variants_do_not(self):
        valid = ('work_total:1', 'work_week:5', 'work_month:3', 'work_total_v2:1',
                 'work_week_v2:5', 'work_month_v2:3', 'work_week_v3:5', 'work_month_v3:5',
                 'sport_total:2', 'sport_streak:4',
                 'sleep_streak:5', 'quest:work_week:2026-10-12', 'quest:work_week_v2:2026-10-12',
                 'quest:study_days_v2:2026-10-12', 'quest:study_month_v2:2026-10-01',
                 'quest:sport_week:2026-10-12', 'quest:sport_days:2026-10-12')
        state = {'version': 1, 'awards': {identity: {'earned_at': '2026-10-18T20:00:00'} for identity in valid}}
        self.assertEqual(validate_state(state), state)
        for identity in ('work_total_v2:6', 'work_total_v3:1', 'work_week_v3:6',
                         'work_month_v3:0', 'work_week_v4:1', 'sport_streak_v2:1',
                         'quest:study_month_v2:2026-10-12', 'quest:sport_week:2026-10-13'):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                validate_state({'version': 1, 'awards': {identity: {'earned_at': '2026-10-18T20:00:00'}}})

    def test_empty_read_and_reconcile_do_not_create_settings(self):
        db = Journal()
        for report in (snapshot(db), reconcile(db)):
            self.assertEqual(report['earned_count'], 0)
            self.assertEqual(report['total_count'], 30)
            self.assertEqual(report['points'], 0)
            self.assertEqual(report['level'], 1)
            self.assertEqual(report['level_floor'], 0)
            self.assertEqual(report['next_level_points'], 500)
            self.assertEqual(report['new_awards'], [])
        self.assertEqual(db.settings, {})
        self.assertEqual(db.writes, 0)

    def test_snapshot_has_current_progress_but_does_not_award(self):
        db = Journal([activity('maths', '2026-10-12T09:00', '2026-10-12T14:00')])
        report = snapshot(db)
        self.assertEqual(family(report, 'work_total')['current'], 300)
        self.assertIsNone(family(report, 'work_total')['tiers'][0]['earned_at'])
        self.assertEqual(db.writes, 0)

    def test_reconciliation_is_idempotent_and_points_are_derived(self):
        db = Journal([activity('maths', '2026-10-12T09:00', '2026-10-13T10:00')])
        report = reconcile(db)
        self.assertEqual({award['id'] for award in report['new_awards']}, {
            'work_week_v3:1', 'quest:work_week_v2:2026-10-12'})
        self.assertEqual(report['points'], 200)
        self.assertEqual(report['earned_count'], 1)
        self.assertEqual(report['quests_completed'], 1)
        self.assertEqual(db.writes, 1)
        again = reconcile(db, datetime(2026, 10, 19))
        self.assertEqual(again['new_awards'], [])
        self.assertEqual(db.writes, 1)
        self.assertEqual(again['points'], 200)
        self.assertTrue(all(award['earned_at'] == '2026-10-18T20:00:00' for award in again['recent_awards']))

    def test_completed_elapsed_only_and_unrelated_categories_do_not_count(self):
        db = Journal([
            activity('maths', '2026-10-12T00:00', '2026-10-12T08:00', status='planned'),
            activity('maths', '2026-10-13T00:00', '2026-10-13T08:00', deleted=1),
            activity('maths', '2026-10-18T19:00', '2026-10-18T21:00'),
            activity('repas', '2026-10-14T00:00', '2026-10-14T08:00'),
            activity('detente', '2026-10-17T00:00', '2026-10-17T08:00'),
        ])
        report = reconcile(db)
        self.assertEqual(family(report, 'work_total')['current'], 0)
        self.assertEqual(report['points'], 0)
        self.assertEqual(db.writes, 0)

    def test_custom_archived_and_legacy_study_categories_count_with_courses(self):
        db = Journal([activity(category, f'2026-10-12T{hour:02d}:00', f'2026-10-12T{hour+1:02d}:00', source='timetable')
                      for hour, category in enumerate(['maths', 'archived-law', 'user-architecture', 'ds', 'cpge', 'permanence'], 8)])
        self.assertEqual(family(snapshot(db), 'work_total')['current'], 360)

    def test_overlapping_study_and_duplicate_sleep_never_double_count(self):
        night = activity('sommeil', '2026-10-12T23:00', '2026-10-13T03:00')
        db = Journal([
            activity('maths', '2026-10-12T09:00', '2026-10-12T12:00'),
            activity('user-architecture', '2026-10-12T10:00', '2026-10-12T13:00'),
            night, deepcopy(night),
        ])
        report = snapshot(db)
        self.assertEqual(family(report, 'work_total')['current'], 240)
        self.assertEqual(family(report, 'work_week')['current'], 240)
        self.assertEqual(quest(report, 'sleep_nights')['current'], 0)

    def test_work_split_across_monday_and_calendar_month_boundaries(self):
        db = Journal([activity('maths', '2026-08-30T23:00', '2026-09-01T01:00')])
        report = snapshot(db, datetime(2026, 9, 2))
        self.assertEqual(family(report, 'work_total')['current'], 1560)
        self.assertEqual(family(report, 'work_week')['current'], 1500)
        self.assertEqual(family(report, 'work_month')['current'], 1500)
        self.assertEqual(quest(report, 'work_week_v2')['current'], 1500)
        self.assertEqual(quest(report, 'study_days_v2')['current'], 1)
        self.assertEqual(quest(report, 'study_month_v2')['current'], 0)

    def test_february_leap_day_is_a_real_study_day(self):
        db = Journal([activity('maths', '2024-02-28T23:30', '2024-03-01T00:30')])
        report = snapshot(db, datetime(2024, 3, 1, 1))
        self.assertEqual(family(report, 'work_total')['current'], 1500)
        self.assertEqual(family(report, 'work_month')['current'], 1470)
        self.assertEqual(quest(report, 'study_days_v2')['current'], 1)
        self.assertEqual(quest(report, 'study_month_v2')['current'], 0)

    def test_eight_hour_overnight_sleep_counts_on_waking_day(self):
        db = Journal([activity('sommeil', f'2026-10-{day:02d}T23:00', f'2026-10-{day+1:02d}T07:00')
                      for day in (11, 12, 13)])
        report = reconcile(db)
        self.assertEqual(family(report, 'sleep_streak')['current'], 3)
        self.assertEqual(quest(report, 'sleep_nights')['current'], 3)
        self.assertEqual(family(report, 'sleep_streak')['earned_count'], 1)
        self.assertIsNotNone(quest(report, 'sleep_nights')['earned_at'])

    def test_missing_or_short_night_breaks_streak_but_best_is_kept(self):
        db = Journal([activity('sommeil', f'2026-10-{day:02d}T23:00', f'2026-10-{day+1:02d}T07:00')
                      for day in (5, 6, 7, 9, 10, 13)])
        db.entries.append(activity('sommeil', '2026-10-08T23:00', '2026-10-09T06:59'))
        self.assertEqual(family(snapshot(db), 'sleep_streak')['current'], 3)

    def test_split_sleep_aggregates_in_same_noon_window(self):
        db = Journal([
            activity('sommeil', '2026-10-12T21:00', '2026-10-13T01:00'),
            activity('sommeil', '2026-10-13T03:00', '2026-10-13T07:00'),
        ])
        report = snapshot(db)
        self.assertEqual(family(report, 'sleep_streak')['current'], 1)
        self.assertEqual(quest(report, 'sleep_nights')['current'], 1)

    def test_noon_boundary_does_not_count_tomorrows_night_early(self):
        db = Journal([activity('sommeil', '2026-10-18T12:00', '2026-10-18T20:00')])
        self.assertEqual(family(snapshot(db), 'sleep_streak')['current'], 0)
        self.assertEqual(family(snapshot(db, datetime(2026, 10, 19)), 'sleep_streak')['current'], 1)

    def test_study_day_threshold_is_accumulated_and_exact(self):
        db = Journal([
            activity('maths', '2026-10-12T09:00', '2026-10-12T10:00'),
            activity('maths', '2026-10-12T11:00', '2026-10-12T12:00'),
            activity('maths', '2026-10-13T09:00', '2026-10-13T10:59'),
            activity('maths', '2026-10-14T09:00', '2026-10-14T11:00'),
            activity('maths', '2026-10-15T09:00', '2026-10-15T11:00'),
            activity('maths', '2026-10-16T09:00', '2026-10-16T11:00'),
            activity('maths', '2026-10-17T09:00', '2026-10-17T11:00'),
        ])
        report = reconcile(db)
        self.assertEqual(quest(report, 'study_days_v2')['current'], 5)
        self.assertIsNotNone(quest(report, 'study_days_v2')['earned_at'])

    def test_all_reached_tiers_awarded_together_and_exact_target_counts(self):
        start = datetime(2026, 7, 1)
        # Defensive overlapping merges are exercised separately; these are
        # 1,500 actual hours across several calendar weeks.
        db = Journal([activity('maths', (start + timedelta(hours=offset)).isoformat(),
                               (start + timedelta(hours=min(1500, offset + 100))).isoformat())
                      for offset in range(0, 1500, 100)])
        report = reconcile(db)
        self.assertEqual(family(report, 'work_total')['earned_count'], 5)
        self.assertEqual(family(report, 'work_week')['earned_count'], 5)
        self.assertEqual(family(report, 'work_month')['earned_count'], 5)
        self.assertEqual(report['earned_count'], 15)
        self.assertGreaterEqual(report['points'], 3 * (100 + 200 + 400 + 700 + 1000))

    def test_malformed_huge_intervals_cannot_freeze_report_or_award_rewards(self):
        db = Journal([
            activity('maths', '0001-01-01T00:00', '2026-10-18T00:00'),
            activity('sommeil', '2026-01-01T00:00', '2026-10-18T00:00'),
            activity('maths', '1999-01-01T00:00', '1999-01-01T08:00'),
        ])
        report = reconcile(db)
        self.assertEqual(report['points'], 0)
        self.assertEqual(db.writes, 0)

    def test_rewards_remain_after_journal_correction_and_selective_restore(self):
        db = Journal([activity('maths', '2026-10-12T09:00', '2026-10-13T10:00')])
        original = reconcile(db)
        restored = Journal()
        restored.settings[SETTING] = deepcopy(db.settings[SETTING])
        report = reconcile(restored)
        self.assertEqual(report['points'], original['points'])
        self.assertEqual(report['earned_count'], original['earned_count'])
        self.assertEqual(family(report, 'work_total')['current'], 0)
        self.assertEqual(report['new_awards'], [])
        self.assertEqual(restored.writes, 0)

    def test_historical_quests_once_per_period_and_current_period_resets(self):
        db = Journal([
            activity('maths', '2026-10-05T09:00', '2026-10-06T10:00'),
            activity('maths', '2026-10-12T09:00', '2026-10-13T10:00'),
        ])
        report = reconcile(db)
        self.assertEqual(report['quests_completed'], 2)
        self.assertIn('quest:work_week_v2:2026-10-05', db.settings[SETTING]['awards'])
        self.assertIn('quest:work_week_v2:2026-10-12', db.settings[SETTING]['awards'])
        next_week = reconcile(db, datetime(2026, 10, 19))
        self.assertEqual(quest(next_week, 'work_week_v2')['current'], 0)
        self.assertIsNone(quest(next_week, 'work_week_v2')['earned_at'])
        self.assertEqual(next_week['points'], report['points'])

    def test_monthly_quest_twenty_distinct_days_and_new_month_resets(self):
        db = Journal([activity('maths', f'2026-10-{day:02d}T09:00', f'2026-10-{day:02d}T11:00')
                      for day in range(1, 21)])
        report = reconcile(db, datetime(2026, 10, 30))
        self.assertEqual(quest(report, 'study_month_v2')['current'], 20)
        self.assertIn('quest:study_month_v2:2026-10-01', db.settings[SETTING]['awards'])
        november = snapshot(db, datetime(2026, 11, 1))
        self.assertEqual(quest(november, 'study_month_v2')['current'], 0)
        self.assertEqual(november['points'], report['points'])

    def test_single_journal_read_and_parse_per_reconciliation(self):
        db = Journal([activity('maths', '2026-10-12T09:00', '2026-10-12T14:00')])
        with (patch.object(db, 'list_time_entries', wraps=db.list_time_entries) as read,
              patch('mpsi_desktop.achievements.local_stamp', wraps=local_stamp) as parse):
            reconcile(db)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(parse.call_count, 2)

    def test_ledger_validation_detaches_and_normalizes_without_modifying_input(self):
        original = {'version': 1, 'awards': {'work_total:1': {'earned_at': '2026-10-18T20:00'}}}
        clean = validate_state(original)
        self.assertEqual(clean['awards']['work_total:1']['earned_at'], '2026-10-18T20:00:00')
        clean['awards']['work_total:1']['earned_at'] = '2026-10-19T20:00:00'
        self.assertEqual(original['awards']['work_total:1']['earned_at'], '2026-10-18T20:00')

    def test_import_cannot_add_arbitrary_rewards_points_or_versions(self):
        valid = {'version': 1, 'awards': {'work_total:1': {'earned_at': '2026-10-18T20:00:00'}}}
        invalid = [None, [], {}, {'version': True, 'awards': {}}, {'version': 2, 'awards': {}},
                   {'version': 1, 'awards': []}, valid | {'points': 100000},
                   {'version': 1, 'awards': {'work_total:6': {'earned_at': '2026-10-18T20:00'}}},
                   {'version': 1, 'awards': {'work_total:1': {'earned_at': '2026-10-18T20:00', 'points': 100000}}},
                   {'version': 1, 'awards': {1: {'earned_at': '2026-10-18T20:00'}}}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_state(value)

    def test_invalid_dates_periods_and_naive_datetime_requirement(self):
        for identity, stamp in (
            ('quest:work_week:2026-10-13', '2026-10-18T20:00'),
            ('quest:study_month:2026-10-02', '2026-10-18T20:00'),
            ('quest:unknown:2026-10-12', '2026-10-18T20:00'),
            ('quest:work_week:20261012', '2026-10-18T20:00'),
            ('quest:study_month:2026-11-01', '2026-10-18T20:00'),
            ('work_total:1', '2026-02-29T20:00'),
            ('work_total:1', '2026-10-18T20:00+02:00'),
            ('work_total:1', '2026-10-18'),
            ('work_total:1', '2026-10-18 20:00'),
            ('work_total:1', '1999-10-18T20:00'),
        ):
            with self.subTest(identity=identity, stamp=stamp), self.assertRaises(ValueError):
                validate_state({'version': 1, 'awards': {identity: {'earned_at': stamp}}})
        with self.assertRaises(ValueError):
            snapshot(Journal(), datetime.fromisoformat('2026-10-18T20:00+02:00'))

    def test_ledger_bound_preserves_existing_awards_without_unbounded_growth(self):
        db = Journal([activity('maths', '2026-10-12T09:00', '2026-10-14T11:00')])
        with patch('mpsi_desktop.achievements.MAX_AWARDS', 2):
            report = reconcile(db)
            self.assertTrue(report['ledger_full'])
            self.assertEqual(len(db.settings[SETTING]['awards']), 2)
            self.assertEqual(reconcile(db)['new_awards'], [])
            with self.assertRaises(ValueError):
                validate_state({'version': 1, 'awards': {
                    f'work_total:{index}': {'earned_at': '2026-10-18T20:00'} for index in (1, 2, 3)}})


if __name__ == '__main__':
    unittest.main()
