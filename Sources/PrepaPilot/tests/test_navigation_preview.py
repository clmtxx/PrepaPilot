"""Hover previews must remain passive and preserve all application state."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QPixmap, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractScrollArea, QDialog, QGraphicsEffect

from mpsi_desktop.context import AppContext
from mpsi_desktop.window import MainWindow
from mpsi_desktop.focus_session import FocusSession


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class NavigationPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append(f'{kind.__name__}: {value}')
        self.window = MainWindow(self.ctx, show_welcome=False)
        self.window.resize(1280, 800)
        self.preview = self.window.navigation_preview
        self.window.show()
        self.window.activateWindow()
        APP.processEvents()
        self.leave_navigation()

    def tearDown(self):
        self.preview.shutdown()
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def leave_navigation(self):
        QTest.mouseMove(self.window.central, QPoint(4, self.window.central.height() - 4))
        APP.processEvents()

    def hover(self, key):
        self.leave_navigation()
        button = self.window.nav[key][0]
        QTest.mouseMove(button, button.rect().center())
        APP.processEvents()

    def open_preview(self, key='notes'):
        self.hover(key)
        self.assertTrue(self.preview.timer.isActive())
        # Other tests exercise the real 550 ms deadline; make state checks quick.
        self.preview.timer.stop()
        self.preview._show_preview()
        APP.processEvents()
        self.assertTrue(self.preview.popup.isVisible())

    def scroll_values(self):
        return [(area, area.horizontalScrollBar().value(), area.verticalScrollBar().value())
                for area in self.window.findChildren(QAbstractScrollArea)]

    def test_delay_and_leave_cancel_without_opening_active_tab(self):
        self.hover('home')
        self.assertFalse(self.preview.timer.isActive())
        self.hover('notes')
        self.assertEqual(self.preview.timer.interval(), 550)
        QTest.qWait(490)
        self.assertFalse(self.preview.popup.isVisible())
        QTest.qWait(90)
        self.assertTrue(self.preview.popup.isVisible())
        self.leave_navigation()
        self.assertFalse(self.preview.popup.isVisible())
        self.hover('documents')
        self.leave_navigation()
        QTest.qWait(570)
        self.assertFalse(self.preview.popup.isVisible())

    def test_hidden_page_capture_preserves_scroll_focus_values_and_database(self):
        # Include a scroll offset retained by a page that was previously visited.
        self.window.navigate('settings', animate=False)
        APP.processEvents()
        self.window.wrappers['settings'].verticalScrollBar().setValue(80)
        self.window.navigate('home', animate=False)
        APP.processEvents()
        before_scroll = self.scroll_values()
        focus = APP.focusWidget()
        before_stack = self.window.stack.currentIndex()
        before_changes = self.ctx.db._connection.total_changes
        before_tables = list(self.ctx.db._connection.iterdump())
        before_geometry = {key: page.geometry() for key, page in self.window.pages.items()}
        before_visibility = {key: page.isVisible() for key, page in self.window.pages.items()}
        with patch.object(self.window, 'navigate', side_effect=AssertionError('Preview must not navigate')):
            for key in self.window.pages:
                image = self.preview._thumbnail(key)
                self.assertFalse(image.isNull(), key)
                self.assertGreater(image.width(), 0)
        APP.processEvents()
        self.assertEqual(self.ctx.db._connection.total_changes, before_changes)
        self.assertEqual(list(self.ctx.db._connection.iterdump()), before_tables)
        self.assertEqual(self.scroll_values(), before_scroll)
        self.assertEqual(self.window.stack.currentIndex(), before_stack)
        self.assertIs(APP.focusWidget(), focus)
        self.assertEqual({key: page.geometry() for key, page in self.window.pages.items()}, before_geometry)
        self.assertEqual({key: page.isVisible() for key, page in self.window.pages.items()}, before_visibility)

    def test_card_is_passive_child_and_reduced_motion_is_static(self):
        focus = APP.focusWidget()
        self.open_preview()
        card = self.preview.popup
        self.assertIs(card.parentWidget(), self.window.central)
        self.assertFalse(card.isWindow())
        self.assertEqual(card.focusPolicy(), Qt.NoFocus)
        self.assertTrue(card.testAttribute(Qt.WA_TransparentForMouseEvents))
        self.assertTrue(card.testAttribute(Qt.WA_ShowWithoutActivating))
        self.assertIsNone(card.graphicsEffect())
        self.assertEqual(card.findChildren(QGraphicsEffect), [])
        self.assertIs(APP.focusWidget(), focus)
        self.assertEqual(self.preview.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(card.progress, 1)
        self.assertFalse(card.thumbnail.isNull())
        self.assertIn('Notes', card.accessibleName())

    def test_preview_image_is_current_when_existing_page_changes(self):
        page = self.window.pages['memory']
        self.window.navigate('memory', animate=False)
        APP.processEvents()
        # A preview follows the page's retained scroll position. Keep the input
        # in that visible crop instead of testing pixels outside the thumbnail.
        offset = page.key_input.mapTo(page, QPoint()).y() - 60
        self.window.wrappers['memory'].verticalScrollBar().setValue(max(0, offset))
        self.window.navigate('home', animate=False)
        APP.processEvents()
        page.key_input.setText('Avant')
        first = self.preview._thumbnail('memory').toImage()
        page.key_input.setText('Après : une idée mise à jour')
        second = self.preview._thumbnail('memory').toImage()
        self.assertNotEqual(first, second)
        self.assertEqual(page.key_input.text(), 'Après : une idée mise à jour')

    def test_repeated_hover_reuses_bounded_image_and_mutation_invalidates_cache(self):
        with patch.object(self.preview, '_thumbnail', wraps=self.preview._thumbnail) as capture:
            first = self.preview._cached_thumbnail('notes')
            second = self.preview._cached_thumbnail('notes')
            self.assertEqual(first.cacheKey(), second.cacheKey())
            self.assertEqual(capture.call_count, 1)
            self.assertLessEqual(first.width() * first.height(), 568 * 264)
            self.ctx.mark_changed()
            self.preview._cached_thumbnail('notes')
            self.assertEqual(capture.call_count, 2)
            self.ctx.set_theme('dark')
            self.preview._cached_thumbnail('notes')
            self.assertEqual(capture.call_count, 3)
        self.preview.shutdown()
        self.assertEqual(self.preview._cache, {})

    def test_extreme_display_bounds_intermediate_capture_before_downsampling(self):
        page = self.window.pages['notes']
        with patch.object(page, 'width', return_value=16000), \
                patch.object(page, 'height', return_value=9000), \
                patch('mpsi_desktop.navigation_preview.QPixmap', wraps=QPixmap) as allocations:
            image = self.preview._thumbnail('notes')
        self.assertFalse(image.isNull())
        self.assertLessEqual(image.width() * image.height(), 568 * 264)
        raster_size = allocations.call_args_list[0].args[0]
        self.assertLessEqual(raster_size.width() * raster_size.height(), self.preview.MAX_CAPTURE_PIXELS)

    def test_relief_and_glint_reuse_surface_through_entire_entrance(self):
        self.open_preview()
        card = self.preview.popup
        card._surface_key = None
        with patch.object(card, '_paint_surface', wraps=card._paint_surface) as compose:
            for progress in (0.1, 0.35, 0.7, 1.0):
                card.set_progress(progress)
                self.assertFalse(card.grab().isNull())
            self.assertEqual(compose.call_count, 1)
            card.accent = '#38A69B'
            card.grab()
            self.assertEqual(compose.call_count, 2)
        self.preview.shutdown()
        self.assertTrue(card._surface.isNull())
        self.assertTrue(card._glint.isNull())

    def test_navigation_discards_previous_page_preview_after_editing_draft(self):
        self.preview._cached_thumbnail('memory')
        self.window.navigate('memory', animate=False)
        self.window.pages['memory'].key_input.setText('Brouillon non enregistré')
        self.window.navigate('home', animate=False)
        self.assertNotIn('memory', self.preview._cache)
        self.assertEqual(self.window.pages['memory'].key_input.text(), 'Brouillon non enregistré')

    def test_live_timer_refreshes_preview_without_invalidating_unchanged_images(self):
        home = self.window.pages['home']
        clock = [datetime.now(), 100.0]
        home.focus_session = FocusSession(self.ctx.db, now=lambda: clock[0], monotonic=lambda: clock[1])
        home.focus_session.start(None, minutes=25)
        home._sync_focus()
        changes = []
        self.ctx.data_changed.connect(lambda: changes.append(True))
        with patch.object(self.preview, '_thumbnail', wraps=self.preview._thumbnail) as capture:
            first = self.preview._cached_thumbnail('home')
            self.assertEqual(first.cacheKey(), self.preview._cached_thumbnail('home').cacheKey())
            self.assertEqual(capture.call_count, 1)
            previous_seconds = home.dial.seconds
            clock[0] += timedelta(seconds=1)
            clock[1] += 1
            home.tick()
            self.assertLess(home.dial.seconds, previous_seconds)
            second = self.preview._cached_thumbnail('home')
            self.assertNotEqual(first.cacheKey(), second.cacheKey())
            self.assertEqual(capture.call_count, 2)
            self.assertEqual(second.cacheKey(), self.preview._cached_thumbnail('home').cacheKey())
            self.assertEqual(capture.call_count, 2)
        self.assertEqual(changes, [])

    def test_reduced_motion_immediately_stops_an_open_preview_animation(self):
        self.ctx.db.set_setting('desktop_reduced_motion', False)
        self.ctx.mark_changed()
        self.open_preview()
        self.assertEqual(self.preview.animation.state(), QAbstractAnimation.Running)
        APP.setProperty('reducedMotion', True)
        self.assertEqual(self.preview.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(self.preview.popup.progress, 1)
        self.assertTrue(self.preview.popup.isVisible())

    def test_click_keyboard_scroll_and_deactivation_close_preview(self):
        self.open_preview()
        QTest.mousePress(self.window.nav['notes'][0], Qt.LeftButton)
        self.assertFalse(self.preview.popup.isVisible())
        QTest.mouseRelease(self.window.nav['notes'][0], Qt.LeftButton)
        self.assertEqual(self.window.current_key, 'notes')
        self.window.navigate('home', animate=False)
        self.open_preview()
        QTest.keyClick(self.window.nav['home'][0], Qt.Key_Tab)
        self.assertFalse(self.preview.popup.isVisible())
        self.open_preview()
        viewport = self.window.wrappers['home'].viewport()
        wheel = QWheelEvent(QPointF(10, 10), QPointF(viewport.mapToGlobal(QPoint(10, 10))),
                            QPoint(), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                            Qt.NoScrollPhase, False)
        APP.sendEvent(viewport, wheel)
        self.assertFalse(self.preview.popup.isVisible())
        self.open_preview()
        APP.sendEvent(self.window, QEvent(QEvent.WindowDeactivate))
        self.assertFalse(self.preview.popup.isVisible())

    def test_modal_theme_data_and_resize_close_visible_or_pending_preview(self):
        self.open_preview()
        dialog = QDialog(self.window)
        dialog.setModal(True)
        dialog.show()
        APP.processEvents()
        self.assertFalse(self.preview.popup.isVisible())
        dialog.close()
        dialog.deleteLater()
        self.window.activateWindow()
        APP.processEvents()
        self.open_preview()
        self.ctx.set_theme('dark')
        self.assertFalse(self.preview.popup.isVisible())
        self.open_preview()
        self.assertEqual(self.preview.popup.theme, 'dark')
        self.ctx.mark_changed()
        self.assertFalse(self.preview.popup.isVisible())
        self.hover('documents')
        self.ctx.data_replaced.emit()
        self.assertFalse(self.preview.timer.isActive())
        self.open_preview()
        self.window.resize(self.window.width() + 40, self.window.height() + 20)
        APP.processEvents()
        self.assertFalse(self.preview.popup.isVisible())

    def test_card_stays_inside_window_at_both_navigation_edges(self):
        self.window.resize(1024, 680)
        APP.processEvents()
        for key in ('time', 'settings'):
            self.open_preview(key)
            self.assertEqual(self.preview.popup.width(), 320)
            self.assertTrue(self.window.central.rect().contains(self.preview.popup.geometry()))

    def test_shutdown_cancels_callbacks_and_disconnects_signals(self):
        self.ctx.db.set_setting('desktop_reduced_motion', False)
        self.ctx.mark_changed()
        self.open_preview()
        self.assertEqual(self.preview.animation.state(), QAbstractAnimation.Running)
        self.preview.shutdown()
        self.preview.shutdown()
        self.assertFalse(self.preview.popup.isVisible())
        self.assertFalse(self.preview.timer.isActive())
        self.assertEqual(self.preview.animation.state(), QAbstractAnimation.Stopped)
        self.hover('documents')
        self.ctx.mark_changed()
        self.assertFalse(self.preview.timer.isActive())


if __name__ == '__main__':
    unittest.main()
