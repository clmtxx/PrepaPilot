"""Material card feedback remains finite, cached and independent of layout."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import unittest
from PySide6.QtCore import QAbstractAnimation, QEvent, QObject, QPointF, Signal
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from mpsi_desktop.page_chrome import AccentCard, PageHero
from mpsi_desktop.page_figures import page_palette
from mpsi_desktop.theme import palette_for


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ThemeContext(QObject):
    theme_changed = Signal(str)
    theme = 'light'

    def set_theme(self, value):
        self.theme = value
        APP.setProperty('visualTheme', value)
        self.theme_changed.emit(value)


class CraftedSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.motion = APP.property('reducedMotion')
        self.theme = APP.property('visualTheme')
        APP.setProperty('reducedMotion', False)
        APP.setProperty('visualTheme', 'light')
        self.ctx = ThemeContext()
        self.cards = []

    def tearDown(self):
        for card in self.cards:
            card.close()
            card.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        APP.setProperty('reducedMotion', self.motion)
        APP.setProperty('visualTheme', self.theme)

    def card(self, hero=False):
        card = (PageHero(self.ctx, 'home', 'AUJOURD’HUI', 'Mon espace', 'Mes prochains cours.')
                if hero else AccentCard(self.ctx, 'documents'))
        card.resize(720, 260)
        card.show()
        APP.processEvents()
        card._reset_motion()
        self.cards.append(card)
        return card

    def enter(self, card):
        point = QPointF(110, 55)
        APP.sendEvent(card, QEnterEvent(point, point, point))

    def test_specular_rim_changes_pixels_without_rebuilding_surface_or_layout(self):
        card = self.card()
        self.enter(card)
        card.hover_animation.setCurrentTime(card.hover_animation.duration())
        card.light_animation.setCurrentTime(card.light_animation.duration())
        card.glint_animation.setCurrentTime(card.glint_animation.duration())
        settled = card.grab().toImage()
        surface = card._surface.cacheKey()
        geometry = card.geometry()
        card.glint_animation.start()
        card.glint_animation.setCurrentTime(230)
        self.assertNotEqual(settled, card.grab().toImage())
        self.assertEqual(surface, card._surface.cacheKey())
        self.assertEqual(card.geometry(), geometry)
        card.glint_animation.setCurrentTime(card.glint_animation.duration())
        self.assertEqual(card._glint, 1.)
        self.assertEqual(card.glint_animation.loopCount(), 1)
        self.assertEqual(card.glint_animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(settled, card.grab().toImage())

    def test_pointer_light_is_bounded_and_settles_without_rebuilding_artwork(self):
        card = self.card()
        card.grab()
        surface = card._surface.cacheKey()
        card._track_light(QPointF(-500, 900))
        card.light_animation.setCurrentTime(card.light_animation.duration())
        self.assertEqual(card._light, QPointF(.05, .98))
        self.assertEqual(card.light_animation.state(), QAbstractAnimation.Stopped)
        card._set_hover(1.)
        first = card.grab().toImage()
        card._track_light(QPointF(900, -500))
        card.light_animation.setCurrentTime(card.light_animation.duration())
        self.assertEqual(card._light, QPointF(.95, .02))
        self.assertNotEqual(first, card.grab().toImage())
        self.assertEqual(surface, card._surface.cacheKey())

    def test_reduced_motion_cancels_all_feedback_and_keeps_material(self):
        card = self.card(hero=True)
        material = card.grab().toImage()
        self.enter(card)
        card.glint_animation.setCurrentTime(220)
        APP.setProperty('reducedMotion', True)
        self.assertEqual(card._light, QPointF(.82, .08))
        self.assertEqual(card._glint, 1.)
        self.assertEqual(card._arrival, 1.)
        self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped
                            for animation in card.findChildren(QAbstractAnimation)))
        self.enter(card)
        self.assertEqual(card.glint_animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(material, card.grab().toImage())

    def test_hide_disable_and_theme_change_end_all_card_feedback(self):
        card = self.card()
        for stop in (card.hide, lambda: card.setEnabled(False), lambda: self.ctx.set_theme('dark')):
            card.show()
            card.setEnabled(True)
            self.enter(card)
            card.glint_animation.setCurrentTime(130)
            stop()
            self.assertEqual(card._glint, 1.)
            self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped
                                for animation in card.findChildren(QAbstractAnimation)))

    def test_reading_surface_is_neutral_and_cached_inside_existing_pixel_budget(self):
        card = self.card()
        for theme in ('light', 'dark'):
            self.ctx.set_theme(theme)
            image = card.grab().toImage()
            center = image.pixelColor(card.width() // 2, card.height() // 2)
            from PySide6.QtGui import QColor
            paper = QColor(palette_for(theme)['surface'])
            self.assertLess(max(abs(a - b) for a, b in zip(center.getRgb()[:3], paper.getRgb()[:3])), 25)
            self.assertLessEqual(card._surface.width() * card._surface.height(), card.MAX_SURFACE_PIXELS)
            self.assertEqual(image, card.grab().toImage())

    def test_pigment_is_visible_in_heading_and_corner_but_leaves_reading_center_neutral(self):
        from PySide6.QtGui import QColor
        for kind in ('home', 'notes', 'documents', 'time', 'memory', 'settings'):
            card = AccentCard(self.ctx, kind)
            card.resize(720, 260)
            card.show()
            self.cards.append(card)
            APP.processEvents()
            card._reset_motion()
            for theme in ('light', 'dark'):
                with self.subTest(kind=kind, theme=theme):
                    self.ctx.set_theme(theme)
                    image = card.grab().toImage()
                    paper = QColor(palette_for(theme)['surface'])
                    distance = lambda color: max(abs(a - b) for a, b in zip(color.getRgb()[:3], paper.getRgb()[:3]))
                    self.assertLess(distance(image.pixelColor(360, 130)), 25)
                    self.assertGreater(distance(image.pixelColor(110, 22)), 7)
                    self.assertGreater(distance(image.pixelColor(690, 100)), 10)

    def test_material_accent_tracks_page_palette_and_theme_for_descendant_controls(self):
        card = self.card()
        for theme in ('light', 'dark'):
            self.ctx.set_theme(theme)
            self.assertEqual(card.property('materialAccent'), page_palette('documents', theme)['accent'])


if __name__ == '__main__':
    unittest.main()
