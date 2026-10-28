"""Painting and bounded motion checks for the Progression illustrations."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import unittest

from PySide6.QtCore import QAbstractAnimation, QEvent, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from mpsi_desktop.progression_visuals import ProgressionFigure, ScoreOrb, axis_palette


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ProgressionVisualTests(unittest.TestCase):
    def setUp(self):
        self.old_motion = APP.property("reducedMotion")
        self.old_theme = APP.property("visualTheme")
        APP.setProperty("reducedMotion", False)
        APP.setProperty("visualTheme", "light")
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append(str(value))
        self.host = QWidget()
        layout = QHBoxLayout(self.host)
        self.figures = [ProgressionFigure(axis) for axis in ("work", "sleep", "sport", "rest")]
        for figure in self.figures:
            layout.addWidget(figure)
        self.orb = ScoreOrb()
        layout.addWidget(self.orb)
        self.host.resize(1100, 200)
        self.host.show()
        APP.processEvents()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
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

    def test_each_axis_has_distinct_palettes_and_accessible_decorative_name(self):
        accents = set()
        for figure in self.figures:
            for theme in ("light", "dark"):
                colors = axis_palette(figure.axis, theme)
                self.assertEqual(set(colors), {"accent", "light", "dark", "tint"})
                self.assertTrue(all(QColor(value).isValid() for value in colors.values()))
            accents.add(axis_palette(figure.axis)["accent"])
            self.assertTrue(figure.accessibleName())
            self.assertEqual(figure.accessibleDescription(), "Illustration décorative")
        self.assertEqual(len(accents), 4)

    def test_all_figures_paint_in_both_themes_and_at_compact_size(self):
        for theme in ("light", "dark"):
            APP.setProperty("visualTheme", theme)
            images = []
            for figure in self.figures:
                for size in ((96, 96), (160, 130), (220, 160)):
                    figure.resize(*size)
                    image = figure.grab().toImage()
                    self.assertFalse(image.isNull())
                    self.assertEqual(image, figure.grab().toImage())
                images.append(image)
            for index, image in enumerate(images):
                for other in images[index + 1:]:
                    self.assertNotEqual(image, other)
            for score in (None, 0, 75, 100):
                self.orb.set_score(score)
                self.orb._reset_motion()
                self.assertFalse(self.orb.grab().isNull())

    def test_parallax_is_bounded_and_completes_without_loop(self):
        for figure in self.figures:
            self.move(figure, figure.width() * 3, -400)
            animation = figure.parallax_animation
            self.assertEqual(animation.state(), QAbstractAnimation.State.Running)
            animation.setCurrentTime(animation.duration())
            self.assertEqual(figure._offset, QPointF(1, -1))
            self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
            APP.sendEvent(figure, QEvent(QEvent.Type.Leave))
            animation.setCurrentTime(animation.duration())
            self.assertEqual(figure._offset, QPointF())
            self.assertEqual(animation.loopCount(), 1)

    def test_hover_glint_is_finite_reuses_every_layer_and_returns_to_identical_rest(self):
        for figure in self.figures:
            figure._reset_motion()
            resting = figure.grab().toImage()
            cached = {name: layer.cacheKey() for name, layer in figure._artwork.layers.items()}
            self.assertEqual(set(cached), {"studio", "orbit", "figure", "satellites", "glint"})
            point = QPointF(100, 80)
            APP.sendEvent(figure, QEnterEvent(point, point, point))
            animation = figure.glint_animation
            self.assertEqual(animation.state(), QAbstractAnimation.State.Running)
            animation.setCurrentTime(animation.duration() // 2)
            self.assertNotEqual(resting, figure.grab().toImage())
            self.assertEqual(cached, {name: layer.cacheKey() for name, layer in figure._artwork.layers.items()})
            animation.setCurrentTime(animation.duration())
            self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
            self.assertEqual(animation.loopCount(), 1)
            self.assertEqual(resting, figure.grab().toImage())
            self.assertEqual(figure.findChildren(QTimer), [])

    def test_glint_stops_immediately_on_leave_hide_or_reduced_motion(self):
        figure = self.figures[0]
        point = QPointF(100, 80)
        for cancel in (lambda: APP.sendEvent(figure, QEvent(QEvent.Type.Leave)),
                       figure.hide,
                       lambda: APP.setProperty("reducedMotion", True)):
            figure.show()
            APP.sendEvent(figure, QEnterEvent(point, point, point))
            figure.glint_animation.setCurrentTime(300)
            cancel()
            self.assertEqual(figure.glint_animation.state(), QAbstractAnimation.State.Stopped)
            self.assertEqual(figure._glint, 1.)
        APP.sendEvent(figure, QEnterEvent(point, point, point))
        self.assertEqual(figure.glint_animation.state(), QAbstractAnimation.State.Stopped)

    def test_score_initializes_without_animation_then_interpolates_only_the_arc(self):
        self.orb.set_score(23)
        self.assertEqual(self.orb._display_score, 23)
        self.assertEqual(self.orb.score_animation.state(), QAbstractAnimation.State.Stopped)
        self.orb.set_score(91)
        animation = self.orb.score_animation
        self.assertEqual(animation.state(), QAbstractAnimation.State.Running)
        animation.setCurrentTime(180)
        self.assertGreater(self.orb._display_score, 23)
        self.assertLess(self.orb._display_score, 91)
        self.assertEqual(self.orb._score, 91)
        self.assertIn("91 sur 100", self.orb.accessibleName())
        animation.setCurrentTime(animation.duration())
        self.assertEqual(self.orb._display_score, 91)
        self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(animation.loopCount(), 1)

    def test_missing_zero_and_invalid_scores_are_not_conflated(self):
        self.orb.set_score(None)
        missing = self.orb.grab().toImage()
        self.assertIn("non renseigné", self.orb.accessibleName())
        self.orb.set_score(0)
        self.assertIn("0 sur 100", self.orb.accessibleName())
        self.assertNotEqual(missing, self.orb.grab().toImage())
        self.orb.set_score(-5)
        self.assertEqual(self.orb._score, 0)
        self.orb.set_score(500)
        self.assertEqual(self.orb._score, 100)
        for invalid in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.orb.set_score(invalid)
        self.assertEqual(self.orb._score, 100)

    def test_live_reduced_motion_stops_every_animation_at_a_readable_rest(self):
        for figure in self.figures:
            self.move(figure, 0, 0)
            figure.parallax_animation.setCurrentTime(80)
        self.orb.set_score(20)
        self.orb.set_score(75)
        self.orb.score_animation.setCurrentTime(80)
        APP.setProperty("reducedMotion", True)
        for figure in self.figures:
            self.assertEqual(figure._offset, QPointF())
            self.assertEqual(figure.parallax_animation.state(), QAbstractAnimation.State.Stopped)
            self.move(figure, 0, 0)
            self.assertEqual(figure.parallax_animation.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(self.orb.score_animation.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(self.orb._display_score, 75)
        self.orb.set_score(12)
        self.assertEqual(self.orb._display_score, 12)
        self.assertEqual(self.orb.score_animation.state(), QAbstractAnimation.State.Stopped)

    def test_hidden_widgets_stop_and_remain_static_when_shown(self):
        for figure in self.figures:
            self.move(figure, 0, 0)
        self.orb.set_score(10)
        self.orb.set_score(80)
        self.host.hide()
        self.assertEqual(self.orb._display_score, 80)
        for widget, animation in [(figure, figure.parallax_animation) for figure in self.figures] + [(self.orb, self.orb.score_animation)]:
            self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
            self.assertIsNone(widget.graphicsEffect())
        self.host.show()
        APP.processEvents()
        self.assertEqual(self.orb.score_animation.state(), QAbstractAnimation.State.Stopped)
        self.assertTrue(all(figure.parallax_animation.state() == QAbstractAnimation.State.Stopped for figure in self.figures))

    def test_theme_change_repaints_without_mutating_score_or_starting_motion(self):
        self.orb.set_score(68)
        light = self.orb.grab().toImage()
        APP.setProperty("visualTheme", "dark")
        self.assertEqual(self.orb._score, 68)
        self.assertNotEqual(light, self.orb.grab().toImage())
        for figure in self.figures:
            self.assertEqual(figure.parallax_animation.state(), QAbstractAnimation.State.Stopped)


if __name__ == "__main__":
    unittest.main()
