"""Grade chart caching retains markers, reveal motion and precise hover data."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import date, timedelta
import unittest
from unittest.mock import patch

from PySide6.QtCore import QAbstractAnimation, QEvent, QObject, QPointF, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from mpsi_desktop.notes import GradeChart


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ChartDatabase:
    def get_setting(self, key, default=None):
        return False

    def grade_kind_labels(self):
        return {'ds': 'Devoir surveillé'}


class ChartContext(QObject):
    theme_changed = Signal()

    def __init__(self):
        super().__init__()
        self.theme = 'light'
        self.selected_year = 2026
        self.year_reads = 0
        self.db = ChartDatabase()

    @property
    def year(self):
        self.year_reads += 1
        return self.selected_year


def grades(count=2000):
    return [dict(id=index, kind=f'Type {index % 30}',
                 graded_on=(date(2026, 8, 1) + timedelta(days=index % 365)).isoformat(),
                 score=index % 21, scale=20, label=f'Évaluation {index}')
            for index in range(count)]


class GradeChartTests(unittest.TestCase):
    def setUp(self):
        APP.setProperty('reducedMotion', False)
        self.ctx = ChartContext()
        self.chart = GradeChart(self.ctx)
        self.chart.resize(1000, 240)

    def tearDown(self):
        self.chart.close()
        self.chart.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        APP.setProperty('reducedMotion', False)

    def test_2000_grades_keep_all_markers_and_repaint_without_database_or_scene_rebuild(self):
        rows = grades()
        self.chart.set_grades(rows)
        self.chart.grab()
        self.assertEqual(len(self.chart._hit_points), 2000)
        self.assertEqual(len(self.chart._series), 30)
        reads = self.ctx.year_reads
        with (patch.object(self.chart, '_paint_axes', wraps=self.chart._paint_axes) as axes,
              patch.object(self.chart, '_paint_curves', wraps=self.chart._paint_curves) as curves,
              patch.object(self.ctx.db, 'get_setting', side_effect=AssertionError('No per-frame SQL'))):
            for fraction in (0, .25, .5, .75, 1):
                self.chart._reveal = fraction
                self.chart.grab()
            self.assertEqual(self.ctx.year_reads, reads)
            axes.assert_not_called()
            curves.assert_not_called()
        layer = self.chart._curves_layer.cacheKey()
        self.chart.set_grades(rows)
        self.chart.grab()
        self.assertEqual(self.chart._curves_layer.cacheKey(), layer)

    def test_scene_invalidates_on_resize_theme_font_year_and_in_place_edit(self):
        rows = grades(40)
        self.chart.set_grades(rows)
        self.chart.grab()

        def refresh_changes_layer(change):
            previous = self.chart._curves_layer.cacheKey()
            change()
            self.chart.grab()
            self.assertNotEqual(previous, self.chart._curves_layer.cacheKey())

        refresh_changes_layer(lambda: self.chart.resize(720, 200))
        refresh_changes_layer(lambda: setattr(self.ctx, 'theme', 'dark'))
        font = QFont(self.chart.font())
        font.setPointSize(12)
        refresh_changes_layer(lambda: self.chart.setFont(font))
        self.ctx.selected_year = 2027
        refresh_changes_layer(lambda: self.chart.set_grades(rows))
        self.assertIn('2027–2028', self.chart.accessibleDescription())
        rows[0]['score'] = 19
        refresh_changes_layer(lambda: self.chart.set_grades(rows))
        self.assertEqual(self.chart.rows[0]['score'], 19)

    def test_spatial_hover_matches_nearest_revealed_point_and_preserves_ties(self):
        self.chart.set_grades(grades(400))
        self.chart.grab()
        for fraction in (.15, .55, 1):
            self.chart._reveal = fraction
            visible = self.chart._hit_points
            for x in range(25, 1000, 19):
                position = QPointF(x, 80 + x % 100)
                distances = [((point.x() - position.x()) ** 2 + (point.y() - position.y()) ** 2, row)
                             for point, row in visible]
                candidate = min(distances, key=lambda pair: pair[0]) if distances else None
                expected = candidate[1] if candidate is not None and candidate[0] < 225 else None
                self.assertEqual(self.chart._nearest(position), expected)
        first, row = self.chart._all_hit_points[0]
        self.assertIsNotNone(self.chart._nearest(first))

    def test_reveal_clips_cached_curves_without_hiding_axes(self):
        self.chart.set_grades(grades(400))
        self.chart._reveal = 0
        empty = self.chart.grab().toImage()
        self.chart._reveal = .5
        half = self.chart.grab().toImage()
        self.chart._reveal = 1
        full = self.chart.grab().toImage()
        # The right side still shows the same axes during the reveal, while
        # the finished chart contains its data. Left-axis labels stay intact.
        self.assertEqual(empty.copy(0, 0, 30, 240), full.copy(0, 0, 30, 240))
        self.assertEqual(empty.copy(540, 0, 460, 240), half.copy(540, 0, 460, 240))
        self.assertNotEqual(empty.copy(540, 0, 440, 220), full.copy(540, 0, 440, 220))

    def test_hidden_minimized_and_reduced_motion_stop_reveal_at_readable_state(self):
        self.chart.set_grades(grades(8))
        self.chart.show()
        APP.processEvents()
        self.chart._set_reveal(.2)
        self.assertLess(self.chart._reveal, 1)
        APP.setProperty('reducedMotion', True)
        self.assertEqual(self.chart._reveal, 1)
        self.assertEqual(self.chart.reveal_animation.state(), QAbstractAnimation.Stopped)
        APP.setProperty('reducedMotion', False)
        self.chart._pending_reveal = True
        self.chart._start_reveal()
        self.chart.hide()
        self.assertEqual(self.chart._reveal, 1)
        self.assertEqual(self.chart.reveal_animation.state(), QAbstractAnimation.Stopped)
        self.chart.setWindowState(Qt.WindowMinimized)
        self.chart._pending_reveal = True
        self.chart._start_reveal()
        self.assertEqual(self.chart._reveal, 1)


if __name__ == '__main__':
    unittest.main()
