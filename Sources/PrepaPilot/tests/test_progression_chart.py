"""Annual chart semantics, input and bounded animation in both themes."""
import os
import sys
import unittest
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolTip

from mpsi_desktop.progression_chart import AnnualProgressionChart
from mpsi_desktop.theme import apply_theme


APP = QApplication.instance() or QApplication([])


def history():
    rows = []
    for index in range(12):
        month = date(2026 + (index + 8) // 12, (index + 8) % 12 + 1, 1)
        recorded = index < 3
        averages = dict(work=120 if index == 0 else 0, sleep=480, sport=25, rest=60) if recorded else None
        totals = {key: value * 30 for key, value in averages.items()} if recorded else dict(work=0, sleep=0, sport=0, rest=0)
        rows.append(dict(month=month, averages=averages, totals=totals, future=index > 3, has_data=recorded, days=30 if index < 4 else 0))
    return rows


class ProgressionChartTests(unittest.TestCase):
    def setUp(self):
        self.previous_motion = APP.property("reducedMotion")
        self.previous_theme = APP.property("visualTheme")
        APP.setProperty("reducedMotion", False)
        apply_theme(APP, "light")
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, error, traceback: self.errors.append((kind.__name__, str(error)))
        self.chart = AnnualProgressionChart(SimpleNamespace(theme="light"))
        self.chart.resize(700, 260)

    def tearDown(self):
        self.chart.close()
        self.chart.deleteLater()
        QToolTip.hideText()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        APP.setProperty("reducedMotion", self.previous_motion)
        if self.previous_theme:
            apply_theme(APP, self.previous_theme)
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def test_zero_unrecorded_and_future_are_distinct_and_data_is_not_mutated(self):
        rows = history()
        original = deepcopy(rows)
        self.chart.set_data(rows, "work")
        self.assertIn("0 h au total", self.chart._detail(1))
        self.assertIn("Aucune activité renseignée", self.chart._detail(3))
        self.assertIn("À venir", self.chart._detail(4))
        self.assertIn("60 h au total", self.chart._detail(0))
        self.assertIn("2 h / jour", self.chart._detail(0))
        self.assertIn("travail", self.chart.accessibleName())
        self.chart.show()
        APP.processEvents()
        self.chart.grab()
        self.assertEqual(rows, original)
        rows[0]["averages"]["work"] = 999
        self.assertEqual(self.chart.rows[0]["averages"]["work"], 120)

    def test_keyboard_exposes_details_without_requiring_hover(self):
        APP.setProperty("reducedMotion", True)
        self.chart.set_data(history(), "sleep")
        self.chart.show()
        self.chart.setFocus()
        APP.processEvents()
        QTest.keyClick(self.chart, Qt.Key_Home)
        self.assertEqual(self.chart._selected_index, 0)
        self.assertIn("Septembre 2026", self.chart.accessibleDescription())
        self.assertIn("8 h / jour", self.chart.accessibleDescription())
        QTest.keyClick(self.chart, Qt.Key_Right)
        self.assertEqual(self.chart._selected_index, 1)
        QTest.keyClick(self.chart, Qt.Key_End)
        self.assertEqual(self.chart._selected_index, 11)
        self.assertIn("À venir", self.chart.accessibleDescription())
        QTest.keyClick(self.chart, Qt.Key_Left)
        self.assertEqual(self.chart._selected_index, 10)
        QTest.keyClick(self.chart, Qt.Key_Escape)
        self.assertEqual(self.chart._selected_index, -1)

    def test_hover_details_match_selected_month_and_leave_dismisses(self):
        APP.setProperty("reducedMotion", True)
        self.chart.set_data(history(), "sport")
        self.chart.show()
        APP.processEvents()
        self.chart.clearFocus()
        plot = self.chart._plot()
        point = QPointF(plot.left() + plot.width() / 24, plot.center().y())
        event = QMouseEvent(QEvent.MouseMove, point, point, self.chart.mapToGlobal(point.toPoint()), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        APP.sendEvent(self.chart, event)
        self.assertEqual(self.chart._hover_index, 0)
        self.assertIn("Septembre 2026", QToolTip.text())
        self.assertIn("12,5 h au total", self.chart.accessibleDescription())
        APP.sendEvent(self.chart, QEvent(QEvent.Leave))
        self.assertEqual(self.chart._hover_index, -1)
        self.assertNotIn("Septembre", self.chart.accessibleDescription())

    def test_animation_is_bounded_skips_identical_data_and_stops_on_hide(self):
        self.chart.set_data(history(), "work")
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Stopped)
        self.chart.show()
        APP.processEvents()
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Running)
        self.chart.animation.setCurrentTime(150)
        self.chart.set_data(history(), "work")
        self.assertGreaterEqual(self.chart.animation.currentTime(), 150)
        self.chart.hide()
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(self.chart._progress, 1)
        self.chart.show()
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Stopped)
        self.chart.set_data(history(), "sport")
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Running)
        self.chart.animation.setCurrentTime(self.chart.animation.duration())
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(self.chart._progress, 1)

    def test_live_reduced_motion_stops_immediately_and_keeps_rendering(self):
        self.chart.show()
        self.chart.set_data(history(), "work")
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Running)
        APP.setProperty("reducedMotion", True)
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(self.chart._progress, 1)
        self.chart.set_data(history(), "rest")
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Stopped)
        self.assertFalse(self.chart.grab().isNull())

    def test_axes_render_in_both_themes_and_compact_width(self):
        APP.setProperty("reducedMotion", True)
        self.chart.show()
        for width in (580, 920):
            self.chart.resize(width, 260)
            for theme in ("light", "dark"):
                apply_theme(APP, theme)
                for axis in ("work", "sleep", "sport", "rest"):
                    self.chart.set_data(history(), axis)
                    self.chart._selected_index = 0
                    image = self.chart.grab().toImage()
                    self.assertFalse(image.isNull())
                    self.assertEqual(image.width(), width)
        self.assertLessEqual(self.chart.minimumHeight(), 260)

    def test_minimized_window_does_not_start_animation(self):
        self.chart.showMinimized()
        APP.processEvents()
        self.chart.set_data(history(), "sleep")
        self.assertEqual(self.chart.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(self.chart._progress, 1)


if __name__ == "__main__":
    unittest.main()
