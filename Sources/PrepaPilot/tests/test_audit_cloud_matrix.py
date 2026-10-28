"""Exercise every non-empty combination of the seven Drive restore categories."""
from contextlib import closing
from itertools import combinations
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext
from mpsi_desktop import cloud_backup as cloud
from tests.test_cloud_backup import FakeDrive

APP = QApplication.instance() or QApplication([])


class CloudSelectionMatrixAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="prepapilot-cloud-matrix-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = AppContext(self.root / "source")
        self.addCleanup(self.source.close)
        self.populate(self.source, "Source", "2000", 16)
        self.drive = FakeDrive()

    def populate(self, ctx, label, year, score):
        ctx.db.set_setting("desktop_name", label)
        ctx.db.set_setting("desktop_schedule_labels", {"S1": label + " A", "S2": label + " B"})
        ctx.db.add_grade("maths", "Examen", score, 20, year + "-09-01", label)
        ctx.db.remember("objectif", label)
        original = self.root / (label + ".txt")
        original.write_text(label, encoding="utf-8")
        folder = ctx.db.create_document_folder(label)
        ctx.db.import_document(original, "maths", "cours", folder_id=folder)
        ctx.db.add_time_entry("maths", year + "-09-02T17:00", year + "-09-02T18:00", label)
        ctx.db.add_time_entry("sommeil", year + "-09-02T23:00", year + "-09-03T07:00", label)
        with ctx.db._lock, ctx.db._connection:
            ctx.db._connection.execute("INSERT INTO time_day_templates(day,semester,slots_json) VALUES (?,'S1','[]')", (year + "-09-02",))

    def records(self, connection, table):
        return [tuple(row) for row in connection.execute('SELECT * FROM "' + table + '" ORDER BY 1')]

    def activities(self, connection, sleep):
        rows = connection.execute("SELECT category,title,start_at,end_at,status FROM time_entries ORDER BY start_at")
        return [tuple(row) for row in rows if (row[0] == "sommeil") == sleep]

    def test_all_127_selections_preserve_excluded_data_and_restore_selected_data(self):
        categories = tuple(cloud.CATEGORIES)
        checked = 0
        for size in range(1, len(categories) + 1):
            for selection in combinations(categories, size):
                with self.subTest(selection=selection):
                    target = AppContext(self.root / ("target-" + str(checked)))
                    try:
                        self.populate(target, "Local", "2001", 12)
                        snapshot = cloud.backup_to_drive(self.source, self.drive, "root", selection)
                        with cloud.prepare_drive_restore(target, self.drive, "root", snapshot["snapshot_id"]) as plan:
                            cloud.validate_restore_target(target, plan)
                            with closing(sqlite3.connect(plan.folder / "data.sqlite3")) as staged:
                                for table, category in (("grades", "grades"), ("documents", "documents"),
                                                        ("document_folders", "documents"), ("memories", "memories"),
                                                        ("time_day_templates", "timetable")):
                                    expected = self.source.db if category in selection else target.db
                                    self.assertEqual(self.records(staged, table), self.records(expected._connection, table))
                                for sleep, category in ((True, "sleep"), (False, "activities")):
                                    expected = self.source.db if category in selection else target.db
                                    self.assertEqual(self.activities(staged, sleep), self.activities(expected._connection, sleep))
                                name = staged.execute("SELECT value FROM settings WHERE key='desktop_name'").fetchone()[0]
                                self.assertEqual(name, '"Source"' if "preferences" in selection else '"Local"')
                                labels = staged.execute("SELECT value FROM settings WHERE key='desktop_schedule_labels'").fetchone()[0]
                                self.assertIn("Source" if "timetable" in selection else "Local", labels)
                            files = list((plan.folder / "documents").iterdir())
                            self.assertEqual(len(files), 1)
                            self.assertEqual(files[0].read_text(encoding="utf-8"), "Source" if "documents" in selection else "Local")
                        self.assertEqual(target.db.get_setting("desktop_name"), "Local")
                        self.assertEqual(target.db.list_grades()[0]["score"], 12)
                        checked += 1
                    finally:
                        target.close()
        self.assertEqual(checked, 127)


if __name__ == "__main__":
    unittest.main()
