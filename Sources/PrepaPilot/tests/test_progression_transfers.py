"""Progression preferences remain portable without weakening archive validation."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext, DesktopStore
from mpsi_desktop import transfers


APP = QApplication.instance() or QApplication([])
TARGETS = {"work": 1200, "sleep": 3360, "sport": 180, "rest": 420}
ACKNOWLEDGEMENTS = ["week:2020-09-07|work", "month:2020-09-01|sleep", "quarter:2020-08-01|recovery"]


class ProgressionTransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = AppContext(self.root / "source")
        self.target = AppContext(self.root / "destination")
        self.source.db.set_setting("desktop_progression_targets", TARGETS)
        self.source.db.set_setting("desktop_progression_acknowledgements", ACKNOWLEDGEMENTS)
        self.source.db.add_time_entry("maths", "2020-09-07T18:00", "2020-09-07T19:15", "Révisions", "completed")
        self.source.db.add_time_entry("sommeil", "2020-09-07T23:00", "2020-09-08T07:00", "Nuit", "completed")
        self.source.db.add_time_entry("sport", "2020-09-08T17:00", "2020-09-08T17:45", "Course", "completed")
        self.source.db.add_time_entry("detente", "2020-09-08T20:00", "2020-09-08T20:30", "Lecture", "completed")
        self.target.db.set_setting("desktop_name", "Données à conserver")
        self.target.db.set_setting("desktop_progression_targets", dict(TARGETS, work=900))
        self.target.db.set_setting("desktop_progression_acknowledgements", ["week:2020-08-31|rest"])
        self.target.db.add_grade("physique", "Oral", 14, 20, "2020-09-01", "Note existante")
        self.target.db.add_time_entry("physique", "2020-09-01T18:00", "2020-09-01T19:00", "Travail existant", "completed")
        self.archive = self.root / "progression.prepapilot"
        transfers.export_archive(self.source, self.archive)
        self.original_target = self.target_state()

    def tearDown(self):
        self.source.close()
        self.target.close()
        self.temporary.cleanup()

    def target_state(self):
        return {name: self.target.db._rows(f"SELECT * FROM {name} ORDER BY 1")
                for name in ("settings", "grades", "time_entries", "documents", "time_day_templates")}

    def modified_archive(self, key=None, value=None, *, remove_progression=False):
        with ZipFile(self.archive) as archive:
            payload = {name: archive.read(name) for name in archive.namelist()}
        database = self.root / "edited.sqlite3"
        database.write_bytes(payload["data.sqlite3"])
        with closing(sqlite3.connect(database)) as connection, connection:
            if remove_progression:
                connection.execute("DELETE FROM settings WHERE key IN (?,?)",
                                   ("desktop_progression_targets", "desktop_progression_acknowledgements"))
            else:
                connection.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)",
                                   (key, json.dumps(value)))
        payload["data.sqlite3"] = database.read_bytes()
        manifest = json.loads(payload["manifest.json"])
        manifest["files"]["data.sqlite3"] = {
            "size": len(payload["data.sqlite3"]),
            "sha256": hashlib.sha256(payload["data.sqlite3"]).hexdigest(),
        }
        payload["manifest.json"] = json.dumps(manifest).encode("utf-8")
        modified = self.root / "modified.prepapilot"
        with ZipFile(modified, "w", ZIP_DEFLATED) as archive:
            for name, data in payload.items():
                archive.writestr(name, data)
        return modified

    def assert_rejected_without_replacement(self, key, value):
        modified = self.modified_archive(key, value)
        original_archive = modified.read_bytes()
        with self.assertRaises(ValueError):
            transfers.inspect_archive(modified, DesktopStore)
        self.assertEqual(self.target_state(), self.original_target)
        self.assertEqual(modified.read_bytes(), original_archive)
        self.assertFalse((self.target.data_dir / "backups").exists())

    def test_targets_acknowledgements_and_recorded_time_round_trip(self):
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            self.assertEqual(plan.counts["time_entries"], 4)
            backup = transfers.apply_import(self.target, plan)
        self.assertEqual(self.target.db.get_setting("desktop_progression_targets"), TARGETS)
        self.assertEqual(self.target.db.get_setting("desktop_progression_acknowledgements"), ACKNOWLEDGEMENTS)
        self.assertEqual(self.target.db._rows("SELECT * FROM time_entries ORDER BY id"),
                         self.source.db._rows("SELECT * FROM time_entries ORDER BY id"))
        with transfers.inspect_archive(backup, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.target_state(), self.original_target)

    def test_previous_archive_without_progression_preferences_still_imports(self):
        previous = self.modified_archive(remove_progression=True)
        with transfers.inspect_archive(previous, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.target.db._rows("SELECT * FROM time_entries ORDER BY id"),
                         self.source.db._rows("SELECT * FROM time_entries ORDER BY id"))
        self.assertIsNone(self.target.db.get_setting("desktop_progression_targets"))
        self.assertIsNone(self.target.db.get_setting("desktop_progression_acknowledgements"))

    def test_disabled_targets_and_empty_acknowledgements_remain_portable(self):
        disabled = dict.fromkeys(TARGETS, 0)
        self.source.db.set_setting("desktop_progression_targets", disabled)
        self.source.db.set_setting("desktop_progression_acknowledgements", [])
        transfers.export_archive(self.source, self.archive)
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.target.db.get_setting("desktop_progression_targets"), disabled)
        self.assertEqual(self.target.db.get_setting("desktop_progression_acknowledgements"), [])

    def test_invalid_targets_rejected_before_replacing_current_data(self):
        invalid = [None, [], {}, {"work": 1200}, dict(TARGETS, extra=60),
                   dict(TARGETS, work=True), dict(TARGETS, work="1200"),
                   dict(TARGETS, work=1200.5), dict(TARGETS, work=-1),
                   dict(TARGETS, sleep=10081), dict.fromkeys(TARGETS, 3000)]
        for value in invalid:
            with self.subTest(value=value):
                self.assert_rejected_without_replacement("desktop_progression_targets", value)

    def test_invalid_acknowledgements_rejected_before_replacing_current_data(self):
        invalid = [None, {}, "week:2020-09-07|work", [False], [1],
                   ["week:2020-09-07|work"] * 2,
                   ["week:2020-09-07|unknown"], ["year:2020-09-07|work"],
                   ["week:2020-09-08|work"], ["month:2020-09-02|sleep"],
                   ["quarter:2020-08-02|rest"], ["week:2020-02-30|work"],
                   ["week:20200907|work"], ["week:2020-09-07|work\n"],
                   ["week:1999-09-06|work"], ["week:2201-09-07|work"],
                   ["week:2020-09-07|work|rest"]]
        for value in invalid:
            with self.subTest(value=value):
                self.assert_rejected_without_replacement("desktop_progression_acknowledgements", value)

    def test_excessive_acknowledgement_history_rejected(self):
        values = [f"month:{year}-{month:02d}-01|{metric}"
                  for year in range(2000, 2084) for month in range(1, 13)
                  for metric in ("work", "sleep", "sport", "rest", "recovery")][:5001]
        self.assertEqual(len(set(values)), 5001)
        self.assert_rejected_without_replacement("desktop_progression_acknowledgements", values)


if __name__ == "__main__":
    unittest.main()
