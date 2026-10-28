"""Manual CPU rendering comparison, without network or application data.

From Sources/PrepaPilot, run: python -B -m tests.benchmark_visual_rendering
The reference draws the same vector layers directly on every frame. This is a
paint-cost comparison on the current machine, not a guarantee of application FPS.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import statistics
import time

from PySide6.QtCore import QPointF, QObject, Signal
from PySide6.QtWidgets import QApplication

from mpsi_desktop.page_figures import PageFigure
from mpsi_desktop.progression_visuals import ProgressionFigure, ScoreOrb
from mpsi_desktop.visuals import StudySculpture
from mpsi_desktop.page_chrome import AccentCard


def measure(widget, *, cached, frames=240):
    artwork = widget._artwork
    cached_draw = artwork.draw

    def draw_vectors(painter, name, render, offset=QPointF()):
        painter.save()
        painter.translate((widget.width() - artwork.width * artwork.scale) / 2,
                          (widget.height() - artwork.height * artwork.scale) / 2)
        painter.scale(artwork.scale, artwork.scale)
        painter.translate(offset)
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        render(painter)
        painter.restore()

    if not cached:
        artwork.draw = draw_vectors
    timings = []
    try:
        for index in range(frames + 30):
            if isinstance(widget, ScoreOrb):
                widget._score = 75.
                widget._display_score = index % 100
            else:
                widget._offset = QPointF((index % 50) / 25 - 1, (index % 40) / 20 - 1)
            started = time.perf_counter()
            widget.grab()
            elapsed = (time.perf_counter() - started) * 1000
            if index >= 30:
                timings.append(elapsed)
    finally:
        artwork.draw = cached_draw
    return statistics.median(timings), sorted(timings)[int(len(timings) * .95)]


def main():
    app = QApplication.instance() or QApplication([])
    app.setProperty("reducedMotion", False)
    print("Figure         vector median/p95 ms   cached median/p95 ms   median reduction")
    for name, widget in (("Sculpture", StudySculpture()), ("Sommeil", ProgressionFigure("sleep")),
                         ("Accueil", PageFigure("home")), ("Score", ScoreOrb())):
        widget.resize(widget.sizeHint())
        widget.show()
        app.processEvents()
        direct = measure(widget, cached=False)
        cached = measure(widget, cached=True)
        print(f"{name:13} {direct[0]:7.3f} / {direct[1]:7.3f}     "
              f"{cached[0]:7.3f} / {cached[1]:7.3f}       {100 * (1 - cached[0] / direct[0]):5.1f}%")
        widget.close()

    class ThemeContext(QObject):
        theme_changed = Signal(str)
        theme = "light"

    ctx = ThemeContext()
    card = AccentCard(ctx, "notes")
    card.resize(850, 260)
    card.show()
    app.processEvents()
    values = {}
    for cached in (False, True):
        samples = []
        for index in range(150):
            if not cached:
                card._surface_key = None
            card._hover = (index % 20) / 20
            started = time.perf_counter()
            card.grab()
            if index >= 30:
                samples.append((time.perf_counter() - started) * 1000)
        values[cached] = statistics.median(samples)
    print(f"Fond de carte  rebuilt {values[False]:.3f} ms ; cached {values[True]:.3f} ms ; "
          f"median reduction {100 * (1 - values[True] / values[False]):.1f}%")
    card.close()


if __name__ == "__main__":
    main()
