"""Panel depth is visible, bounded and returns cleanly to the native page."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QAbstractAnimation, QEvent, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget
from mpsi_desktop.page_transition import PageTransition

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class PanelMotionTests(unittest.TestCase):
    def setUp(self):
        self.motion = APP.property('reducedMotion')
        APP.setProperty('reducedMotion', False)
        self.window = QWidget()
        self.window.ctx = SimpleNamespace(theme='light')
        self.window.resize(720, 440)
        self.window.central = QWidget(self.window)
        self.window.central.resize(720, 440)
        self.layer = PageTransition(self.window)
        self.window.show()
        APP.processEvents()
        self.before = self.image('#A74D42', 'Previous page')
        self.after = self.image('#308466', 'Destination page')

    def tearDown(self):
        self.layer.shutdown()
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        APP.setProperty('reducedMotion', self.motion)

    def image(self, color, text):
        image = QPixmap(720, 440)
        image.fill(QColor(color))
        painter = QPainter(image)
        painter.setPen(QColor('#FFFFFF'))
        painter.drawText(QRect(25, 20, 600, 50), Qt.AlignLeft | Qt.AlignVCenter, text)
        painter.fillRect(QRect(25, 100, 70, 220), QColor('#ECE5D6'))
        painter.end()
        return image

    def start(self, direction=1):
        self.layer.start(self.before, self.after, QRect(0, 0, 720, 440), direction)
        self.layer.animation.pause()

    def test_exact_first_and_last_frame_do_not_shift_or_blend_text(self):
        self.start()
        self.layer.advance(0)
        self.assertEqual(self.layer.grab().toImage(), self.before.toImage())
        self.layer.advance(1)
        self.assertEqual(self.layer.grab().toImage(), self.after.toImage())
        self.layer.animation.resume()
        self.layer.animation.setCurrentTime(self.layer.animation.duration())
        self.assertFalse(self.layer.isVisible())
        self.assertTrue(self.layer.before.isNull())
        self.assertTrue(self.layer.after.isNull())
        self.assertTrue(self.layer._light.isNull())

    def test_entry_is_opaque_by_middle_and_displacement_is_directional(self):
        self.start()
        self.layer.advance(.35)
        forward = self.layer.grab().toImage()
        # The central reading area contains only destination content, even while
        # the panel continues to move: old text does not bleed through it.
        self.assertEqual(forward.pixelColor(360, 220), QColor('#308466'))
        frame = self.layer.frame_layout()
        self.assertGreater(frame['incoming'].left(), 70)
        self.assertEqual(frame['opacity'], 1)
        self.start(-1)
        self.layer.advance(.35)
        backward = self.layer.grab().toImage()
        self.assertLess(self.layer.frame_layout()['incoming'].left(), -50)
        self.assertNotEqual(forward, backward)
        self.assertEqual(backward.pixelColor(360, 220), QColor('#308466'))

    def test_motion_is_visible_and_responsive_without_live_geometry_changes(self):
        self.start()
        geometry = self.window.central.geometry()
        frames = []
        before_key, after_key = self.layer.before.cacheKey(), self.layer.after.cacheKey()
        with patch.object(self.layer, 'capture', side_effect=AssertionError('No recapture')):
            for progress in (0, .2, .5, .8, 1):
                self.layer.advance(progress)
                frames.append(self.layer.grab().toImage())
        self.assertTrue(all(frames[index] != frames[index + 1] for index in range(4)))
        self.assertEqual(self.window.central.geometry(), geometry)
        self.assertEqual((self.layer.before.cacheKey(), self.layer.after.cacheKey()), (before_key, after_key))
        self.assertEqual(self.layer.animation.loopCount(), 1)
        self.assertTrue(500 <= self.layer.animation.duration() <= 560)
        for width in (320, 720, 1360, 3840):
            self.layer.resize(width, 440)
            self.assertTrue(100 <= self.layer.frame_layout(.5)['distance'] <= 180)

    def test_direct_large_images_are_bounded_and_configuration_survives_start(self):
        large = QPixmap(2048, 2048)
        large.fill(QColor('#EDE8DE'))
        self.layer.configure(accent='#A34469')
        self.layer.start(large, large, QRect(0, 0, 720, 440), 1)
        self.layer.animation.pause()
        self.assertEqual(self.layer._accent.name(), '#a34469')
        for image in (self.layer.before, self.layer.after):
            self.assertLessEqual(image.width() * image.height(), self.layer.MAX_CAPTURE_PIXELS)
        self.layer.finish()
        self.layer.configure(accent='invalid colour')
        self.start()
        self.assertTrue(self.layer._accent.isValid())

    def test_hide_reduced_motion_and_new_inputs_release_every_capture_immediately(self):
        for cancel in (self.layer.hide, lambda: self.window.hide(),
                       lambda: APP.setProperty('reducedMotion', True),
                       lambda: APP.sendEvent(self.window, QEvent(QEvent.WindowDeactivate))):
            self.window.show()
            APP.processEvents()
            APP.setProperty('reducedMotion', False)
            self.start()
            self.layer.advance(.4)
            cancel()
            self.assertEqual(self.layer.animation.state(), QAbstractAnimation.Stopped)
            self.assertTrue(self.layer.before.isNull())
            self.assertTrue(self.layer.after.isNull())
            self.assertTrue(self.layer._light.isNull())


if __name__ == '__main__':
    unittest.main()
