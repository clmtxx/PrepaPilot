"""Regression tests for durable records, validation and meaningful grade statistics."""

import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from mpsi_core.grades import format_stats, normalize_kind, normalize_subject, plot_grades, stats
from mpsi_core.storage import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "nested" / "study.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_grade_conversion_original_values_and_durability(self):
        identifier = self.store.add_grade("Mathématiques", "Évaluations de cours", 4.5, 5, "2026-09-20", "Suites", 2)
        self.store.close()
        self.store = Store(self.path)
        grade = self.store.list_grades("maths")[0]
        self.assertEqual(grade["id"], identifier)
        self.assertEqual((grade["score"], grade["scale"]), (4.5, 5))
        self.assertEqual(grade["normalized_score"], 18)
        self.assertEqual(grade["coefficient"], 2)
        self.assertEqual(grade["subject"], "maths")
        self.assertEqual(grade["kind"], "cours")

    def test_grade_constraints_do_not_leave_partial_records(self):
        invalid = [
            {"score": -1}, {"score": 11}, {"score": float("nan")}, {"score": float("inf")},
            {"score": True}, {"scale": 0}, {"scale": -10}, {"scale": float("inf")},
            {"coefficient": 0}, {"coefficient": float("nan")},
            {"graded_on": "2026-02-30"}, {"graded_on": "20260920"},
            {"subject": "français"}, {"subject": "../outside"}, {"kind": " "},
            {"kind": "x" * 61}, {"kind": "Deux\nlignes"}, {"label": "x" * 241},
        ]
        defaults = dict(subject="maths", kind="ds", score=8, scale=10, graded_on="2026-09-20")
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.add_grade(**(defaults | change))
        self.assertEqual(self.store.list_grades(), [])
        self.store.add_grade("anglais", "colles", 0, 20, "2026-09-20")
        self.assertEqual(len(self.store.list_grades()), 1)

    def test_optional_class_comparison_preserves_scale_zero_and_missing_values(self):
        plain = self.store.add_grade("maths", "ds", 8, 10, "2026-09-20")
        average = self.store.add_grade("maths", "ds", 9, 10, "2026-09-21", class_average=0)
        ranked = self.store.add_grade("anglais", "Oral", 17, 20, "2026-09-22", rank=2, class_size=32)
        full = self.store.add_grade("physique", "Projet", 38, 50, "2026-09-23",
                                    class_average=27.5, rank=5, class_size=29)
        self.store.close()
        self.store = Store(self.path)
        rows = {row["id"]: row for row in self.store.list_grades()}
        self.assertEqual(tuple(rows[plain][key] for key in ("class_average", "normalized_class_average", "rank", "class_size")),
                         (None, None, None, None))
        self.assertEqual((rows[average]["class_average"], rows[average]["normalized_class_average"]), (0, 0))
        self.assertEqual((rows[ranked]["rank"], rows[ranked]["class_size"], rows[ranked]["class_average"]), (2, 32, None))
        self.assertEqual((rows[full]["class_average"], rows[full]["normalized_class_average"]), (27.5, 11))

    def test_invalid_comparison_is_atomic_for_add_and_edit(self):
        base = dict(subject="maths", kind="ds", score=8, scale=10, graded_on="2026-09-20")
        identifier = self.store.add_grade(**base, class_average=6, rank=1, class_size=30)
        original = self.store.list_grades()
        invalid = [dict(class_average=value) for value in (-1, 10.01, float("nan"), float("inf"), True, "oops")]
        invalid += [dict(rank=1), dict(class_size=30), dict(rank=31, class_size=30)]
        invalid += [dict(rank=value, class_size=30) for value in (0, -1, 1.5, float("nan"), True)]
        invalid += [dict(rank=1, class_size=value) for value in (0, -1, 30.5, float("inf"), True, 2_147_483_648)]
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.store.add_grade(**base, **values)
                with self.assertRaises(ValueError):
                    self.store.update_grade(identifier, **base, **values)
                self.assertEqual(self.store.list_grades(), original)

    def test_comparisons_can_be_edited_and_removed_independently(self):
        base = dict(subject="maths", kind="ds", score=8, scale=10, graded_on="2026-09-20")
        identifier = self.store.add_grade(**base)
        self.assertTrue(self.store.update_grade(identifier, **base, class_average=7.5, rank=2, class_size=40))
        self.assertEqual(self.store.list_grades()[0]["rank"], 2)
        self.store.update_grade(identifier, **base, class_average=0)
        self.assertEqual(tuple(self.store.list_grades()[0][key] for key in ("class_average", "rank", "class_size")), (0, None, None))
        self.store.update_grade(identifier, **base, rank=40, class_size=40)
        self.assertIsNone(self.store.list_grades()[0]["class_average"])
        self.store.update_grade(identifier, **base)
        self.assertIsNone(self.store.list_grades()[0]["rank"])

    def test_csv_and_json_keep_comparisons_and_empty_values(self):
        self.store.add_grade("maths", "ds", 8, 10, "2026-09-20", class_average=5.5, rank=3, class_size=28)
        self.store.add_grade("maths", "ds", 8, 10, "2026-09-21")
        rows = list(csv.DictReader(io.StringIO(self.store.export_grades_csv()), delimiter=";"))
        self.assertEqual([rows[0][key] for key in ("class_average", "normalized_class_average", "rank", "class_size")],
                         ["5.5", "11.0", "3", "28"])
        self.assertTrue(all(rows[1][key] == "" for key in ("class_average", "normalized_class_average", "rank", "class_size")))
        self.assertEqual(self.store.export_data()["grades"], self.store.list_grades())

    def test_tasks_keep_actual_time_and_order_completed_separately(self):
        no_deadline = self.store.add_task("Lire le chapitre", "français", "lecture", None, 45)
        earlier = self.store.add_task("DM matrices", "maths", "dm", "2026-10-01", 90, 3)
        later = self.store.add_task("TP circuits", "physique", "tp", "2026-10-02", 50, 1)
        self.assertEqual([t["id"] for t in self.store.list_tasks()], [earlier, later, no_deadline])
        self.assertTrue(self.store.complete_task(earlier, 110))
        self.assertFalse(self.store.complete_task(earlier, 999))
        self.assertEqual([t["id"] for t in self.store.list_tasks()], [later, no_deadline])
        completed = next(t for t in self.store.list_tasks(True) if t["id"] == earlier)
        self.assertIs(completed["completed"], True)
        self.assertEqual(completed["actual_minutes"], 110)
        self.assertTrue(self.store.complete_task(later, None))
        self.assertTrue(self.store.delete_task(no_deadline))
        self.assertFalse(self.store.delete_task(no_deadline))

    def test_invalid_task_times_and_difficulties(self):
        for change in ({"estimated_minutes": 0}, {"estimated_minutes": 1.5}, {"difficulty": 4}, {"difficulty": True}, {"deadline": "demain"}, {"title": " "}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.add_task(**(dict(title="Un exercice", subject="maths", kind="exo", deadline=None, estimated_minutes=30) | change))
        identifier = self.store.add_task("Un exercice", "maths", "exo", None, 30)
        with self.assertRaises(ValueError):
            self.store.complete_task(identifier, -1)
        self.assertFalse(self.store.list_tasks()[0]["completed"])

    def test_reschedule_updates_only_unfinished_tasks_and_preserves_other_fields(self):
        identifier = self.store.add_task("DM suites", "maths", "dm", "2026-09-20", 90, 3)
        before = self.store.list_tasks()[0]
        self.assertTrue(self.store.update_task(identifier, deadline="2026-10-01", estimated_minutes=120))
        after = self.store.list_tasks()[0]
        self.assertEqual(after["deadline"], "2026-10-01")
        self.assertEqual(after["estimated_minutes"], 120)
        for field in ("id", "title", "subject", "kind", "difficulty", "completed", "actual_minutes", "created_at"):
            self.assertEqual(after[field], before[field])
        self.assertTrue(self.store.update_task(identifier, estimated_minutes=45))
        self.assertEqual(self.store.list_tasks()[0]["deadline"], "2026-10-01")
        self.assertTrue(self.store.update_task(identifier, deadline="2026-10-02"))
        self.assertEqual(self.store.list_tasks()[0]["estimated_minutes"], 45)
        self.assertFalse(self.store.update_task(identifier))
        with self.assertRaises(ValueError):
            self.store.update_task(identifier, deadline="2026-10-10", estimated_minutes=0)
        self.assertEqual(self.store.list_tasks()[0]["deadline"], "2026-10-02")
        with self.assertRaises(ValueError):
            self.store.update_task(identifier, deadline="2026-02-30")
        self.assertFalse(self.store.update_task(99999, estimated_minutes=30))
        self.store.complete_task(identifier, 50)
        self.assertFalse(self.store.update_task(identifier, deadline="2026-11-01", estimated_minutes=80))
        done = self.store.list_tasks(True)[0]
        self.assertEqual((done["deadline"], done["estimated_minutes"], done["actual_minutes"]), ("2026-10-02", 45, 50))

    def test_memory_settings_summaries_and_export(self):
        self.store.remember("préférence", "séances de 45 minutes")
        self.store.remember("préférence", "séances de 50 minutes")
        self.store.set_setting("availability", {"monday": ["18:00", "20:00"]})
        self.store.set_setting("api_key", "never-export")
        self.store.set_setting("provider", {"name": "test", "token": "never-export-either"})
        summary_id = self.store.save_summary("Cours d'optique", "Résumé avec accents", "extractive")
        self.assertEqual(self.store.memories(), {"préférence": "séances de 50 minutes"})
        self.assertEqual(self.store.get_setting("availability"), {"monday": ["18:00", "20:00"]})
        self.assertEqual(self.store.get_setting("missing", 42), 42)
        self.assertEqual(self.store.list_summaries()[0]["id"], summary_id)
        self.assertEqual(self.store.get_summary(summary_id)["text"], "Résumé avec accents")
        self.assertIsNone(self.store.get_summary(12345))
        exported = self.store.export_data()
        self.assertEqual(exported["summaries"][0]["text"], "Résumé avec accents")
        self.assertNotIn("never-export", json.dumps(exported))
        self.assertTrue(self.store.forget("préférence"))
        self.assertFalse(self.store.forget("préférence"))

    def test_csv_preserves_original_scale_and_neutralizes_formulas(self):
        identifier = self.store.add_grade("physique", "ds", 7.5, 10, "2026-09-20", '=HYPERLINK("example")')
        rows = list(csv.DictReader(io.StringIO(self.store.export_grades_csv()), delimiter=";"))
        self.assertEqual(float(rows[0]["normalized_score"]), 15)
        self.assertEqual(float(rows[0]["scale"]), 10)
        self.assertTrue(rows[0]["label"].startswith("'="))
        self.assertTrue(self.store.delete_grade(identifier))
        self.assertFalse(self.store.delete_grade(identifier))


class GradeStatisticsTests(unittest.TestCase):
    @staticmethod
    def grade(value, day, kind="cours", coefficient=1):
        return dict(id=day, subject="maths", kind=kind, score=value, scale=20, coefficient=coefficient, graded_on=f"2026-09-{day:02d}")

    def test_weighted_mean_median_groups_and_chronological_trend(self):
        rows = [self.grade(v, day, "cours" if day <= 3 else "ds", coefficient=2 if day == 6 else 1)
                for day, v in enumerate([8, 10, 12, 14, 16, 18], start=1)]
        result = stats(list(reversed(rows)))
        self.assertEqual(result["count"], 6)
        self.assertEqual(result["mean"], 13)
        self.assertAlmostEqual(result["weighted_mean"], 96 / 7)
        self.assertEqual(result["median"], 13)
        self.assertEqual((result["min"], result["max"]), (8, 18))
        self.assertEqual(result["last_score"], 18)
        self.assertAlmostEqual(result["trend"], 6.5)
        self.assertEqual(result["by_kind"]["cours"]["weighted_mean"], 10)
        self.assertEqual(result["by_kind"]["ds"]["count"], 3)
        self.assertIn("indicative", format_stats(rows, "maths"))

    def test_empty_grades_and_subject_filtering(self):
        self.assertIsNone(stats([])["weighted_mean"])
        self.assertEqual(stats([])["count"], 0)
        self.assertIsNone(stats([self.grade(20, 1)])["trend"])
        self.assertIn("aucune note", format_stats([self.grade(20, 1)], "anglais"))

    def test_extreme_finite_inputs_do_not_overflow(self):
        rows = [self.grade(20, 1), self.grade(10, 2)]
        for row in rows:
            row["coefficient"] = 1e308
        rows[0]["score"] = rows[0]["scale"] = 1e308
        self.assertEqual(stats(rows)["weighted_mean"], 15)

    def test_normalization(self):
        self.assertEqual(normalize_subject(" Mathématiques "), "maths")
        self.assertEqual(normalize_kind("Évaluations de cours"), "cours")
        self.assertEqual(normalize_subject("informatique"), "informatique")
        self.assertEqual(normalize_kind("Soutenance de projet"), "Soutenance de projet")
        self.assertEqual(normalize_kind("Examen écrit"), "ds")

    def test_plot_is_png_and_supports_single_date(self):
        chart = plot_grades([self.grade(15, 1)], "maths")
        self.assertEqual(chart.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertGreater(len(chart.getvalue()), 5000)
        with self.assertRaises(ValueError):
            plot_grades([], "anglais")


if __name__ == "__main__":
    unittest.main()
