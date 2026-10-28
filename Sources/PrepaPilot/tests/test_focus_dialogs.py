"""Focus dialogs preserve pauses, draft edits and explicit journal consent."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
from datetime import datetime, timedelta
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QDateTime, QEvent, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from mpsi_desktop.context import AppContext
from mpsi_desktop.focus_dialogs import FocusReviewDialog, FocusSetupDialog
from mpsi_desktop.focus_session import FocusSession
from mpsi_desktop.theme import apply_theme


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
APP.setStyle("Fusion")
for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)


class ReviewSession:
    """Dialog boundary fake; atomic storage and rounding have engine tests."""

    def __init__(self, category="maths", entries=None):
        self.state = dict(category=category, title="Suites et séries", status="review", interrupted=False)
        self.entries = entries if entries is not None else [
            dict(start_at="2026-09-20T18:01", end_at="2026-09-20T18:11"),
            dict(start_at="2026-09-20T18:20", end_at="2026-09-20T18:32"),
        ]
        self.save_calls = []
        self.update_calls = []
        self.discard_calls = 0
        self.failure = None

    def review_entries(self):
        return copy.deepcopy(self.entries)

    def save(self, **values):
        self.save_calls.append(copy.deepcopy(values))
        if self.failure:
            raise ValueError(self.failure)
        return [41 + index for index in range(len(values["segments"]))]

    def update_review(self, **values):
        self.update_calls.append(copy.deepcopy(values))
        self.state.update(category=values["category"], title=values["title"])
        self.entries = copy.deepcopy(values["segments"])

    def discard(self):
        self.discard_calls += 1


class FocusDialogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(self.temp.name)
        self.ctx.db.set_setting("desktop_reduced_motion", True)
        APP.setProperty("reducedMotion", True)
        apply_theme(APP, "light")
        self.dialogs = []
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, error, tb: self.errors.append((kind.__name__, str(error)))

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.hide()
            dialog.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def setup_dialog(self, **kwargs):
        dialog = FocusSetupDialog(self.ctx, **kwargs)
        self.dialogs.append(dialog)
        return dialog

    def review_dialog(self, session=None):
        dialog = FocusReviewDialog(self.ctx, session or ReviewSession())
        self.dialogs.append(dialog)
        return dialog

    def completed_session(self, category="maths"):
        clock = [datetime(2026, 9, 20, 18, 0, 20), 0.0]
        session = FocusSession(self.ctx.db, now=lambda: clock[0], monotonic=lambda: clock[1])
        session.start(category=category, minutes=25, title="Suites")
        for index in range(130):
            clock[0] += timedelta(seconds=1)
            clock[1] += 1
            session.tick()
        session.pause()
        clock[0] += timedelta(seconds=90)
        clock[1] += 90
        session.resume()
        for index in range(125):
            clock[0] += timedelta(seconds=1)
            clock[1] += 1
            session.tick()
        session.finish()
        return session, clock

    def test_setup_free_timer_default_and_active_custom_subjects(self):
        self.ctx.db.set_setting("desktop_subjects", [
            dict(id="maths", name="Droit civil", color="#0071E3", active=True),
            dict(id="physique", name="Archives", color="#8E44AD", active=False),
        ])
        dialog = self.setup_dialog()
        self.assertIsNone(dialog.category.currentData())
        self.assertEqual(dialog.minutes.value(), 25)
        self.assertEqual((dialog.minutes.minimum(), dialog.minutes.maximum()), (1, 240))
        self.assertEqual(dialog.category.findData("physique"), -1)
        self.assertIn("rien n’est ajouté", dialog.hint.text())
        self.assertIsNone(dialog.values)
        dialog.category.setCurrentIndex(dialog.category.findData("maths"))
        self.assertEqual(dialog.category.currentText(), "Droit civil")
        dialog.minutes.setValue(45)
        dialog.title.setText("  Préparer le cas pratique  ")
        dialog.start()
        self.assertEqual(dialog.values, dict(category="maths", minutes=45, title="Préparer le cas pratique"))
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.ctx.db._rows("SELECT * FROM time_entries"), [])

    def test_setup_keeps_free_timer_and_generic_study_when_no_subjects(self):
        self.ctx.db.set_setting("desktop_subjects", [])
        dialog = self.setup_dialog(default_minutes=50)
        self.assertEqual(dialog.category.count(), 2)
        dialog.start()
        self.assertIsNone(dialog.values["category"])
        self.assertEqual(dialog.values["minutes"], 50)
        generic = self.setup_dialog()
        generic.category.setCurrentIndex(generic.category.findData("permanence"))
        generic.start()
        self.assertEqual(generic.values["category"], "permanence")

    def test_review_keeps_pause_gaps_and_only_saves_once_after_edits(self):
        session = ReviewSession()
        dialog = self.review_dialog(session)
        self.assertEqual(dialog._entries(), session.entries)
        self.assertIn("22 min", dialog.total.text())
        dialog.table.cellWidget(1, 1).setDateTime(QDateTime.fromString("2026-09-20T18:30", Qt.DateFormat.ISODate))
        self.assertIn("20 min", dialog.total.text())
        dialog.title.setText(" Suites · exercices ")
        dialog.save()
        dialog.save()
        self.assertEqual(dialog.saved_ids, [41, 42])
        self.assertEqual(len(session.save_calls), 1)
        saved = session.save_calls[0]
        self.assertEqual(saved["title"], "Suites · exercices")
        self.assertEqual(saved["segments"][0]["end_at"], "2026-09-20T18:11")
        self.assertEqual(saved["segments"][1]["start_at"], "2026-09-20T18:20")
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_review_conflict_keeps_dialog_and_periods_for_retry(self):
        session = ReviewSession()
        session.failure = "La période chevauche une activité. Ajuste les horaires dans ce bilan."
        dialog = self.review_dialog(session)
        dialog.show()
        APP.processEvents()
        dialog.save()
        self.assertTrue(dialog.isVisible())
        self.assertTrue(dialog.error.isVisible())
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertEqual(dialog.saved_ids, [])
        self.assertEqual(dialog._entries(), session.entries)
        session.failure = None
        dialog.table.selectRow(0)
        dialog.remove_period()
        dialog.save()
        self.assertEqual(dialog.saved_ids, [41])
        self.assertEqual(session.save_calls[-1]["segments"], [session.entries[1]])

    def test_later_and_escape_preserve_review_edits_without_saving(self):
        session = ReviewSession()
        dialog = self.review_dialog(session)
        dialog.show()
        APP.processEvents()
        dialog.title.setText("À poursuivre demain")
        dialog.category.setCurrentIndex(dialog.category.findData("anglais"))
        dialog.table.cellWidget(0, 0).setDateTime(QDateTime.fromString("2026-09-20T18:02", Qt.DateFormat.ISODate))
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertFalse(dialog.isVisible())
        self.assertEqual(session.save_calls, [])
        self.assertEqual(session.discard_calls, 0)
        reopened = self.review_dialog(session)
        self.assertEqual(reopened.title.text(), "À poursuivre demain")
        self.assertEqual(reopened.category.currentData(), "anglais")
        self.assertEqual(reopened._entries()[0]["start_at"], "2026-09-20T18:02")

    def test_discard_needs_confirmation_and_never_saves(self):
        session = ReviewSession()
        dialog = self.review_dialog(session)
        with patch("mpsi_desktop.focus_dialogs.confirm", return_value=False):
            dialog.discard()
        self.assertFalse(dialog.discarded)
        self.assertEqual(session.discard_calls, 0)
        with patch("mpsi_desktop.focus_dialogs.confirm", return_value=True):
            dialog.discard()
            dialog.discard()
        self.assertTrue(dialog.discarded)
        self.assertEqual(session.discard_calls, 1)
        self.assertEqual(session.save_calls, [])
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_free_review_requires_subject_and_empty_periods_disable_save(self):
        dialog = self.review_dialog(ReviewSession(category=None))
        self.assertFalse(dialog.save_button.isEnabled())
        dialog.category.setCurrentIndex(dialog.category.findData("maths"))
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.table.cellWidget(0, 1).setDateTime(dialog.table.cellWidget(0, 0).dateTime())
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertEqual(dialog.table.item(0, 2).text(), "À corriger")
        empty = self.review_dialog(ReviewSession(entries=[]))
        self.assertFalse(empty.save_button.isEnabled())
        self.assertFalse(empty.remove_button.isEnabled())
        self.assertIn("minutes entières", empty.rounding_hint.text())

    def test_real_engine_conflict_is_atomic_and_retried_after_period_removal(self):
        session, clock = self.completed_session()
        existing = self.ctx.db.add_time_entry("maths", "2026-09-20T18:01", "2026-09-20T18:02", "Déjà enregistré")
        dialog = self.review_dialog(session)
        dialog.save()
        self.assertEqual(dialog.saved_ids, [])
        self.assertIn("Plus tard", dialog.error.text())
        self.assertEqual([row["id"] for row in self.ctx.db._rows("SELECT id FROM time_entries")], [existing])
        dialog.table.selectRow(0)
        dialog.remove_period()
        dialog.save()
        dialog.save()
        entries = self.ctx.db._rows("SELECT * FROM time_entries ORDER BY start_at")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["id"], existing)
        self.assertEqual(entries[1]["start_at"], "2026-09-20T18:04")
        self.assertEqual(entries[1]["end_at"], "2026-09-20T18:06")
        self.assertEqual(session.status, "saved")

    def test_real_engine_later_survives_reload_and_free_timer_can_be_recorded(self):
        session, clock = self.completed_session(category=None)
        dialog = self.review_dialog(session)
        self.assertFalse(dialog.save_button.isEnabled())
        dialog.category.setCurrentIndex(dialog.category.findData("anglais"))
        dialog.title.setText("Révision vocabulaire")
        dialog.table.selectRow(0)
        dialog.remove_period()
        dialog.reject()
        recovered = FocusSession(self.ctx.db, now=lambda: clock[0], monotonic=lambda: clock[1])
        reopened = self.review_dialog(recovered)
        self.assertEqual(reopened.title.text(), "Révision vocabulaire")
        self.assertEqual(reopened.category.currentData(), "anglais")
        self.assertEqual(reopened.table.rowCount(), 1)
        self.assertEqual(self.ctx.db._rows("SELECT * FROM time_entries"), [])
        reopened.save()
        entry = self.ctx.db._rows("SELECT * FROM time_entries")[0]
        self.assertEqual(entry["category"], "anglais")
        self.assertEqual(entry["title"], "Révision vocabulaire")

    def test_dialog_controls_fit_small_screen_in_both_themes_with_error(self):
        session = ReviewSession()
        session.state["interrupted"] = True
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                apply_theme(APP, theme)
                setup = self.setup_dialog()
                setup.show()
                review = self.review_dialog(session)
                review._show_error("Une activité occupe déjà cette période. Modifie les heures ci-dessus, ou corrige l’activité dans Gestion du temps, puis réessaie.")
                review.show()
                APP.processEvents()
                for dialog in (setup, review):
                    self.assertLessEqual(dialog.width(), 1000)
                    self.assertLessEqual(dialog.height(), 640)
                self.assertTrue(review.rect().contains(review.save_button.geometry()))
                self.assertTrue(review.rect().contains(review.discard_button.geometry()))
                self.assertGreaterEqual(review.error.height(), review.error.heightForWidth(review.error.width()))
                self.assertEqual(review.table.horizontalScrollBar().maximum(), 0)
                editor = review.table.cellWidget(0, 0)
                self.assertGreaterEqual(editor.findChild(QLineEdit).height(), editor.fontMetrics().height())
                setup.hide()
                review.hide()


if __name__ == "__main__":
    unittest.main()
