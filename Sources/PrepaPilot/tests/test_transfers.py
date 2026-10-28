"""Portable round trips, hostile archive rejection and recoverable replacement."""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext, DesktopStore
from mpsi_desktop.settings_page import SettingsPage
from mpsi_desktop import transfers

APP = QApplication.instance() or QApplication([])


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = AppContext(self.root / "premier-pc")
        self.target = AppContext(self.root / "autre-pc")
        self.source.db.add_grade("maths", "ds", 16, 20, "2026-09-20", "Suites", 2)
        self.source.db.remember("objectif", "Progresser régulièrement")
        self.source.db.set_setting("desktop_name", "Alice")
        self.source.db.set_setting("desktop_theme", "dark")
        self.source.db.set_setting("desktop_reduced_motion", True)
        self.source.db.set_setting("school_year", 2026)
        original = self.root / "cours.txt"
        original.write_text("Un vrai document original : ∑ n²", encoding="utf-8")
        self.doc = self.source.db.import_document(original, "maths", "cours")
        original.unlink()
        self.source.db.add_time_entry("maths", "2026-09-10T21:00", "2026-09-10T22:15", "Révisions", "completed")
        removed = self.source.db.add_time_entry("repas", "2026-09-10T22:30", "2026-09-10T23:00", "Dîner", "completed")
        self.source.db.delete_time_entry(removed)
        self.source.db.ensure_day("2026-09-14")
        self.source.db.set_semester("S2", "2027-02-08")
        self.target.db.set_setting("desktop_name", "Bob")
        self.target.db.add_grade("physique", "ds", 12, 20, "2026-09-18")
        self.archive = self.root / "export.prepapilot"
        transfers.export_archive(self.source, self.archive)

    def tearDown(self):
        self.source.close()
        self.target.close()
        self.temp.cleanup()

    def rewrite(self, mutation=None, extra=None):
        with ZipFile(self.archive) as archive:
            payload = {name: archive.read(name) for name in archive.namelist()}
        manifest = json.loads(payload["manifest.json"])
        if mutation:
            mutation(payload, manifest)
        payload["manifest.json"] = json.dumps(manifest).encode()
        result = self.root / "changed.prepapilot"
        with ZipFile(result, "w", ZIP_DEFLATED) as archive:
            for name, value in payload.items():
                archive.writestr(name, value)
            if extra:
                archive.writestr(*extra)
        return result

    def mutate_database(self, sql):
        def edit(payload, manifest):
            path = self.root / "edit.sqlite3"
            path.write_bytes(payload["data.sqlite3"])
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("PRAGMA ignore_check_constraints=ON")
                connection.executescript(sql)
            payload["data.sqlite3"] = path.read_bytes()
            manifest["files"]["data.sqlite3"] = {"size": len(payload["data.sqlite3"]), "sha256": hashlib.sha256(payload["data.sqlite3"]).hexdigest()}
        return self.rewrite(edit)

    def assert_original_target(self):
        self.assertEqual(self.target.db.get_setting("desktop_name"), "Bob")
        self.assertEqual(self.target.db.list_grades()[0]["subject"], "physique")
        self.assertEqual(self.target.db.list_documents(), [])

    def test_round_trip_another_directory_all_data_and_automatic_backup(self):
        moved = self.root / "cle-usb" / "donnees.prepapilot"
        moved.parent.mkdir()
        shutil.move(self.archive, moved)
        with transfers.inspect_archive(moved, DesktopStore) as plan:
            self.assertEqual(plan.counts["grades"], 1)
            self.assertEqual(plan.counts["documents"], 1)
            backup = transfers.apply_import(self.target, plan)
        self.assertTrue(backup.is_file())
        self.assertEqual(self.target.theme, "dark")
        self.assertEqual(self.target.db.get_setting("desktop_name"), "Alice")
        self.assertEqual(self.target.db.memories(), self.source.db.memories())
        self.assertEqual(self.target.db.get_setting("desktop_timetable"), self.source.db.get_setting("desktop_timetable"))
        self.assertEqual(self.target.db.get_setting("time_semester_transitions"), self.source.db.get_setting("time_semester_transitions"))
        for table in ("grades", "time_entries", "time_day_templates", "documents", "document_migrations"):
            self.assertEqual(self.target.db._rows(f"SELECT * FROM {table}"), self.source.db._rows(f"SELECT * FROM {table}"))
        path = self.target.db.document_path(self.doc)
        self.assertTrue(path.is_relative_to(self.target.data_dir))
        self.assertIn("∑ n²", path.read_text(encoding="utf-8"))
        with transfers.inspect_archive(backup, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assert_original_target()

    def test_cancel_validated_import_leaves_target_and_profile_unchanged(self):
        page = SettingsPage(self.target)
        with patch("mpsi_desktop.settings_page.QFileDialog.getOpenFileName", return_value=(str(self.archive), "")), patch("mpsi_desktop.settings_page.confirm", return_value=False):
            page.import_all()
        self.assert_original_target()
        self.assertFalse((self.target.data_dir / "backups").exists())
        self.assertEqual(page.name.text(), "Bob")
        page.deleteLater()

    def test_checksum_and_unknown_version_rejected_before_mutation(self):
        for mutation in (
            lambda files, manifest: files.__setitem__("data.sqlite3", files["data.sqlite3"] + b"changed"),
            lambda files, manifest: manifest.__setitem__("version", 999),
        ):
            with self.assertRaises(ValueError):
                transfers.inspect_archive(self.rewrite(mutation), DesktopStore)
            self.assert_original_target()

    def test_unsafe_zip_paths_duplicates_and_symlinks_rejected(self):
        for name in ("../outside.txt", "documents/../../outside.txt", "C:/outside.txt", "documents\\outside.txt", "documents/CON.txt", "documents/x:stream", "DATA.SQLITE3"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                transfers.inspect_archive(self.rewrite(extra=(name, b"x")), DesktopStore)
        info = ZipInfo("documents/link.txt")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        with self.assertRaises(ValueError):
            transfers.inspect_archive(self.rewrite(extra=(info, b"../../other")), DesktopStore)
        self.assertFalse((self.root / "outside.txt").exists())

    def test_trigger_and_schema_change_rejected(self):
        for sql in (
            "CREATE TRIGGER hostile AFTER INSERT ON grades BEGIN DELETE FROM memories; END;",
            "ALTER TABLE grades ADD COLUMN surprise TEXT;",
        ):
            with self.assertRaises(ValueError):
                transfers.inspect_archive(self.mutate_database(sql), DesktopStore)
            self.assert_original_target()

    def test_invalid_document_activity_and_timetable_metadata_rejected(self):
        for sql in (
            "UPDATE documents SET stored_path='C:/Users/person/private.pdf';",
            "UPDATE documents SET subject='inconnue';",
            "UPDATE time_entries SET category='inconnue';",
            "UPDATE time_entries SET start_at='bad-date';",
            "UPDATE time_day_templates SET slots_json='{}';",
            "UPDATE settings SET value='{}' WHERE key='desktop_timetable';",
            "UPDATE settings SET value='\"nonsense\"' WHERE key='school_year';",
        ):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                transfers.inspect_archive(self.mutate_database(sql), DesktopStore)
            self.assert_original_target()

    def test_missing_attachment_rejected_even_with_updated_manifest(self):
        def remove(payload, manifest):
            name = next(name for name in payload if name.startswith("documents/"))
            del payload[name]
            del manifest["files"][name]
        with self.assertRaises(ValueError):
            transfers.inspect_archive(self.rewrite(remove), DesktopStore)

    def test_size_limits_prevent_expansion_and_preserve_existing_export(self):
        with patch.object(transfers, "MAX_TOTAL", 10), self.assertRaises(ValueError):
            transfers.inspect_archive(self.archive, DesktopStore)
        original = self.archive.read_bytes()
        with patch.object(transfers, "MAX_DATABASE", 10), self.assertRaises(ValueError):
            transfers.export_archive(self.source, self.archive)
        self.assertEqual(self.archive.read_bytes(), original)

    def test_replace_failure_rolls_back_and_keeps_backup(self):
        real_replace = os.replace
        def fail_documents(source, target):
            if Path(source).name == "documents" and Path(source).parent.name == "new":
                raise OSError("simulated unavailable destination")
            return real_replace(source, target)
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            with patch.object(transfers.os, "replace", side_effect=fail_documents), self.assertRaises(OSError):
                transfers.apply_import(self.target, plan)
        self.assert_original_target()
        backups = list((self.target.data_dir / "backups").glob("*.prepapilot"))
        self.assertEqual(len(backups), 1)
        with transfers.inspect_archive(backups[0], DesktopStore) as plan:
            self.assertEqual(plan.counts["grades"], 1)

    def test_changed_staging_and_busy_context_rejected(self):
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            document = next((plan.folder / "documents").iterdir())
            document.write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                transfers.apply_import(self.target, plan)
        self.target._jobs.add(object())
        with self.assertRaises(ValueError):
            transfers.export_archive(self.target, self.root / "busy.prepapilot")
        self.target._jobs.clear()
        self.assert_original_target()

    def test_school_years_and_manual_holidays_round_trip(self):
        holidays = [{"start": "2026-10-17", "end": "2026-11-01", "label": "Toussaint"}]
        values = {"school_year_start": 2025, "school_years": [2025, 2026, 2027], "time_holidays": holidays}
        for key, value in values.items():
            self.source.db.set_setting(key, value)
        transfers.export_archive(self.source, self.archive)
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        for key, value in values.items():
            self.assertEqual(self.target.db.get_setting(key), value)

    def test_old_archive_without_year_or_holiday_settings_remains_readable(self):
        old = self.mutate_database("DELETE FROM settings WHERE key IN ('school_year_start','school_years','time_holidays');")
        with transfers.inspect_archive(old, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.target.db.get_setting("desktop_name"), "Alice")
        self.assertEqual(self.target.db.list_grades()[0]["score"], 16)

    def test_invalid_year_lists_and_holiday_periods_rejected(self):
        values = [
            ("school_year_start", True), ("school_year_start", 1999), ("school_year_start", "2026"),
            ("school_years", [2027, 2026]), ("school_years", [2026, 2026]),
            ("school_years", [2026, "2027"]), ("school_years", {"2026": True}),
            ("time_holidays", {}),
            ("time_holidays", [{"start": "2026-02-30", "end": "2026-03-02", "label": "Pause"}]),
            ("time_holidays", [{"start": "2026-11-02", "end": "2026-10-17", "label": "Pause"}]),
            ("time_holidays", [{"start": "20261017", "end": "2026-11-01", "label": "Pause"}]),
            ("time_holidays", [{"start": "2026-10-17", "end": "2026-11-01", "label": ""}]),
            ("time_holidays", [{"start": "2026-10-17", "end": "2026-11-01", "label": "A"}, {"start": "2026-10-20", "end": "2026-11-03", "label": "B"}]),
        ]
        for key, value in values:
            serialized = json.dumps(value).replace("'", "''")
            sql = f"INSERT OR REPLACE INTO settings(key,value) VALUES ('{key}','{serialized}');"
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                transfers.inspect_archive(self.mutate_database(sql), DesktopStore)
            self.assert_original_target()

    def test_custom_archived_subject_and_alternating_weeks_round_trip(self):
        subject = dict(id='subject_'+'d'*32, name='Astronomie', color='#123ABC', active=True)
        self.source.db.save_subjects(self.source.db.get_subjects()+[subject])
        document = self.root/'astronomie.txt'
        document.write_bytes(b'Original astronomie')
        identity = self.source.db.import_document(document,subject['id'],'td')
        timetable = {'version':2,'week_anchor':'2026-09-07','semesters':{'S1':[
            {'id':'astro-a','weekday':6,'start':'09:00','end':'10:00','category':subject['id'],'title':'Astro A','week':'A'},
            {'id':'astro-b','weekday':6,'start':'09:00','end':'10:00','category':subject['id'],'title':'Astro B','week':'B'},
        ],'S2':[]}}
        self.source.db.save_timetable(timetable)
        self.source.db.ensure_day('2026-09-13')
        self.source.db.add_time_entry(subject['id'],'2000-09-01T08:00','2000-09-01T09:00','Ancien travail','completed')
        subjects = self.source.db.get_subjects()
        next(row for row in subjects if row['id']==subject['id'])['active'] = False
        self.source.db.save_subjects(subjects)
        self.source.db.set_setting('setup_completed',True)
        transfers.export_archive(self.source,self.archive)
        with transfers.inspect_archive(self.archive,DesktopStore) as plan:
            transfers.apply_import(self.target,plan)
        self.assertEqual(self.target.db.get_subjects(),self.source.db.get_subjects())
        self.assertEqual(self.target.db.get_timetable(),self.source.db.get_timetable())
        self.assertEqual(self.target.db.category_color(subject['id']),'#123ABC')
        self.assertNotIn(subject['id'],self.target.db.subject_labels())
        self.assertTrue(self.target.db.get_setting('setup_completed'))
        self.assertEqual(self.target.db.document_path(identity).read_bytes(),b'Original astronomie')
        self.assertEqual(self.target.db._rows('SELECT * FROM time_day_templates'),self.source.db._rows('SELECT * FROM time_day_templates'))
        self.assertEqual(self.target.db._rows('SELECT * FROM time_entries'),self.source.db._rows('SELECT * FROM time_entries'))

    def test_old_archive_without_catalogue_and_version_one_timetable(self):
        old_timetable = {'version':1,'semesters':{'S1':[{'id':'old-maths','weekday':0,'start':'08:00','end':'09:00','category':'maths','title':'Maths'}],'S2':[]}}
        serialized = json.dumps(old_timetable).replace("'", "''")
        archive = self.mutate_database("DELETE FROM settings WHERE key IN ('desktop_subjects','setup_completed'); UPDATE settings SET value='"+serialized+"' WHERE key='desktop_timetable';")
        with transfers.inspect_archive(archive,DesktopStore) as plan:
            transfers.apply_import(self.target,plan)
        self.assertIn('maths',self.target.db.subject_labels())
        self.assertEqual(self.target.db.get_timetable()['version'],2)
        self.assertEqual(self.target.db.get_timetable()['semesters']['S1'][0]['week'],'all')
        self.assertEqual(self.target.db.get_document(self.doc)['subject'],'maths')
        self.assertTrue(self.target.db.document_path(self.doc).is_file())

    def test_invalid_catalogue_setup_and_alternating_week_archive_rejected(self):
        subjects = self.source.db.get_subjects()
        invalid_color = [dict(row) for row in subjects]
        invalid_color[0]['color'] = 'red; unsafe'
        invalid_active = [dict(row) for row in subjects]
        invalid_active[0]['active'] = 'yes'
        missing_custom = 'subject_'+'e'*32
        timetable = {'version':2,'week_anchor':'2026-09-07','semesters':{'S1':[{'id':'a','weekday':0,'start':'08:00','end':'09:00','category':'maths','title':'Maths','week':'C'}],'S2':[]}}
        bad_anchor = {'version':2,'week_anchor':'2026-09-08','semesters':{'S1':[],'S2':[]}}
        for key,value in [('desktop_subjects',invalid_color),('desktop_subjects',invalid_active),('desktop_subjects',subjects+[subjects[0]]),('setup_completed',1),('desktop_timetable',timetable),('desktop_timetable',bad_anchor),('desktop_tutorial_version',True),('desktop_tutorial_version',-1),('desktop_tutorial_version',10001),('desktop_tutorial_version','1')]:
            encoded = json.dumps(value).replace("'", "''")
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                transfers.inspect_archive(self.mutate_database(f"INSERT OR REPLACE INTO settings(key,value) VALUES ('{key}','{encoded}');"),DesktopStore)
            self.assert_original_target()
        for sql in (f"UPDATE documents SET subject='{missing_custom}';",f"UPDATE time_entries SET category='{missing_custom}';"):
            with self.assertRaises(ValueError):
                transfers.inspect_archive(self.mutate_database(sql),DesktopStore)
            self.assert_original_target()

    def test_custom_grades_archived_subject_and_named_schedules_round_trip(self):
        biology = dict(id='subject_'+'b'*32, name='Biologie cellulaire', color='#008578', active=True)
        self.source.db.save_subjects(self.source.db.get_subjects()+[biology])
        kinds = ('projet', 'tp', 'autre', 'Compte rendu de laboratoire', 'Oral')
        for index, kind in enumerate(kinds):
            self.source.db.add_grade(biology['id'], kind, 17+index, 30, '2026-09-22', f'Évaluation {index}', 1.5)
        self.source.db.add_grade('anglais', 'ds', 82, 100, '2026-09-23', 'Expression écrite', 3)
        subjects = self.source.db.get_subjects()
        next(row for row in subjects if row['id'] == biology['id'])['active'] = False
        self.source.db.save_subjects(subjects)
        settings = {'desktop_program':'Licence de biologie', 'desktop_schedule_labels':{'S1':'Cours à l’université','S2':'Stage au laboratoire'}}
        for key, value in settings.items():
            self.source.db.set_setting(key,value)
        transfers.export_archive(self.source,self.archive)
        with transfers.inspect_archive(self.archive,DesktopStore) as plan:
            self.assertEqual(plan.counts['grades'],7)
            transfers.apply_import(self.target,plan)
        self.assertEqual(self.target.db.list_grades(),self.source.db.list_grades())
        self.assertEqual(self.target.db.subject_labels(include_archived=True)[biology['id']],'Biologie cellulaire')
        self.assertNotIn(biology['id'],self.target.db.subject_labels())
        self.assertIn('Compte rendu de laboratoire',self.target.db.grade_kind_labels())
        for key,value in settings.items():
            self.assertEqual(self.target.db.get_setting(key),value)
        second = self.root/'second-export.prepapilot'
        transfers.export_archive(self.target,second)
        with transfers.inspect_archive(second,DesktopStore) as plan:
            self.assertEqual(plan.counts['grades'],7)

    def test_first_profile_with_only_custom_subject_transfers_without_default_subjects(self):
        biology = dict(id='subject_'+'c'*32,name='Biologie',color='#008578',active=True)
        fresh = AppContext(self.root/'biologie-seulement')
        try:
            fresh.db.save_setup([biology],{'semesters':{'S1':[],'S2':[]}})
            fresh.db.set_setting('desktop_program','')
            fresh.db.set_setting('desktop_schedule_labels',{'S1':'Cours','S2':'Stage'})
            fresh.db.add_grade(biology['id'],'Dossier de recherche',37,40,'2026-09-23','Cellules',2)
            original = self.root/'cellules.txt'
            original.write_bytes(b'Cours de biologie')
            identity = fresh.db.import_document(original,biology['id'],'cours')
            fresh.db.add_time_entry(biology['id'],'2026-09-24T18:00','2026-09-24T19:00','Recherche','completed')
            archive = self.root/'biologie.prepapilot'
            transfers.export_archive(fresh,archive)
            with transfers.inspect_archive(archive,DesktopStore) as plan:
                transfers.apply_import(self.target,plan)
            self.assertEqual(self.target.db.get_subjects(),[biology])
            self.assertEqual(self.target.db.list_grades(),fresh.db.list_grades())
            self.assertEqual(self.target.db.get_document(identity)['subject'],biology['id'])
            self.assertEqual(self.target.db.document_path(identity).read_bytes(),b'Cours de biologie')
            self.assertEqual(self.target.db.get_setting('desktop_program'),'')
            self.assertNotIn('maths',self.target.db.subject_labels(include_archived=True))
        finally:
            fresh.close()

    def test_legacy_three_subject_grade_schema_imports_and_accepts_new_types(self):
        self.source.db.add_grade('anglais','colle',14,20,'2026-09-23','Ancien oral',1)
        self.source.db.add_grade('physique','cours',8,10,'2026-09-24','Ancien cours',2)
        transfers.export_archive(self.source,self.archive)
        old = self.mutate_database('''
            DELETE FROM settings WHERE key IN ('desktop_subjects','desktop_program','desktop_schedule_labels');
            ALTER TABLE grades RENAME TO grades_new;
            CREATE TABLE grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL CHECK(subject IN ('maths','physique','anglais')),
                kind TEXT NOT NULL CHECK(kind IN ('cours','colle','ds')),
                score REAL NOT NULL CHECK(score>=0),
                scale REAL NOT NULL CHECK(scale>0 AND score<=scale),
                coefficient REAL NOT NULL DEFAULT 1 CHECK(coefficient>0),
                graded_on TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK(subject!='anglais' OR kind='colle')
            );
            INSERT INTO grades SELECT id,subject,kind,score,scale,coefficient,graded_on,label,created_at FROM grades_new;
            DROP TABLE grades_new;
            CREATE INDEX grades_subject_date ON grades(subject,graded_on);
        ''')
        with transfers.inspect_archive(old,DesktopStore) as plan:
            transfers.apply_import(self.target,plan)
        self.assertEqual(self.target.db.list_grades(),self.source.db.list_grades())
        biology = dict(id='subject_'+'f'*32,name='Biologie',color='#008578',active=True)
        self.target.db.save_subjects(self.target.db.get_subjects()+[biology])
        self.target.db.add_grade(biology['id'],'Soutenance',18,20,'2026-09-25','Projet importé',2)
        self.target.db.add_grade('anglais','projet',16,20,'2026-09-26','Projet écrit',1)
        second = self.root/'legacy-converted.prepapilot'
        transfers.export_archive(self.target,second)
        with transfers.inspect_archive(second,DesktopStore) as plan:
            self.assertEqual(plan.counts['grades'],5)

    def test_optional_comparisons_round_trip_with_partial_and_missing_context(self):
        self.source.db.add_grade('maths', 'ds', 8, 10, '2026-09-22', class_average=5.5, rank=2, class_size=31)
        self.source.db.add_grade('physique', 'projet', 0, 50, '2026-09-23', class_average=0)
        self.source.db.add_grade('anglais', 'Oral', 18, 20, '2026-09-24', rank=1, class_size=1)
        transfers.export_archive(self.source, self.archive)
        with transfers.inspect_archive(self.archive, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.target.db.list_grades(), self.source.db.list_grades())

    def test_previous_universal_schema_imports_without_modifying_archive(self):
        old = self.mutate_database('''
            ALTER TABLE grades RENAME TO grades_current;
            CREATE TABLE grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, kind TEXT NOT NULL,
                score REAL NOT NULL CHECK(score>=0), scale REAL NOT NULL CHECK(scale>0 AND score<=scale),
                coefficient REAL NOT NULL DEFAULT 1 CHECK(coefficient>0), graded_on TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO grades SELECT id,subject,kind,score,scale,coefficient,graded_on,label,created_at FROM grades_current;
            DROP TABLE grades_current;
            CREATE INDEX grades_subject_date ON grades(subject,graded_on);
        ''')
        original = old.read_bytes()
        with transfers.inspect_archive(old, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(old.read_bytes(), original)
        self.assertEqual(self.target.db.list_grades(), self.source.db.list_grades())

    def test_old_orphan_grade_subjects_recovered_in_staging_and_kept_archived(self):
        self.source.db.add_grade('anglais','colle',14,20,'2026-09-23','Ancien oral',1)
        self.source.db.add_grade('physique','cours',8,10,'2026-09-24','Ancien cours',2)
        transfers.export_archive(self.source,self.archive)
        subjects = [dict(id='subject_'+'e'*32,name='Mathématiques',color='#008578',active=True)]
        catalogue = json.dumps(subjects).replace("'","''")
        empty = json.dumps({'semesters':{'S1':[],'S2':[]}})
        old = self.mutate_database(f"UPDATE settings SET value='{catalogue}' WHERE key='desktop_subjects'; UPDATE settings SET value='{empty}' WHERE key='desktop_timetable'; DELETE FROM time_entries; DELETE FROM time_day_templates;")
        archive_bytes = old.read_bytes()
        with transfers.inspect_archive(old,DesktopStore) as plan:
            with closing(sqlite3.connect(plan.folder/'data.sqlite3')) as connection:
                staged = json.loads(connection.execute("SELECT value FROM settings WHERE key='desktop_subjects'").fetchone()[0])
            restored = {row['id']:row for row in staged}
            self.assertEqual(set(restored),{subjects[0]['id'],'maths','physique','anglais'})
            self.assertEqual(restored['maths']['name'],'Mathématiques (archives)')
            self.assertTrue(restored[subjects[0]['id']]['active'])
            self.assertTrue(all(not restored[key]['active'] for key in ('maths','physique','anglais')))
            transfers.apply_import(self.target,plan)
        self.assertEqual(old.read_bytes(),archive_bytes)
        self.assertEqual(self.target.db.get_subjects(),staged)
        self.assertEqual(self.target.db.list_grades(),self.source.db.list_grades())
        self.assertEqual(self.target.db.get_document(self.doc)['subject'],'maths')
        self.assertEqual(self.target.db.subject_labels(),{subjects[0]['id']:'Mathématiques'})
        second = self.root/'restored-history.prepapilot'
        transfers.export_archive(self.target,second)
        with transfers.inspect_archive(second,DesktopStore) as plan:
            self.assertEqual(plan.counts['grades'],3)

    def test_invalid_grade_references_types_titles_dates_and_numbers_rejected(self):
        for sql in (
            "UPDATE grades SET subject='subject_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee';",
            "UPDATE grades SET subject='repas';",
            "UPDATE grades SET kind='';", "UPDATE grades SET kind='   ';",
            "UPDATE grades SET kind='"+'x'*61+"';",
            "UPDATE grades SET kind='Rapport'||char(10)||'suite';",
            "UPDATE grades SET kind='Rapport'||char(127);",
            "UPDATE grades SET kind=x'0102';",
            "UPDATE grades SET label='"+'x'*241+"';",
            "UPDATE grades SET label='Titre'||char(10)||'suite';",
            "UPDATE grades SET label='Titre'||char(127);",
            "UPDATE grades SET graded_on='20260920';",
            "UPDATE grades SET score=-1;", "UPDATE grades SET score=21;",
            "UPDATE grades SET score=1e999;", "UPDATE grades SET scale=0;",
            "UPDATE grades SET coefficient=0;", "UPDATE grades SET coefficient=1e999;",
            "UPDATE grades SET class_average=-1;", "UPDATE grades SET class_average=21;",
            "UPDATE grades SET class_average=1e999;", "UPDATE grades SET class_average=x'0102';",
            "UPDATE grades SET rank=1;", "UPDATE grades SET class_size=30;",
            "UPDATE grades SET rank=31,class_size=30;", "UPDATE grades SET rank=0,class_size=30;",
            "UPDATE grades SET rank=1.5,class_size=30;", "UPDATE grades SET rank=1,class_size=30.5;",
            "UPDATE grades SET rank=1,class_size=2147483648;",
        ):
            with self.subTest(sql=sql),self.assertRaises(ValueError):
                transfers.inspect_archive(self.mutate_database(sql),DesktopStore)
            self.assert_original_target()

    def test_invalid_program_and_schedule_names_rejected(self):
        invalid = [
            ('desktop_program',True),('desktop_program',None),('desktop_program','x'*81),
            ('desktop_program','Licence\nBiologie'),('desktop_program','Licence\x7f'),
            ('desktop_schedule_labels',[]),('desktop_schedule_labels',{'S1':'Cours'}),
            ('desktop_schedule_labels',{'S1':'Cours','S2':'Stage','S3':'Autre'}),
            ('desktop_schedule_labels',{'S1':'','S2':'Stage'}),
            ('desktop_schedule_labels',{'S1':'   ','S2':'Stage'}),
            ('desktop_schedule_labels',{'S1':'Cours','S2':42}),
            ('desktop_schedule_labels',{'S1':'Cours','S2':'x'*41}),
            ('desktop_schedule_labels',{'S1':'Cours','S2':'Stage\nÉté'}),
        ]
        for key,value in invalid:
            encoded = json.dumps(value).replace("'","''")
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                transfers.inspect_archive(self.mutate_database(f"INSERT OR REPLACE INTO settings(key,value) VALUES ('{key}','{encoded}');"),DesktopStore)
            self.assert_original_target()
