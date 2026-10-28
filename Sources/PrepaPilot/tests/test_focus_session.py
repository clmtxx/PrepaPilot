"""Trusted elapsed time, recovery and atomic journal registration."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from mpsi_desktop.context import DesktopStore
from mpsi_desktop.focus_session import FocusSession, SETTING, validate_focus_session


class Clock:
    def __init__(self, stamp=None):
        self.stamp = stamp or datetime(2026, 9, 1, 17)
        self.seconds = 1000.

    def now(self):
        return self.stamp

    def monotonic(self):
        return self.seconds

    def advance(self, seconds, wall=None):
        self.seconds += seconds
        self.stamp += timedelta(seconds=seconds if wall is None else wall)


class FocusSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DesktopStore(Path(self.temp.name) / "test.sqlite3")
        self.clock = Clock()
        self.db._time_now = self.clock.now
        self.focus = self.engine()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def engine(self):
        return FocusSession(self.db, self.clock.now, self.clock.monotonic)

    def run_for(self, seconds):
        for _ in range(seconds):
            self.clock.advance(1)
            self.focus.tick()

    def reviewed(self):
        self.focus.start("maths", 25, "Suites")
        self.run_for(125)
        self.focus.finish()

    def test_start_and_lesser_ticks_are_in_memory_not_per_tick_sql(self):
        self.focus.start("maths", 25, "Suites")
        with patch.object(self.db, "get_setting", wraps=self.db.get_setting) as read:
            self.run_for(14)
            read.assert_not_called()
            self.run_for(1)
            self.assertEqual(read.call_count, 1)
        self.assertEqual(self.focus.elapsed_seconds, 15)
        self.assertEqual(self.db.list_time_entries(), [])

    def test_pauses_do_not_count_and_each_interval_rounds_inward(self):
        self.clock.advance(.4)
        self.focus.start("maths")
        self.run_for(125)
        self.focus.pause()
        self.clock.advance(300)
        self.focus.resume()
        self.run_for(125)
        self.focus.finish()
        self.assertEqual(self.focus.elapsed_seconds, 250)
        entries = self.focus.review_entries()
        self.assertEqual(entries, [dict(start_at="2026-09-01T17:01", end_at="2026-09-01T17:02"),
                                   dict(start_at="2026-09-01T17:08", end_at="2026-09-01T17:09")])
        ids = self.focus.save()
        self.assertEqual(len(ids), 2)
        self.assertEqual(self.db.time_totals()["maths"], 2)

    def test_sleep_long_gap_excluded_and_pauses_at_previous_tick(self):
        self.focus.start("maths")
        self.run_for(20)
        self.clock.advance(3600)
        self.assertEqual(self.focus.tick(), "paused")
        self.assertEqual(self.focus.elapsed_seconds, 20)
        self.assertTrue(self.focus.state["interrupted"])

    def test_clock_jump_or_backward_monotonic_never_inflates_work(self):
        for elapsed, wall in ((1, 1000), (1, -10), (-1, 1), (float("nan"), 1)):
            with self.subTest(elapsed=elapsed, wall=wall):
                self.focus.discard()
                self.clock.seconds = 1000.
                self.focus.start("maths")
                self.run_for(5)
                self.clock.advance(elapsed, wall=wall)
                self.focus.tick()
                self.assertEqual(self.focus.status, "paused")
                self.assertEqual(self.focus.elapsed_seconds, 5)

    def test_crash_recovers_only_checkpoint_and_never_counts_offline(self):
        self.focus.start("maths")
        self.run_for(29)
        before = self.db.get_setting(SETTING)
        self.clock.advance(86400)
        recovered = self.engine()
        self.assertEqual(recovered.status, "paused")
        self.assertTrue(recovered.state["interrupted"])
        self.assertEqual(recovered.elapsed_seconds, 15)
        self.assertEqual(self.db.get_setting(SETTING), before)
        recovered.resume()
        self.clock.advance(1)
        recovered.tick()
        self.assertEqual(recovered.elapsed_seconds, 16)

    def test_shutdown_checkpoints_and_pauses_without_saving_journal(self):
        self.focus.start("maths")
        self.run_for(11)
        self.focus.shutdown()
        self.assertEqual(self.engine().elapsed_seconds, 11)
        self.assertEqual(self.engine().status, "paused")
        self.assertEqual(self.db.list_time_entries(), [])

    def test_timer_limit_stops_exactly_and_waits_for_confirmation(self):
        self.focus.start("maths", 1)
        self.run_for(58)
        self.clock.advance(4)
        self.assertEqual(self.focus.tick(), "review")
        self.assertEqual(self.focus.elapsed_seconds, 60)
        self.assertEqual(self.focus.remaining_seconds, 0)
        self.assertEqual(self.db.list_time_entries(), [])
        self.focus.save()
        self.assertEqual(self.db.time_totals()["maths"], 1)

    def test_simple_timer_requires_subject_only_when_saving(self):
        self.focus.start(None, 1)
        self.run_for(60)
        with self.assertRaisesRegex(ValueError, "matière"):
            self.focus.save()
        self.focus.save(category="physique")
        self.assertEqual(self.db.time_totals()["physique"], 1)

    def test_no_complete_minute_is_never_fabricated(self):
        self.focus.start("maths")
        self.run_for(59)
        self.focus.finish()
        self.assertEqual(self.focus.review_entries(), [])
        with self.assertRaisesRegex(ValueError, "minute complète"):
            self.focus.save()

    def test_save_idempotent_after_double_click_and_recovery(self):
        self.reviewed()
        ids = self.focus.save()
        self.assertEqual(self.focus.save(), ids)
        recovered = self.engine()
        self.assertEqual(recovered.save(), ids)
        self.assertEqual(len(self.db.list_time_entries()), 1)

    def test_later_preserves_user_corrections_without_journal_side_effect(self):
        self.reviewed()
        corrected = [dict(start_at="2026-09-01T16:40", end_at="2026-09-01T16:50")]
        self.focus.update_review("physique", "Ondes", corrected)
        recovered = self.engine()
        self.assertEqual(recovered.review_entries(), corrected)
        self.assertEqual(recovered.state["title"], "Ondes")
        self.assertEqual(self.db.list_time_entries(), [])
        recovered.save()
        self.assertEqual(self.db.time_totals(), {"physique": 10})

    def test_overlap_existing_activity_keeps_entire_session_pending(self):
        self.reviewed()
        self.db.add_time_entry("maths", "2026-09-01T17:00", "2026-09-01T17:01")
        pending = self.focus.state
        with self.assertRaisesRegex(ValueError, "chevauche"):
            self.focus.save()
        self.assertEqual(self.focus.state, pending)
        self.assertEqual(len(self.db.list_time_entries()), 1)

    def test_overlap_second_segment_inserts_nothing_and_leaves_prior_activity(self):
        self.reviewed()
        self.db.add_time_entry("maths", "2026-09-01T16:50", "2026-09-01T17:00")
        with self.assertRaisesRegex(ValueError, "chevauche"):
            self.focus.save(segments=[dict(start_at="2026-09-01T16:30", end_at="2026-09-01T16:40"),
                                      dict(start_at="2026-09-01T16:55", end_at="2026-09-01T17:00")])
        self.assertEqual(len(self.db.list_time_entries()), 1)
        self.assertEqual(self.focus.status, "review")

    def test_sql_failure_rolls_back_entries_and_saved_marker_together(self):
        self.reviewed()
        pending = self.db.get_setting(SETTING)
        with patch.object(self.focus, "_write", side_effect=sqlite3.OperationalError("disk full")):
            with self.assertRaises(sqlite3.OperationalError):
                self.focus.save()
        self.assertEqual(self.db.list_time_entries(), [])
        self.assertEqual(self.db.get_setting(SETTING), pending)
        self.assertEqual(self.focus.status, "review")
        self.assertEqual(len(self.focus.save()), 1)

    def test_import_clears_draft_and_reload_never_writes_old_timer(self):
        self.focus.start("maths")
        self.run_for(5)
        self.db.set_setting(SETTING, None)
        with patch.object(self.focus, "_write") as write:
            self.assertEqual(self.focus.reload(), "idle")
            self.focus.shutdown()
            write.assert_not_called()
        self.assertEqual(self.focus.elapsed_seconds, 0)

    def test_stale_instance_cannot_overwrite_imported_or_discarded_draft(self):
        self.reviewed()
        self.db.set_setting(SETTING, None)
        with self.assertRaisesRegex(ValueError, "données ont changé"):
            self.focus.save()
        self.assertEqual(self.db.list_time_entries(), [])

    def test_active_session_cannot_be_replaced_accidentally(self):
        self.reviewed()
        with self.assertRaises(ValueError):
            self.focus.start("physique")
        self.assertEqual(self.focus.state["category"], "maths")
        self.focus.discard()
        self.focus.start("physique")
        self.assertEqual(self.focus.state["category"], "physique")

    def test_future_reversed_overlapping_or_second_precision_corrections_rejected(self):
        self.reviewed()
        bad = [[dict(start_at="2026-09-01T17:00", end_at="2026-09-01T18:00")],
               [dict(start_at="2026-09-01T17:00", end_at="2026-09-01T16:00")],
               [dict(start_at="2026-09-01T16:00", end_at="2026-09-01T17:00"),
                dict(start_at="2026-09-01T16:50", end_at="2026-09-01T17:01")],
               [dict(start_at="2026-09-01T16:00:01", end_at="2026-09-01T17:00")]]
        for segments in bad:
            with self.subTest(segments=segments), self.assertRaises(ValueError):
                self.focus.save(segments=segments)
        self.assertEqual(self.db.list_time_entries(), [])

    def test_archived_subject_recovery_retains_draft_but_requires_active_subject_to_save(self):
        self.reviewed()
        subjects = self.db.get_subjects()
        for subject in subjects:
            if subject["id"] == "maths":
                subject["active"] = False
        self.db.set_setting("desktop_subjects", subjects)
        recovered = self.engine()
        self.assertEqual(recovered.state["category"], "maths")
        with self.assertRaises(ValueError):
            recovered.save()
        recovered.save(category="physique")

    def test_validation_rejects_malformed_import_without_mutating_input(self):
        self.reviewed()
        valid = self.focus.state
        original = deepcopy(valid)
        self.assertEqual(validate_focus_session(valid), valid)
        self.assertEqual(valid, original)
        for field, value in (("version", True), ("id", "not-an-id"), ("status", "idle"),
                             ("target_minutes", 0), ("target_minutes", 241), ("target_minutes", True),
                             ("interrupted", 1), ("entry_ids", [1]), ("category", "unknown"),
                             ("title", "a"*251), ("unknown", True)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_focus_session({**valid, field: value}, self.db.subject_labels())

    def test_validation_rejects_capture_time_inflation_or_aware_timestamp(self):
        self.reviewed()
        for segments in ([dict(start_at="2026-09-01T16:00", end_at="2026-09-01T17:00")],
                         [dict(start_at="2026-09-01T17:00+02:00", end_at="2026-09-01T17:02+02:00")]):
            with self.subTest(segments=segments), self.assertRaises(ValueError):
                validate_focus_session({**self.focus.state, "segments": segments})

    def test_checkpoint_storage_failure_pauses_recoverable_work(self):
        self.focus.start("maths")
        self.run_for(14)
        with patch.object(self.focus, "_write", side_effect=sqlite3.OperationalError("disk full")):
            self.clock.advance(1)
            with self.assertRaises(sqlite3.OperationalError):
                self.focus.tick()
        self.assertEqual(self.focus.status, "paused")
        self.assertEqual(self.focus.elapsed_seconds, 15)
        self.focus.resume()
        self.run_for(110)
        self.focus.finish()
        self.focus.save()
        self.assertEqual(self.db.time_totals()["maths"], 1)

    def test_start_and_resume_storage_failure_leave_no_running_timer(self):
        with patch.object(self.focus, "_write", side_effect=sqlite3.OperationalError("disk full")):
            with self.assertRaises(sqlite3.OperationalError):
                self.focus.start("maths")
        self.assertEqual(self.focus.status, "idle")
        self.focus.start("maths")
        self.run_for(10)
        self.focus.pause()
        previous = self.focus.state
        with patch.object(self.focus, "_write", side_effect=sqlite3.OperationalError("disk full")):
            with self.assertRaises(sqlite3.OperationalError):
                self.focus.resume()
        self.assertEqual(self.focus.state, previous)

    def test_stale_same_identity_cannot_overwrite_saved_marker_or_newer_checkpoint(self):
        self.reviewed()
        stale = self.engine()
        ids = self.focus.save()
        with self.assertRaisesRegex(ValueError, "données ont changé"):
            stale.checkpoint()
        self.assertEqual(stale.save(), ids)
        self.assertEqual(self.db.get_setting(SETTING)["status"], "saved")
        self.focus.start("maths")
        stale = self.engine()
        self.run_for(15)
        with self.assertRaisesRegex(ValueError, "données ont changé"):
            stale.resume()
        self.assertEqual(stale.status, "paused")
        self.assertEqual(self.db.get_setting(SETTING)["status"], "running")

    def test_autonomous_work_uses_existing_generic_category(self):
        self.focus.start("permanence", 1)
        self.run_for(60)
        self.engine().save()
        self.assertEqual(self.db.time_totals(), {"permanence": 1})


if __name__ == "__main__":
    unittest.main()
