"""Pointer light and parallax are reached through real native child controls."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import sys
import tempfile
import unittest

from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget
from mpsi_desktop.context import AppContext
from mpsi_desktop.page_chrome import AccentCard
from mpsi_desktop.page_figures import PageFigure
from mpsi_desktop.progression_visuals import axis_palette
from mpsi_desktop.theme import apply_theme
from mpsi_desktop.widgets import Card, button
from mpsi_desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


def finish_motion(widget):
    for animation in widget.findChildren(QAbstractAnimation):
        if animation.duration() > 0:
            animation.setCurrentTime(animation.duration())


def move(widget, x, y):
    QTest.mouseMove(widget, QPoint(round(x), round(y)))
    APP.processEvents()


class CardPointerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', False)
        self.old_motion = APP.property('reducedMotion')
        self.old_theme = APP.property('visualTheme')
        APP.setProperty('reducedMotion', False)
        apply_theme(APP, 'light')
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append((kind.__name__, str(value)))
        self.host = QWidget()
        self.host.resize(800, 620)
        layout = QVBoxLayout(self.host)
        layout.setContentsMargins(24, 24, 24, 24)
        self.card = AccentCard(self.ctx, 'documents')
        self.title = QLabel('A native text label spanning this card')
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.field = QLineEdit()
        self.action = button('Enregistrer')
        self.figure = PageFigure('documents')
        self.figure.setFixedSize(196, 144)
        self.card.bind_pointer_figure(self.figure)
        for control in (self.title, self.field, self.action, self.figure):
            self.card.body.addWidget(control)
        layout.addWidget(self.card)
        self.host.show()
        APP.processEvents()
        move(self.host, 2, 2)
        self.card._reset_motion()
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.close()
            window.deleteLater()
        self.host.close()
        self.host.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        APP.setProperty('reducedMotion', self.old_motion)
        APP.setProperty('visualTheme', self.old_theme)
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def assert_pointer_reaches_card(self, control):
        move(control, max(3, control.width() * .18), max(2, control.height() * .3))
        finish_motion(self.card)
        left_light, left_target = QPointF(self.card._light), QPointF(self.figure._target)
        move(control, control.width() * .82, control.height() * .7)
        finish_motion(self.card)
        self.assertGreater(self.card._light.x(), left_light.x() + .15)
        self.assertGreater(self.figure._target.x(), left_target.x() + .3)
        self.assertLessEqual(abs(self.figure._offset.x()), 1)
        self.assertLessEqual(abs(self.figure._offset.y()), 1)

    def test_native_label_button_and_editor_moves_reach_parent_light_and_figure(self):
        self.assertTrue(self.card.testAttribute(Qt.WA_Hover))
        for control in (self.title, self.action, self.field):
            with self.subTest(control=type(control).__name__):
                self.assert_pointer_reaches_card(control)

    def test_child_added_after_show_needs_no_new_event_filter_or_registration(self):
        late = QLabel('Added after the parent card was already visible')
        self.card.body.insertWidget(0, late)
        APP.processEvents()
        self.assert_pointer_reaches_card(late)

    def test_leaving_only_illustration_keeps_tracking_over_text_then_leaving_card_rests(self):
        move(self.figure, 15, 15)
        finish_motion(self.card)
        move(self.title, self.title.width() * .78, 5)
        finish_motion(self.card)
        self.assertNotEqual(self.figure._offset, QPointF())
        self.assertEqual(self.figure._offset, self.figure._target)
        move(self.host, 2, 2)
        finish_motion(self.card)
        self.assertEqual(self.figure._offset, QPointF())
        self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped
                            for animation in self.card.findChildren(QAbstractAnimation)))

    def test_native_clicks_editing_and_control_geometry_remain_unchanged(self):
        controls = (self.title, self.action, self.field, self.figure)
        bounds = {control: control.geometry() for control in controls}
        calls = []
        self.action.clicked.connect(lambda: calls.append(True))
        self.assert_pointer_reaches_card(self.action)
        QTest.mouseClick(self.action, Qt.LeftButton)
        QTest.mouseClick(self.field, Qt.LeftButton)
        QTest.keyClicks(self.field, 'un brouillon intact')
        self.assertEqual(calls, [True])
        self.assertEqual(self.field.text(), 'un brouillon intact')
        self.assertEqual({control: control.geometry() for control in controls}, bounds)

    def test_pointer_updates_reuse_card_and_illustration_cached_layers(self):
        self.card.grab()
        self.figure.grab()
        surface = self.card._surface.cacheKey()
        artwork = {key: value.cacheKey() for key, value in self.figure._artwork.layers.items()}
        self.assert_pointer_reaches_card(self.title)
        self.card.grab()
        self.figure.grab()
        self.assertEqual(self.card._surface.cacheKey(), surface)
        self.assertEqual({key: value.cacheKey() for key, value in self.figure._artwork.layers.items()}, artwork)

    def test_hide_disable_and_live_reduced_motion_cancel_and_block_new_tracking(self):
        for state in ('reduced', 'disabled', 'hidden'):
            with self.subTest(state=state):
                APP.setProperty('reducedMotion', False)
                self.card.setEnabled(True)
                self.card.show()
                APP.processEvents()
                move(self.title, self.title.width() * .8, 5)
                if state == 'reduced':
                    APP.setProperty('reducedMotion', True)
                elif state == 'disabled':
                    self.card.setEnabled(False)
                else:
                    self.card.hide()
                self.card._track_pointer(QPointF(15, 15))
                self.assertEqual(self.figure._offset, QPointF())
                self.assertEqual(self.figure._target, QPointF())
                self.assertEqual(self.card._light, QPointF(.82, .08))
                self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped
                                    for animation in self.card.findChildren(QAbstractAnimation)))

    def test_all_seven_pages_receive_descendant_hover_with_local_page_colors(self):
        self.host.hide()
        window = MainWindow(self.ctx, show_welcome=False)
        self.windows.append(window)
        window.resize(1360, 900)
        window.show()
        APP.processEvents()
        for key, page in window.pages.items():
            with self.subTest(page=key):
                window.navigate(key, animate=False)
                card = page.metric_cards['work'] if key == 'progression' else page.hero
                title = page.metric_titles['work'] if key == 'progression' else card.title_label
                figure = page.figures['work'] if key == 'progression' else card.figure
                window.wrappers[key].ensureWidgetVisible(card, 0, 20)
                APP.processEvents()
                move(title, title.width() * .15, max(2, title.height() * .3))
                finish_motion(card)
                light = QPointF(card._light)
                move(title, title.width() * .85, max(2, title.height() * .6))
                finish_motion(card)
                self.assertGreater(card._light.x(), light.x())
                self.assertNotEqual(figure._offset, QPointF())
                self.assertEqual(window.current_key, key)
                wrapper = window.wrappers[key]
                self.assertLessEqual(page.width(), wrapper.viewport().width())

    def test_scroll_mapping_remains_local_and_progression_gradients_are_preserved(self):
        self.host.hide()
        window = MainWindow(self.ctx, show_welcome=False)
        self.windows.append(window)
        window.resize(1024, 680)
        window.show()
        window.navigate('memory', animate=False)
        field = window.pages['memory'].key_input
        card = field.parentWidget()
        while card is not None and not isinstance(card, Card):
            card = card.parentWidget()
        wrapper = window.wrappers['memory']
        wrapper.ensureWidgetVisible(field, 0, 20)
        APP.processEvents()
        move(field, field.width() * .7, field.height() * .4)
        finish_motion(card)
        initial = QPointF(card._light)
        wrapper.verticalScrollBar().setValue(max(0, wrapper.verticalScrollBar().value() - 35))
        APP.processEvents()
        move(field, field.width() * .7, field.height() * .4)
        finish_motion(card)
        self.assertAlmostEqual(card._light.x(), initial.x(), places=2)
        self.assertAlmostEqual(card._light.y(), initial.y(), places=2)
        page = window.pages['progression']
        for theme in ('light', 'dark'):
            self.ctx.set_theme(theme)
            window.navigate('progression', animate=False)
            APP.processEvents()
            expected = ('#123C71', '#34275F', '#572451') if theme == 'dark' else ('#CEE7FF', '#E2D7FF', '#FFD8EC')
            hero_style = page.hero_card.styleSheet()
            for color in expected:
                self.assertIn(color, hero_style)
            for axis, metric in page.metric_cards.items():
                palette = axis_palette(axis, theme)
                self.assertIn(palette['tint'], metric.styleSheet())
                self.assertIn(palette['accent'], metric.styleSheet())
                self.assertEqual(metric.property('materialAccent'), palette['accent'])
            styles = {axis: metric.styleSheet() for axis, metric in page.metric_cards.items()}
            wrapper = window.wrappers['progression']
            wrapper.ensureWidgetVisible(page.metric_cards['work'], 0, 20)
            move(page.metric_titles['work'], 15, 8)
            finish_motion(page.metric_cards['work'])
            self.assertEqual(page.hero_card.styleSheet(), hero_style)
            self.assertEqual({axis: metric.styleSheet() for axis, metric in page.metric_cards.items()}, styles)


if __name__ == '__main__':
    unittest.main()
