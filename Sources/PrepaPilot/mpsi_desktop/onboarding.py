"""Initial configuration, kept separate from the future guided tutorials.

Run before constructing pages: they materialize dated timetable entries.
Tutorial progress is versioned independently so a later tutorial can be offered
to an existing user without reopening or replacing their configuration.
"""
from .i18n import tr
from PySide6.QtWidgets import QApplication, QDialog


def tutorial_needed(db, version):
    """A future tutorial calls this with its own positive content version."""
    return version > 0 and db.get_setting("desktop_tutorial_version", 0) < version


def complete_tutorial(db, version):
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError(tr("La version du tutoriel doit être un entier positif."))
    db.set_setting("desktop_tutorial_version", version)


def run_initial_setup(ctx, parent=None):
    if ctx.db.get_setting("setup_completed", False):
        return True
    # Local imports keep the startup flow independent from the window/pages.
    from .window import WelcomeDialog
    from .schedule_setup import SetupDialog

    app = QApplication.instance()
    previous = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)
    try:
        if not ctx.db.get_setting("desktop_welcomed", False):
            if WelcomeDialog(ctx, parent).exec() != QDialog.Accepted:
                return False
        return SetupDialog(ctx, parent, first_run=True).exec() == QDialog.Accepted
    finally:
        app.setQuitOnLastWindowClosed(previous)
