"""Earned rewards travel independently of optional journal backup categories."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext, DesktopStore
from mpsi_desktop import achievements, cloud_backup as cloud, transfers
from test_cloud_backup import FakeDrive

APP = QApplication.instance() or QApplication([])


def ledger(**awards):
    return {'version': 1, 'awards': {key: {'earned_at': stamp} for key, stamp in awards.items()}}


class AchievementTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = AppContext(self.root / 'source')
        self.target = AppContext(self.root / 'target')
        self.drive = FakeDrive()

    def tearDown(self):
        self.source.close()
        self.target.close()
        self.temp.cleanup()

    def qualifying_activity(self, ctx):
        return ctx.db.add_time_entry('sport', '2020-09-07T10:00', '2020-09-07T11:00', 'Sport validé')

    def awards(self, ctx):
        return ctx.db.get_setting(achievements.SETTING, {'version': 1, 'awards': {}})['awards']

    def snapshot(self, selection=('grades',)):
        return cloud.backup_to_drive(self.source, self.drive, 'root', list(selection))

    def restore(self, snapshot):
        with cloud.prepare_drive_restore(self.target, self.drive, 'root', snapshot['snapshot_id']) as plan:
            cloud.validate_restore_target(self.target, plan)
            return transfers.apply_import(self.target, plan)

    def target_state(self):
        return {table: self.target.db._rows(f'SELECT * FROM "{table}" ORDER BY 1')
                for table in transfers._schema(self.target.db._connection)}

    def test_selective_drive_backup_reconciles_and_restores_without_journal(self):
        self.qualifying_activity(self.source)
        self.assertFalse(self.awards(self.source))
        result = self.snapshot()
        earned = self.awards(self.source)
        self.assertIn('sport_total:1', earned)
        self.assertIn('quest:sport_week:2020-09-07', earned)
        manifest = json.loads(self.drive.payloads[result['snapshot_id']])
        self.assertNotIn('time_entries', manifest['records'])
        self.restore(result)
        self.assertEqual(self.awards(self.target), earned)
        self.assertEqual(self.target.db.list_time_entries(), [])
        achievements.reconcile(self.target.db)
        self.assertEqual(self.awards(self.target), earned)

    def test_unchanged_rewards_never_duplicate_drive_objects_or_snapshot(self):
        self.qualifying_activity(self.source)
        first = self.snapshot()
        uploads = len(self.drive.uploads)
        second = self.snapshot()
        self.assertEqual(second['snapshot_id'], first['snapshot_id'])
        self.assertFalse(second['changed'])
        self.assertEqual(second['uploaded'], 0)
        self.assertEqual(len(self.drive.uploads), uploads)

    def test_selective_restore_unions_rewards_keeps_first_date_and_is_idempotent(self):
        self.source.db.set_setting(achievements.SETTING, ledger(**{
            'work_total:1': '2020-09-10T15:00:00',
            'work_week:1': '2020-09-10T15:00:00',
        }))
        self.target.db.set_setting(achievements.SETTING, ledger(**{
            'work_total:1': '2020-09-07T15:00:00',
            'sleep_streak:1': '2020-09-06T07:00:00',
        }))
        result = self.snapshot()
        self.restore(result)
        merged = self.awards(self.target)
        self.assertEqual(set(merged), {'work_total:1', 'work_week:1', 'sleep_streak:1'})
        self.assertEqual(merged['work_total:1']['earned_at'], '2020-09-07T15:00:00')
        self.restore(result)
        self.assertEqual(self.awards(self.target), merged)

    def test_full_drive_restore_also_preserves_local_trophies(self):
        self.source.db.set_setting(achievements.SETTING, ledger(**{'work_total:1': '2020-09-07T15:00:00'}))
        self.target.db.set_setting(achievements.SETTING, ledger(**{'sleep_streak:1': '2020-09-06T07:00:00'}))
        self.restore(self.snapshot(cloud.CATEGORIES))
        self.assertEqual(set(self.awards(self.target)), {'work_total:1', 'sleep_streak:1'})

    def test_legacy_new_study_and_sport_rewards_round_trip_without_journal_or_duplicates(self):
        state = ledger(**{
            'work_total:1': '2020-09-07T15:00:00',
            'quest:work_week:2020-09-07': '2020-09-11T18:00:00',
            'work_total_v2:1': '2020-10-05T18:00:00',
            'work_week_v2:1': '2020-10-05T18:00:00',
            'work_month_v2:5': '2020-10-25T18:00:00',
            'work_week_v3:2': '2020-10-09T18:00:00',
            'work_month_v3:2': '2020-10-20T18:00:00',
            'quest:work_week_v2:2020-10-05': '2020-10-09T18:00:00',
            'sport_total:1': '2020-10-05T19:00:00',
            'sport_streak:1': '2020-10-12T19:00:00',
            'quest:sport_week:2020-10-05': '2020-10-05T19:00:00',
        })
        self.source.db.set_setting(achievements.SETTING, state)
        first = self.snapshot()
        self.assertEqual(self.awards(self.source), state['awards'])
        uploads = len(self.drive.uploads)
        self.assertEqual(self.snapshot()['snapshot_id'], first['snapshot_id'])
        self.assertEqual(len(self.drive.uploads), uploads)
        self.restore(first)
        points = achievements.snapshot(self.target.db)['points']
        self.assertGreater(points, 0)
        self.assertEqual(self.awards(self.target), state['awards'])
        self.assertEqual(self.target.db.list_time_entries(), [])
        self.restore(first)
        self.assertEqual(achievements.snapshot(self.target.db)['points'], points)
        self.assertEqual(self.awards(self.target), state['awards'])
        archive = self.root / 'legacy-new-sport.prepapilot'
        transfers.export_archive(self.source, archive)
        with transfers.inspect_archive(archive, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.awards(self.target), state['awards'])
        self.assertEqual(achievements.snapshot(self.target.db)['points'], points)

    def test_previous_week_and_month_diamonds_restore_without_unlocking_harder_diamonds(self):
        state = ledger(**{
            'work_week_v2:5': '2020-10-11T18:00:00',
            'work_month_v2:5': '2020-10-25T18:00:00',
        })
        self.source.db.set_setting(achievements.SETTING, state)
        self.restore(self.snapshot())
        archive = self.root / 'previous-diamonds.prepapilot'
        transfers.export_archive(self.source, archive)
        for restore_local in (False, True):
            with self.subTest(restore_local=restore_local):
                if restore_local:
                    with transfers.inspect_archive(archive, DesktopStore) as plan:
                        transfers.apply_import(self.target, plan)
                report = achievements.reconcile(self.target.db)
                self.assertEqual(self.awards(self.target), state['awards'])
                self.assertEqual(report['points'], 2000)
                self.assertEqual(report['legacy_points'], 2000)
                self.assertEqual(report['earned_count'], 0)
                self.assertEqual(report['new_awards'], [])
                self.assertEqual(self.target.db.list_time_entries(), [])

    def test_old_drive_snapshot_without_rewards_keeps_local_collection(self):
        self.target.db.set_setting(achievements.SETTING, ledger(**{'sleep_streak:1': '2020-09-06T07:00:00'}))
        before = self.awards(self.target)
        result = self.snapshot()
        raw = b'\n'.join(self.drive.payloads.values())
        self.assertNotIn(achievements.SETTING.encode(), raw)
        self.restore(result)
        self.assertEqual(self.awards(self.target), before)

    def test_deleted_source_activities_do_not_retract_saved_rewards(self):
        identity = self.qualifying_activity(self.source)
        first = self.snapshot()
        earned = self.awards(self.source)
        self.source.db.delete_time_entry(identity)
        second = self.snapshot()
        self.assertEqual(second['snapshot_id'], first['snapshot_id'])
        self.restore(second)
        self.assertEqual(self.awards(self.target), earned)

    def test_malformed_drive_rewards_are_rejected_before_target_mutation(self):
        self.source.db.set_setting(achievements.SETTING, ledger(**{'work_total:1': '2020-09-07T15:00:00'}))
        original_json = cloud._json
        before = self.target_state()
        for malformed in (
            {'version': True, 'awards': {}},
            ledger(**{'unknown:1': '2020-09-07T15:00:00'}),
            {'version': 1, 'awards': {'work_total:1': {'earned_at': '2020-09-07T15:00:00', 'points': 100000}}},
            ledger(**{'quest:work_week:2020-09-08': '2020-09-10T15:00:00'}),
        ):
            def tamper(value):
                if isinstance(value, dict) and value.get('table') == 'settings' and value['values']['key'] == achievements.SETTING:
                    value = {**value, 'values': {**value['values'], 'value': json.dumps(malformed)}}
                return original_json(value)
            with self.subTest(malformed=malformed):
                with patch.object(cloud, '_json', side_effect=tamper):
                    result = self.snapshot()
                with self.assertRaises(ValueError):
                    cloud.prepare_drive_restore(self.target, self.drive, 'root', result['snapshot_id'])
                self.assertEqual(self.target_state(), before)
                self.assertFalse((self.target.data_dir / 'backups').exists())

    def test_local_export_reconciles_and_full_import_restores_exact_ledger(self):
        self.qualifying_activity(self.source)
        self.target.db.set_setting(achievements.SETTING, ledger(**{'sleep_streak:1': '2020-09-06T07:00:00'}))
        archive = self.root / 'donnees.prepapilot'
        transfers.export_archive(self.source, archive)
        earned = self.awards(self.source)
        self.assertIn('sport_total:1', earned)
        with transfers.inspect_archive(archive, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assertEqual(self.awards(self.target), earned)
        self.assertNotIn('sleep_streak:1', self.awards(self.target))

    def test_pre_import_safety_archive_captures_exact_state_without_extra_awards(self):
        self.qualifying_activity(self.target)
        self.assertFalse(self.awards(self.target))
        archive = self.root / 'safety.prepapilot'
        transfers.export_archive(self.target, archive, reconcile_achievements=False)
        self.assertFalse(self.awards(self.target))
        with transfers.inspect_archive(archive, DesktopStore) as plan:
            with closing(sqlite3.connect(plan.folder / 'data.sqlite3')) as connection:
                self.assertIsNone(connection.execute('SELECT value FROM settings WHERE key=?', (achievements.SETTING,)).fetchone())

    def test_local_import_rejects_corrupt_ledger_before_replacing_anything(self):
        self.source.db.set_setting(achievements.SETTING, ledger(**{'work_total:1': '2020-09-07T15:00:00'}))
        archive = self.root / 'original.prepapilot'
        transfers.export_archive(self.source, archive)
        with ZipFile(archive) as source:
            files = {name: source.read(name) for name in source.namelist()}
        database = self.root / 'mutated.sqlite3'
        database.write_bytes(files['data.sqlite3'])
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute('UPDATE settings SET value=? WHERE key=?',
                               (json.dumps(ledger(**{'invented:5': '2020-09-07T15:00:00'})), achievements.SETTING))
        files['data.sqlite3'] = database.read_bytes()
        manifest = json.loads(files['manifest.json'])
        manifest['files']['data.sqlite3'] = {'size': len(files['data.sqlite3']), 'sha256': hashlib.sha256(files['data.sqlite3']).hexdigest()}
        files['manifest.json'] = json.dumps(manifest).encode()
        changed = self.root / 'changed.prepapilot'
        with ZipFile(changed, 'w', ZIP_DEFLATED) as target:
            for name, raw in files.items():
                target.writestr(name, raw)
        before = self.target_state()
        with self.assertRaises(ValueError):
            transfers.inspect_archive(changed, DesktopStore)
        self.assertEqual(self.target_state(), before)


if __name__ == '__main__':
    unittest.main()
