"""Fullscreen controls, maximize conversion and safe return to windowed mode."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from mpsi_desktop.context import AppContext
from mpsi_desktop.window import MainWindow

APP=QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class FullScreenTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.ctx=AppContext(Path(self.temp.name)/'data')
        self.ctx.db.set_setting('desktop_reduced_motion',True)
        self.errors=[]
        self.previous_hook=sys.excepthook
        sys.excepthook=lambda kind,value,tb:self.errors.append((kind.__name__,str(value)))
        self.window=MainWindow(self.ctx,show_welcome=False)
        self.window.show()
        self.window.activateWindow()
        QTest.qWait(20)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None,QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        sys.excepthook=self.previous_hook
        self.assertEqual(self.errors,[])

    def test_button_restores_original_window_geometry(self):
        original=self.window.geometry()
        self.assertFalse(self.window.exit_fullscreen_shortcut.isEnabled())
        QTest.mouseClick(self.window.fullscreen_button,Qt.LeftButton)
        APP.processEvents()
        self.assertTrue(self.window.isFullScreen())
        self.assertTrue(self.window.fullscreen_button.isChecked())
        self.assertTrue(self.window.exit_fullscreen_shortcut.isEnabled())
        self.assertIn('Quitter',self.window.fullscreen_button.toolTip())
        QTest.mouseClick(self.window.fullscreen_button,Qt.LeftButton)
        APP.processEvents()
        self.assertFalse(self.window.isFullScreen())
        self.assertFalse(self.window.isMaximized())
        self.assertEqual(self.window.geometry(),original)
        self.assertFalse(self.window.exit_fullscreen_shortcut.isEnabled())

    def test_f11_and_escape_from_focused_input(self):
        self.window.navigate('settings',animate=False)
        field=self.window.pages['settings'].name
        field.setFocus()
        QTest.keyClick(field,Qt.Key_F11)
        APP.processEvents()
        self.assertTrue(self.window.isFullScreen())
        self.ctx.set_theme('dark')
        self.assertTrue(self.window.fullscreen_button.isChecked())
        QTest.keyClick(field,Qt.Key_Escape)
        APP.processEvents()
        self.assertFalse(self.window.isFullScreen())
        QTest.keyClick(field,Qt.Key_F11)
        APP.processEvents()
        QTest.keyClick(field,Qt.Key_F11)
        APP.processEvents()
        self.assertFalse(self.window.isFullScreen())

    def test_windows_maximize_uses_fullscreen_and_preserves_normal_geometry(self):
        original=self.window.geometry()
        self.window.showMaximized()
        APP.processEvents()
        APP.processEvents()
        self.assertTrue(self.window.isFullScreen())
        self.window.exit_fullscreen()
        APP.processEvents()
        self.assertFalse(self.window.isMaximized())
        self.assertEqual(self.window.geometry(),original)

    def test_escape_closes_modal_dialog_before_leaving_fullscreen(self):
        self.window.enter_fullscreen()
        dialog=QDialog(self.window)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.show()
        dialog.activateWindow()
        QTest.qWait(20)
        QTest.keyClick(dialog,Qt.Key_Escape)
        APP.processEvents()
        self.assertFalse(dialog.isVisible())
        self.assertTrue(self.window.isFullScreen())
        dialog.deleteLater()

    def test_tray_restore_keeps_fullscreen_after_minimizing(self):
        self.window.enter_fullscreen()
        self.window.showMinimized()
        APP.processEvents()
        self.window.restore_window()
        APP.processEvents()
        self.assertTrue(self.window.isFullScreen())
        self.assertFalse(self.window.isMinimized())

    def test_close_cancels_pending_maximize_conversion(self):
        self.window.showMaximized()
        self.window.close()
        APP.processEvents()
        self.assertFalse(self.window.maximize_timer.isActive())
        self.assertFalse(self.window.isFullScreen())


if __name__=='__main__':unittest.main()
