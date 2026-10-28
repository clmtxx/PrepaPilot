"""Deterministic adversarial checks from the October 2026 application audit.

All databases are temporary. Calendar expectations use a minute-by-minute
oracle independent of the production aggregation and interval-merging code.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
import random
import tempfile
import unittest

from mpsi_desktop.achievements import reconcile, snapshot
from mpsi_desktop.context import DesktopStore
from mpsi_desktop.focus_session import FocusSession, SETTING, validate_focus_session
from mpsi_desktop.progression import annual_history, build_report


class Clock:
    def __init__(self, stamp):
        self.stamp, self.seconds = stamp, 1000.0

    def now(self):
        return self.stamp

    def monotonic(self):
        return self.seconds

    def advance(self, seconds):
        self.stamp += timedelta(seconds=seconds)
        self.seconds += seconds


def activity(category, start, end, *, status="completed", deleted=0):
    return dict(category=category, start_at=start.isoformat(timespec="minutes"),
                end_at=end.isoformat(timespec="minutes"), status=status,
                deleted=deleted, source="manual")


class Journal:
    def __init__(self, entries, now):
        self.entries, self.now, self.settings = entries, now, {}

    def _time_now(self):
        return self.now

    def get_setting(self, key, default=None):
        return deepcopy(self.settings.get(key, default))

    def set_setting(self, key, value):
        self.settings[key] = deepcopy(value)

    def list_time_entries(self, *args):
        return deepcopy(self.entries)

    def study_categories(self):
        return {"maths", "physique"}

    def category_labels(self, **kwargs):
        return {"maths": "Mathématiques", "physique": "Physique"}


def minute_totals(entries, start, end, now, *, merge=False):
    buckets = {metric: set() if merge else [] for metric in ("work", "sleep", "sport", "rest")}
    mapping = {"maths": "work", "physique": "work", "sommeil": "sleep",
               "eps": "sport", "sport": "sport", "detente": "rest"}
    for entry in entries:
        finish = datetime.fromisoformat(entry["end_at"])
        if entry["status"] != "completed" or entry["deleted"] or finish > now:
            continue
        metric = mapping.get(entry["category"])
        if metric is None:
            continue
        cursor = max(start, datetime.fromisoformat(entry["start_at"]))
        while cursor < min(end, finish):
            if merge:
                buckets[metric].add(cursor)
            else:
                buckets[metric].append(cursor)
            cursor += timedelta(minutes=1)
    return {metric: len(minutes) for metric, minutes in buckets.items()}


class FocusAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "audit.sqlite3"
        self.db = DesktopStore(self.path)
        self.clock = Clock(datetime(2026, 12, 31, 23, 59))
        self.db._time_now = self.clock.now
        self.focus = self.engine()

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def engine(self, db=None):
        return FocusSession(db or self.db, self.clock.now, self.clock.monotonic)

    def advance(self, seconds):
        while seconds:
            step = min(5, seconds)
            self.clock.advance(step)
            self.focus.tick()
            seconds -= step

    def test_year_boundary_saves_one_interval_and_progress_splits_both_years(self):
        self.focus.start("maths", 2)
        self.advance(120)
        self.focus.save()
        self.assertEqual(self.db.time_totals(), {"maths": 2})
        before = build_report(self.db, "month", date(2026, 12, 1), self.clock.now())
        after = build_report(self.db, "month", date(2027, 1, 1), self.clock.now())
        self.assertEqual((before["totals"]["work"], after["totals"]["work"]), (1, 1))

    def test_random_pause_resume_sequence_counts_only_observed_work(self):
        randomizer = random.Random(20261025)
        self.focus.start("maths", 240)
        expected = 0
        for _ in range(80):
            duration = randomizer.randrange(65, 125)
            self.advance(duration)
            expected += duration
            self.focus.pause()
            self.clock.advance(randomizer.randrange(1, 7200))
            self.assertEqual(self.focus.elapsed_seconds, expected)
            self.focus = self.engine()
            self.assertEqual(self.focus.elapsed_seconds, expected)
            self.focus.resume()
        self.focus.finish()
        self.assertEqual(self.focus.elapsed_seconds, expected)
        ids = self.focus.save()
        intervals = self.focus.review_entries()
        expected_minutes = sum(int((datetime.fromisoformat(row["end_at"]) -
                                    datetime.fromisoformat(row["start_at"])).total_seconds() // 60)
                               for row in intervals)
        self.assertEqual(self.db.time_totals(), {"maths": expected_minutes})
        self.assertEqual(self.focus.save(), ids)

    def test_saving_same_review_from_independent_database_connections_is_idempotent(self):
        self.focus.start("maths", 2)
        self.advance(120)
        with_other = DesktopStore(self.path)
        try:
            with_other._time_now = self.clock.now
            second = self.engine(with_other)
            first_ids = self.focus.save()
            self.assertEqual(second.save(), first_ids)
            self.assertEqual(len(with_other.list_time_entries()), 1)
            self.assertEqual(with_other.time_totals(), {"maths": 2})
        finally:
            with_other.close()

    def test_crash_recovery_at_each_side_of_checkpoint_never_counts_downtime(self):
        for elapsed, expected in ((0, 0), (14, 0), (15, 15), (16, 15), (29, 15), (30, 30), (31, 30)):
            with self.subTest(elapsed=elapsed):
                self.focus.discard()
                self.focus.start("maths")
                for _ in range(elapsed):
                    self.clock.advance(1)
                    self.focus.tick()
                before = self.db.get_setting(SETTING)
                self.clock.advance(86400 * 40)
                recovered = self.engine()
                self.assertEqual(recovered.status, "paused")
                self.assertEqual(recovered.elapsed_seconds, expected)
                self.assertEqual(self.db.get_setting(SETTING), before)

    def test_largest_timer_finishes_at_exact_limit_even_with_five_second_ticks(self):
        self.focus.start("maths", 240)
        self.advance(14405)
        self.assertEqual(self.focus.status, "review")
        self.assertEqual(self.focus.elapsed_seconds, 14400)
        self.assertEqual(self.focus.remaining_seconds, 0)
        self.focus.save()
        self.assertEqual(self.db.time_totals(), {"maths": 240})

    def test_leap_day_pause_and_resume_preserve_disjoint_journal_intervals(self):
        self.clock.stamp = datetime(2024, 2, 28, 23, 59)
        self.focus.start("maths", 4)
        self.advance(120)
        self.focus.pause()
        self.clock.advance(86400)
        self.focus.resume()
        self.advance(120)
        self.focus.save()
        self.assertEqual(self.db.time_totals(), {"maths": 4})
        self.assertEqual(len(self.db.list_time_entries()), 2)

    def test_maximum_segment_count_validates_and_resume_does_not_destroy_draft(self):
        self.focus.start("maths")
        state = self.focus.state
        stamp = self.clock.now().isoformat(timespec="microseconds")
        state.update(status="paused", segments=[dict(start_at=stamp, end_at=stamp) for _ in range(1000)])
        self.db.set_setting(SETTING, validate_focus_session(state))
        self.focus.reload()
        before = self.focus.state
        with self.assertRaises(ValueError):
            self.focus.resume()
        self.assertEqual(self.focus.state, before)
        with self.assertRaises(ValueError):
            validate_focus_session({**state, "segments": state["segments"] + [state["segments"][0]]})


class CalendarAndAchievementsAuditTests(unittest.TestCase):
    def test_generated_calendar_reports_match_independent_minute_oracle(self):
        randomizer = random.Random(10025)
        for year in (2000, 2024, 2026, 2100, 2200):
            start = datetime(year, 1, 1)
            entries = []
            for _ in range(85):
                begin = start + timedelta(minutes=randomizer.randrange(360 * 1440))
                finish = begin + timedelta(minutes=randomizer.randrange(1, 1441))
                entries.append(activity(randomizer.choice(("maths", "physique", "sport", "sommeil", "detente", "repas")),
                                        begin, finish, status=randomizer.choice(("completed", "completed", "planned")),
                                        deleted=randomizer.randrange(7) == 0))
            now = datetime(year, 11, 23, 12)
            db = Journal(entries, now)
            for kind in ("week", "month", "quarter"):
                for month in range(1, 13):
                    with self.subTest(year=year, kind=kind, month=month):
                        report = build_report(db, kind, date(year, month, 15))
                        self.assertEqual(report["totals"], minute_totals(entries, report["start"], report["end"], now))
                        self.assertGreaterEqual(report["elapsed_days"], 0)
                        self.assertGreaterEqual(report["comparison"]["duration_days"], 0)
            self.assertEqual(db.settings, {})

    def test_school_year_history_matches_each_calendar_month_in_leap_and_century_years(self):
        for year in (2000, 2023, 2099, 2199, 2200):
            first = datetime(year, 9, 1)
            now = datetime(year + 1, 8, 31, 23, 59)
            entries = [activity("maths", first + timedelta(days=offset, hours=23),
                                first + timedelta(days=offset + 1, hours=1))
                       for offset in range(0, 360, 3)]
            db = Journal(entries, now)
            for row in annual_history(db, year):
                month_end = (row["month"].replace(day=28) + timedelta(days=4)).replace(day=1)
                end = min(datetime.combine(month_end, datetime.min.time()), now)
                with self.subTest(year=year, month=row["month"]):
                    self.assertEqual(row["totals"], minute_totals(entries,
                                     datetime.combine(row["month"], datetime.min.time()), end, now))

    def test_generated_overlapping_activities_do_not_inflate_achievement_totals(self):
        randomizer = random.Random(17)
        first = datetime(2026, 10, 5)
        entries = []
        for _ in range(200):
            begin = first + timedelta(minutes=randomizer.randrange(10080))
            entries.append(activity(randomizer.choice(("maths", "physique", "sport", "eps")),
                                    begin, begin + timedelta(minutes=randomizer.randrange(1, 240))))
        now = datetime(2026, 10, 13)
        expected = minute_totals(entries, first, now, now, merge=True)
        db = Journal(entries, now)
        report = reconcile(db)
        families = {family["id"]: family for family in report["families"]}
        self.assertEqual(families["work_total"]["current"], expected["work"])
        self.assertEqual(families["sport_total"]["current"], expected["sport"])
        self.assertEqual(reconcile(db)["new_awards"], [])
        self.assertEqual(reconcile(db)["points"], report["points"])

    def test_earliest_supported_week_award_can_use_1999_period_identity(self):
        start, end = datetime(2000, 1, 1, 8), datetime(2000, 1, 1, 9)
        db = Journal([activity("sport", start, end)], datetime(2000, 1, 2))
        report = reconcile(db)
        self.assertIn("quest:sport_week:1999-12-27", {award["id"] for award in report["new_awards"]})
        self.assertEqual(reconcile(db)["points"], report["points"])

    def test_leap_year_and_century_year_work_minutes_are_exact(self):
        for year, expected in ((2000, 1500), (2024, 1500), (2100, 60), (2200, 60)):
            start = datetime(year, 2, 28, 23, 30)
            end = datetime(year, 3, 1, 0, 30)
            report = snapshot(Journal([activity("maths", start, end)], end))
            with self.subTest(year=year):
                self.assertEqual(next(family for family in report["families"] if family["id"] == "work_total")["current"], expected)


if __name__ == "__main__":
    unittest.main()
