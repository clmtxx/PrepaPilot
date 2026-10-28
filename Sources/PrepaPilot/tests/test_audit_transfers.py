"""Additional adversarial checks using disposable documents and simulated Drive."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext, DesktopStore
from mpsi_desktop import transfers, google_auth
from mpsi_desktop.cloud_preferences import CloudPreferences, stamp
from mpsi_desktop.document_store import ALLOWED_EXTENSIONS

APP = QApplication.instance() or QApplication([])


class PortableBackupAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="prepapilot-transfer-audit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ctx = AppContext(self.root / "source")
        self.addCleanup(self.ctx.close)
        self.original = self.root / "Cours avec accents et Σ.txt"
        self.original.write_bytes(b"disposable original\x00\xff")
        self.identity = self.ctx.db.import_document(self.original, "maths", "cours")
        self.archive = self.root / "Sauvegardes avec espaces" / "Export été.prepapilot"
        transfers.export_archive(self.ctx, self.archive)

    def test_missing_managed_original_cannot_replace_a_valid_backup(self):
        previous = self.archive.read_bytes()
        self.ctx.db.document_path(self.identity).unlink()
        with self.assertRaises(ValueError):
            transfers.export_archive(self.ctx, self.archive)
        self.assertEqual(self.archive.read_bytes(), previous)
        self.assertEqual(list(self.archive.parent.glob("*.tmp-*")), [])

    def test_modified_managed_original_cannot_replace_a_valid_backup(self):
        previous = self.archive.read_bytes()
        self.ctx.db.document_path(self.identity).write_bytes(b"truncated")
        with self.assertRaises(ValueError):
            transfers.export_archive(self.ctx, self.archive)
        self.assertEqual(self.archive.read_bytes(), previous)

    def test_restore_recovers_missing_original_and_marks_previous_incomplete_state(self):
        target = AppContext(self.root / "damaged-target")
        self.addCleanup(target.close)
        target.db.set_setting("desktop_name", "Previous local profile")
        local = target.db.import_document(self.original, "maths", "cours")
        target.db.document_path(local).unlink()
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            recovery = transfers.apply_import(target, plan)
        self.assertEqual(target.db.document_path(self.identity).read_bytes(), self.original.read_bytes())
        self.assertTrue(recovery.name.startswith("etat-incomplet-avant-import-"))
        self.assertEqual(recovery.suffix, ".zip")
        with ZipFile(recovery) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["format"], "prepapilot-incomplete")
            self.assertEqual(len(manifest["incomplete_documents"]), 1)
            database = self.root / "recovery.sqlite3"
            database.write_bytes(archive.read("data.sqlite3"))
        with closing(sqlite3.connect(database)) as connection:
            previous = json.loads(connection.execute("SELECT value FROM settings WHERE key='desktop_name'").fetchone()[0])
            self.assertEqual(previous, "Previous local profile")
            self.assertEqual(connection.execute("SELECT count(*) FROM documents").fetchone()[0], 1)
        with self.assertRaises(ValueError):
            transfers.inspect_archive(recovery, DesktopStore)

    def test_unrelated_backup_errors_never_allow_import_without_safety_copy(self):
        self.ctx.db.set_setting("desktop_name", "Keep this profile")
        database = self.ctx.db
        for error in (OSError("disposable full disk"), sqlite3.DatabaseError("disposable database failure")):
            with self.subTest(error=type(error).__name__):
                with transfers.inspect_archive(self.archive, DesktopStore) as plan:
                    with patch.object(transfers, "_snapshot", side_effect=error):
                        with self.assertRaises(type(error)):
                            transfers.apply_import(self.ctx, plan)
                self.assertIs(self.ctx.db, database)
                self.assertEqual(self.ctx.db.get_setting("desktop_name"), "Keep this profile")
                self.assertEqual(list((self.ctx.data_dir / "backups").iterdir()), [])

    def test_incomplete_recovery_copy_failure_prevents_import(self):
        self.ctx.db.set_setting("desktop_name", "Keep damaged profile")
        self.ctx.db.document_path(self.identity).unlink()
        snapshot = transfers._snapshot
        attempts = []

        def fail_recovery_copy(source, target):
            attempts.append(target)
            if len(attempts) == 2:
                raise OSError("disposable recovery disk failure")
            return snapshot(source, target)

        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            with patch.object(transfers, "_snapshot", side_effect=fail_recovery_copy):
                with self.assertRaises(OSError):
                    transfers.apply_import(self.ctx, plan)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(self.ctx.db.get_setting("desktop_name"), "Keep damaged profile")
        self.assertEqual(list((self.ctx.data_dir / "backups").iterdir()), [])

    def test_failed_import_rolls_back_exact_originals_with_incomplete_recovery_copy(self):
        target = AppContext(self.root / "truncated-target")
        self.addCleanup(target.close)
        target.db.set_setting("desktop_name", "Keep damaged profile")
        local = target.db.import_document(self.original, "maths", "cours")
        target.db.document_path(local).write_bytes(b"truncated available bytes")
        replace = transfers.os.replace

        def fail_install(source, destination):
            if Path(source).name == "documents" and Path(source).parent.name == "new":
                raise OSError("disposable install failure")
            return replace(source, destination)

        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            with patch.object(transfers.os, "replace", side_effect=fail_install):
                with self.assertRaises(OSError):
                    transfers.apply_import(target, plan)
        self.assertEqual(target.db.get_setting("desktop_name"), "Keep damaged profile")
        self.assertEqual(target.db.document_path(local).read_bytes(), b"truncated available bytes")
        recovery = list((target.data_dir / "backups").glob("etat-incomplet-*.zip"))
        self.assertEqual(len(recovery), 1)
        self.assertEqual(list(target.data_dir.glob(".restore-*")), [])

    def test_failed_reload_restores_profile_data_connections_and_ui_for_all_original_states(self):
        self.ctx.db.set_setting("desktop_name", "Imported profile")
        self.ctx.db.set_setting("desktop_theme", "dark")
        self.ctx.db.set_setting("school_year", 2028)
        self.ctx.db.set_setting("school_years", [2026, 2028])
        transfers.export_archive(self.ctx, self.archive)
        for original_state in ("normal", "missing", "modified"):
            with self.subTest(original_state=original_state):
                target = AppContext(self.root / ("r-" + original_state[:2]))
                self.addCleanup(target.close)
                target.db.set_setting("desktop_name", "Original local profile")
                target.db.add_grade("physique", "Examen", 13, 20, "2020-09-01", "Original grade")
                target.db.remember("objectif", "Keep original memory")
                local = target.db.import_document(self.original, "physique", "td", title="Original local document")
                original_path = target.db.document_path(local)
                if original_state == "missing":
                    original_path.unlink()
                elif original_state == "modified":
                    original_path.write_bytes(b"available modified original bytes")
                original_bytes = original_path.read_bytes() if original_path.exists() else None
                target.reload_data()
                before = {table: target.db._rows('SELECT * FROM "' + table + '" ORDER BY 1')
                          for table in transfers._schema(target.db._connection)}
                previous_connection = target.db._connection
                previous_year = target.year
                previous_years = target.available_years
                themes, profiles, connections = [], [], []
                target.theme_changed.connect(themes.append)
                target.data_replaced.connect(lambda: profiles.append(target.db.get_setting("desktop_name")))
                real_reload = target.reload_data
                failure = OSError("disposable failure after partially refreshing imported UI")

                def reload_then_fail_once():
                    connections.append(target.db._connection)
                    real_reload()
                    if len(connections) == 1:
                        raise failure

                with transfers.inspect_archive(self.archive, DesktopStore) as plan:
                    with patch.object(target, "reload_data", side_effect=reload_then_fail_once):
                        with self.assertRaises(OSError) as caught:
                            transfers.apply_import(target, plan)
                self.assertIs(caught.exception, failure, str(caught.exception))
                self.assertEqual(len(connections), 2)
                self.assertIs(target.db._connection, connections[1])
                for closed_connection in (previous_connection, connections[0]):
                    with self.assertRaises(sqlite3.ProgrammingError):
                        closed_connection.execute("SELECT 1")
                self.assertEqual(target.db._connection.execute("SELECT 1").fetchone()[0], 1)
                for table, rows in before.items():
                    self.assertEqual(target.db._rows('SELECT * FROM "' + table + '" ORDER BY 1'), rows)
                self.assertEqual(target.theme, "light")
                self.assertEqual(target.year, previous_year)
                self.assertEqual(target.available_years, previous_years)
                self.assertEqual(themes, ["dark", "light"])
                self.assertEqual(profiles, ["Imported profile", "Original local profile"])
                self.assertEqual(original_path.read_bytes() if original_path.exists() else None, original_bytes)
                self.assertEqual(list(target.data_dir.glob(".restore-*")), [])
                backups = list((target.data_dir / "backups").iterdir())
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].suffix, ".prepapilot" if original_state == "normal" else ".zip")

    def test_persistent_reload_failure_preserves_original_error_and_accessible_original_data(self):
        self.ctx.db.set_setting("desktop_name", "Original local profile")
        original_bytes = self.ctx.db.document_path(self.identity).read_bytes()
        first = OSError("initial reload failure")
        second = RuntimeError("secondary refresh failure must not mask initial failure")
        imported_connections = []

        def fail_reload():
            imported_connections.append(self.ctx.db._connection)
            raise first if len(imported_connections) == 1 else second

        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            with patch.object(self.ctx, "reload_data", side_effect=fail_reload):
                with self.assertRaises(OSError) as caught:
                    transfers.apply_import(self.ctx, plan)
        self.assertIs(caught.exception, first)
        self.assertEqual(len(imported_connections), 2)
        with self.assertRaises(sqlite3.ProgrammingError):
            imported_connections[0].execute("SELECT 1")
        self.assertEqual(self.ctx.db._connection.execute("SELECT 1").fetchone()[0], 1)
        self.assertEqual(self.ctx.db.get_setting("desktop_name"), "Original local profile")
        self.assertEqual(self.ctx.db.document_path(self.identity).read_bytes(), original_bytes)
        self.assertEqual(list(self.ctx.data_dir.glob(".restore-*")), [])

    def test_failed_physical_rollback_keeps_original_staging_available(self):
        self.ctx.db.set_setting("desktop_name", "Original local profile")
        original_bytes = self.ctx.db.document_path(self.identity).read_bytes()
        replace = transfers.os.replace

        def fail_rollback(source, destination):
            if Path(source).name == "mpsi.sqlite3" and Path(source).parent.name == "original":
                raise OSError("disposable rollback destination failure")
            return replace(source, destination)

        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            with patch.object(self.ctx, "reload_data", side_effect=OSError("disposable reload failure")):
                with patch.object(transfers.os, "replace", side_effect=fail_rollback):
                    with self.assertRaisesRegex(OSError, "rollback destination"):
                        transfers.apply_import(self.ctx, plan)
        staging = list(self.ctx.data_dir.glob(".restore-*"))
        self.assertEqual(len(staging), 1)
        original = staging[0] / "original"
        self.assertEqual(next((original / "documents").iterdir()).read_bytes(), original_bytes)
        with closing(sqlite3.connect(original / "mpsi.sqlite3")) as connection:
            name = connection.execute("SELECT value FROM settings WHERE key='desktop_name'").fetchone()[0]
            self.assertEqual(json.loads(name), "Original local profile")

    def test_document_original_names_extensions_and_binary_payload_round_trip(self):
        for extension in sorted(ALLOWED_EXTENSIONS):
            source = self.root / ("Exercice Σ avec accents" + extension.upper())
            source.write_bytes(bytes(range(256)))
            self.ctx.db.import_document(source, "maths", "td")
        transfers.export_archive(self.ctx, self.archive)
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            self.assertEqual(plan.counts["documents"], len(ALLOWED_EXTENSIONS) + 1)
            self.assertEqual(len(list((plan.folder / "documents").iterdir())), len(ALLOWED_EXTENSIONS) + 1)

    def test_truncated_zip_never_mutates_the_original_database_or_documents(self):
        raw = self.archive.read_bytes()
        before = self.ctx.db.get_document(self.identity)
        attachment = self.ctx.db.document_path(self.identity).read_bytes()
        for length in (0, 1, 4, len(raw) // 2, len(raw) - 22, len(raw) - 1):
            with self.subTest(length=length):
                broken = self.root / "truncated.prepapilot"
                broken.write_bytes(raw[:length])
                with self.assertRaises(ValueError):
                    transfers.inspect_archive(broken, DesktopStore)
                self.assertEqual(self.ctx.db.get_document(self.identity), before)
                self.assertEqual(self.ctx.db.document_path(self.identity).read_bytes(), attachment)

    def test_failed_atomic_archive_replacement_preserves_previous_backup(self):
        previous = self.archive.read_bytes()
        with patch.object(transfers.os, "replace", side_effect=OSError("disposable destination locked")):
            with self.assertRaises(OSError):
                transfers.export_archive(self.ctx, self.archive)
        self.assertEqual(self.archive.read_bytes(), previous)
        self.assertEqual(list(self.archive.parent.glob("*.tmp-*")), [])

    def test_invalid_archive_binary_encoding_is_a_user_validation_error(self):
        with ZipFile(self.archive) as archive:
            payload = {name: archive.read(name) for name in archive.namelist()}
        payload["manifest.json"] = b"\xff\xfeinvalid"
        broken = self.root / "encoding.prepapilot"
        with ZipFile(broken, "w", ZIP_DEFLATED) as archive:
            for name, raw in payload.items():
                archive.writestr(name, raw)
        with self.assertRaises(ValueError):
            transfers.inspect_archive(broken, DesktopStore)


class CorruptCloudConfigurationAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="prepapilot-cloud-audit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_out_of_range_utc_timestamp_is_ignored(self):
        for raw in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
            with self.subTest(raw=raw):
                self.assertIsNone(stamp(raw))
                preferences = CloudPreferences(self.root)
                preferences.path.parent.mkdir(exist_ok=True)
                preferences.path.write_text(json.dumps({"first_seen": raw}), encoding="utf-8")
                self.assertIsNone(preferences.read()["first_seen"])

    def test_far_future_reminder_timestamp_does_not_overflow(self):
        preferences = CloudPreferences(self.root)
        preferences.update(first_seen="9999-12-31T23:59:59+00:00")
        self.assertFalse(preferences.due(datetime(2026, 10, 25, tzinfo=timezone.utc)))

    def test_deeply_nested_google_configuration_is_a_user_validation_error(self):
        path = self.root / "invalid-google.json"
        path.write_bytes(b'{"installed":' + b'[' * 20000 + b'0' + b']' * 20000 + b'}')
        connection = google_auth.GoogleConnection(self.root)
        with self.assertRaises(google_auth.GoogleDriveError):
            connection.configure(path)
        self.assertFalse(connection.config_path.exists())

    def test_deeply_nested_google_response_is_a_user_validation_error(self):
        raw = b'{"reply":' + b'[' * 20000 + b'0' + b']' * 20000 + b'}'
        with self.assertRaises(google_auth.GoogleDriveError):
            google_auth.decode_json(raw)

    def test_deeply_nested_saved_tokens_make_connection_disconnected(self):
        connection = google_auth.GoogleConnection(self.root)
        connection.cloud_dir.mkdir(parents=True)
        config = {"client_id": "123456789-test.apps.googleusercontent.com", "client_secret": ""}
        connection.config_path.write_text(json.dumps({"installed": config}), encoding="utf-8")
        connection.token_path.write_bytes(b'disposable encrypted fixture')
        raw = b'{"reply":' + b'[' * 20000 + b'0' + b']' * 20000 + b'}'
        with patch.object(google_auth, "_protect", return_value=raw):
            self.assertFalse(connection.connected)

    def test_oversized_token_expiration_is_invalid_instead_of_overflowing(self):
        config = {"client_id": "123456789-test.apps.googleusercontent.com", "client_secret": ""}
        tokens = dict(client_id=config["client_id"], access_token="fixture", refresh_token="fixture", expires_at=10**400)
        self.assertFalse(google_auth._valid_tokens(tokens, config["client_id"]))
        connection = google_auth.GoogleConnection(self.root)
        response = dict(access_token="fixture", refresh_token="fixture", expires_in=10**400)
        with self.assertRaises(google_auth.GoogleDriveError):
            connection._save_tokens(response, config)


if __name__ == "__main__":
    unittest.main()
