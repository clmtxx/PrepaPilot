"""Real asynchronous review and application of assistant file proposals."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from string import Formatter
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from mpsi_desktop.context import AppContext
from mpsi_desktop.documents_page import DocumentsPage
from mpsi_desktop.i18n import set_language
from mpsi_desktop.local_organization_dialog import LocalOrganizationDialog
from mpsi_desktop.theme import apply_theme
from mpsi_desktop.translations_organization import EN


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class LocalOrganizationUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ctx = AppContext(self.root / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        source = self.root / 'cours.txt'
        source.write_text('Le cours original', encoding='utf-8')
        self.identity = self.ctx.db.import_document(source, 'maths', 'cours')
        self.dialog = LocalOrganizationDialog(self.ctx)
        self.dialog.show()
        APP.processEvents()

    def tearDown(self):
        self.wait_jobs()
        self.dialog.close()
        self.dialog.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        QApplication.clipboard().clear()
        set_language('fr')
        apply_theme(APP, 'light')

    def wait_jobs(self):
        deadline = time.monotonic() + 10
        while (self.ctx.busy or self.dialog._busy) and time.monotonic() < deadline:
            APP.processEvents()
            QTest.qWait(10)
        APP.processEvents()
        self.assertFalse(self.ctx.busy)
        self.assertFalse(self.dialog._busy)

    def prepare(self):
        self.dialog.prepare()
        self.assertFalse(self.dialog.apply_button.isEnabled())
        self.assertFalse(self.dialog.close_button.isEnabled())
        self.dialog.reject()
        self.assertTrue(self.dialog.isVisible())
        self.wait_jobs()
        self.assertIsNotNone(self.dialog.workspace)
        return self.dialog.workspace

    def write_proposal(self, folder='Mathématiques · Chapitre 1', *, include_import=True):
        workspace = self.dialog.workspace
        path = workspace / 'proposition.json'
        plan = json.loads(path.read_text(encoding='utf-8'))
        plan['documents'][0]['title'] = 'Cours de mathématiques'
        plan['documents'][0]['folder'] = folder
        if include_import:
            (workspace / 'A-importer' / 'exercices.txt').write_text('Exercices nouveaux', encoding='utf-8')
            plan['imports'] = [{'source': 'A-importer/exercices.txt', 'title': 'Exercices',
                'subject': 'maths', 'kind': 'td', 'description': '', 'folder': folder}]
        path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')

    def test_prepare_copy_review_and_apply_real_proposal(self):
        workspace = self.prepare()
        self.assertEqual(self.dialog.workspace_path.text(), str(workspace))
        self.assertEqual(self.dialog.originals_path.text(), str(self.ctx.db.document_directory.resolve()))
        self.dialog.copy_instruction()
        instruction = QApplication.clipboard().text()
        self.assertIn(str(workspace), instruction)
        for name in ('AGENTS.md', 'NOTICE-IA.md', 'catalogue.json', 'proposition.json', 'A-importer'):
            self.assertIn(name, instruction)
        original = self.ctx.db.document_path(self.identity).read_bytes()
        self.write_proposal()
        self.dialog.read_proposal()
        self.wait_jobs()
        self.assertTrue(self.dialog.apply_button.isEnabled())
        self.assertEqual(self.dialog.preview['update_count'], 1)
        self.assertEqual(self.dialog.preview['import_count'], 1)
        self.assertIn('Mathématiques · Chapitre 1', self.dialog.preview_text.toPlainText())
        self.assertEqual(self.ctx.db.get_document(self.identity)['title'], 'cours')
        self.dialog.apply()
        self.wait_jobs()
        self.assertEqual(self.ctx.db.get_document(self.identity)['title'], 'Cours de mathématiques')
        self.assertEqual(len(self.ctx.db.list_documents()), 2)
        self.assertEqual(self.ctx.db.document_path(self.identity).read_bytes(), original)
        self.assertFalse(self.dialog.apply_button.isEnabled())
        self.assertIn('Classement appliqué', self.dialog.status.text())

    def test_changed_proposal_is_refused_after_review_and_can_be_read_again(self):
        self.prepare()
        self.write_proposal(include_import=False)
        self.dialog.read_proposal()
        self.wait_jobs()
        self.write_proposal(folder='Autre proposition', include_import=False)
        self.dialog.apply()
        self.wait_jobs()
        self.assertIsNone(self.dialog.preview)
        self.assertFalse(self.dialog.apply_button.isEnabled())
        self.assertIn('changé', self.dialog.status.text())
        self.assertEqual(self.ctx.db.get_document(self.identity)['title'], 'cours')
        self.dialog.read_proposal()
        self.wait_jobs()
        self.assertTrue(self.dialog.apply_button.isEnabled())
        self.assertIn('Autre proposition', self.dialog.preview_text.toPlainText())

    def test_library_change_invalidates_preview_and_resume_checks_session(self):
        workspace = self.prepare()
        self.write_proposal(include_import=False)
        self.dialog.read_proposal()
        self.wait_jobs()
        self.ctx.db.update_document(self.identity, 'Titre manuel', 'maths', 'cours')
        self.ctx.mark_changed('documents')
        self.assertFalse(self.dialog.apply_button.isEnabled())
        with patch('mpsi_desktop.local_organization_dialog.QFileDialog.getExistingDirectory', return_value=str(workspace)):
            self.dialog.choose_workspace()
        self.dialog.read_proposal()
        self.wait_jobs()
        self.assertIn('bibliothèque a changé', self.dialog.status.text())
        self.assertEqual(self.ctx.db.get_document(self.identity)['title'], 'Titre manuel')
        self.assertFalse(self.dialog.apply_button.isEnabled())

    def test_last_workspace_resumes_without_regenerating_copies(self):
        workspace = self.prepare()
        self.write_proposal(include_import=False)
        before = (workspace / 'proposition.json').read_bytes()
        resumed = LocalOrganizationDialog(self.ctx)
        self.assertEqual(resumed.workspace, workspace)
        self.assertEqual((workspace / 'proposition.json').read_bytes(), before)
        self.assertFalse(resumed.apply_button.isEnabled())
        resumed.deleteLater()

    def test_original_path_and_entry_point_in_document_library(self):
        page = DocumentsPage(self.ctx)
        page.resize(1024, 680)
        page.show()
        APP.processEvents()
        self.assertEqual(page.stored_path.text(), str(self.ctx.db.document_path(self.identity)))
        self.assertTrue(page.stored_path.isReadOnly())
        self.assertTrue(page.organization_button.isVisible())
        with patch('mpsi_desktop.local_organization_dialog.LocalOrganizationDialog.exec', return_value=QDialog.Rejected) as opened:
            page.organize_with_ai()
        opened.assert_called_once()
        self.assertLessEqual(page.minimumSizeHint().width(), 1024)
        page.close()
        page.deleteLater()

    def test_small_dialog_in_both_languages_and_themes_has_no_horizontal_overflow(self):
        for locale in ('fr', 'en'):
            set_language(locale)
            for theme in ('light', 'dark'):
                apply_theme(APP, theme)
                dialog = LocalOrganizationDialog(self.ctx)
                dialog.resize(600, 440)
                dialog.show()
                APP.processEvents()
                state = (locale, theme, dialog.size(), dialog.scroll.widget().size(), dialog.scroll.viewport().size())
                self.assertEqual(dialog.scroll.horizontalScrollBar().maximum(), 0, state)
                self.assertLessEqual(dialog.scroll.widget().width(), dialog.scroll.viewport().width(), state)
                self.assertLessEqual(dialog.height(), 440, state)
                self.assertLess(dialog.apply_button.mapTo(dialog, dialog.apply_button.rect().bottomRight()).y(), dialog.height(), state)
                self.assertTrue(dialog.scroll.verticalScrollBar().maximum() > 0, state)
                if locale == 'en':
                    self.assertEqual(dialog.windowTitle(), 'Organise with AI')
                    self.assertEqual(dialog.prepare_button.text(), 'Prepare a new workspace')
                dialog.reject()
                dialog.deleteLater()

    def test_translations_keep_all_format_fields(self):
        formatter = Formatter()
        for source, target in EN.items():
            with self.subTest(source=source):
                fields = lambda text: {name for _, name, _, _ in formatter.parse(text) if name is not None}
                self.assertEqual(fields(source), fields(target))


if __name__ == '__main__':
    unittest.main()
