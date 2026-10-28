"""Optional class data never become invented marks or positions in the chart."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import unittest
from unittest.mock import patch

from PySide6.QtCore import QAbstractAnimation, QEvent

from mpsi_desktop.notes import GradeChart, class_average_color
from tests.test_grade_chart import APP, ChartContext


def evaluation(identifier, score=12, scale=20, **optional):
    return dict(id=identifier, kind='ds', graded_on=f'2026-{identifier + 8:02d}-10',
                score=score, scale=scale, label=f'Évaluation {identifier}', **optional)


class GradeComparisonChartTests(unittest.TestCase):
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

    def test_average_is_chronological_normalized_and_zero_is_a_real_value(self):
        rows = [evaluation(3, score=80, scale=100, class_average=60),
                evaluation(1, score=6, scale=10, class_average=0),
                evaluation(2)]
        self.chart.set_grades(rows)
        self.chart.grab()
        self.assertEqual([score for _, score, _ in self.chart._class_series], [0, 12])
        self.assertEqual(len(self.chart._all_hit_points), 5)
        averages = [(point, row) for point, row in self.chart._all_hit_points
                    if row.get('_chart_value') == 'class_average']
        self.assertEqual([row['id'] for _, row in averages], [1, 3])
        self.assertEqual(averages[0][0].y(), self.chart._axis().bottom())
        self.assertIn('60/100 → 12/20', self.chart._tooltip(averages[1][1]))
        self.assertTrue(all('_chart_value' not in row for row in rows))
        self.assertNotEqual(class_average_color('dark'), class_average_color('light'))

    def test_ranking_uses_absolute_position_first_at_top_and_exact_class_size(self):
        rows = [evaluation(1, rank=1, class_size=30), evaluation(2),
                evaluation(3, rank=50, class_size=50)]
        self.chart.set_grades(rows)
        self.chart.set_mode('ranking')
        self.chart.grab()
        self.assertEqual(self.chart._rank_limit, 50)
        self.assertEqual(len(self.chart._all_hit_points), 2)
        (first, row1), (last, row2) = self.chart._all_hit_points
        self.assertEqual(first.y(), self.chart._axis().top())
        self.assertEqual(last.y(), self.chart._axis().bottom())
        self.assertIn('Classement : 1/30', self.chart._tooltip(row1))
        self.assertIn('Classement : 50/50', self.chart._tooltip(row2))
        self.assertEqual(self.chart._nearest(first), row1)
        self.assertIn('2 classements renseignés', self.chart.accessibleDescription())
        self.assertEqual(self.chart._axis_values()[0], 1)
        self.assertEqual(self.chart._axis_values()[-1], 50)

    def test_rank_unknown_is_empty_and_one_person_class_is_well_defined(self):
        self.chart.set_grades([evaluation(1, class_average=10)])
        self.chart.set_mode('ranking')
        self.chart.grab()
        self.assertEqual(self.chart._all_hit_points, [])
        self.assertIn('0 classements renseignés', self.chart.accessibleDescription())
        self.chart.set_grades([evaluation(1, rank=1, class_size=1)])
        self.chart.grab()
        self.assertEqual(self.chart._axis_values(), [1])
        self.assertEqual(self.chart._all_hit_points[0][0].y(), self.chart._axis().top())

    def test_modes_and_optional_data_edits_invalidate_only_when_changed(self):
        rows = [evaluation(1, class_average=10, rank=2, class_size=20)]
        self.chart.set_grades(rows)
        self.chart.grab()
        grades_layer = self.chart._curves_layer.cacheKey()
        self.chart.set_mode('ranking')
        self.chart.grab()
        rank_layer = self.chart._curves_layer.cacheKey()
        self.assertNotEqual(grades_layer, rank_layer)
        with (patch.object(self.chart, '_paint_curves', wraps=self.chart._paint_curves) as paint,
              patch.object(self.ctx.db, 'get_setting', side_effect=AssertionError('No per-frame SQL'))):
            self.chart.set_mode('ranking')
            for fraction in (0, .25, .7, 1):
                self.chart._reveal = fraction
                self.chart.grab()
            paint.assert_not_called()
        rows[0]['rank'] = 1
        self.chart.set_grades(rows)
        self.chart.grab()
        self.assertNotEqual(rank_layer, self.chart._curves_layer.cacheKey())
        self.chart.set_mode('grades')
        self.chart.grab()
        previous = self.chart._curves_layer.cacheKey()
        rows[0]['class_average'] = 0
        self.chart.set_grades(rows)
        self.chart.grab()
        self.assertNotEqual(previous, self.chart._curves_layer.cacheKey())
        self.assertEqual(self.chart._class_series[0][1], 0)
        with self.assertRaises(ValueError):
            self.chart.set_mode('unsupported')

    def test_identical_mark_and_average_remain_available_in_tooltip(self):
        self.chart.set_grades([evaluation(1, class_average=12)])
        self.chart.grab()
        point, _ = self.chart._all_hit_points[0]
        caption = self.chart._tooltip(self.chart._nearest(point))
        self.assertIn('Ta note : 12/20', caption)
        self.assertIn('Moyenne de classe : 12/20', caption)
        comparison = self.chart._class_series[0][2]
        self.assertIn('Moyenne de classe', self.chart._tooltip(comparison))

    def test_mode_switch_obeys_reduced_motion_and_has_no_pending_hidden_scene(self):
        self.chart.set_grades([evaluation(1, rank=1, class_size=30)])
        self.chart.show()
        APP.processEvents()
        APP.setProperty('reducedMotion', True)
        self.chart.set_mode('ranking')
        self.chart.grab()
        self.assertEqual(self.chart._reveal, 1)
        self.assertEqual(self.chart.reveal_animation.state(), QAbstractAnimation.Stopped)
        self.chart.hide()
        self.chart.set_mode('grades')
        self.assertEqual(self.chart._reveal, 1)
        self.assertFalse(self.chart._pending_reveal)


if __name__ == '__main__':
    unittest.main()
