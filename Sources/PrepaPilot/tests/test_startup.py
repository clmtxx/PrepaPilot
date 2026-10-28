"""The disposable loading screen must never keep the application alive."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import lancer
from mpsi_desktop.startup import StartupScreen


class StartupControllerTests(unittest.TestCase):
    def test_messages_and_graceful_close_reach_only_the_owned_process(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'messages.jsonl'
            script = "import sys; from pathlib import Path; Path(sys.argv[1]).write_text(sys.stdin.read(), encoding='utf-8')"
            screen = StartupScreen([sys.executable, '-B', '-c', script, str(output)])
            screen.start()
            process = screen.process
            screen.update('Préparation des pages…', theme='dark', reduced_motion=True)
            screen.close()
            screen.close()
            self.assertIsNone(screen.process)
            self.assertEqual(process.returncode, 0)
            messages = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(messages[-2], dict(status='Préparation des pages…', theme='dark', reduced_motion=True))
            self.assertEqual(messages[-1], {'close': True})

    def test_helper_failure_cannot_prevent_startup_or_cleanup(self):
        screen = StartupScreen(['prepapilot-nonexistent-helper'])
        screen.start()
        screen.update('Chargement…')
        screen.close()
        self.assertIsNone(screen.process)
        screen = StartupScreen([sys.executable, '-B', '-c', 'raise SystemExit(1)'])
        screen.start()
        process = screen.process
        process.wait(timeout=5)
        screen.update('Chargement…')
        screen.close()
        self.assertEqual(process.returncode, 1)

    def test_unresponsive_owned_helper_is_reaped_without_long_delay(self):
        screen = StartupScreen([sys.executable, '-B', '-c', 'import time; time.sleep(60)'])
        screen.start()
        process = screen.process
        started = time.monotonic()
        screen.close()
        self.assertLess(time.monotonic() - started, 3)
        self.assertIsNotNone(process.poll())

    def test_launcher_always_closes_feedback_when_loading_fails(self):
        def fail(**kwargs):
            raise RuntimeError('Simulated startup failure')
        module = types.SimpleNamespace(main=fail)
        with patch.object(sys, 'argv', ['lancer.py']), patch.dict(sys.modules, {'mpsi_desktop.main': module}), \
             patch('mpsi_desktop.startup.StartupScreen') as factory:
            with self.assertRaisesRegex(RuntimeError, 'Simulated startup failure'):
                lancer.launch()
            factory.return_value.start.assert_called_once()
            factory.return_value.close.assert_called_once()

    def test_self_test_does_not_spawn_external_feedback(self):
        module = types.SimpleNamespace(main=lambda **kwargs: 0)
        with patch.object(sys, 'argv', ['lancer.py', '--self-test']), patch.dict(sys.modules, {'mpsi_desktop.main': module}), \
             patch('mpsi_desktop.startup.StartupScreen') as factory:
            self.assertEqual(lancer.launch(), 0)
            factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
