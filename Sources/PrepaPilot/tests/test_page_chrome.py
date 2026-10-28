"""Satin surfaces cache their artwork while controls and preferences stay live."""
import os
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QAbstractAnimation, QEvent, QObject, Signal, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mpsi_desktop.page_chrome import AccentCard, PageHero
from mpsi_desktop.widgets import button


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ThemeContext(QObject):
    theme_changed = Signal(str)
    theme = 'light'

    def set_theme(self, value):
        self.theme = value
        APP.setProperty('visualTheme', value)
        self.theme_changed.emit(value)


class PageChromeTests(unittest.TestCase):
    def setUp(self):
        self.motion = APP.property('reducedMotion')
        self.theme = APP.property('visualTheme')
        APP.setProperty('reducedMotion', False)
        APP.setProperty('visualTheme', 'light')
        self.ctx = ThemeContext()
        self.widgets = []
        self.errors = []
        self.hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append((kind.__name__, str(value)))

    def tearDown(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        APP.setProperty('reducedMotion', self.motion)
        APP.setProperty('visualTheme', self.theme)
        sys.excepthook = self.hook
        self.assertEqual(self.errors, [])

    def show(self, widget):
        self.widgets.append(widget)
        widget.resize(680, 240)
        widget.show()
        APP.processEvents()
        widget._reset_motion()
        return widget

    def test_hover_reuses_surface_and_keeps_text_and_controls_live(self):
        control = button('Enregistrer')
        hero = self.show(PageHero(self.ctx, 'notes', 'MES NOTES', 'Mes progrès.',
                                  'Des repères pour apprendre.', actions=[control]))
        resting = hero.grab().toImage()
        surface = hero._surface.cacheKey()
        bounds = control.geometry()
        hero._set_hover(1.)
        self.assertNotEqual(resting, hero.grab().toImage())
        self.assertEqual(surface, hero._surface.cacheKey())
        hero.title_label.setText('Mon nouveau titre')
        hero.grab()
        self.assertEqual(surface, hero._surface.cacheKey())
        calls = []
        control.clicked.connect(lambda: calls.append(True))
        QTest.mouseClick(control, Qt.LeftButton)
        self.assertEqual(calls, [True])
        self.assertEqual(control.geometry(), bounds)

    def test_cache_rebuilds_for_theme_size_and_pixel_ratio_without_accumulation(self):
        class ScreenCard(AccentCard):
            ratio = 1.

            def devicePixelRatioF(self):
                return self.ratio

        card = self.show(ScreenCard(self.ctx, 'documents'))
        light = card.grab().toImage()
        original = card._surface.cacheKey()
        self.ctx.set_theme('dark')
        self.assertNotEqual(light, card.grab().toImage())
        self.assertNotEqual(original, card._surface.cacheKey())
        previous = card._surface.cacheKey()
        card.ratio = 2.
        card.grab()
        self.assertNotEqual(previous, card._surface.cacheKey())
        previous = card._surface.cacheKey()
        card.resize(720, 280)
        card.grab()
        self.assertNotEqual(previous, card._surface.cacheKey())
        self.assertLessEqual(card._surface.width() * card._surface.height(), card.MAX_SURFACE_PIXELS)

    def test_large_card_surface_budget_excludes_live_widget_resolution(self):
        card = self.show(AccentCard(self.ctx, 'time'))
        card.resize(3840, 2160)
        bounds = card.geometry()
        surface = card._cached_surface()
        self.assertLessEqual(surface.width() * surface.height(), card.MAX_SURFACE_PIXELS)
        self.assertEqual(card.geometry(), bounds)
        self.assertEqual(surface.cacheKey(), card._cached_surface().cacheKey())

    def test_arrival_is_finite_and_stops_immediately_on_hide_or_reduced_motion(self):
        hero = self.show(PageHero(self.ctx, 'memory', 'MES REPÈRES', 'Une idée.',
                                  'Garder le fil.'))
        hero.hide()
        hero.show()
        self.assertEqual(hero.arrival_animation.state(), QAbstractAnimation.Running)
        hero.arrival_animation.setCurrentTime(350)
        hero.grab()
        cached = hero._surface.cacheKey()
        hero.arrival_animation.setCurrentTime(700)
        hero.grab()
        self.assertEqual(cached, hero._surface.cacheKey())
        self.assertLess(hero.arrival_animation.duration(), 1000)
        APP.setProperty('reducedMotion', True)
        self.assertEqual(hero._arrival, 1.)
        self.assertEqual(hero.arrival_animation.state(), QAbstractAnimation.Stopped)
        APP.setProperty('reducedMotion', False)
        hero.hide()
        hero.show()
        hero.hide()
        self.assertEqual(hero._arrival, 1.)
        self.assertEqual(hero.arrival_animation.state(), QAbstractAnimation.Stopped)

    def test_theme_change_cancels_arrival_and_keeps_accessible_content(self):
        hero = self.show(PageHero(self.ctx, 'home', 'AUJOURD’HUI', 'Bonjour <Camille>.',
                                  'Un rythme personnel.'))
        hero.hide()
        hero.show()
        hero.arrival_animation.setCurrentTime(200)
        self.ctx.set_theme('dark')
        self.assertEqual(hero.arrival_animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(hero._arrival, 1.)
        self.assertEqual(hero.title_label.text(), 'Bonjour <Camille>.')
        self.assertEqual(hero.title_label.textFormat(), Qt.PlainText)
        self.assertFalse(hero.grab().isNull())


if __name__ == '__main__':
    unittest.main()
