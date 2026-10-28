"""Reproducible UI timings on synthetic data; never opens the installed database."""
import argparse
import inspect
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from datetime import date, timedelta

from chemins import local_root

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources' / 'PrepaPilot'))
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext
from mpsi_desktop.window import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='mesure')
    args = parser.parse_args()
    if not args.label.replace('-', '').replace('_', '').isalnum():
        parser.error('Utilise un nom court avec lettres, chiffres et tirets.')
    app = QApplication([])
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)
    errors = []
    sys.excepthook = lambda kind, value, tb: errors.append(f'{kind.__name__}: {value}')
    results = {'platform': app.platformName(), 'grades': 2000, 'documents': 600, 'activity_days': 400}
    with tempfile.TemporaryDirectory(prefix='prepapilot-fluidite-') as temporary:
        ctx = AppContext(Path(temporary) / 'data')
        ctx.db.set_setting('desktop_reduced_motion', False)
        start = date(ctx.year, 8, 1)
        with ctx.db._lock, ctx.db._connection:
            ctx.db._connection.executemany(
                'INSERT INTO grades(subject,kind,score,scale,graded_on,label,coefficient) VALUES (?,?,?,?,?,?,?)',
                [('maths', 'cours', 10 + i % 10, 20, (start + timedelta(days=i % 365)).isoformat(), f'Évaluation {i}', 1) for i in range(2000)])
        sample = Path(temporary) / 'cours.txt'
        sample.write_text('Document fictif pour les mesures de fluidité.', encoding='utf-8')
        for i in range(600):
            ctx.db.import_document(sample, 'maths', 'cours', title=f'Document {i:04d}')
        for i in range(1, 401):
            day = (date.today() - timedelta(days=i)).isoformat()
            for category, begin, end in [('sommeil', '00:00', '07:00'), ('maths', '09:00', '12:00'), ('sport', '17:00', '18:00'), ('detente', '20:00', '21:00')]:
                ctx.db.add_time_entry(category, f'{day}T{begin}', f'{day}T{end}', status='completed')
        clock = time.perf_counter()
        window = MainWindow(ctx, show_welcome=False)
        window.resize(1360, 900)
        window.show()
        app.processEvents()
        results['startup_ms'] = round((time.perf_counter() - clock) * 1000, 2)

        def measure(name, callback, repeats=5):
            values, queries = [], []
            for _ in range(repeats):
                app.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
                statements = []
                ctx.db._connection.set_trace_callback(statements.append)
                began = time.perf_counter()
                callback()
                values.append((time.perf_counter() - began) * 1000)
                ctx.db._connection.set_trace_callback(None)
                queries.append(len(statements))
            results[name] = {'median_ms': round(statistics.median(values), 2), 'max_ms': round(max(values), 2), 'sql_statements': statistics.median(queries)}

        measure('grade_lookup', ctx.grades)
        measure('notes_refresh', window.pages['notes'].refresh)
        measure('documents_refresh', window.pages['documents'].refresh)
        measure('progression_refresh', window.pages['progression'].refresh)
        measure('all_data_notification', ctx.mark_changed)
        scoped = 'domains' in inspect.signature(ctx.mark_changed).parameters
        measure('memory_notification', lambda: ctx.mark_changed('memories') if scoped else ctx.mark_changed())
        measure('page_capture', lambda: window.transition.capture(window.stack) if hasattr(window.transition, 'capture') else window.stack.grab())
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        ctx.close()
    results['errors'] = errors
    output = local_root() / 'Verification' / 'Fluidite'
    output.mkdir(parents=True, exist_ok=True)
    path = output / (args.label + '.json')
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(path)
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
