"""Rendering caches keep motion while following live display/content changes."""
import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from mpsi_desktop.page_figures import PageFigure
from mpsi_desktop.progression_visuals import ProgressionFigure, ScoreOrb
from mpsi_desktop.visuals import ReflectiveTitle, StudySculpture


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class VisualRenderCacheTests(unittest.TestCase):
    def setUp(self):
        self.theme = APP.property("visualTheme")
        self.motion = APP.property("reducedMotion")
        APP.setProperty("visualTheme", "light")
        APP.setProperty("reducedMotion", False)
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.setProperty("visualTheme", self.theme)
        APP.setProperty("reducedMotion", self.motion)

    def widget(self, widget):
        self.widgets.append(widget)
        widget.resize(widget.sizeHint())
        widget.show()
        APP.processEvents()
        return widget

    def test_moving_figures_reuse_shapes_but_still_change_the_rendered_image(self):
        for widget in (PageFigure("home"), ProgressionFigure("sleep"), StudySculpture()):
            self.widget(widget)
            resting = widget.grab().toImage()
            cached = {name: pix.cacheKey() for name, pix in widget._artwork.layers.items()}
            widget._offset = QPointF(1, -1)
            moving = widget.grab().toImage()
            self.assertNotEqual(resting, moving)
            self.assertEqual(cached, {name: pix.cacheKey() for name, pix in widget._artwork.layers.items()})
            widget._offset = QPointF()
            self.assertEqual(resting, widget.grab().toImage())

    def test_theme_rebuilds_current_layers_without_accumulating_previous_themes(self):
        for widget in (PageFigure("notes"), ProgressionFigure("sleep"), StudySculpture(), ScoreOrb()):
            self.widget(widget)
            light = widget.grab().toImage()
            before = widget._artwork.layers.copy()
            APP.setProperty("visualTheme", "dark")
            dark = widget.grab().toImage()
            self.assertNotEqual(light, dark)
            self.assertEqual(set(before), set(widget._artwork.layers))
            for name, old in before.items():
                self.assertNotEqual(old.cacheKey(), widget._artwork.layers[name].cacheKey())
            APP.setProperty("visualTheme", "light")
            self.assertEqual(light, widget.grab().toImage())

    def test_resize_rebuilds_only_current_resolution_and_keeps_artwork_proportions(self):
        widget = self.widget(PageFigure("documents"))
        widget.grab()
        original = widget._artwork.layers["figure"]
        # More whitespace alone must not rasterize the same drawing again.
        widget.resize(440, 160)
        widget.grab()
        self.assertEqual(original.cacheKey(), widget._artwork.layers["figure"].cacheKey())
        widget.resize(440, 320)
        widget.grab()
        doubled = widget._artwork.layers["figure"]
        self.assertNotEqual(original.cacheKey(), doubled.cacheKey())
        self.assertEqual(doubled.width(), original.width() * 2)
        self.assertEqual(set(widget._artwork.layers), {"studio", "orbit", "figure", "satellites", "glint"})

    def test_screen_pixel_ratio_change_rebuilds_at_native_resolution(self):
        class ScreenFigure(PageFigure):
            ratio = 1.

            def devicePixelRatioF(self):
                return self.ratio

        widget = self.widget(ScreenFigure("memory"))
        widget.grab()
        first = widget._artwork.layers["figure"]
        widget.ratio = 1.5
        widget.grab()
        second = widget._artwork.layers["figure"]
        self.assertNotEqual(first.cacheKey(), second.cacheKey())
        self.assertEqual(second.devicePixelRatioF(), 1.5)
        self.assertEqual(second.width(), math.ceil(first.width() * 1.5))
        self.assertEqual(second.height(), math.ceil(first.height() * 1.5))
        widget.grab()
        self.assertEqual(second.cacheKey(), widget._artwork.layers["figure"].cacheKey())

    def test_variant_change_cannot_reuse_another_illustration(self):
        widget = self.widget(PageFigure("home"))
        first = widget.grab().toImage()
        widget.kind = "notes"
        self.assertNotEqual(first, widget.grab().toImage())
        widget.kind = "home"
        self.assertEqual(first, widget.grab().toImage())

    def test_score_changes_reuse_background_without_reusing_the_value(self):
        widget = self.widget(ScoreOrb())
        widget.set_score(20)
        first = widget.grab().toImage()
        background = widget._artwork.layers["orb"].cacheKey()
        widget.set_score(80)
        widget._reset_motion()
        self.assertNotEqual(first, widget.grab().toImage())
        self.assertEqual(widget._artwork.layers["orb"].cacheKey(), background)

    def test_reflection_reuses_layout_and_preserves_formatted_text(self):
        widget = self.widget(ReflectiveTitle("Un parcours <b>personnel</b>"))
        widget.resize(420, 75)
        widget.setTextFormat(Qt.TextFormat.RichText)
        resting = widget.grab().toImage()
        document = widget._document
        widget._reflection = .3
        self.assertNotEqual(resting, widget.grab().toImage())
        self.assertIs(widget._document, document)
        widget._reflection = None
        self.assertEqual(resting, widget.grab().toImage())

    def test_title_reflows_for_all_layout_inputs(self):
        widget = self.widget(ReflectiveTitle("Un parcours personnel sur plusieurs lignes"))
        widget.resize(420, 150)
        changes = (
            lambda: widget.setText("Un autre parcours"),
            lambda: widget.setTextFormat(Qt.TextFormat.RichText),
            lambda: widget.setFont(QFont(widget.font().family(), 23)),
            lambda: widget.setWordWrap(True),
            lambda: widget.setAlignment(Qt.AlignmentFlag.AlignRight),
            lambda: widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft),
            lambda: widget.resize(160, 150),
        )
        for change in changes:
            widget.grab()
            document = widget._document
            change()
            widget.grab()
            self.assertIsNot(widget._document, document)


if __name__ == "__main__":
    unittest.main()
