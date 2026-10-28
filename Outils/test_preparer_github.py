"""Public repository preparation excludes private files and preserves packaging."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

import preparer_github as github


class GithubPreparationTests(TestCase):
    def test_only_selected_sources_and_guides_are_copied(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            source = workspace / "Sources" / "PrepaPilot"
            (source / "assets").mkdir(parents=True)
            (source / "lancer.py").write_text("# public", encoding="utf-8")
            (source / "assets/google-oauth-client.json").write_text("PRIVATE", encoding="utf-8")
            (source / "assets/update-channel.json").write_text('{"repository":"example/PrepaPilot"}', encoding="utf-8")
            (workspace / "Outils").mkdir()
            (workspace / "Outils/tool.py").write_text("# public", encoding="utf-8")
            (workspace / "Outils/private.json").write_text("PRIVATE", encoding="utf-8")
            (workspace / "Application/data").mkdir(parents=True)
            (workspace / "Application/data/private.sqlite3").write_text("PRIVATE", encoding="utf-8")
            destination = workspace / "PrepaPilot-GitHub"
            (destination / "packaging").mkdir(parents=True)
            installer = destination / "packaging/PrepaPilot.iss"
            installer.write_text("# kept", encoding="utf-8")
            selected = [(source / "lancer.py", "lancer.py"),
                        (source / "assets/update-channel.json", "assets/update-channel.json"),
                        (source / "assets/google-oauth-client.json", "assets/google-oauth-client.json")]
            with patch.object(github, "source_files", return_value=selected), patch.object(github, "DOCUMENTATION", set()):
                result, count = github.prepare_github_sources(workspace)
            self.assertEqual(result, destination)
            self.assertEqual(count, 3)
            self.assertEqual(installer.read_text(encoding="utf-8"), "# kept")
            self.assertFalse((destination / "Sources/PrepaPilot/assets/google-oauth-client.json").exists())
            self.assertEqual((destination / "Sources/PrepaPilot/assets/update-channel.json").read_text(encoding="utf-8"), '{"repository":"example/PrepaPilot"}')
            self.assertFalse((destination / "Outils/private.json").exists())
            self.assertFalse((destination / "Application").exists())
            self.assertIn("Sources/PrepaPilot/lancer.py", (destination / "SOURCES-SHA256.json").read_text(encoding="utf-8"))

    def test_prepared_repository_cannot_create_nested_copies(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "scripts").mkdir()
            (workspace / "scripts/build_release.py").write_text("# build", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "déjà"):
                github.prepare_github_sources(workspace)


if __name__ == "__main__":
    main()
