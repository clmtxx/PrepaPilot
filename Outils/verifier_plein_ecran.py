"""Native Windows fullscreen geometry verification with temporary data."""
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Sources'/'PrepaPilot'))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext
from mpsi_desktop.window import MainWindow

app=QApplication([])
app.setStyle('Fusion')
temporary=tempfile.TemporaryDirectory(prefix='prepapilot-fullscreen-')
ctx=AppContext(Path(temporary.name)/'data')
window=MainWindow(ctx,show_welcome=False)
window.show()


def report(label):
    print(label, 'state:',window.windowState(), 'full:',window.isFullScreen(),
          'frame:',window.frameGeometry().getRect(), 'geometry:',window.geometry().getRect(),
          'screen:',window.screen().geometry().getRect(), flush=True)
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        getter=ctypes.WinDLL('user32',use_last_error=True).GetWindowLongW
        getter.argtypes=[wintypes.HWND,ctypes.c_int]
        getter.restype=ctypes.c_long
        style=getter(int(window.winId()),-16)
        print('Windows title bar:',bool(style & 0x00C00000),flush=True)


def start():
    report('Windowed')
    window.showMaximized()
    app.processEvents()
    app.processEvents()
    report('Immediate')
    QTimer.singleShot(250,finish)


def finish():
    report('Settled')
    window.exit_fullscreen()
    app.processEvents()
    report('Restored')
    window.close()
    app.quit()


QTimer.singleShot(150,start)
app.exec()
ctx.close()
temporary.cleanup()
