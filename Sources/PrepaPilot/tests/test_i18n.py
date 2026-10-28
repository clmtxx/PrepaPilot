"""Language choice, full UI refresh, durable preferences and unchanged drafts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from datetime import date, datetime, timedelta
from pathlib import Path
from string import Formatter
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import QEvent
from shiboken6 import isValid
from mpsi_desktop.context import AppContext
from mpsi_desktop.i18n import english_catalog, format_date, language, load_saved_language, set_language, tr
from mpsi_desktop.language_choice import LanguageDialog, choose_language
from mpsi_desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.windows = []
        self.ctx.db.set_setting('desktop_reduced_motion', True)

    def tearDown(self):
        for window in self.windows:
            if isValid(window):
                window.close()
                window.deleteLater()
        APP.processEvents()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        self.ctx.close()
        self.temp.cleanup()
        set_language('fr')

    def window(self):
        result = MainWindow(self.ctx, show_welcome=False)
        result.show()
        self.windows.append(result)
        APP.processEvents()
        return result

    def test_bilingual_choice_is_saved_and_not_repeated(self):
        dialog = LanguageDialog(self.ctx)
        self.assertEqual([dialog.language.itemText(i) for i in range(2)], ['Français', 'English'])
        dialog.language.setCurrentIndex(dialog.language.findData('en'))
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(load_saved_language(self.ctx.data_dir), 'en')
        self.assertEqual(language(), 'en')
        with patch('mpsi_desktop.language_choice.LanguageDialog') as factory:
            self.assertTrue(choose_language(self.ctx))
            factory.assert_not_called()
        dialog.deleteLater()

    def test_cancel_does_not_record_a_language(self):
        with patch('mpsi_desktop.language_choice.LanguageDialog') as factory:
            factory.return_value.exec.return_value = QDialog.Rejected
            self.assertFalse(choose_language(self.ctx))
        self.assertIsNone(self.ctx.db.get_setting('desktop_language'))

    def test_language_does_not_change_user_data(self):
        self.ctx.db.remember('Méthode', 'Un texte que je garde en français.')
        before = self.ctx.db.memories()
        self.ctx.set_language('en')
        self.assertEqual(self.ctx.db.memories(), before)
        self.ctx.set_language('fr')
        self.assertEqual(self.ctx.db.memories(), before)

    def test_refresh_preserves_running_session_and_unsaved_draft(self):
        old = self.window()
        memory = old.pages['memory']
        memory.new_memory()
        memory.key_input.setText('Mon brouillon')
        memory.value_input.setPlainText('À conserver tel quel.')
        session = old.pages['home'].focus_session
        session.start('maths', minutes=25)
        old.pages['home']._sync_focus()
        old.navigate('settings', animate=False)
        settings = old.pages['settings']
        settings.language.setCurrentIndex(settings.language.findData('en'))
        settings.save_profile()
        APP.processEvents()
        new = APP._prepapilot_window
        self.windows.append(new)
        self.assertIsNot(old, new)
        self.assertEqual(new.current_key, 'settings')
        self.assertEqual(new.nav['home'][0].text(), 'Today')
        self.assertEqual(new.nav['notes'][0].text(), 'Grades')
        self.assertEqual(new.pages['settings'].language.currentData(), 'en')
        self.assertEqual(new.pages['memory'].key_input.text(), 'Mon brouillon')
        self.assertEqual(new.pages['memory'].value_input.toPlainText(), 'À conserver tel quel.')
        self.assertIs(new.pages['home'].focus_session, session)
        self.assertEqual(session.status, 'running')
        self.assertIsNone(self.ctx.db.memories().get('Mon brouillon'))
        self.ctx.set_language('fr')
        APP.processEvents()
        french = APP._prepapilot_window
        self.windows.append(french)
        self.assertEqual(french.nav['home'][0].text(), 'Aujourd’hui')
        self.assertEqual(french.pages['memory'].key_input.text(), 'Mon brouillon')
        self.assertEqual(session.status, 'running')

    def test_refresh_preserves_editing_an_existing_note(self):
        self.ctx.db.remember('Mon objectif', 'Texte enregistré')
        old = self.window()
        memory = old.pages['memory']
        memory.memory_list.setCurrentRow(0)
        memory.value_input.setPlainText('Modification non enregistrée')
        self.ctx.set_language('en')
        APP.processEvents()
        new = APP._prepapilot_window
        self.windows.append(new)
        self.assertEqual(new.pages['memory']._selected_key, 'Mon objectif')
        self.assertTrue(new.pages['memory'].key_input.isReadOnly())
        self.assertEqual(new.pages['memory'].value_input.toPlainText(), 'Modification non enregistrée')
        self.assertEqual(self.ctx.db.memories()['Mon objectif'], 'Texte enregistré')

    def test_slow_language_refresh_excludes_ui_time_and_keeps_timer_running(self):
        old = self.window()
        session = old.pages['home'].focus_session
        clock = [datetime(2026, 10, 24, 14), 1000.0]
        session._now = lambda: clock[0]
        session._monotonic = lambda: clock[1]
        session.start('maths', minutes=25)

        def slow_window(*args, **kwargs):
            clock[0] += timedelta(seconds=10)
            clock[1] += 10
            return MainWindow(*args, **kwargs)

        with patch('mpsi_desktop.window.MainWindow', side_effect=slow_window):
            self.ctx.set_language('en')
            APP.processEvents()
        new = APP._prepapilot_window
        self.windows.append(new)
        self.assertIs(new.pages['home'].focus_session, session)
        self.assertEqual(session.status, 'running')
        self.assertEqual(session.elapsed_seconds, 0)
        clock[0] += timedelta(seconds=1)
        clock[1] += 1
        self.assertEqual(session.tick(), 'running')
        self.assertEqual(session.elapsed_seconds, 1)

    def test_background_work_blocks_language_changes(self):
        job = object()
        self.ctx._jobs.add(job)
        try:
            with self.assertRaises(ValueError):
                self.ctx.set_language('en')
            self.assertEqual(language(), 'fr')
        finally:
            self.ctx._jobs.clear()

    def test_catalog_preserves_every_format_field(self):
        formatter = Formatter()
        def fields(text):
            return {name for _, name, _, _ in formatter.parse(text) if name is not None}
        catalog = english_catalog()
        self.assertGreater(len(catalog), 1000)
        for source, target in catalog.items():
            with self.subTest(source=source):
                self.assertEqual(fields(source), fields(target))

    def test_localized_dates_and_exact_personal_values(self):
        set_language('en')
        self.assertEqual(format_date(date(2026, 10, 23)), '23 Oct 2026')
        self.assertEqual(tr('Aperçu : {title}. {description}', title='Mes notes', description='En français'), 'Preview: Mes notes. En français')
        set_language('fr')
        self.assertEqual(format_date(date(2026, 10, 23)), '23/10/2026')


if __name__ == '__main__':
    unittest.main()
