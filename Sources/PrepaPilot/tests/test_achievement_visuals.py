"""Cached trophy rendering, finite motion and stable achievement widgets."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import datetime
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from PySide6.QtCore import QAbstractAnimation, QEvent, QPointF, QTimer
from PySide6.QtWidgets import QAbstractItemView, QApplication, QTableWidget, QWidget

from mpsi_desktop.achievement_panel import AchievementHistoryDialog, AchievementPanel, _amount
from mpsi_desktop.achievement_visuals import BadgeFigure, TIER_NAMES
from mpsi_desktop.achievements import reconcile, snapshot


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class _Journal:
    def __init__(self):
        self.settings = {}
        self.entries = []

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = value

    def list_time_entries(self):
        return self.entries

    def study_categories(self):
        return {'maths'}

    def _time_now(self):
        return datetime(2026, 10, 18, 20)


class AchievementVisualTests(unittest.TestCase):
    def setUp(self):
        self.motion, self.theme = APP.property('reducedMotion'), APP.property('visualTheme')
        APP.setProperty('reducedMotion', False)
        APP.setProperty('visualTheme', 'light')
        self.widgets = []
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append(str(value))

    def tearDown(self):
        for widget in self.widgets:
            if isinstance(widget, AchievementPanel):
                widget.shutdown()
            widget.close()
            widget.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        APP.setProperty('reducedMotion', self.motion)
        APP.setProperty('visualTheme', self.theme)
        sys.excepthook = self.old_hook
        self.assertEqual(self.errors, [])

    def figure(self, **options):
        widget = BadgeFigure(**options)
        self.widgets.append(widget)
        widget.resize(220, 200)
        widget.show()
        APP.processEvents()
        return widget

    @staticmethod
    def cached(figure):
        return {name: layer.cacheKey() for name, layer in figure._artwork.layers.items()}

    def test_hover_and_celebration_reuse_artwork_without_idle_render_loop(self):
        figure = self.figure(tier=4)
        resting = figure.grab().toImage()
        cached = self.cached(figure)
        self.assertEqual(set(cached), {'studio', 'medal'})
        figure._move_to(QPointF(1, -1))
        figure.parallax_animation.setCurrentTime(figure.parallax_animation.duration())
        self.assertNotEqual(resting, figure.grab().toImage())
        self.assertEqual(cached, self.cached(figure))
        figure.celebrate()
        figure.reveal_animation.setCurrentTime(200)
        self.assertEqual(cached, self.cached(figure))
        self.assertFalse(figure.grab().isNull())
        figure.reveal_animation.setCurrentTime(figure.reveal_animation.duration())
        self.assertEqual(figure._reveal, 1)
        for animation in figure.findChildren(QAbstractAnimation):
            self.assertEqual(animation.loopCount(), 1)
            self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(figure.findChildren(QTimer), [])

    def test_tiers_locked_state_and_theme_rebuild_only_current_cache(self):
        figure = self.figure()
        for theme in ('light', 'dark'):
            APP.setProperty('visualTheme', theme)
            images = []
            for index, name in enumerate(TIER_NAMES):
                figure.set_badge(index, 'sleep_streak', False)
                image = figure.grab().toImage()
                self.assertFalse(image.isNull())
                self.assertIn(name, figure.accessibleName())
                self.assertIn('obtenue', figure.accessibleName())
                for previous in images:
                    self.assertNotEqual(previous, image)
                images.append(image)
                cached = self.cached(figure)
                figure.set_badge(index, 'sleep_streak', False)
                self.assertEqual(image, figure.grab().toImage())
                self.assertEqual(cached, self.cached(figure))
                figure.set_badge(index, 'sleep_streak', True)
                self.assertNotEqual(image, figure.grab().toImage())
                self.assertIn('à débloquer', figure.accessibleName())
                self.assertEqual(set(figure._artwork.layers), {'studio', 'medal'})

    def test_reduced_motion_immediately_stops_live_effects_and_future_reveals(self):
        figure = self.figure(tier=2)
        figure._move_to(QPointF(1, 1))
        figure.parallax_animation.setCurrentTime(80)
        figure.celebrate()
        figure.reveal_animation.setCurrentTime(200)
        APP.setProperty('reducedMotion', True)
        self.assertEqual(figure._offset, QPointF())
        self.assertEqual(figure._reveal, 1)
        figure.celebrate()
        figure._move_to(QPointF(-1, -1))
        self.assertTrue(all(animation.state() == QAbstractAnimation.State.Stopped
                            for animation in figure.findChildren(QAbstractAnimation)))
        self.assertFalse(figure.grab().isNull())

    def test_hidden_and_locked_figures_do_not_run_celebrations(self):
        figure = self.figure(locked=True)
        figure.celebrate()
        self.assertEqual(figure.reveal_animation.state(), QAbstractAnimation.State.Stopped)
        figure.set_badge(3, 'work_month', False)
        figure.celebrate()
        self.assertEqual(figure.reveal_animation.state(), QAbstractAnimation.State.Running)
        figure.hide()
        self.assertEqual(figure._reveal, 1)
        self.assertEqual(figure.reveal_animation.state(), QAbstractAnimation.State.Stopped)
        figure.celebrate()
        self.assertEqual(figure.reveal_animation.state(), QAbstractAnimation.State.Stopped)
        figure.show()
        APP.processEvents()
        self.assertEqual(figure.reveal_animation.state(), QAbstractAnimation.State.Stopped)

    def test_refresh_preserves_widgets_and_cached_illustrations(self):
        db = _Journal()
        ctx = SimpleNamespace(theme='light', db=db)
        panel = AchievementPanel(ctx)
        self.widgets.append(panel)
        panel.resize(940, 1800)
        report = snapshot(db)
        panel.refresh(report)
        panel.show()
        APP.processEvents()
        panel.grab()
        identities = tuple(id(widget) for widget in panel.findChildren(QWidget))
        figures = panel.findChildren(BadgeFigure)
        caches = [self.cached(figure) for figure in figures]
        for _ in range(4):
            panel.refresh(report)
            panel.grab()
        self.assertEqual(identities, tuple(id(widget) for widget in panel.findChildren(QWidget)))
        self.assertEqual(caches, [self.cached(figure) for figure in figures])
        self.assertEqual(db.settings, {})

    def test_pending_reveal_uses_earned_medal_and_shutdown_cancels_effects(self):
        db = _Journal()
        panel = AchievementPanel(SimpleNamespace(theme='light', db=db))
        self.widgets.append(panel)
        panel.resize(940, 1800)
        panel.refresh(snapshot(db))
        db.entries = [dict(category='sport', start_at='2026-10-12T09:00',
                           end_at='2026-10-12T10:00', status='completed', deleted=0)]
        report = reconcile(db)
        panel.celebrate(report['new_awards'])
        self.assertTrue(panel._pending_celebration)
        panel.refresh(report)
        panel.show()
        APP.processEvents()
        self.assertFalse(panel._pending_celebration)
        self.assertFalse(panel.hero_figure.locked)
        self.assertEqual(panel.hero_figure.reveal_animation.state(), QAbstractAnimation.State.Running)
        panel.shutdown()
        panel.celebrate(report['new_awards'])
        self.assertTrue(all(animation.state() == QAbstractAnimation.State.Stopped
                            for animation in panel.findChildren(QAbstractAnimation)))

    def test_sport_collections_have_distinct_embossed_symbols(self):
        figure = self.figure(tier=1, family='work_total')
        book = figure.grab().toImage()
        figure.set_badge(1, 'sport_total', False)
        dumbbell = figure.grab().toImage()
        figure.set_badge(1, 'sport_streak', False)
        flame = figure.grab().toImage()
        self.assertNotEqual(book, dumbbell)
        self.assertNotEqual(book, flame)
        self.assertNotEqual(dumbbell, flame)
        cached = self.cached(figure)
        self.assertEqual(flame, figure.grab().toImage())
        self.assertEqual(cached, self.cached(figure))

    def test_six_quests_and_six_collections_reuse_widgets_when_period_changes(self):
        db = _Journal()
        panel = AchievementPanel(SimpleNamespace(theme='light', db=db))
        self.widgets.append(panel)
        report = snapshot(db)
        panel.refresh(report)
        panel.resize(920, 2200)
        panel.show()
        APP.processEvents()
        self.assertEqual(len(report['quests']), 6)
        self.assertEqual(len(panel.quest_cards), 6)
        self.assertTrue(all(card.isVisible() for card in panel.quest_cards))
        self.assertEqual(len(panel.family_cards), 6)
        self.assertTrue(all(card.isVisible() for card in panel.family_cards.values()))
        self.assertEqual(panel.collection_count.text(), '0 / 30')
        self.assertIn('semaine', panel.family_cards['sport_streak'].value.text())
        self.assertEqual(_amount(1, 'weeks'), '1 semaine')
        self.assertEqual(_amount(4, 'weeks'), '4 semaines')
        self.assertLessEqual(panel.minimumSizeHint().width(), 920)
        identities = tuple(id(card) for card in panel.quest_cards)
        fewer = dict(report, quests=report['quests'][:2])
        panel.refresh(fewer)
        self.assertEqual(sum(card.isVisible() for card in panel.quest_cards), 2)
        panel.refresh(report)
        self.assertEqual(identities, tuple(id(card) for card in panel.quest_cards))
        for quest, card in zip(report['quests'], panel.quest_cards):
            if quest['id'].startswith('quest:sport_'):
                self.assertEqual(card.axis, 'sport')
        self.assertEqual(db.settings, {})

    def test_legacy_awards_remain_separate_and_history_is_lazy_bounded_readonly(self):
        db = _Journal()
        panel = AchievementPanel(SimpleNamespace(theme='light', db=db))
        self.widgets.append(panel)
        report = snapshot(db)
        legacy = [dict(id=f'old-{index}', title='Ancienne collection', tier='Bronze',
                       points=100, earned_at='2026-10-12T10:00:00', legacy=True)
                  for index in range(105)]
        legacy[0].update(tier='Quête', period_label='Du 05/10 au 11/10/2026')
        legacy[1].update(target=300, unit='minutes')
        report.update(legacy_count=105, legacy_points=10500, legacy_awards=legacy,
                      points=10500, level=22, level_floor=10500, next_level_points=11000)
        panel.refresh(report)
        panel.resize(920, 2200)
        panel.show()
        APP.processEvents()
        self.assertTrue(panel.legacy_info.isVisible())
        self.assertIn('105', panel.legacy_caption.text())
        self.assertIn('10\u202f500 XP', panel.hero_stats.text())
        self.assertEqual(panel.collection_count.text(), '0 / 30')
        self.assertTrue(panel.hero_figure.locked)
        self.assertEqual(panel.findChildren(QTableWidget), [])
        with patch.object(AchievementHistoryDialog, 'exec', return_value=0) as execute:
            panel.show_history()
            execute.assert_called_once()
            table = panel.findChildren(QTableWidget)[0]
            self.assertEqual(table.rowCount(), 100)
            self.assertEqual(table.item(0, 0).text(), 'Ancienne collection\nDu 05/10 au 11/10/2026')
            self.assertEqual(table.item(1, 0).text(), 'Ancienne collection\nAncien objectif : 5 h 00')
            self.assertEqual(table.item(0, 2).text(), '12/10/2026')
            self.assertEqual(table.item(0, 3).text(), '100')
            self.assertEqual(table.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers)
            dialog = panel.findChild(AchievementHistoryDialog)
            self.assertIn('100', dialog.history_hint.text())
            self.assertIn('105', dialog.history_hint.text())
        panel.refresh(snapshot(db))
        self.assertFalse(panel.legacy_info.isVisible())
        self.assertEqual(db.settings, {})


if __name__ == '__main__':
    unittest.main()
