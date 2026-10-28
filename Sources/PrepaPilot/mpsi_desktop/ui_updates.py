"""Small scoped helpers for replacing list contents without intermediate redraws."""
from contextlib import contextmanager
from PySide6.QtCore import QSignalBlocker


@contextmanager
def updating(widget):
    enabled = widget.updatesEnabled()
    blocker = QSignalBlocker(widget)
    widget.setUpdatesEnabled(False)
    try:
        yield
    finally:
        widget.setUpdatesEnabled(enabled)
        blocker.unblock()
