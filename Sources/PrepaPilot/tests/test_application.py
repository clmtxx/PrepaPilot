"""Offline regression tests of the current application."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import traceback
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt, QEvent, QDate, QTimer, QAbstractAnimation
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel
from mpsi_desktop.context import AppContext, prepare_data, snapshot_database
from mpsi_desktop.window import MainWindow, WelcomeDialog
from mpsi_desktop.notes import GradeDialog
from mpsi_desktop.widgets import button
from mpsi_core.storage import Store

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        data, _ = prepare_data(self.temp.name, migrate=False)
        self.ctx = AppContext(data)
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append((str(value), ''.join(traceback.format_tb(tb))))
        self.window = MainWindow(self.ctx, show_welcome=False)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        sys.excepthook = self.old_hook
        self.assertEqual(self.errors, [])

    def test_seven_pages_theme_and_removed_features(self):
        self.assertEqual(list(self.window.pages), ['home', 'time', 'progression', 'notes', 'documents', 'memory', 'settings'])
        self.assertFalse(hasattr(self.window, 'ai_button'))
        for key in self.window.pages:
            self.window.navigate(key, animate=False)
            APP.processEvents()
            self.assertIs(self.window.stack.currentWidget(), self.window.wrappers[key])
        self.window.toggle_theme()
        self.assertEqual(self.ctx.theme, 'dark')
        self.window.toggle_theme()
        self.assertEqual(self.ctx.db.get_setting('desktop_theme'), 'light')

    def test_profile_plain_text_and_persistence(self):
        dialog = WelcomeDialog(self.ctx, self.window)
        dialog.name.setText('Alex <test>')
        dialog.save()
        self.assertTrue(self.ctx.db.get_setting('desktop_welcomed'))
        heading = self.window.pages['home'].header.findChild(QLabel, 'heroTitle')
        self.assertEqual(heading.text(), 'Bonjour Alex <test>.')
        self.assertEqual(heading.textFormat(), Qt.PlainText)

    def test_grade_conversion_edit_and_validation(self):
        dialog = GradeDialog(self.ctx, parent=self.window)
        dialog.score.setValue(5.5)
        dialog.scale.setValue(10)
        dialog.graded_on.setDate(QDate(2026,9,7))
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        grade = self.ctx.grades('maths')[0]
        self.assertEqual(grade['normalized_score'], 11)
        edit = GradeDialog(self.ctx, grade=grade, parent=self.window)
        edit.subject.setCurrentIndex(edit.subject.findData('anglais'))
        self.assertEqual(edit.kind.currentData(), 'cours')
        edit.save()
        self.assertEqual(len(self.ctx.grades('anglais')), 1)
        invalid = GradeDialog(self.ctx, parent=self.window)
        invalid.score.setValue(12)
        invalid.scale.setValue(10)
        invalid.save()
        self.assertNotEqual(invalid.result(), QDialog.Accepted)
        self.assertEqual(len(self.ctx.grades()), 1)

    def test_grade_retry_and_duplicate_submit(self):
        dialog = GradeDialog(self.ctx, parent=self.window)
        dialog.score.setValue(14)
        with patch.object(self.ctx.db, 'add_grade', side_effect=sqlite3.OperationalError('Occupé')):
            dialog.save()
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertIsNone(dialog.saved_id)
        dialog.save()
        dialog.save()
        self.assertEqual(len(self.ctx.db.list_grades()), 1)

    def test_memory_and_reload_clear_stale_editors(self):
        page = self.window.pages['memory']
        page.key_input.setText('Objectif')
        page.value_input.setPlainText('Travailler les suites')
        page.save_memory()
        self.assertEqual(self.ctx.db.memories()['Objectif'], 'Travailler les suites')
        self.ctx.db.set_setting('school_year', 2028)
        self.ctx.reload_data()
        self.assertEqual(self.window.year.currentData(), 2028)
        self.assertEqual(page.key_input.text(), '')
        self.assertFalse(page.key_input.isReadOnly())

    def test_repeated_navigation_and_reduced_motion(self):
        self.ctx.db.set_setting('desktop_reduced_motion', False)
        self.ctx.mark_changed()
        for key in ('time','notes','documents','home','notes'):
            self.window.navigate(key)
            APP.processEvents()
        self.window.animation.setCurrentTime(self.window.animation.duration())
        self.assertEqual(self.window.current_key, 'notes')
        self.assertFalse(self.window.transition.isVisible())
        self.window.navigate('time')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.ctx.mark_changed()
        self.assertEqual(self.window.animation.state(), QAbstractAnimation.Stopped)
        self.assertFalse(self.window.transition.isVisible())

    def test_button_mouse_keyboard_and_disabled(self):
        values = []
        control = button('Ajouter', lambda: values.append(True))
        control.setParent(self.window)
        control.show()
        QTest.mouseClick(control, Qt.LeftButton)
        control.setFocus()
        QTest.keyClick(control, Qt.Key_Space)
        control.setEnabled(False)
        QTest.mouseClick(control, Qt.LeftButton)
        self.assertEqual(values, [True, True])
        self.assertEqual(control.press_animation.state(), QAbstractAnimation.Stopped)

    def test_close_cancels_all_presentation_callbacks(self):
        self.window.notify('Enregistré')
        self.window.welcome_timer.start(500)
        self.window.migration_timer.start(500)
        home = self.window.pages['home']
        home.focus_session.start(None, minutes=25)
        home._sync_focus()
        self.window.close()
        self.assertFalse(any(timer.isActive() for timer in self.window.findChildren(QTimer)))
        self.assertFalse(any(animation.state()==QAbstractAnimation.Running for animation in self.window.findChildren(QAbstractAnimation)))

    def test_shortcuts_route_to_current_feature(self):
        self.window.navigate('documents')
        with patch.object(self.window.pages['documents'], 'add_documents') as add:
            self.window.quick_add()
            add.assert_called_once()
        self.window.navigate('home')
        with patch.object(self.window.pages['time'], 'add_activity') as add:
            self.window.quick_add()
            add.assert_called_once()
        self.assertEqual(self.window.current_key, 'time')


class MigrationTests(unittest.TestCase):
    def test_failed_document_copy_keeps_migration_retryable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root/'CompagnonMPSI'/'data'
            store = Store(legacy/'mpsi.sqlite3')
            store.add_grade('maths', 'ds', 15, 20, '2026-09-21')
            store.close()
            (legacy/'documents').mkdir()
            (legacy/'documents'/'cours.txt').write_text('Cours original', encoding='utf-8')
            with patch('mpsi_desktop.context.shutil.copytree', side_effect=OSError('Disque plein')):
                with self.assertRaises(OSError):
                    prepare_data(root/'PrepaPilot')
            self.assertFalse((root/'PrepaPilot'/'data'/'mpsi.sqlite3').exists())
            data, migrated = prepare_data(root/'PrepaPilot')
            self.assertTrue(migrated)
            self.assertEqual((data/'documents'/'cours.txt').read_text(encoding='utf-8'), 'Cours original')
            ctx = AppContext(data)
            self.assertEqual(len(ctx.grades()), 1)
            ctx.close()

    def test_previous_portable_data_are_copied_once_with_committed_wal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root/'CompagnonMPSI'/'data'/'mpsi.sqlite3'
            store = Store(legacy)
            store.add_grade('maths','ds',15,20,'2026-09-21')
            store.remember('Objectif', 'Persévérer')
            data, migrated = prepare_data(root/'PrepaPilot')
            self.assertTrue(migrated)
            ctx = AppContext(data)
            self.assertEqual(len(ctx.grades()), 1)
            self.assertEqual(ctx.db.memories(), {'Objectif':'Persévérer'})
            ctx.db.add_grade('physique','ds',12,20,'2026-09-22')
            ctx.close()
            _, migrated = prepare_data(root/'PrepaPilot')
            self.assertFalse(migrated)
            self.assertEqual(len(store.list_grades()), 1)
            store.close()
            again = AppContext(data)
            self.assertEqual(len(again.grades()), 2)
            again.close()

    def test_snapshot_rejects_active_database_as_target(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'data.sqlite3'
            store = Store(path)
            with self.assertRaises(ValueError):
                snapshot_database(path, path)
            store.close()


if __name__ == '__main__':
    unittest.main()
