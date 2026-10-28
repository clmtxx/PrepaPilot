"""Exercise personal subjects and free evaluation types through the Notes UI."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
import sqlite3
import sys
import tempfile
import traceback
import unittest
import uuid
from unittest.mock import patch

from PySide6.QtCore import QDate, QEvent, Qt
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from mpsi_desktop.context import AppContext
from mpsi_desktop.notes import GradeDialog, NotesPage, SubjectDialog, kind_color
from mpsi_desktop.theme import apply_theme


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
APP.setStyle("Fusion")
for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "segoeuil.ttf"):
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)


def subject(name, color="#0071E3", active=True, identity=None):
    return dict(id=identity or "subject_" + uuid.uuid4().hex, name=name, color=color, active=active)


class CustomNotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(self.temp.name)
        self.ctx.db.set_setting("desktop_reduced_motion", True)
        self.biology = subject("Biologie", "#287D5B")
        self.law = subject("Droit", "#7437A0")
        self.english = subject("Anglais", identity="anglais")
        self.ctx.db.set_setting("desktop_subjects", [self.biology, self.law, self.english])
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append((str(value), "".join(traceback.format_tb(tb))))
        apply_theme(APP, "light")
        self.page = NotesPage(self.ctx)
        self.page.resize(940, 1000)
        self.page.show()
        APP.processEvents()

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        sys.excepthook = self.old_hook
        self.assertEqual(self.errors, [])

    def create_grade(self, identity=None, kind="projet", label="Travail de groupe"):
        return self.ctx.db.add_grade(identity or self.biology["id"], kind, 16, 20, date.today().isoformat(), label)

    def test_empty_profile_can_create_its_first_subject_directly(self):
        self.ctx.db.set_setting("desktop_subjects", [])
        self.ctx.mark_changed()
        self.assertTrue(self.page.empty_profile.isVisible())
        self.assertFalse(self.page.add_button.isEnabled())

        def create(dialog):
            dialog.name.setText("Sciences politiques")
            dialog.color = "#A24464"
            dialog.save()
            dialog.save()
            return dialog.result()

        with patch.object(SubjectDialog, "exec", new=create):
            QTest.mouseClick(self.page.empty_add_button, Qt.MouseButton.LeftButton)
        records = self.ctx.db.get_subjects()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["name"], "Sciences politiques")
        self.assertEqual(records[0]["color"], "#A24464")
        self.assertEqual(self.page.subject, records[0]["id"])
        self.assertTrue(self.page.add_button.isEnabled())
        self.assertFalse(self.page.empty_profile.isVisible())

    def test_rename_and_color_update_preserve_identity_and_existing_notes(self):
        grade_id = self.create_grade()
        self.page.set_subject(self.biology["id"])

        def rename(dialog):
            dialog.name.setText("Biologie cellulaire")
            dialog.color = "#8C3B6F"
            dialog.save()
            return dialog.result()

        with patch.object(SubjectDialog, "exec", new=rename):
            QTest.mouseClick(self.page.subject_edit_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.page.subject_selector.currentText(), "Biologie cellulaire")
        self.assertEqual(self.ctx.db.category_color(self.biology["id"]), "#8C3B6F")
        self.assertEqual(self.page.rows[0]["id"], grade_id)
        self.assertEqual(self.page.rows[0]["subject"], self.biology["id"])
        icon = self.page.subject_selector.itemIcon(self.page.subject_selector.currentIndex()).pixmap(18, 18)
        self.assertEqual(icon.toImage().pixelColor(9, 9).name().upper(), "#8C3B6F")

    def test_add_note_button_saves_free_type_title_and_selects_new_record(self):
        self.page.set_subject(self.law["id"])

        def enter(dialog):
            self.assertEqual(dialog.subject.currentData(), self.law["id"])
            dialog.kind.setEditText("Commentaire d’arrêt")
            dialog.label.setText("<Décision> du Conseil constitutionnel")
            dialog.score.setValue(7.5)
            dialog.scale.setValue(10)
            dialog.coefficient.setValue(2)
            dialog.save()
            dialog.save()
            return dialog.result()

        with patch.object(GradeDialog, "exec", new=enter):
            QTest.mouseClick(self.page.add_button, Qt.MouseButton.LeftButton)
        row = self.page.selected_grade()
        self.assertIsNotNone(row)
        self.assertEqual(row["kind"], "Commentaire d’arrêt")
        self.assertEqual(row["label"], "<Décision> du Conseil constitutionnel")
        self.assertEqual(row["normalized_score"], 15)
        self.assertEqual(len(self.ctx.db.list_grades()), 1)
        self.assertEqual(self.page.table.item(0, 1).text(), "Commentaire d’arrêt")
        self.assertIn("Commentaire d’arrêt : 15/20", self.page.details_label.text())

    def test_english_has_every_type_and_subject_changes_keep_typed_choice(self):
        dialog = GradeDialog(self.ctx, subject="anglais", parent=self.page)
        keys = {dialog.kind.itemData(index) for index in range(dialog.kind.count())}
        self.assertTrue({"cours", "ds", "colle", "projet", "tp", "autre"}.issubset(keys))
        self.assertTrue(dialog.kind.isEditable())
        self.assertTrue(dialog.kind.isEnabled())
        dialog.kind.setEditText("Compréhension écrite")
        dialog.subject.setCurrentIndex(dialog.subject.findData(self.biology["id"]))
        dialog.subject.setCurrentIndex(dialog.subject.findData("anglais"))
        self.assertEqual(dialog.kind.currentText(), "Compréhension écrite")
        dialog.score.setValue(14)
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.ctx.db.list_grades("anglais")[0]["kind"], "Compréhension écrite")

    def test_grade_dialog_actions_fit_small_screen_with_long_labels(self):
        self.create_grade(kind="Exposé en groupe et discussion contradictoire",
                          label="Protection des droits fondamentaux et contrôle constitutionnel")
        dialog = GradeDialog(self.ctx, grade=self.ctx.db.list_grades()[0], parent=self.page)
        dialog.show()
        APP.processEvents()
        self.assertLessEqual(dialog.height(), 640)
        self.assertLessEqual(dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()).y(), dialog.height())
        self.assertEqual(dialog.label.cursorPosition(), 0)
        self.assertTrue(dialog.save_button.isVisible())

    def test_archived_subject_with_notes_remains_editable_but_not_offered_for_new_notes(self):
        self.create_grade(kind="Mémoire")
        subjects = self.ctx.db.get_subjects()
        subjects[0]["active"] = False
        self.ctx.db.save_subjects(subjects)
        self.page.set_subject(self.biology["id"])
        self.assertIn("archivée", self.page.subject_selector.currentText())
        current = self.page.rows[0]
        edit = GradeDialog(self.ctx, grade=current, parent=self.page)
        self.assertEqual(edit.subject.currentData(), self.biology["id"])
        edit.label.setText("Mémoire corrigé")
        edit.save()
        self.assertEqual(edit.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.ctx.db.list_grades()[0]["label"], "Mémoire corrigé")
        create = GradeDialog(self.ctx, subject=self.biology["id"], parent=self.page)
        self.assertEqual(create.subject.findData(self.biology["id"]), -1)
        self.assertIsNotNone(create.subject.currentData())

    def test_archived_subject_without_notes_is_not_a_notes_choice(self):
        subjects = self.ctx.db.get_subjects()
        subjects[0]["active"] = False
        self.ctx.db.save_subjects(subjects)
        self.ctx.mark_changed()
        self.assertEqual(self.page.subject_selector.findData(self.biology["id"]), -1)
        self.assertEqual(self.page.subject_selector.count(), 2)

    def test_many_subjects_and_long_types_do_not_expand_page_width(self):
        subjects = [subject(f"Matière {index:02d} · " + "Un intitulé détaillé " * 2) for index in range(80)]
        self.ctx.db.set_setting("desktop_subjects", subjects)
        for index in range(10):
            self.create_grade(subjects[-1]["id"], f"Évaluation {index} " + "x" * 42)
        self.page.set_subject(subjects[-1]["id"])
        self.page.resize(940, 1100)
        APP.processEvents()
        self.assertEqual(self.page.width(), 940)
        self.assertLessEqual(self.page.minimumSizeHint().width(), 940)
        self.assertEqual(self.page.subject_selector.count(), 80)
        self.assertGreater(self.page.legend_scroll.horizontalScrollBar().maximum(), 0)
        self.assertEqual(self.page.table.columnWidth(1), 155)
        self.page.grab()

    def test_custom_types_are_all_drawn_and_have_stable_theme_colors(self):
        for kind in ("Projet final", "Quiz de lecture", "TP", "ds"):
            self.create_grade(kind=kind)
        self.page.set_subject(self.biology["id"])
        self.page.grab()
        self.assertEqual(len(self.page.chart._hit_points), 4)
        labels = [item.text() for item in self.page.legend.parentWidget().findChildren(QLabel)]
        self.assertTrue(any("Projet final" in text for text in labels))
        first = kind_color("Projet final", "light")
        self.ctx.set_theme("dark")
        self.page.grab()
        self.ctx.set_theme("light")
        self.assertEqual(first, kind_color("Projet final", "light"))
        self.assertTrue(QColor(kind_color("Quiz de lecture", "dark")).isValid())
        self.assertNotEqual(kind_color("Projet final", "light"), kind_color("Projet final", "dark"))

    def test_empty_type_rejected_and_persistence_error_can_be_retried(self):
        notices = []
        self.ctx.notice.connect(notices.append)
        dialog = GradeDialog(self.ctx, subject=self.biology["id"], parent=self.page)
        dialog.kind.setEditText("   ")
        dialog.save()
        self.assertEqual(self.ctx.db.list_grades(), [])
        self.assertEqual(notices, [])
        dialog.kind.setEditText("Présentation")
        with patch.object(self.ctx.db, "add_grade", side_effect=sqlite3.OperationalError("Occupé")):
            dialog.save()
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertEqual(notices, [])
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(notices), 1)

    def test_subject_duplicate_name_error_keeps_dialog_retryable(self):
        dialog = SubjectDialog(self.ctx, parent=self.page)
        dialog.name.setText("Biologie")
        dialog.save()
        self.assertIsNone(dialog.saved_id)
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertEqual(len(self.ctx.db.get_subjects()), 3)
        dialog.name.setText("Économie")
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(self.ctx.db.get_subjects()), 4)

    def test_saved_grade_moved_to_another_subject_is_selected_and_can_be_deleted(self):
        self.create_grade(kind="Soutenance")
        self.page.set_subject(self.biology["id"])
        self.page.table.selectRow(0)

        def move(dialog):
            dialog.subject.setCurrentIndex(dialog.subject.findData(self.law["id"]))
            dialog.save()
            return dialog.result()

        with patch.object(GradeDialog, "exec", new=move):
            QTest.mouseClick(self.page.edit_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.page.subject, self.law["id"])
        self.assertEqual(self.page.selected_grade()["kind"], "Soutenance")
        with patch("mpsi_desktop.notes.confirm", return_value=True):
            QTest.mouseClick(self.page.delete_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.ctx.db.list_grades(), [])
        self.assertIsNone(self.page.selected_grade())


if __name__ == "__main__":
    unittest.main()
