"""Optional work-session drafts survive portable and selective cloud transfers."""
from contextlib import closing
import copy
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
from mpsi_desktop.focus_session import FocusSession
from mpsi_desktop import cloud_backup as cloud, transfers
from tests.test_cloud_backup import FakeDrive


APP = QApplication.instance() or QApplication([])
KEY = "desktop_focus_session"


def draft():
    return dict(version=1, id="a" * 32, status="running", category="maths",
                title="Comprendre les suites", target_minutes=30,
                segments=[{"start_at": "2020-09-02T17:00:00.000000",
                           "end_at": "2020-09-02T17:10:00.000000"}],
                interrupted=False, entry_ids=[], review_segments=None)


class FocusTransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = AppContext(self.root / "source")
        self.target = AppContext(self.root / "destination")
        self.source.db.set_setting(KEY, draft())
        self.target.db.set_setting(KEY, {**draft(), "id": "b" * 32, "status": "paused"})
        self.target.db.set_setting("desktop_name", "À conserver")
        self.drive = FakeDrive()
        self.archive = self.root / "session.prepapilot"

    def tearDown(self):
        self.source.close()
        self.target.close()
        self.temporary.cleanup()

    def state(self, ctx):
        return {table: ctx.db._rows(f'SELECT * FROM "{table}" ORDER BY 1')
                for table in transfers._schema(ctx.db._connection)}

    def portable(self):
        transfers.export_archive(self.source, self.archive)
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            return transfers.apply_import(self.target, plan)

    def backup(self, selection):
        return cloud.backup_to_drive(self.source, self.drive, "root", selection)

    def restore(self, result):
        with cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"]) as plan:
            cloud.validate_restore_target(self.target, plan)
            return transfers.apply_import(self.target, plan)

    def changed_archive(self, value):
        transfers.export_archive(self.source, self.archive)
        with ZipFile(self.archive) as source:
            payload = {name: source.read(name) for name in source.namelist()}
        database = self.root / "edited.sqlite3"
        database.write_bytes(payload["data.sqlite3"])
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(value), KEY))
        payload["data.sqlite3"] = database.read_bytes()
        manifest = json.loads(payload["manifest.json"])
        manifest["files"]["data.sqlite3"] = {
            "size": len(payload["data.sqlite3"]),
            "sha256": hashlib.sha256(payload["data.sqlite3"]).hexdigest(),
        }
        payload["manifest.json"] = json.dumps(manifest).encode("utf-8")
        result = self.root / "changed.prepapilot"
        with ZipFile(result, "w", ZIP_DEFLATED) as target:
            for name, raw in payload.items():
                target.writestr(name, raw)
        return result

    def test_portable_checkpoint_and_rollback_preserve_optional_session(self):
        before = self.state(self.target)
        backup = self.portable()
        self.assertEqual(self.target.db.get_setting(KEY), draft())
        with transfers.inspect_archive(backup, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.state(self.target), before)

    def test_imported_running_checkpoint_loads_paused_without_adding_offline_time(self):
        self.portable()
        before = self.state(self.target)
        session = FocusSession(self.target.db)
        self.assertEqual(session.status, "paused")
        self.assertEqual(session.elapsed_seconds, 600)
        self.assertTrue(session.state["interrupted"])
        session.tick()
        self.assertEqual(session.elapsed_seconds, 600)
        self.assertEqual(self.state(self.target), before)

    def test_simple_timer_and_autonomous_work_remain_portable_and_selective(self):
        for category in (None, "permanence"):
            with self.subTest(category=category):
                value = {**draft(), "category": category}
                self.source.db.set_setting(KEY, value)
                self.portable()
                self.assertEqual(self.target.db.get_setting(KEY), value)
                self.restore(self.backup(["activities"]))
                self.assertEqual(self.target.db.get_setting(KEY), value)

    def test_old_archive_without_draft_and_explicit_empty_draft_are_supported(self):
        self.source.db._change("DELETE FROM settings WHERE key=?", (KEY,))
        self.portable()
        self.assertIsNone(self.target.db.get_setting(KEY))
        self.source.db.set_setting(KEY, None)
        self.portable()
        self.assertIsNone(self.target.db.get_setting(KEY))

    def test_archived_subject_draft_is_portable_but_unknown_subject_is_rejected(self):
        subjects = self.source.db.get_subjects()
        next(row for row in subjects if row["id"] == "maths")["active"] = False
        self.source.db.save_subjects(subjects)
        self.portable()
        self.assertEqual(self.target.db.get_setting(KEY)["category"], "maths")
        self.assertNotIn("maths", self.target.db.subject_labels())
        changed = self.changed_archive({**draft(), "category": "subject_" + "c" * 32})
        with self.assertRaises(ValueError):
            transfers.inspect_archive(changed, DesktopStore)

    def test_invalid_or_future_schema_draft_is_rejected_before_replacement(self):
        before = self.state(self.target)
        invalid = [[], "session", {}, {**draft(), "version": 2},
                   {**draft(), "target_minutes": True}, {**draft(), "target_minutes": 1000000},
                   {**draft(), "title": "a" * 251}, {**draft(), "oauth_token": "PRIVATE"},
                   {**draft(), "segments": draft()["segments"] * 1001},
                   {**draft(), "segments": [{"start_at": "bad", "end_at": "bad"}]}]
        for value in invalid:
            with self.subTest(value=str(value)[:100]):
                changed = self.changed_archive(value)
                original = changed.read_bytes()
                with self.assertRaises(ValueError):
                    transfers.inspect_archive(changed, DesktopStore)
                self.assertEqual(self.state(self.target), before)
                self.assertEqual(changed.read_bytes(), original)

    def test_activities_backup_carries_draft_without_credentials_and_deduplicates(self):
        self.source.db.set_setting("cloud_refresh_token", "PRIVATE-ACCOUNT-TOKEN")
        result = self.backup(["activities"])
        uploaded = len(self.drive.uploads)
        self.assertFalse(self.backup(["activities"])["changed"])
        self.assertEqual(len(self.drive.uploads), uploaded)
        self.assertNotIn(b"PRIVATE-ACCOUNT-TOKEN", b"\n".join(self.drive.payloads.values()))
        self.restore(result)
        self.assertEqual(self.target.db.get_setting(KEY), draft())
        self.assertEqual(self.target.db.get_setting("desktop_name"), "À conserver")
        self.source.db.set_setting(KEY, {**draft(), "status": "paused"})
        self.assertEqual(self.backup(["activities"])["uploaded"], 1)

    def test_other_selections_never_upload_or_replace_local_draft(self):
        before = copy.deepcopy(self.target.db.get_setting(KEY))
        for selection in (["preferences"], ["sleep"], ["grades"]):
            with self.subTest(selection=selection):
                self.drive = FakeDrive()
                result = self.backup(selection)
                self.assertNotIn(KEY.encode(), b"\n".join(self.drive.payloads.values()))
                self.restore(result)
                self.assertEqual(self.target.db.get_setting(KEY), before)

    def test_old_activities_backup_clears_newer_local_draft(self):
        self.source.db._change("DELETE FROM settings WHERE key=?", (KEY,))
        self.restore(self.backup(["activities"]))
        self.assertIsNone(self.target.db.get_setting(KEY))

    def test_selective_restore_remaps_draft_subject_to_imported_catalogue(self):
        incoming = self.source.db.get_subjects()
        next(row for row in incoming if row["id"] == "maths")["name"] = "Analyse"
        self.source.db.save_subjects(incoming)
        self.restore(self.backup(["activities"]))
        restored = self.target.db.get_setting(KEY)
        self.assertNotEqual(restored["category"], "maths")
        self.assertEqual(self.target.db.subject_labels()[restored["category"]], "Analyse")
        self.assertEqual(self.target.db.subject_labels()["maths"], "Mathématiques")

    def test_saved_session_references_follow_entries_renumbered_around_preserved_sleep(self):
        source_id = self.source.db.add_time_entry("maths", "2020-09-02T17:00", "2020-09-02T17:10", "Séance")
        sleep_id = self.target.db.add_time_entry("sommeil", "2020-09-01T23:00", "2020-09-02T07:00", "Nuit conservée")
        self.assertEqual(source_id, sleep_id)
        self.source.db.set_setting(KEY, {**draft(), "status": "saved", "entry_ids": [source_id]})
        self.restore(self.backup(["activities"]))
        restored = self.target.db.get_setting(KEY)
        journal = self.target.db._rows("SELECT * FROM time_entries ORDER BY id")
        work = next(row for row in journal if row["category"] == "maths")
        self.assertNotEqual(work["id"], sleep_id)
        self.assertEqual(restored["entry_ids"], [work["id"]])
        session = FocusSession(self.target.db)
        self.assertEqual(session.save(), [work["id"]])
        self.assertEqual(self.target.db._rows("SELECT * FROM time_entries ORDER BY id"), journal)

    def test_invalid_draft_rejected_before_selective_restore_changes_anything(self):
        before = self.state(self.target)
        self.source.db.set_setting(KEY, {**draft(), "category": "subject_" + "c" * 32})
        result = self.backup(["activities"])
        with self.assertRaises(ValueError):
            self.restore(result)
        self.assertEqual(self.state(self.target), before)

    def test_stale_restore_advises_pausing_running_session(self):
        result = self.backup(["grades"])
        with cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"]) as plan:
            self.target.db.set_setting(KEY, draft())
            with self.assertRaisesRegex(ValueError, "séance de travail en pause"):
                cloud.validate_restore_target(self.target, plan)


if __name__ == "__main__":
    unittest.main()
