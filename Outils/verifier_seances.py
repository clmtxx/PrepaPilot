"""Render focus-session states using an isolated clock and disposable data."""
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
import tempfile

from chemins import local_root


def main():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'Sources' / 'PrepaPilot'))
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    from mpsi_desktop.context import AppContext
    from mpsi_desktop.focus_session import FocusSession
    from mpsi_desktop.focus_dialogs import FocusSetupDialog, FocusReviewDialog
    from mpsi_desktop.window import MainWindow

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
    output = local_root() / 'Verification' / 'Seances'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, value, trace: errors.append((kind.__name__, str(value)))
    try:
        with tempfile.TemporaryDirectory() as temporary:
            ctx = AppContext(Path(temporary) / 'data')
            ctx.db.set_setting('desktop_reduced_motion', True)
            ctx.db.set_setting('desktop_name', 'Camille')
            window = MainWindow(ctx, show_welcome=False)
            window.show()
            home = window.pages['home']
            clock = [datetime.now().replace(hour=20, minute=0, second=0, microsecond=0) - timedelta(days=1), 1000.0]
            home.focus_session = FocusSession(ctx.db, now=lambda: clock[0], monotonic=lambda: clock[1])
            home.focus_session.start('maths', minutes=40, title='Revoir les intégrales et terminer deux exercices')
            for _ in range(120):
                clock[0] += timedelta(seconds=1)
                clock[1] += 1
                home.focus_session.tick()
            home.focus_session.pause()
            clock[0] += timedelta(minutes=5)
            clock[1] += 300
            home.focus_session.resume()
            for _ in range(180):
                clock[0] += timedelta(seconds=1)
                clock[1] += 1
                home.focus_session.tick()
            home.focus_session.pause()
            home._sync_focus()
            for width, height in ((1360, 900), (1024, 680)):
                window.resize(width, height)
                for theme in ('light', 'dark'):
                    ctx.set_theme(theme)
                    app.processEvents()
                    window.wrappers['home'].ensureWidgetVisible(home.focus_card)
                    app.processEvents()
                    window.grab().save(str(output / f'accueil-{theme}-{width}.png'))
                    home.focus_card.grab().save(str(output / f'seance-{theme}-{width}.png'))
                    if home.width() > window.wrappers['home'].viewport().width():
                        errors.append(('HomeOverflow', f'{theme}/{width}'))
                    setup = FocusSetupDialog(ctx, parent=window)
                    setup.show()
                    app.processEvents()
                    setup.grab().save(str(output / f'preparer-{theme}-{width}.png'))
                    if setup.height() > 640:
                        errors.append(('SetupTooTall', setup.height()))
                    setup.reject()
                    setup.deleteLater()
            home.focus_session.finish()
            for theme in ('light', 'dark'):
                ctx.set_theme(theme)
                review = FocusReviewDialog(ctx, home.focus_session, parent=window)
                review.show()
                app.processEvents()
                review.grab().save(str(output / f'bilan-{theme}.png'))
                if review.height() > 640 or not review.save_button.isVisible():
                    errors.append(('ReviewTooTall', review.height()))
                review.reject()
                review.deleteLater()
            window.close()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            ctx.close()
    finally:
        sys.excepthook = previous_hook
    print('Captures :', output)
    print('Qt/layout errors:', errors)
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
