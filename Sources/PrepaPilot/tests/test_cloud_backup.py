"""Incremental cloud snapshots and selective restoration, without a real account."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext
from mpsi_desktop import cloud_backup as cloud
from mpsi_desktop import transfers

APP = QApplication.instance() or QApplication([])


class FakeDrive:
    def __init__(self):
        self.files = {"root": {"id": "root", "name": "PrépaPilot", "mimeType": cloud.FOLDER,
                               "appProperties": {"prepapilot": "backup-v1"}}}
        self.payloads = {}
        self.uploads = []
        self.fail_after = None

    def get_file(self, identity):
        if identity not in self.files:
            raise ValueError("Fichier Drive absent")
        return copy.deepcopy(self.files[identity])

    def list_children(self, parent):
        return [self.get_file(key) for key, value in self.files.items() if parent in value.get("parents", [])]

    def upload_file(self, parent, name, path, mime_type="application/octet-stream", properties=None):
        if self.fail_after is not None and len(self.uploads) >= self.fail_after:
            raise ValueError("Connexion interrompue")
        identity = str(len(self.files))
        raw = Path(path).read_bytes()
        self.files[identity] = {"id": identity, "name": name, "mimeType": mime_type, "parents": [parent],
                                "size": str(len(raw)), "md5Checksum": hashlib.md5(raw).hexdigest(),
                                "appProperties": properties or {}}
        self.payloads[identity] = raw
        self.uploads.append(identity)
        return self.get_file(identity)

    def download_file(self, identity, target, max_bytes):
        raw = self.payloads[identity]
        if len(raw) > max_bytes:
            raise ValueError("Limite de téléchargement dépassée")
        Path(target).write_bytes(raw)
        return self.get_file(identity)


class CloudBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = AppContext(self.root / "source")
        self.target = AppContext(self.root / "target")
        self.drive = FakeDrive()
        self.grade = self.source.db.add_grade("maths", "Examen", 16, 20, "2020-09-01", "Suites")
        self.source.db.add_time_entry("maths", "2020-09-02T17:00", "2020-09-02T18:00", "Révisions")
        self.source.db.add_time_entry("sommeil", "2020-09-02T23:00", "2020-09-03T07:00", "Nuit")
        self.source.db.set_setting("desktop_name", "Alice")
        self.source.db.remember("objectif", "Réviser régulièrement")
        self.original = self.root / "cours.txt"
        self.original.write_text("Un cours avec ∑ et des accents.", encoding="utf-8")
        self.document = self.source.db.import_document(self.original, "maths", "cours")
        self.target.db.set_setting("desktop_name", "Bob")
        self.target.db.add_grade("physique", "Oral", 12, 20, "2020-09-01")

    def tearDown(self):
        self.source.close()
        self.target.close()
        self.temp.cleanup()

    def backup(self, selection=None):
        return cloud.backup_to_drive(self.source, self.drive, "root", selection or list(cloud.CATEGORIES))

    def state(self, ctx):
        with ctx.db._lock:
            return {table: ctx.db._rows(f'SELECT * FROM "{table}" ORDER BY 1')
                    for table in transfers._schema(ctx.db._connection)}

    def test_two_unchanged_backups_do_not_upload_anything_or_duplicate_snapshot(self):
        first = self.backup()
        count = len(self.drive.uploads)
        second = self.backup()
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(second["uploaded"], 0)
        self.assertEqual(second["reused"], first["uploaded"])
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(len(self.drive.uploads), count)
        self.assertEqual(len(cloud.list_snapshots(self.drive, "root")), 1)

    def test_one_changed_record_only_uploads_that_record_and_new_manifest(self):
        first = self.backup()
        count = len(self.drive.uploads)
        self.source.db.update_grade(self.grade, "maths", "Examen", 17, 20, "2020-09-01", "Suites")
        second = self.backup()
        self.assertTrue(second["changed"])
        self.assertEqual(second["uploaded"], 1)
        self.assertEqual(len(self.drive.uploads), count + 2)
        self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(len(cloud.list_snapshots(self.drive, "root")), 2)

    def test_comparisons_survive_selective_restore_and_only_changed_note_is_uploaded(self):
        self.backup(["grades"])
        self.source.db.update_grade(self.grade, "maths", "Examen", 8, 10, "2020-09-01", "Suites",
                                    class_average=5.5, rank=2, class_size=30)
        result = self.backup(["grades"])
        self.assertEqual(result["uploaded"], 1)
        before = self.state(self.target)
        with cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"]) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.target.db.list_grades(), self.source.db.list_grades())
        after = self.state(self.target)
        for table in ("documents", "time_entries", "memories", "time_day_templates"):
            self.assertEqual(after[table], before[table])
        self.assertFalse(self.backup(["grades"])["changed"])

    def test_pre_comparison_drive_snapshot_restores_unknown_fields_as_none(self):
        original_json = cloud._json

        def legacy_json(value):
            if isinstance(value, dict) and value.get("table") == "grades":
                value = {**value, "values": {key: item for key, item in value["values"].items()
                                             if key not in transfers.GRADE_COMPARISON_COLUMNS}}
            return original_json(value)

        with patch.object(cloud, "_json", side_effect=legacy_json):
            result = self.backup(["grades"])
        with cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"]) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.target.db.list_grades(), self.source.db.list_grades())
        row = self.target.db.list_grades()[0]
        self.assertTrue(all(row[key] is None for key in transfers.GRADE_COMPARISON_COLUMNS))

    def test_invalid_drive_comparisons_are_rejected_before_sqlite_type_coercion(self):
        original_json = cloud._json
        before = self.state(self.target)
        for changes in ({"class_average": True}, {"class_average": "10"},
                        {"rank": True, "class_size": 30}, {"rank": 1.0, "class_size": 30},
                        {"rank": 1, "class_size": "30"}, {"rank": 1},
                        {"rank": 31, "class_size": 30}, {"class_average": 21}):
            def changed_json(value):
                if isinstance(value, dict) and value.get("table") == "grades":
                    value = {**value, "values": {**value["values"], **changes}}
                return original_json(value)
            with self.subTest(changes=changes):
                with patch.object(cloud, "_json", side_effect=changed_json):
                    result = self.backup(["grades"])
                with self.assertRaises(ValueError):
                    cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"])
                self.assertEqual(self.state(self.target), before)

    def test_identical_document_binaries_are_stored_once(self):
        self.source.db.import_document(self.original, "physique", "td")
        result = self.backup(["documents"])
        manifest = json.loads(self.drive.payloads[result["snapshot_id"]])
        self.assertEqual(len(manifest["files"]), 2)
        self.assertEqual(len({item["hash"] for item in manifest["files"].values()}), 1)

    def test_full_restore_another_pc_and_local_rollback_archive(self):
        result = self.backup()
        before = self.state(self.target)
        with cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"]) as plan:
            self.assertEqual(set(plan.cloud_selection), set(cloud.CATEGORIES))
            self.assertEqual(self.state(self.target), before)
            backup = transfers.apply_import(self.target, plan)
        self.assertEqual(self.target.db.get_setting("desktop_name"), "Alice")
        for table in ("grades", "documents", "time_entries", "memories"):
            self.assertEqual(self.state(self.target)[table], self.state(self.source)[table])
        self.assertEqual(self.target.db.document_path(self.document).read_bytes(), self.original.read_bytes())
        with transfers.inspect_archive(backup, type(self.target.db)) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.state(self.target), before)

    def test_sleep_only_preserves_all_other_categories_and_replaces_previous_sleep(self):
        local_doc = self.target.db.import_document(self.original, "physique", "cours")
        self.target.db.add_time_entry("sport", "2020-09-02T18:00", "2020-09-02T19:00", "Course")
        self.target.db.add_time_entry("sommeil", "2020-09-01T23:00", "2020-09-02T07:00", "Ancienne nuit")
        self.target.db.set_setting("cloud_secret", "LOCAL-ONLY-TOKEN")
        before = self.state(self.target)
        result = self.backup(["sleep"])
        with cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"]) as plan:
            transfers.apply_import(self.target, plan)
        after = self.state(self.target)
        for table in ("grades", "documents", "memories", "time_day_templates"):
            self.assertEqual(before[table], after[table])
        self.assertEqual(self.target.db.get_setting("desktop_name"), "Bob")
        self.assertEqual(self.target.db.get_setting("cloud_secret"), "LOCAL-ONLY-TOKEN")
        self.assertEqual(self.target.db.document_path(local_doc).read_bytes(), self.original.read_bytes())
        self.assertEqual({row["title"] for row in after["time_entries"]}, {"Course", "Nuit"})
        self.assertEqual(next(row for row in after["time_entries"] if row["title"] == "Course"),
                         next(row for row in before["time_entries"] if row["title"] == "Course"))

    def test_credentials_and_unselected_data_are_never_uploaded(self):
        self.source.db.set_setting("cloud_refresh_token", "VERY-PRIVATE-TOKEN")
        self.source.db.set_setting("google_oauth", {"secret": "ALSO-PRIVATE"})
        self.source.db.remember("private", "NEVER-UPLOADED")
        result = self.backup(["grades"])
        raw = b"\n".join(self.drive.payloads.values())
        for value in (b"VERY-PRIVATE-TOKEN", b"ALSO-PRIVATE", b"NEVER-UPLOADED", self.original.read_bytes()):
            self.assertNotIn(value, raw)
        manifest = json.loads(self.drive.payloads[result["snapshot_id"]])
        self.assertEqual(set(manifest["records"]), {"settings", "grades"})

    def test_overlap_during_selective_restore_rejected_without_changing_local_data(self):
        self.target.db.add_time_entry("sport", "2020-09-03T06:30", "2020-09-03T07:30", "Course")
        before = self.state(self.target)
        result = self.backup(["sleep"])
        with self.assertRaisesRegex(ValueError, "chevauchent"):
            cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"])
        self.assertEqual(self.state(self.target), before)
        self.assertFalse((self.target.data_dir / "backups").exists())

    def test_interrupted_backup_publishes_no_manifest_and_retry_reuses_objects(self):
        self.drive.fail_after = 3
        with self.assertRaisesRegex(ValueError, "interrompue"):
            self.backup()
        self.assertEqual(cloud.list_snapshots(self.drive, "root"), [])
        self.drive.fail_after = None
        result = self.backup()
        self.assertEqual(result["reused"], 3)
        self.assertEqual(len(cloud.list_snapshots(self.drive, "root")), 1)

    def test_tampered_or_missing_object_never_changes_local_data(self):
        result = self.backup()
        before = self.state(self.target)
        manifest = json.loads(self.drive.payloads[result["snapshot_id"]])
        identity = next(iter(manifest["objects"].values()))["id"]
        original = self.drive.payloads[identity]
        self.drive.payloads[identity] = b"X" * len(original)
        with self.assertRaises(ValueError):
            cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"])
        self.assertEqual(self.state(self.target), before)
        del self.drive.files[identity]
        with self.assertRaises(ValueError):
            cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"])
        self.assertEqual(self.state(self.target), before)

    def test_existing_corrupt_object_is_replaced_before_publishing_a_new_snapshot(self):
        first = self.backup()
        manifest = json.loads(self.drive.payloads[first["snapshot_id"]])
        identity = next(iter(manifest["objects"].values()))["id"]
        self.drive.files[identity]["md5Checksum"] = "0" * 32
        second = self.backup()
        self.assertEqual(second["uploaded"], 1)
        self.assertTrue(second["changed"])
        with cloud.prepare_drive_restore(self.target, self.drive, "root", second["snapshot_id"]) as plan:
            self.assertEqual(plan.counts["grades"], 1)

    def test_cancel_does_not_publish_snapshot(self):
        cancelled = threading.Event()
        def progress(message):
            if message.startswith("Vérification"):
                cancelled.set()
        with self.assertRaisesRegex(ValueError, "annulée"):
            cloud.backup_to_drive(self.source, self.drive, "root", ["grades"], progress, cancelled)
        self.assertEqual(cloud.list_snapshots(self.drive, "root"), [])

    def test_foreign_folder_or_snapshot_parent_is_rejected(self):
        result = self.backup()
        self.drive.files[result["snapshot_id"]]["parents"] = ["someone-else"]
        with self.assertRaises(ValueError):
            cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"])
        self.drive.files["root"]["appProperties"] = {}
        with self.assertRaises(ValueError):
            self.backup()

    def test_subject_collision_does_not_rename_subject_used_by_local_documents(self):
        subjects = self.target.db.get_subjects()
        next(row for row in subjects if row["id"] == "maths")["name"] = "Droit"
        self.target.db.save_subjects(subjects)
        local_doc = self.target.db.import_document(self.original, "maths", "cours")
        result = self.backup(["grades"])
        for _ in range(2):
            with cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"]) as plan:
                transfers.apply_import(self.target, plan)
        self.assertEqual(self.target.db.subject_labels()["maths"], "Droit")
        grade = self.target.db.list_grades()[0]
        self.assertNotEqual(grade["subject"], "maths")
        self.assertEqual(self.target.db.subject_labels()[grade["subject"]], "Mathématiques")
        self.assertEqual(self.target.db.list_documents()[0]["id"], local_doc)
        self.assertEqual(len(self.target.db.get_subjects()), len(subjects) + 1)

    def test_progress_callback_and_busy_context_do_not_block_background_snapshot(self):
        messages = []
        sentinel = object()
        self.source._jobs.add(sentinel)
        try:
            result = cloud.backup_to_drive(self.source, self.drive, "root", ["grades"], messages.append)
        finally:
            self.source._jobs.remove(sentinel)
        self.assertTrue(messages)
        with cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"]) as plan:
            self.assertEqual(plan.counts["grades"], 1)

    def test_changed_local_database_rejects_prepared_restore(self):
        result = self.backup(['grades'])
        with cloud.prepare_drive_restore(self.target, self.drive, 'root', result['snapshot_id']) as plan:
            cloud.validate_restore_target(self.target, plan)
            self.target.db.remember('Nouveau repère', 'À conserver')
            with self.assertRaisesRegex(ValueError, 'changé'):
                cloud.validate_restore_target(self.target, plan)
        self.assertIn('Nouveau repère', str(self.target.db.memories()))

    def test_external_edit_of_preserved_document_rejects_prepared_restore(self):
        identity = self.target.db.import_document(self.original, 'maths', 'cours')
        path = self.target.db.document_path(identity)
        result = self.backup(['grades'])
        with cloud.prepare_drive_restore(self.target, self.drive, 'root', result['snapshot_id']) as plan:
            cloud.validate_restore_target(self.target, plan)
            revision = self.target.db._connection.total_changes
            changed = b'X' * path.stat().st_size
            path.write_bytes(changed)
            self.assertEqual(revision, self.target.db._connection.total_changes)
            with self.assertRaisesRegex(ValueError, 'document conservé'):
                cloud.validate_restore_target(self.target, plan)
        self.assertEqual(path.read_bytes(), changed)


if __name__ == "__main__":
    unittest.main()
