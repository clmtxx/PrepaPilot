"""Changing language keeps the visible document and the user's working context."""
from datetime import date
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QDate, QEvent, Qt
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from mpsi_desktop.context import AppContext
from mpsi_desktop.i18n import set_language
from mpsi_desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class LanguageStateTests(unittest.TestCase):
    def setUp(self):
        set_language("fr")
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ctx = AppContext(self.root / "data")
        self.ctx.db.set_setting("desktop_reduced_motion", True)
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            if isValid(window):
                window.close()
                window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        set_language("fr")

    def window(self):
        window = MainWindow(self.ctx, show_welcome=False)
        self.windows.append(window)
        window.show()
        APP.processEvents()
        return window

    def switch(self, code):
        self.ctx.set_language(code)
        APP.processEvents()
        replacement = APP._prepapilot_window
        self.windows.append(replacement)
        return replacement

    def add_document(self, filename, content, title):
        path = self.root / filename
        path.write_bytes(content)
        return self.ctx.db.import_document(path, "maths", "cours", title=title)

    def select_document(self, page, identity):
        for index in range(page.documents.count()):
            item = page.documents.item(index)
            if item.data(Qt.UserRole) == identity:
                page.documents.setCurrentItem(item)
                return
        self.fail("The test document was not listed")

    def test_document_selection_and_preview_stay_together_in_both_languages(self):
        target = self.add_document("alpha.txt", b"TEXT FROM ALPHA", "Alpha")
        self.add_document("zeta.txt", b"TEXT FROM ZETA", "Zeta")
        old = self.window()
        self.select_document(old.pages["documents"], target)
        old.navigate("documents", animate=False)
        self.assertEqual(old.pages["documents"].reader.toPlainText(), "TEXT FROM ALPHA")
        for code in ("en", "fr"):
            new = self.switch(code)
            page = new.pages["documents"]
            self.assertEqual(new.current_key, "documents")
            self.assertEqual(page._selected_id, target)
            self.assertEqual(page.selected_document_ids(), [target])
            self.assertEqual(page.title_label.text(), "Alpha")
            self.assertEqual(page.reader.toPlainText(), "TEXT FROM ALPHA")

    def test_read_only_document_preview_is_regenerated_in_english(self):
        target = self.add_document("sample.pdf", b"%PDF-1.4\n", "Sample handout")
        old = self.window()
        self.select_document(old.pages["documents"], target)
        self.assertIn("Ce document est conservé", old.pages["documents"].reader.toPlainText())
        new = self.switch("en")
        reader = new.pages["documents"].reader
        self.assertTrue(reader.isReadOnly())
        self.assertEqual(reader.toPlainText(),
                         "This document is stored in its original format.\n\nOpen it to view it in your usual app.")

    def test_dates_period_and_chart_modes_survive_language_refresh(self):
        old = self.window()
        journal = old.pages["time"]
        journal.day.setDate(QDate(2026, 1, 15))
        journal.period.setCurrentIndex(journal.period.findData("custom"))
        journal.from_date.setDate(QDate(2026, 1, 1))
        journal.to_date.setDate(QDate(2026, 1, 31))
        progress = old.pages["progression"]
        progress.set_mode("month")
        progress.date_picker.setDate(QDate(2026, 1, 15))
        old.pages["notes"].set_chart_mode("ranking")
        new = self.switch("en")
        journal = new.pages["time"]
        self.assertEqual(journal.selected_day(), "2026-01-15")
        self.assertEqual(journal.period.currentData(), "custom")
        self.assertEqual(journal.from_date.date(), QDate(2026, 1, 1))
        self.assertEqual(journal.to_date.date(), QDate(2026, 1, 31))
        self.assertIn("Thursday", journal.journal_title.text())
        self.assertEqual(new.pages["progression"].mode, "month")
        self.assertEqual(new.pages["progression"].anchor, date(2026, 1, 15))
        self.assertEqual(new.pages["progression"].date_picker.date(), QDate(2026, 1, 15))
        self.assertEqual(new.pages["notes"].chart.mode, "ranking")

    def test_search_scope_and_unsaved_checkbox_choice_are_preserved(self):
        old = self.window()
        old.pages["documents"].search_everywhere.setChecked(False)
        old.pages["settings"].motion.setChecked(False)
        self.assertTrue(self.ctx.db.get_setting("desktop_reduced_motion"))
        new = self.switch("en")
        self.assertFalse(new.pages["documents"].search_everywhere.isChecked())
        self.assertFalse(new.pages["settings"].motion.isChecked())
        self.assertTrue(self.ctx.db.get_setting("desktop_reduced_motion"))


if __name__ == "__main__":
    unittest.main()
