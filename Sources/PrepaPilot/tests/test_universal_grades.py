"""Universal evaluations, lossless legacy migration and archived subject history."""
from contextlib import closing
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from mpsi_core.grades import KIND_LABELS, format_stats, normalize_kind, normalize_subject, plot_grades, stats
from mpsi_core.storage import Store
from mpsi_desktop.context import AppContext, DesktopStore, current_school_year
from mpsi_desktop.subject_store import restore_legacy_grade_subjects


CUSTOM = 'subject_' + 'c' * 32
SECOND = 'subject_' + 'd' * 32
LEGACY_SCHEMA = """
CREATE TABLE grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL CHECK(subject IN ('maths', 'physique', 'anglais')),
    kind TEXT NOT NULL CHECK(kind IN ('cours', 'colle', 'ds')),
    score REAL NOT NULL CHECK(score >= 0),
    scale REAL NOT NULL CHECK(scale > 0 AND score <= scale),
    coefficient REAL NOT NULL DEFAULT 1 CHECK(coefficient > 0),
    graded_on TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(subject != 'anglais' OR kind = 'colle')
);
CREATE INDEX grades_subject_date ON grades(subject, graded_on);
CREATE INDEX legacy_label_index ON grades(label);
CREATE TABLE grade_audit (grade_id INTEGER NOT NULL);
CREATE TRIGGER legacy_grade_audit AFTER INSERT ON grades
BEGIN INSERT INTO grade_audit(grade_id) VALUES (NEW.id); END;
"""


def legacy_database(path):
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(LEGACY_SCHEMA)
        connection.executemany(
            'INSERT INTO grades(id,subject,kind,score,scale,coefficient,graded_on,label,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            [(3, 'maths', 'ds', 17, 25, 2.5, '2024-02-29', '  ' + 'Ancien titre ' * 30, '2024-03-01 10:20:30'),
             (7, 'anglais', 'colle', 13, 20, 1, '2026-09-30', 'Oral', '2026-10-01 08:00:01'),
             (80, 'physique', 'cours', 3, 5, 1, '2026-09-28', 'Supprimée', '2026-09-28 12:00:00')])
        connection.execute('DELETE FROM grades WHERE id=80')
        return connection.execute('SELECT * FROM grades ORDER BY id').fetchall()


class GradeMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'legacy.sqlite3'
        self.original = legacy_database(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_migration_preserves_all_values_sequence_indexes_and_triggers(self):
        with closing(Store(self.path)) as store:
            self.assertEqual([tuple(row.values()) for row in store._rows('SELECT * FROM grades ORDER BY id')],
                             [(*row, None, None, None) for row in self.original])
            self.assertEqual(store._rows("SELECT seq FROM sqlite_sequence WHERE name='grades'")[0]['seq'], 80)
            schema = {row['name'] for row in store._rows("SELECT name FROM sqlite_master WHERE tbl_name='grades'")}
            self.assertTrue({'grades_subject_date', 'legacy_label_index', 'legacy_grade_audit'} <= schema)
            # Copying the table must not replay the original INSERT trigger.
            self.assertEqual(len(store._rows('SELECT * FROM grade_audit')), 3)
            identifier = store.add_grade('biologie', 'Soutenance', 15, 20, '2026-10-04', 'Stage', 3)
            self.assertEqual(identifier, 81)
            self.assertEqual(store._rows('SELECT * FROM grade_audit')[-1]['grade_id'], identifier)
            store.add_grade('anglais', 'projet', 16, 20, '2026-10-04')
        with closing(Store(self.path)) as reopened:
            self.assertEqual(len(reopened.list_grades()), 4)
            self.assertEqual(reopened._rows("SELECT seq FROM sqlite_sequence WHERE name='grades'")[0]['seq'], 82)
            self.assertEqual(len(reopened._rows('SELECT * FROM grade_audit')), 5)
            self.assertEqual(reopened._rows("SELECT name FROM sqlite_master WHERE name='grades_universal_migration'"), [])

    def test_failure_after_table_drop_rolls_back_every_record_and_schema(self):
        with closing(sqlite3.connect(self.path)) as connection:
            before = connection.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        connect = sqlite3.connect

        def connection_with_failure(*args, **kwargs):
            connection = connect(*args, **kwargs)
            def authorize(action, first, second, database, source):
                return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ALTER_TABLE else sqlite3.SQLITE_OK
            connection.set_authorizer(authorize)
            return connection

        with patch('mpsi_core.storage.sqlite3.connect', side_effect=connection_with_failure):
            with self.assertRaises(sqlite3.DatabaseError):
                Store(self.path)
        with closing(connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT * FROM grades ORDER BY id').fetchall(), self.original)
            self.assertEqual(connection.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall(), before)
            self.assertEqual(connection.execute("SELECT seq FROM sqlite_sequence WHERE name='grades'").fetchone()[0], 80)
        # A failed first attempt must remain recoverable on the next launch.
        with closing(Store(self.path)) as store:
            self.assertEqual(store.add_grade('anglais', 'ds', 12, 20, '2026-10-04'), 81)

    def test_previous_universal_database_migrates_once_and_keeps_new_comparisons(self):
        path = Path(self.temp.name) / 'universal.sqlite3'
        schema = (LEGACY_SCHEMA.replace(" CHECK(subject IN ('maths', 'physique', 'anglais'))", "")
                  .replace(" CHECK(kind IN ('cours', 'colle', 'ds'))", "")
                  .replace(",\n    CHECK(subject != 'anglais' OR kind = 'colle')", ""))
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript(schema)
            connection.execute("INSERT INTO grades(subject,kind,score,scale,graded_on) VALUES ('maths','Projet',8,10,'2026-09-20')")
            original = connection.execute('SELECT * FROM grades').fetchone()
        with closing(Store(path)) as store:
            self.assertEqual(tuple(store._rows('SELECT * FROM grades')[0].values()), (*original, None, None, None))
            self.assertEqual(len(store._rows('SELECT * FROM grade_audit')), 1)
            store.update_grade(original[0], 'maths', 'Projet', 8, 10, '2026-09-20',
                               class_average=6.5, rank=3, class_size=32)
            before = store.list_grades()
        with closing(Store(path)) as reopened:
            self.assertEqual(reopened.list_grades(), before)
            self.assertEqual(len(reopened._rows('SELECT * FROM grade_audit')), 1)
            self.assertEqual(reopened._connection.total_changes, 0)

    def test_new_comparison_constraints_survive_legacy_migration(self):
        with closing(Store(self.path)) as store:
            for assignments in ('class_average=-1', 'class_average=26', 'rank=1', 'class_size=30',
                                'rank=31,class_size=30', 'rank=0,class_size=30',
                                'rank=1.5,class_size=30', 'rank=1,class_size=30.5'):
                with self.subTest(assignments=assignments), self.assertRaises(sqlite3.IntegrityError):
                    store._change('UPDATE grades SET ' + assignments + ' WHERE id=3', ())
            row = store.list_grades()[0]
            self.assertTrue(all(row[key] is None for key in ('class_average', 'rank', 'class_size')))

    def test_numeric_database_constraints_survive_migration(self):
        with closing(Store(self.path)) as store:
            for values in ((-1, 20, 1), (21, 20, 1), (1, 0, 1), (1, 20, 0)):
                with self.subTest(values=values), self.assertRaises(sqlite3.IntegrityError):
                    store._insert("INSERT INTO grades(subject,kind,score,scale,coefficient,graded_on) VALUES ('biologie','Portfolio',?,?,?,'2026-10-04')", values)
            self.assertEqual(len(store.list_grades()), 2)

    def test_orphaned_legacy_subjects_reappear_archived_without_changing_notes(self):
        custom = dict(id=CUSTOM, name='Mathématiques', color='#338855', active=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            connection.execute("INSERT INTO settings(key,value) VALUES ('desktop_subjects',?)", (json.dumps([custom]),))
            connection.execute("INSERT INTO settings(key,value) VALUES ('desktop_timetable',?)",
                               (json.dumps({'semesters': {'S1': [], 'S2': []}}),))
        with closing(DesktopStore(self.path)) as store:
            self.assertEqual(store.subject_labels(), {CUSTOM: 'Mathématiques'})
            archived = {row['id']: row for row in store.get_subjects() if not row['active']}
            self.assertEqual(set(archived), {'maths', 'anglais'})
            self.assertEqual(archived['maths']['name'], 'Mathématiques (archives)')
            self.assertEqual([tuple(row.values()) for row in store._rows('SELECT * FROM grades ORDER BY id')],
                             [(*row, None, None, None) for row in self.original])
            with self.assertRaises(ValueError):
                store.add_grade('maths', 'projet', 15, 20, '2026-10-04')
            self.assertTrue(store.update_grade(3, 'maths', 'Projet', 15, 20, '2026-10-04', 'Ancienne note corrigée'))
            expected = store.get_subjects()
        with closing(DesktopStore(self.path)) as reopened:
            self.assertEqual(reopened.get_subjects(), expected)
            self.assertEqual(len(reopened.list_grades()), 2)

    def test_recovery_only_recognizes_historical_subject_ids_and_is_idempotent(self):
        original = [dict(id=CUSTOM, name='Biologie', color='#338855', active=True)]
        restored = restore_legacy_grade_subjects(original, ['maths', 'maths', SECOND, 'repas'])
        self.assertEqual(original, [dict(id=CUSTOM, name='Biologie', color='#338855', active=True)])
        self.assertEqual({row['id'] for row in restored}, {CUSTOM, 'maths'})
        self.assertEqual(restore_legacy_grade_subjects(restored, ['maths']), restored)


class UniversalGradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'data' / 'mpsi.sqlite3'
        self.store = DesktopStore(self.path)
        self.store.save_subjects(self.store.get_subjects() + [
            dict(id=CUSTOM, name='Biologie', color='#338855', active=True),
            dict(id=SECOND, name='Économie', color='#883355', active=True)])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_custom_subject_and_types_participate_in_stats_and_filtering(self):
        self.store.add_grade(CUSTOM, '  Soutenance  ', 18, 20, '2026-10-01', coefficient=2)
        self.store.add_grade(CUSTOM, 'Portfolio', 7, 10, '2026-10-02')
        self.store.add_grade('anglais', 'Examen écrit', 11, 20, '2026-10-03')
        rows = self.store.list_grades(CUSTOM)
        self.assertEqual(len(rows), 2)
        summary = stats(rows)
        self.assertEqual(set(summary['by_kind']), {'Soutenance', 'Portfolio'})
        self.assertEqual(sum(group['count'] for group in summary['by_kind'].values()), summary['count'])
        self.assertAlmostEqual(summary['weighted_mean'], 50 / 3)
        labels = self.store.grade_kind_labels()
        self.assertEqual(labels['Soutenance'], 'Soutenance')
        self.assertEqual({key: labels[key] for key in KIND_LABELS}, KIND_LABELS)
        self.assertIn('Soutenance : 18,00', format_stats(rows, CUSTOM, 'Biologie'))
        self.assertEqual(self.store.list_grades('anglais')[0]['kind'], 'ds')

    def test_archive_preserves_subject_and_only_existing_note_can_keep_it(self):
        identifier = self.store.add_grade(CUSTOM, 'Portfolio', 15, 20, '2026-10-01')
        second = self.store.add_grade(SECOND, 'cours', 12, 20, '2026-10-02')
        created = self.store.list_grades(CUSTOM)[0]['created_at']
        subjects = self.store.get_subjects()
        next(row for row in subjects if row['id'] == CUSTOM)['name'] = 'Sciences du vivant'
        self.store.save_subjects(subjects)
        self.store.save_subjects([row for row in subjects if row['id'] != CUSTOM])
        self.assertEqual(self.store.subject_labels(True)[CUSTOM], 'Sciences du vivant')
        self.assertNotIn(CUSTOM, self.store.subject_labels())
        with self.assertRaises(ValueError):
            self.store.add_grade(CUSTOM, 'Portfolio', 18, 20, '2026-10-03')
        with self.assertRaises(ValueError):
            self.store.update_grade(second, CUSTOM, 'Portfolio', 18, 20, '2026-10-03')
        self.assertTrue(self.store.update_grade(identifier, CUSTOM, 'Mémoire', 18, 20, '2026-10-03', 'Version corrigée'))
        self.assertEqual(self.store.list_grades(CUSTOM)[0]['created_at'], created)
        self.assertEqual(len(self.store.list_grades()), 2)
        self.assertFalse(self.store.update_grade(99999, CUSTOM, 'Mémoire', 18, 20, '2026-10-03'))

    def test_csv_uses_current_labels_and_neutralizes_all_free_text(self):
        self.store.add_grade(CUSTOM, '@Portfolio', 17, 20, '2026-10-01', '=Titre')
        subjects = self.store.get_subjects()
        next(row for row in subjects if row['id'] == CUSTOM)['name'] = '=Sciences du vivant'
        self.store.save_subjects(subjects)
        exported = list(csv.DictReader(io.StringIO(self.store.export_grades_csv()), delimiter=';'))[0]
        self.assertEqual(exported['subject'], "'=Sciences du vivant")
        self.assertEqual(exported['kind'], "'@Portfolio")
        self.assertEqual(exported['label'], "'=Titre")
        self.assertEqual(float(exported['normalized_score']), 17)
        self.assertNotIn(CUSTOM, self.store.export_grades_csv())

    def test_invalid_inputs_never_modify_notes(self):
        values = dict(subject=CUSTOM, kind='Portfolio', score=14, scale=20, graded_on='2026-10-01')
        identifier = self.store.add_grade(**values)
        before = self.store.list_grades()
        for invalid in ({'subject': 'subject_'+'f'*32}, {'kind': ''}, {'kind': 'X'*61},
                        {'kind': 'Une\ndeux'}, {'kind': 'x\x7f'}, {'label': 'x'*241},
                        {'label': '\tTest'}, {'coefficient': float('inf')}, {'score': True}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError): self.store.add_grade(**(values | invalid))
                with self.assertRaises(ValueError): self.store.update_grade(identifier, **(values | invalid))
        self.assertEqual(self.store.list_grades(), before)

    def test_context_filters_custom_subject_by_selected_year(self):
        year = current_school_year()
        self.store.add_grade(CUSTOM, 'Projet', 15, 20, f'{year}-10-01')
        self.store.add_grade(CUSTOM, 'Portfolio', 18, 20, f'{year-1}-10-01')
        self.store.close()
        context = AppContext(self.path.parent)
        try:
            self.assertEqual(len(context.grades(CUSTOM)), 1)
            self.assertEqual(context.grades(CUSTOM)[0]['kind'], 'projet')
        finally:
            context.close()
            self.store = DesktopStore(self.path)

    def test_plain_types_legacy_aliases_and_generic_ids(self):
        for alias, expected in [('Évaluations de cours', 'cours'), ('Contrôle', 'cours'),
                                ('Colles', 'colle'), ('Oral', 'colle'), ('DS', 'ds'),
                                ('Travaux pratiques', 'tp'), ('Projet', 'projet')]:
            self.assertEqual(normalize_kind(alias), expected)
        self.assertEqual(normalize_kind('  Étude de cas  '), 'Étude de cas')
        self.assertEqual(normalize_subject(CUSTOM), CUSTOM)
        self.assertEqual(normalize_subject('biologie'), 'biologie')
        self.assertEqual(normalize_subject('Mathématiques'), 'maths')
        for value in (None, 4, ' ', 'a\tb', 'a\x00b', 'a'*61):
            with self.subTest(value=value), self.assertRaises(ValueError): normalize_kind(value)

    def test_chart_can_render_a_custom_type_and_subject(self):
        self.store.add_grade(CUSTOM, 'Soutenance', 15, 20, '2026-10-01')
        chart = plot_grades(self.store.list_grades(CUSTOM), CUSTOM, 'Biologie')
        self.assertEqual(chart.read(8), b'\x89PNG\r\n\x1a\n')


if __name__ == '__main__':
    unittest.main()
