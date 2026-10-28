"""Check grade comparisons with disposable data and save visual QA captures."""
from __future__ import annotations

import os
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile

from chemins import local_root


def main() -> int:
    # This tool never opens the portable installation's personal database.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "Sources" / "PrepaPilot"))
    from PySide6.QtCore import QEvent, QLocale, Qt
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QScrollArea
    from mpsi_desktop.context import AppContext, prepare_data
    from mpsi_desktop.notes import GradeDialog
    from mpsi_desktop.window import MainWindow

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    QLocale.setDefault(QLocale("fr_FR"))
    for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "segoeuil.ttf", "seguiemj.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)
    errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, value, _tb: errors.append((kind.__name__, str(value)))
    output = local_root() / "Verification" / "Notes"
    output.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="prepapilot-notes-qa-") as temporary, ExitStack() as cleanup:
            data, _ = prepare_data(temporary, migrate=False)
            ctx = AppContext(data)
            cleanup.callback(ctx.close)
            ctx.db.set_setting("desktop_name", "Camille")
            ctx.db.set_setting("desktop_program", "Études de biologie")
            ctx.db.set_setting("desktop_reduced_motion", True)
            ctx.db.save_subjects([
                dict(id="maths", name="Biologie cellulaire", color="#287D5B", active=True),
                dict(id="anglais", name="Anglais", color="#0071E3", active=True),
            ])
            examples = [
                (3, "Examen", 7, 10, 5.5, 17, 36),
                (8, "Examen", 14, 20, 12, 12, 36),
                (13, "Projet", 82, 100, 70, 3, 24),
                (18, "Examen", 16, 20, None, None, None),
                (23, "Projet", 18, 20, 15, 1, 24),
                (28, "Examen", 5, 10, 0, 36, 36),
            ]
            for day, kind, score, scale, average, rank, size in examples:
                ctx.db.add_grade(
                    "maths", kind, score, scale, f"{ctx.year}-08-{day:02d}",
                    "Évaluation de démonstration", class_average=average, rank=rank, class_size=size,
                )
            ctx.db.add_grade("anglais", "Oral", 15, 20, f"{ctx.year}-08-05", "Sans comparaison")
            window = MainWindow(ctx, show_welcome=False)
            window.show()
            window.navigate("notes", animate=False)
            page = window.pages["notes"]
            wrapper = window.wrappers["notes"]
            for width, height in ((1360, 900), (1024, 680)):
                window.resize(width, height)
                for theme in ("light", "dark"):
                    ctx.set_theme(theme)
                    page.set_subject("maths")
                    for mode in ("grades", "ranking"):
                        page.set_chart_mode(mode)
                        wrapper.verticalScrollBar().setValue(0)
                        QTest.qWait(30)
                        if page.width() > wrapper.viewport().width():
                            errors.append(("PageOverflow", f"{width}/{theme}/{mode}"))
                        name = f"notes-{mode}-{theme}-{width}"
                        window.grab().save(str(output / f"{name}.png"))
                        wrapper.ensureWidgetVisible(page.chart)
                        QTest.qWait(20)
                        page.chart_card.grab().save(str(output / f"{name}-graphique.png"))
                    wrapper.verticalScrollBar().setValue(wrapper.verticalScrollBar().maximum())
                    QTest.qWait(20)
                    window.grab().save(str(output / f"notes-historique-{theme}-{width}.png"))
                    page.set_subject("anglais")
                    page.set_chart_mode("ranking")
                    page.chart_card.grab().save(str(output / f"classement-absent-{theme}-{width}.png"))

                    grade = ctx.db.list_grades("maths")[0]
                    dialog = GradeDialog(ctx, grade=grade, parent=window)
                    dialog.show()
                    QTest.qWait(30)
                    if dialog.height() > 640:
                        errors.append(("DialogTooTall", f"{width}/{theme}: {dialog.height()}"))
                    save_bottom = dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()).y()
                    if save_bottom >= dialog.height() or not dialog.save_button.isVisible():
                        errors.append(("SaveButtonClipped", f"{width}/{theme}"))
                    dialog.grab().save(str(output / f"note-dialogue-{theme}-{width}.png"))
                    QTest.mouseClick(dialog.detail_buttons[1], Qt.MouseButton.LeftButton)
                    QTest.qWait(20)
                    dialog.grab().save(str(output / f"note-classe-{theme}-{width}.png"))
                    for area in dialog.findChildren(QScrollArea):
                        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
                    QTest.qWait(20)
                    dialog.grab().save(str(output / f"note-dialogue-{theme}-{width}-bas.png"))
                    dialog.class_average.setValue(dialog.scale.value() + 1)
                    dialog.save()
                    QTest.qWait(20)
                    if dialog.height() > 640:
                        errors.append(("DialogErrorTooTall", f"{width}/{theme}: {dialog.height()}"))
                    dialog.grab().save(str(output / f"note-erreur-{theme}-{width}.png"))
                    dialog.reject()
                    dialog.deleteLater()
            # Each optional datum survives loading; unavailable values stay unknown.
            rows = ctx.db.list_grades("maths")
            assert len(rows) == 6
            assert any(row["class_average"] == 0 for row in rows)
            assert any(row["rank"] is None and row["class_size"] is None for row in rows)
            window.close()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
    finally:
        sys.excepthook = previous_hook
    print("Captures :", output)
    print("Qt/layout errors:", errors)
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
