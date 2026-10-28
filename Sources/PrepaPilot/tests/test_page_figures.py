"""The shared illustrations render and respect motion preferences on every page."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import unittest

from PySide6.QtCore import QAbstractAnimation, QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from mpsi_desktop.page_figures import PageFigure, page_palette


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
KINDS = ("home", "notes", "documents", "time", "memory", "settings")


class PageFigureTests(unittest.TestCase):
    def setUp(self):
        self.old_motion = APP.property("reducedMotion")
        self.old_theme = APP.property("visualTheme")
        APP.setProperty("reducedMotion", False)
        APP.setProperty("visualTheme", "light")
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append(str(value))
        self.figures = [PageFigure(kind) for kind in KINDS]
        for figure in self.figures:
            figure.resize(220, 160)
            figure.show()
        APP.processEvents()

    def tearDown(self):
        for figure in self.figures:
            figure.close()
            figure.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        APP.setProperty("reducedMotion", self.old_motion)
        APP.setProperty("visualTheme", self.old_theme)
        sys.excepthook = self.old_hook
        self.assertEqual(self.errors, [])

    def move(self, figure, x, y):
        point = QPointF(x, y)
        APP.sendEvent(figure, QMouseEvent(QEvent.Type.MouseMove, point, point,
                      Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

    def test_six_distinct_figures_render_at_every_supported_size_and_theme(self):
        for theme in ("light", "dark"):
            APP.setProperty("visualTheme", theme)
            images = []
            for figure in self.figures:
                for size in ((96, 96), (154, 128), (220, 160)):
                    figure.resize(*size)
                    image = figure.grab().toImage()
                    self.assertFalse(image.isNull())
                    self.assertEqual(image, figure.grab().toImage())
                images.append(image)
            for index, image in enumerate(images):
                for other in images[index + 1:]:
                    self.assertNotEqual(image, other)

    def test_palettes_are_valid_and_each_figure_is_named_as_decoration(self):
        for figure in self.figures:
            self.assertTrue(figure.accessibleName())
            self.assertEqual(figure.accessibleDescription(), "Illustration décorative")
            for theme in ("light", "dark"):
                colors = page_palette(figure.kind, theme)
                self.assertEqual(set(colors), {"accent", "light", "dark", "tint"})
                self.assertTrue(all(QColor(value).isValid() for value in colors.values()))
                colors["accent"] = "invalid"
                self.assertTrue(QColor(page_palette(figure.kind, theme)["accent"]).isValid())

    def test_pointer_motion_is_bounded_finite_and_returns_to_rest(self):
        for figure in self.figures:
            self.move(figure, 1500, -400)
            animation = figure.parallax_animation
            self.assertEqual(animation.state(), QAbstractAnimation.State.Running)
            animation.setCurrentTime(animation.duration())
            self.assertEqual(figure._offset, QPointF(1, -1))
            self.assertEqual(animation.loopCount(), 1)
            self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
            APP.sendEvent(figure, QEvent(QEvent.Type.Leave))
            animation.setCurrentTime(animation.duration())
            self.assertEqual(figure._offset, QPointF())

    def test_every_page_has_cached_satellites_and_cancels_its_glint_when_hidden(self):
        for figure in self.figures:
            figure._reset_motion()
            resting = figure.grab().toImage()
            cached = {name: pix.cacheKey() for name, pix in figure._artwork.layers.items()}
            point = QPointF(100, 80)
            APP.sendEvent(figure, QEnterEvent(point, point, point))
            figure.glint_animation.setCurrentTime(380)
            self.assertNotEqual(resting, figure.grab().toImage())
            self.assertEqual(cached, {name: pix.cacheKey() for name, pix in figure._artwork.layers.items()})
            figure.hide()
            self.assertEqual(figure._glint, 1.)
            self.assertTrue(all(animation.state() == QAbstractAnimation.State.Stopped
                                for animation in figure.findChildren(QAbstractAnimation)))
            figure.show()
            self.assertEqual(resting, figure.grab().toImage())

    def test_live_reduced_motion_stops_all_figures_and_blocks_new_animation(self):
        for figure in self.figures:
            self.move(figure, 0, 0)
            figure.parallax_animation.setCurrentTime(70)
        APP.setProperty("reducedMotion", True)
        for figure in self.figures:
            self.assertEqual(figure._offset, QPointF())
            self.assertEqual(figure.parallax_animation.state(), QAbstractAnimation.State.Stopped)
            self.move(figure, 500, 500)
            self.assertEqual(figure.parallax_animation.state(), QAbstractAnimation.State.Stopped)

    def test_hide_cancels_motion_and_reshow_does_not_restart_it(self):
        for figure in self.figures:
            self.move(figure, 0, 0)
            figure.parallax_animation.setCurrentTime(70)
            figure.hide()
            self.assertEqual(figure._offset, QPointF())
            self.assertEqual(figure.parallax_animation.state(), QAbstractAnimation.State.Stopped)
            figure.show()
            APP.processEvents()
            self.assertEqual(figure.parallax_animation.state(), QAbstractAnimation.State.Stopped)
            self.assertIsNone(figure.graphicsEffect())

    def test_theme_change_repaints_without_starting_motion(self):
        images = [figure.grab().toImage() for figure in self.figures]
        APP.setProperty("visualTheme", "dark")
        for figure, image in zip(self.figures, images):
            self.assertNotEqual(image, figure.grab().toImage())
            self.assertEqual(figure.parallax_animation.state(), QAbstractAnimation.State.Stopped)


if __name__ == "__main__":
    unittest.main()
