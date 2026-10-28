"""Portable and selective backups keep folders, references and originals together."""
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext, DesktopStore
from mpsi_desktop import cloud_backup as cloud, transfers
from tests.test_cloud_backup import FakeDrive


APP = QApplication.instance() or QApplication([])


class DocumentFolderTransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = AppContext(self.root / "source")
        self.target = AppContext(self.root / "target")
        self.original = self.root / "Suites numériques.txt"
        self.original.write_text("Cours original : suites et limites.", encoding="utf-8")
        self.source.db._change("INSERT INTO document_folders(id,name) VALUES(1,?)", ("Analyse",))
        self.source.db._change("INSERT INTO document_folders(id,name) VALUES(2,?)", ("Dossier vide",))
        self.doc = self.source.db.import_document(self.original, "maths", "cours")
        self.source.db._change("UPDATE documents SET folder_id=1 WHERE id=?", (self.doc,))
        self.target.db._change("INSERT INTO document_folders(id,name) VALUES(1,?)", ("Local à conserver",))
        self.local_doc = self.target.db.import_document(self.original, "physique", "td")
        self.target.db._change("UPDATE documents SET folder_id=1 WHERE id=?", (self.local_doc,))
        self.target.db.set_setting("desktop_name", "Local")
        self.drive = FakeDrive()
        self.archive = self.root / "documents.prepapilot"

    def tearDown(self):
        self.source.close()
        self.target.close()
        self.temporary.cleanup()

    def state(self, ctx):
        return {table: ctx.db._rows(f'SELECT * FROM "{table}" ORDER BY 1')
                for table in transfers._schema(ctx.db._connection)}

    def files(self, ctx):
        return {path.name: path.read_bytes() for path in ctx.db.document_directory.iterdir() if path.is_file()}

    def backup(self, selection=("documents",)):
        return cloud.backup_to_drive(self.source, self.drive, "root", selection)

    def restore(self, result):
        with cloud.prepare_drive_restore(self.target, self.drive, "root", result["snapshot_id"]) as plan:
            cloud.validate_restore_target(self.target, plan)
            return transfers.apply_import(self.target, plan)

    def changed_archive(self, edit):
        transfers.export_archive(self.source, self.archive)
        with ZipFile(self.archive) as source:
            payload = {name: source.read(name) for name in source.namelist()}
        database = self.root / "changed.sqlite3"
        database.write_bytes(payload["data.sqlite3"])
        with closing(sqlite3.connect(database)) as connection, connection:
            edit(connection)
        payload["data.sqlite3"] = database.read_bytes()
        manifest = json.loads(payload["manifest.json"])
        manifest["files"]["data.sqlite3"] = {
            "size": len(payload["data.sqlite3"]),
            "sha256": hashlib.sha256(payload["data.sqlite3"]).hexdigest(),
        }
        payload["manifest.json"] = json.dumps(manifest).encode("utf-8")
        result = self.root / "changed.prepapilot"
        with ZipFile(result, "w", ZIP_DEFLATED) as destination:
            for name, raw in payload.items():
                destination.writestr(name, raw)
        return result

    def test_portable_roundtrip_empty_folders_originals_and_rollback(self):
        before, files = self.state(self.target), self.files(self.target)
        transfers.export_archive(self.source, self.archive)
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            rollback = transfers.apply_import(self.target, plan)
        for table in ("document_folders", "documents"):
            self.assertEqual(self.state(self.target)[table], self.state(self.source)[table])
        self.assertEqual(self.target.db.document_path(self.doc).read_bytes(), self.original.read_bytes())
        with transfers.inspect_archive(rollback, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.state(self.target), before)
        self.assertEqual(self.files(self.target), files)

    def test_legacy_portable_archive_with_or_without_grade_comparisons(self):
        for old_grades in (False, True):
            def legacy(connection):
                connection.execute("DROP TABLE document_folders")
                connection.execute("DROP INDEX documents_folder")
                connection.execute("ALTER TABLE documents DROP COLUMN folder_id")
                if old_grades:
                    connection.execute("ALTER TABLE grades RENAME TO grades_current")
                    connection.execute("""CREATE TABLE grades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, kind TEXT NOT NULL,
                        score REAL NOT NULL, scale REAL NOT NULL, coefficient REAL NOT NULL DEFAULT 1,
                        graded_on TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
                    connection.execute("INSERT INTO grades SELECT id,subject,kind,score,scale,coefficient,graded_on,label,created_at FROM grades_current")
                    connection.execute("DROP TABLE grades_current")
            with self.subTest(old_grades=old_grades):
                path = self.changed_archive(legacy)
                with transfers.inspect_archive(path, DesktopStore) as plan:
                    transfers.apply_import(self.target, plan)
                self.assertEqual(self.target.db._rows("SELECT * FROM document_folders"), [])
                self.assertIsNone(self.target.db.get_document(self.doc)["folder_id"])
                self.assertEqual(self.target.db.document_path(self.doc).read_bytes(), self.original.read_bytes())

    def test_partial_folder_schema_is_rejected(self):
        for statement in ("DROP TABLE document_folders", "ALTER TABLE documents DROP COLUMN folder_id"):
            with self.subTest(statement=statement):
                def partial(connection):
                    connection.execute("DROP INDEX documents_folder")
                    connection.execute(statement)
                path = self.changed_archive(partial)
                with self.assertRaises(ValueError):
                    transfers.inspect_archive(path, DesktopStore)

    def test_invalid_portable_folder_or_reference_never_changes_target(self):
        before, files = self.state(self.target), self.files(self.target)
        updates = [("UPDATE document_folders SET name=? WHERE id=1", (name,))
                   for name in ("", "  Analyse", "Dossier vide", "dOsSiEr ViDe", "A" * 101, "Cours\nTD")]
        updates.extend([
            ("UPDATE document_folders SET created_at='invalid' WHERE id=1", ()),
            ("UPDATE documents SET folder_id=999 WHERE id=?", (self.doc,)),
            ("UPDATE documents SET folder_id='bad' WHERE id=?", (self.doc,)),
        ])
        for sql, values in updates:
            with self.subTest(sql=sql, values=values):
                path = self.changed_archive(lambda connection: connection.execute(sql, values))
                original = path.read_bytes()
                with self.assertRaises(ValueError):
                    transfers.inspect_archive(path, DesktopStore)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(self.state(self.target), before)
                self.assertEqual(self.files(self.target), files)

    def test_drive_document_selection_replaces_folders_and_preserves_other_categories(self):
        self.target.db.add_grade("physique", "Oral", 12, 20, "2020-09-01")
        before = self.state(self.target)
        result = self.backup()
        manifest = json.loads(self.drive.payloads[result["snapshot_id"]])
        self.assertEqual(manifest["counts"]["documents"], 1)  # Empty folders are not documents.
        self.assertEqual(len(manifest["records"]["document_folders"]), 2)
        self.restore(result)
        after = self.state(self.target)
        for table in ("documents", "document_folders"):
            self.assertEqual(after[table], self.state(self.source)[table])
        for table in ("grades", "time_entries", "memories"):
            self.assertEqual(after[table], before[table])
        self.assertEqual(self.target.db.get_setting("desktop_name"), "Local")
        self.assertEqual(self.target.db.document_path(self.doc).read_bytes(), self.original.read_bytes())

    def test_drive_unselected_documents_and_folders_remain_intact(self):
        before, files = self.state(self.target), self.files(self.target)
        for selection in (["grades"], ["sleep"], ["activities"], ["preferences"]):
            with self.subTest(selection=selection):
                result = self.backup(selection)
                manifest = json.loads(self.drive.payloads[result["snapshot_id"]])
                self.assertNotIn("document_folders", manifest["records"])
                self.restore(result)
                for table in ("documents", "document_folders"):
                    self.assertEqual(self.state(self.target)[table], before[table])
                self.assertEqual(self.files(self.target), files)

    def test_old_drive_snapshot_restores_unfiled_documents_and_clears_local_folders(self):
        original_json, original_selected = cloud._json, cloud._selected
        def legacy_json(value):
            if isinstance(value, dict) and value.get("table") == "documents":
                value = {**value, "values": {key: item for key, item in value["values"].items() if key != "folder_id"}}
            return original_json(value)
        def legacy_selected(table, row, selection):
            return table != "document_folders" and original_selected(table, row, selection)
        with patch.object(cloud, "_json", side_effect=legacy_json), patch.object(cloud, "_selected", side_effect=legacy_selected):
            result = self.backup()
        self.restore(result)
        self.assertEqual(self.target.db._rows("SELECT * FROM document_folders"), [])
        self.assertIsNone(self.target.db.get_document(self.doc)["folder_id"])
        self.assertEqual(self.target.db.document_path(self.doc).read_bytes(), self.original.read_bytes())

    def test_empty_library_can_still_restore_empty_folders(self):
        self.source.db.delete_document(self.doc)
        self.restore(self.backup())
        self.assertEqual(self.target.db.list_documents(), [])
        self.assertEqual(self.target.db._rows("SELECT * FROM document_folders ORDER BY id"),
                         self.source.db._rows("SELECT * FROM document_folders ORDER BY id"))

    def test_unchanged_backup_reuses_every_object_and_folder_rename_only_uploads_metadata(self):
        self.backup()
        count = len(self.drive.uploads)
        unchanged = self.backup()
        self.assertFalse(unchanged["changed"])
        self.assertEqual(len(self.drive.uploads), count)
        self.source.db._change("UPDATE document_folders SET name='Algèbre' WHERE id=1", ())
        renamed = self.backup()
        self.assertEqual(renamed["uploaded"], 1)
        self.source.db._change("UPDATE documents SET folder_id=2 WHERE id=?", (self.doc,))
        moved = self.backup()
        self.assertEqual(moved["uploaded"], 1)
        self.assertEqual(self.source.db.document_path(self.doc).read_bytes(), self.original.read_bytes())

    def test_invalid_drive_types_references_and_folder_names_fail_before_replacement(self):
        original_json = cloud._json
        before, files = self.state(self.target), self.files(self.target)
        changes = [("document_folders", {"id": value}) for value in (True, 1.0, "1", 0, -1, 2 ** 63)]
        changes += [("document_folders", {"name": value}) for value in (" ", "\tCours", "A" * 101, True)]
        changes += [("documents", {"folder_id": value}) for value in (True, 1.0, "1", 999, -1)]
        for table, change in changes:
            def bad_json(value):
                if isinstance(value, dict) and value.get("table") == table and value["values"]["id"] == 1:
                    value = {**value, "values": {**value["values"], **change}}
                return original_json(value)
            with self.subTest(table=table, change=change):
                with patch.object(cloud, "_json", side_effect=bad_json):
                    result = self.backup()
                with self.assertRaises(ValueError):
                    self.restore(result)
                self.assertEqual(self.state(self.target), before)
                self.assertEqual(self.files(self.target), files)

    def test_folder_validation_rejects_duplicate_names_ids_and_excessive_count(self):
        base = {"id": 1, "name": "Cours", "created_at": "2020-09-01 12:00:00"}
        for rows in ([base, copy.deepcopy(base)], [base, {**base, "id": 2, "name": "COURS"}],
                     [{**base, "id": index + 1, "name": str(index)} for index in range(1001)]):
            with self.subTest(count=len(rows)):
                with self.assertRaises(ValueError):
                    transfers._validate_document_folders(rows, [])


if __name__ == "__main__":
    unittest.main()
