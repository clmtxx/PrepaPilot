"""Both languages cover study tools without altering personal content or IDs."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import string
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from mpsi_desktop.context import AppContext
from mpsi_desktop.documents_page import DocumentFolderDialog, DocumentMetadataDialog, DocumentsPage, size_text
from mpsi_desktop.focus_dialogs import FocusReviewDialog, FocusSetupDialog
from mpsi_desktop.focus_session import validate_focus_session
from mpsi_desktop.i18n import language, set_language, tr
from mpsi_desktop.memory import MemoryPage
from mpsi_desktop.notes import GradeDialog, NotesPage, SubjectDialog, number
from mpsi_desktop.subject_store import validate_subjects
from mpsi_desktop.translations_study import EN


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ReviewSession:
    state = {"category": "maths", "title": "Réviser les suites", "interrupted": False}

    def review_entries(self):
        return [{"start_at": "2026-09-20T18:00", "end_at": "2026-09-20T18:25"}]

    def update_review(self, **values):
        pass


class StudyTranslationTests(unittest.TestCase):
    def setUp(self):
        self.previous_language = language()
        set_language("fr")
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(self.temp.name)
        self.ctx.db.set_setting("desktop_reduced_motion", True)
        self.ctx.db.set_setting("desktop_subjects", [
            dict(id="maths", name="Mon cours personnalisé", color="#0071E3", active=True),
        ])
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            widget.hide()
            widget.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        set_language(self.previous_language)

    def keep(self, widget):
        self.widgets.append(widget)
        return widget

    def test_translation_placeholders_match_french_messages(self):
        formatter = string.Formatter()
        for source, english in EN.items():
            with self.subTest(source=source):
                fields = lambda text: {key for _, key, _, _ in formatter.parse(text) if key is not None}
                self.assertEqual(fields(source), fields(english))

    def test_grade_dialog_uses_natural_english_and_keeps_saved_content(self):
        set_language("en")
        dialog = self.keep(GradeDialog(self.ctx))
        self.assertEqual(dialog.windowTitle(), "Add a grade")
        self.assertEqual(dialog.score.accessibleName(), "Your score")
        self.assertEqual(dialog.scale.accessibleName(), "Maximum score")
        self.assertEqual(dialog.subject.currentText(), "Mon cours personnalisé")
        self.assertEqual(dialog.kind.currentData(), "cours")
        dialog.label.setText("Contrôle de suites")
        dialog.score.setValue(15.5)
        dialog.save()
        row = next(row for row in self.ctx.grades("maths") if row["id"] == dialog.saved_id)
        self.assertEqual(row["subject"], "maths")
        self.assertEqual(row["kind"], "cours")
        self.assertEqual(row["label"], "Contrôle de suites")
        self.assertEqual(row["score"], 15.5)

    def test_grade_validation_appears_in_selected_language(self):
        for code, expected in (("fr", "La note doit être comprise entre 0 et le barème."),
                               ("en", "The score must be between 0 and the maximum.")):
            with self.subTest(language=code):
                set_language(code)
                dialog = self.keep(GradeDialog(self.ctx))
                dialog.score.setValue(21)
                dialog.save()
                self.assertEqual(dialog.error.text(), expected)
                self.assertIsNone(dialog.saved_id)

    def test_recreated_pages_follow_language_and_localise_numbers_and_dates(self):
        self.ctx.db.add_grade("maths", "cours", 15.5, 20, f"{self.ctx.year}-09-20", "Évaluation personnelle")
        french = self.keep(NotesPage(self.ctx))
        self.assertEqual(french.add_button.text(), "+  Ajouter une note")
        self.assertEqual(number(15.5), "15,5")
        set_language("en")
        english = self.keep(NotesPage(self.ctx))
        self.assertEqual(english.add_button.text(), "+  Add a grade")
        self.assertEqual(number(15.5), "15.5")
        self.assertEqual(english.table.item(0, 0).text(), f"20 Sep {self.ctx.year}")
        self.assertEqual(english.table.item(0, 2).text(), "Évaluation personnelle")
        self.assertEqual(self.ctx.db.subject_labels()["maths"], "Mon cours personnalisé")

    def test_document_dialogs_and_metadata_keep_personal_titles(self):
        set_language("en")
        folder = self.keep(DocumentFolderDialog(self.ctx))
        self.assertEqual(folder.windowTitle(), "New folder")
        self.assertEqual(folder.name.accessibleName(), "Folder name")
        folder.name.setText("Mes révisions")
        folder.save()
        path = Path(self.temp.name) / "Cours français.txt"
        path.write_text("Un contenu inchangé", encoding="utf-8")
        identity = self.ctx.db.import_document(path, "maths", "cours", title="Mon document", folder_id=folder.saved_id)
        row = self.ctx.db.get_document(identity)
        dialog = self.keep(DocumentMetadataDialog(self.ctx, document=row))
        self.assertEqual(dialog.windowTitle(), "Edit document")
        self.assertEqual(dialog.title.text(), "Mon document")
        self.assertEqual(dialog.folder.currentText(), "Mes révisions")
        self.assertEqual(dialog.kind.currentText(), tr("Cours"))
        page = self.keep(DocumentsPage(self.ctx))
        self.assertIn("Folder: Mes révisions", page.meta_label.text())
        self.assertIn("Cours français.txt", page.meta_label.text())
        self.assertEqual(page.reader.toPlainText(), "Un contenu inchangé")
        self.assertEqual(size_text(2048), "2 KB")
        set_language("fr")
        self.assertEqual(size_text(2048), "2 Ko")

    def test_folder_validation_is_english_without_changing_input(self):
        set_language("en")
        dialog = self.keep(DocumentFolderDialog(self.ctx))
        dialog.save()
        self.assertEqual(dialog.error.text(), "The folder name must be between 1 and 100 characters long.")
        with self.assertRaisesRegex(ValueError, "The file “Introuvable.txt” could not be found"):
            self.ctx.db.import_document(Path(self.temp.name) / "Introuvable.txt", "maths", "cours")

    def test_personal_notes_translate_controls_and_preserve_content(self):
        self.ctx.db.remember("Méthode de travail", "Relire les exemples corrigés")
        set_language("en")
        page = self.keep(MemoryPage(self.ctx))
        self.assertEqual(page.new_button.text(), "+ New note")
        page.memory_list.setCurrentRow(0)
        self.assertEqual(page.key_input.text(), "Méthode de travail")
        self.assertEqual(page.value_input.toPlainText(), "Relire les exemples corrigés")
        page.save_memory()
        self.assertEqual(self.ctx.db.memories()["Méthode de travail"], "Relire les exemples corrigés")
        self.assertEqual(page.feedback.text(), "Personal note saved.")
        page.new_memory()
        with patch("mpsi_desktop.memory.show_error") as show_error:
            page.save_memory()
        self.assertEqual(show_error.call_args.args[1:], ("Incomplete note", "Add a title and some content before saving."))

    def test_focus_dialogs_translate_review_and_keep_session_title(self):
        set_language("en")
        setup = self.keep(FocusSetupDialog(self.ctx))
        self.assertEqual(setup.windowTitle(), "Study session")
        self.assertEqual(setup.start_button.text(), "Start")
        self.assertIn("nothing is added", setup.hint.text())
        review = self.keep(FocusReviewDialog(self.ctx, ReviewSession()))
        self.assertEqual(review.windowTitle(), "Review your study session")
        self.assertEqual(review.title.text(), "Réviser les suites")
        self.assertEqual(review.table.horizontalHeaderItem(0).text(), "Start")
        self.assertIn("to save", review.total.text())
        self.assertEqual(review.table.cellWidget(0, 0).accessibleName(), "Period 1 Start")

    def test_storage_and_session_errors_use_language_at_validation_time(self):
        for code, expected in (("fr", "Une matière est invalide."), ("en", "A subject is invalid.")):
            set_language(code)
            with self.assertRaisesRegex(ValueError, expected):
                validate_subjects([None])
        set_language("en")
        with self.assertRaisesRegex(ValueError, "The draft session is invalid"):
            validate_focus_session("invalid")
        subject = self.keep(SubjectDialog(self.ctx))
        self.assertEqual(subject.windowTitle(), "Add a subject")
        subject.name.setText("Mon cours en français")
        subject.save()
        self.assertIn("Mon cours en français", self.ctx.db.subject_labels().values())

    def test_subjects_matching_translatable_words_remain_user_content(self):
        self.ctx.db.set_setting("desktop_subjects", [
            dict(id="maths", name="Travail autonome", color="#0071E3", active=True),
        ])
        set_language("en")
        self.assertEqual(self.ctx.db.category_labels()["maths"], "Travail autonome")
        self.assertEqual(self.ctx.db.category_labels()["permanence"], "Independent study")
        setup = self.keep(FocusSetupDialog(self.ctx))
        self.assertEqual(setup.category.itemText(setup.category.findData("maths")), "Travail autonome")

    def test_new_timetable_titles_use_english_fallback_and_preserve_given_titles(self):
        set_language("en")
        timetable = {"semesters": {"S1": [
            dict(id="free", weekday=0, start="08:00", end="09:00", category="permanence", title=""),
            dict(id="custom", weekday=0, start="09:00", end="10:00", category="permanence", title="Mon temps personnel"),
        ], "S2": []}}
        saved = self.ctx.db.save_setup(self.ctx.db.get_subjects(), timetable)
        self.assertEqual(saved["semesters"]["S1"][0]["title"], "Independent study")
        self.assertEqual(saved["semesters"]["S1"][1]["title"], "Mon temps personnel")

    def test_legacy_migration_localises_generated_description_and_keeps_original_text(self):
        set_language("en")
        self.ctx.db._insert("INSERT INTO summaries(title,text,mode) VALUES (?,?,?)", ("", "Texte d’origine", "off"))
        self.ctx.db.init_document_tables()
        document = self.ctx.db.list_documents()[0]
        self.assertEqual(document["title"], "Legacy note")
        self.assertEqual(document["description"], "Note kept from the previous app. The original source file was not stored.")
        self.assertEqual(self.ctx.db.document_path(document["id"]).read_text(encoding="utf-8"), "Texte d’origine")


if __name__ == "__main__":
    unittest.main()
