"""Personal subjects and alternating timetables without historical data loss."""
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from mpsi_core.storage import Store
from mpsi_desktop.catalog import default_subjects
from mpsi_desktop.context import DesktopStore
from mpsi_desktop.subject_store import validate_subjects
from mpsi_desktop.time_store import validate_timetable


CUSTOM='subject_'+'a'*32


def slot(identity='math-a', category='maths', week='all', start='09:00', end='10:00'):
    return dict(id=identity,weekday=0,start=start,end=end,category=category,title=identity,week=week)


def timetable(slots=None,anchor='2026-08-31'):
    return dict(version=2,week_anchor=anchor,semesters={'S1':slots or [],'S2':[]})


class SubjectValidationTests(unittest.TestCase):
    def test_stable_identity_color_and_name_validation(self):
        result=validate_subjects([dict(id=CUSTOM,name='  Biologie  ',color='#ab12ef',active=True)])
        self.assertEqual(result,[dict(id=CUSTOM,name='Biologie',color='#AB12EF',active=True)])
        for row in (dict(id='new',name='Test',color='#123456',active=True),
                    dict(id=CUSTOM,name='',color='#123456',active=True),
                    dict(id=CUSTOM,name='Test',color='red; background: url(x)',active=True),
                    dict(id=CUSTOM,name='Test',color='#123456',active=1)):
            with self.assertRaises(ValueError):validate_subjects([row])
        duplicate={**result[0],'id':'subject_'+'b'*32,'name':'BIOLOGIE'}
        with self.assertRaises(ValueError):validate_subjects(result+[duplicate])
        with self.assertRaises(ValueError):validate_subjects(result+result)

    def test_overlap_rules_distinguish_alternate_weeks(self):
        rows=[slot('a',week='A'),slot('b',category='physique',week='B')]
        result=validate_timetable(timetable(rows))
        self.assertEqual(len(result['semesters']['S1']),2)
        for conflict in (slot('all',week='all'),slot('another-a',week='A')):
            with self.assertRaises(ValueError):validate_timetable(timetable(rows+[conflict]))
        with self.assertRaises(ValueError):validate_timetable(timetable(rows,anchor='2026-09-01'))
        with self.assertRaises(ValueError):validate_timetable(timetable([slot(week='C')]))

    def test_custom_categories_validate_and_legacy_slots_gain_all_weeks(self):
        row=slot(category=CUSTOM)
        with self.assertRaises(ValueError):validate_timetable(timetable([row]))
        result=validate_timetable(timetable([row]),categories={CUSTOM:'Biologie'})
        self.assertEqual(result['semesters']['S1'][0]['category'],CUSTOM)
        legacy=slot()
        del legacy['week']
        upgraded=validate_timetable({'version':1,'semesters':{'S1':[legacy],'S2':[]}})
        self.assertEqual(upgraded['version'],2)
        self.assertEqual(upgraded['week_anchor'],'2026-08-31')
        self.assertEqual(upgraded['semesters']['S1'][0]['week'],'all')


class PersonalScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'data/mpsi.sqlite3'
        self.db=DesktopStore(self.path)
        self.clock=patch.object(self.db,'_time_now',return_value=datetime(2026,8,30,12))
        self.now=self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.db.close()
        self.temp.cleanup()

    def subjects(self):
        return self.db.get_subjects()+[dict(id=CUSTOM,name='Biologie',color='#228844',active=True)]

    def test_new_installation_waits_for_setup_even_after_restart(self):
        self.assertFalse(self.db.get_setting('setup_completed'))
        self.assertEqual(self.db.get_subjects(),default_subjects())
        self.db.close()
        self.db=DesktopStore(self.path)
        self.assertFalse(self.db.get_setting('setup_completed'))

    def test_atomic_setup_persists_subjects_timetable_and_completion(self):
        self.db.save_setup(self.subjects(),timetable([slot(category=CUSTOM,week='A')]))
        self.assertTrue(self.db.get_setting('setup_completed'))
        self.assertEqual(self.db.subject_labels()[CUSTOM],'Biologie')
        self.assertEqual(self.db.category_color(CUSTOM),'#228844')
        self.assertIn(CUSTOM,self.db.study_categories())
        self.assertEqual(self.db.get_timetable()['semesters']['S1'][0]['week'],'A')
        self.db.ensure_day('2026-08-31')
        self.assertEqual(self.db.list_time_entries('2026-08-31','2026-08-31')[0]['category'],CUSTOM)

    def test_first_blank_setup_can_use_builtin_name_without_ghost_subjects(self):
        subject=dict(id=CUSTOM,name='Mathématiques',color='#228844',active=True)
        self.db.save_setup([subject],timetable([slot(category=CUSTOM)]))
        self.assertEqual(self.db.get_subjects(),[subject])
        self.assertEqual(self.db.subject_labels(),{CUSTOM:'Mathématiques'})
        self.assertTrue(self.db.get_setting('setup_completed'))

    def test_setup_saves_custom_schedule_names_atomically(self):
        labels = {'S1': '  Formation initiale  ', 'S2': 'Stage'}
        self.db.save_setup(self.subjects(), timetable([slot(category=CUSTOM)]), schedule_labels=labels)
        self.assertEqual(self.db.get_setting('desktop_schedule_labels'), {'S1': 'Formation initiale', 'S2': 'Stage'})
        self.assertEqual(self.db.subject_labels()[CUSTOM], 'Biologie')
        self.assertTrue(self.db.get_setting('setup_completed'))
        # Older callers omit the new optional field without erasing custom names.
        self.db.save_setup(self.db.get_subjects(), timetable())
        self.assertEqual(self.db.get_setting('desktop_schedule_labels'), {'S1': 'Formation initiale', 'S2': 'Stage'})

    def test_invalid_names_and_failed_final_setting_roll_back_whole_setup(self):
        before = self.db._rows('SELECT * FROM settings ORDER BY key')
        with self.assertRaises(ValueError):
            self.db.save_setup(self.subjects(), timetable(), schedule_labels={'S1': '', 'S2': 'Stage'})
        self.assertEqual(self.db._rows('SELECT * FROM settings ORDER BY key'), before)
        with self.db._connection:
            self.db._connection.execute("CREATE TRIGGER fail_names BEFORE INSERT ON settings WHEN NEW.key='desktop_schedule_labels' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.save_setup(self.subjects(), timetable([slot(category=CUSTOM)]),
                               schedule_labels={'S1': 'Cours', 'S2': 'Stage'})
        self.assertEqual(self.db._rows('SELECT * FROM settings ORDER BY key'), before)
        self.assertFalse(self.db.get_setting('setup_completed'))

    def test_initial_setup_never_discards_subjects_referenced_by_existing_data(self):
        self.db.add_grade('maths','ds',15,20,'2026-08-20')
        subject=dict(id=CUSTOM,name='Biologie',color='#228844',active=True)
        self.db.save_setup([subject],timetable())
        self.assertIn('maths',self.db.subject_labels(include_archived=True))
        self.assertNotIn('maths',self.db.subject_labels())
        self.assertEqual(len(self.db.list_grades()),1)

    def test_invalid_setup_and_database_failure_leave_all_settings_unchanged(self):
        original_subjects=self.db.get_subjects()
        original_timetable=self.db.get_timetable()
        with self.assertRaises(ValueError):
            self.db.save_setup(self.subjects(),timetable([slot(),slot('conflict')]))
        self.assertEqual(self.db.get_subjects(),original_subjects)
        self.assertEqual(self.db.get_timetable(),original_timetable)
        self.assertFalse(self.db.get_setting('setup_completed'))
        with self.db._connection:
            self.db._connection.execute("CREATE TRIGGER fail_setup BEFORE INSERT ON settings WHEN NEW.key='desktop_timetable' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.save_setup(self.subjects(),timetable([slot(category=CUSTOM)]))
        self.assertEqual(self.db.get_subjects(),original_subjects)
        self.assertEqual(self.db.get_timetable(),original_timetable)
        self.assertFalse(self.db.get_setting('setup_completed'))

    def test_renaming_preserves_ids_and_omission_archives_instead_of_deleting(self):
        self.db.save_subjects(self.subjects())
        subjects=self.db.get_subjects()
        next(row for row in subjects if row['id']==CUSTOM)['name']='Sciences du vivant'
        self.db.save_subjects(subjects)
        self.assertEqual(self.db.subject_labels()[CUSTOM],'Sciences du vivant')
        self.db.save_subjects([row for row in subjects if row['id']!=CUSTOM])
        self.assertNotIn(CUSTOM,self.db.subject_labels())
        self.assertEqual(self.db.subject_labels(True)[CUSTOM],'Sciences du vivant')
        self.assertIn(CUSTOM,self.db.study_categories())
        self.assertEqual(self.db.category_color(CUSTOM),'#228844')

    def test_alternating_generation_is_idempotent_and_holidays_do_not_shift_it(self):
        self.db.save_setup(self.db.get_subjects(),timetable([slot('a',week='A'),slot('b','physique','B')]))
        for day,subject in [('2026-08-31','maths'),('2026-09-07','physique'),('2026-09-14','maths')]:
            self.db.ensure_day(day)
            entries=self.db.list_time_entries(day,day)
            self.assertEqual([row['category'] for row in entries],[subject])
            original=entries[0]['id']
            self.db.ensure_day(day)
            self.assertEqual(self.db.list_time_entries(day,day)[0]['id'],original)
        self.db.add_holiday('2026-09-07','2026-09-13')
        self.assertEqual(self.db.list_time_entries('2026-09-07','2026-09-07'),[])
        self.assertEqual(self.db.week_for_day('2026-09-14'),'A')
        self.assertEqual(self.db.list_time_entries('2026-09-14','2026-09-14')[0]['category'],'maths')

    def test_week_parity_crosses_new_year_leap_day_and_negative_offsets(self):
        self.db.save_timetable(timetable(anchor='2026-12-28'))
        self.assertEqual(self.db.week_for_day('2026-12-21'),'B')
        self.assertEqual(self.db.week_for_day('2026-12-28'),'A')
        self.assertEqual(self.db.week_for_day('2027-01-03'),'A')
        self.assertEqual(self.db.week_for_day('2027-01-04'),'B')
        self.db.save_timetable(timetable(anchor='2028-02-28'))
        self.assertEqual(self.db.week_for_day('2028-02-29'),'A')
        self.assertEqual(self.db.week_for_day('2028-03-06'),'B')
        self.assertEqual(self.db.week_for_day('2028-03-13'),'A')

    def test_archiving_keeps_history_and_cancels_only_future_automatic_entries(self):
        self.db.save_setup(self.db.get_subjects(),timetable([slot()]))
        self.db.ensure_day('2026-08-31')
        self.db.ensure_day('2026-09-07')
        history=self.db.list_time_entries('2026-08-31','2026-08-31')[0]
        self.now.return_value=datetime(2026,9,1,12)
        self.db.update_time_entry(history['id'],status='completed')
        subjects=self.db.get_subjects()
        next(row for row in subjects if row['id']=='maths')['active']=False
        self.db.save_subjects(subjects)
        self.assertEqual(self.db.list_time_entries('2026-09-07','2026-09-07'),[])
        self.assertEqual(self.db.time_totals('2026-08-31','2026-08-31'),{'maths':60})
        self.db.update_time_entry(history['id'],title='Cours conservé')
        with self.assertRaises(ValueError):self.db.add_time_entry('maths','2026-08-30T09:00','2026-08-30T10:00')
        self.db.ensure_day('2026-08-31')
        self.assertEqual(self.db.list_time_entries('2026-08-31','2026-08-31')[0]['title'],'Cours conservé')

    def test_alternation_change_preserves_past_snapshot_and_cancelled_exception(self):
        self.db.save_setup(self.db.get_subjects(),timetable([slot('a',week='A'),slot('b','physique','B')]))
        self.db.ensure_day('2026-08-31')
        self.db.ensure_day('2026-09-07')
        cancelled=self.db.list_time_entries('2026-09-07','2026-09-07')[0]
        self.db.delete_time_entry(cancelled['id'])
        self.now.return_value=datetime(2026,9,1,12)
        self.db.save_timetable(timetable([slot('a',week='A'),slot('b','physique','B')],anchor='2026-09-07'))
        self.db.ensure_day('2026-08-31')
        self.assertEqual(self.db.list_time_entries('2026-08-31','2026-08-31')[0]['category'],'maths')
        cancelled_row=self.db._rows('SELECT * FROM time_entries WHERE id=?',(cancelled['id'],))[0]
        self.assertEqual(cancelled_row['deleted'],1)

    def test_legacy_migration_retains_timetable_and_skips_new_setup(self):
        path=Path(self.temp.name)/'legacy.sqlite3'
        legacy=Store(path)
        old=slot()
        del old['week']
        legacy.set_setting('desktop_timetable',dict(version=1,semesters={'S1':[old],'S2':[]}))
        legacy.close()
        migrated=DesktopStore(path)
        try:
            self.assertTrue(migrated.get_setting('setup_completed'))
            self.assertEqual(migrated.get_timetable()['semesters']['S1'],[{**old,'week':'all'}])
            self.assertEqual(migrated.get_subjects(),default_subjects())
        finally:migrated.close()


if __name__=='__main__':unittest.main()
