"""Distribution privacy, integrity, portability and replacement regressions."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from zipfile import ZipFile
import json

from chemins import local_root
import preparer_projet as project
import partager_application as sharing


class ProjectDistributionTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve() / "Mon projet"
        self.workspace.mkdir()
        self.put("LIRE-MOI.md", "# Projet partageable\n")
        self.put(".gitignore", "data/\n__pycache__/\n")
        self.put("Ouvrir PrepaPilot.cmd", '@echo off\nstart "" "%~dp0Application\\PrepaPilot\\PrepaPilot.exe"\n')
        self.put("Application/PrepaPilot/PrepaPilot.exe", b"test binary")
        self.put("Application/PrepaPilot/_internal/runtime.dll", b"test runtime")
        self.put("Application/PrepaPilot/VERIFICATION.md", "Test fixture")
        for name in project.SOURCE_FILES:
            self.put("Sources/PrepaPilot/" + name, "# source\n")
        for name in project.ASSETS:
            self.put("Sources/PrepaPilot/assets/" + name, "asset")
        for name in project.CODE_DIRS:
            self.put(f"Sources/PrepaPilot/{name}/__init__.py", "# code")
        self.put("Sources/PrepaPilot/licenses/Qt/LICENSE.txt", "license")
        for name in project.DOCUMENTATION:
            self.put("Documentation/" + name, "# Guide")
        for name in ("chemins.py", "preparer_projet.py", "partager_application.py", "README.md"):
            self.put("Outils/" + name, "# tool")

    def put(self, name, contents):
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, bytes):
            path.write_bytes(contents)
        else:
            path.write_text(contents, encoding="utf-8")
        return path

    def test_complete_project_excludes_private_runtime_and_redundant_files(self):
        private = [
            "Application/PrepaPilot/data/mpsi.sqlite3", "Application/PrepaPilot/data/documents/cours.pdf",
            "Application/PrepaPilot/data/cloud/credentials.bin", "Application/PrepaPilot/data/cloud/client.json",
            "Application/PrepaPilot/backups/mes-notes.prepapilot", "Application/PrepaPilot/self-test.log",
            "Sources/PrepaPilot/documents/cours.md", "Sources/PrepaPilot/.env", "Sources/PrepaPilot/notes.txt",
            "Sources/PrepaPilot/mpsi_desktop/__pycache__/app.pyc", "Sources/PrepaPilot/assets/photo.png",
            "Sources/PrepaPilot/tests/data/personnel.py", "Documentation/Apercus/ecran.png",
            "Documentation/Emploi-du-temps/horaires.pdf", "Documentation/Validation-native/test.log",
            "Outils/build/personnel.py", "Outils/Livraison/PrepaPilot.exe", "Outils/__pycache__/tool.pyc",
            "Archives/Anciennes-versions/secrets.md", "Partage/ancien.zip",
        ]
        for name in private:
            self.put(name, "PRIVATE_SENTINEL")
        result = project.prepare_project(self.workspace)
        manifest = sharing.verify_folder(result, "project", project.project_allowed)
        archive = result.with_suffix(".zip")
        self.assertEqual(manifest, sharing.verify_zip(archive, result.name, "project", project.project_allowed))
        names = set(manifest["files"])
        self.assertFalse(names.intersection(private))
        self.assertTrue({"LIRE-MOI.md", "Outils/chemins.py", "Application/PrepaPilot/PrepaPilot.exe"} <= names)
        self.assertTrue(all((result / name).read_bytes() != b"PRIVATE_SENTINEL" for name in names))
        with ZipFile(archive) as bundle:
            self.assertEqual(len(bundle.namelist()), manifest["file_count"] + 1)
        self.assertIn(sharing.digest_file(archive), archive.with_suffix(".zip.sha256").read_text())
        for name in private:
            self.assertTrue((self.workspace / name).exists(), name)

    def test_explicit_oauth_application_configuration_without_user_tokens(self):
        name = 'Sources/PrepaPilot/assets/google-oauth-client.json'
        config = '{"installed":{"client_id":"fixture.apps.googleusercontent.com"}}'
        self.put(name, config)
        self.put('Application/PrepaPilot/data/cloud/credentials.bin', 'PRIVATE_GOOGLE_TOKEN')
        result = project.prepare_project(self.workspace)
        self.assertEqual((result / name).read_text(encoding='utf-8'), config)
        manifest = sharing.verify_folder(result, 'project', project.project_allowed)
        self.assertFalse(any('/data/' in name for name in manifest['files']))

    def test_rebuild_preserves_previous_folder_zip_and_personal_data(self):
        result = project.prepare_project(self.workspace)
        old_zip = result.with_suffix(".zip").read_bytes()
        (result / "LIRE-MOI.md").write_text("OLD EDITION", encoding="utf-8")
        self.put("Application/PrepaPilot/data/mpsi.sqlite3", b"personal")
        self.put("LIRE-MOI.md", "NEW EDITION")
        project.prepare_project(self.workspace)
        history = local_root(self.workspace) / "Archives" / "Distributions"
        entries = list(history.iterdir())
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0] / result.name / "LIRE-MOI.md").read_text(), "OLD EDITION")
        self.assertEqual((entries[0] / "PrepaPilot-Projet.zip").read_bytes(), old_zip)
        self.assertEqual((result / "LIRE-MOI.md").read_text(), "NEW EDITION")
        self.assertEqual((self.workspace / "Application/PrepaPilot/data/mpsi.sqlite3").read_bytes(), b"personal")
        self.assertFalse(history.is_relative_to(self.workspace))

    def test_wrong_destination_cannot_replace_source_or_application(self):
        for destination in (self.workspace, self.workspace / "Sources/PrepaPilot", self.workspace / "Application/PrepaPilot", self.workspace.parent / "export", self.workspace / "Partage"):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                project.prepare_project(self.workspace, destination)
        self.assertTrue((self.workspace / "Sources/PrepaPilot/lancer.py").is_file())
        self.assertTrue((self.workspace / "Application/PrepaPilot/PrepaPilot.exe").is_file())

    def test_linked_output_or_source_is_rejected(self):
        real = sharing.is_link
        with patch.object(sharing, "is_link", side_effect=lambda path: path.name == "Partage" or real(path)), self.assertRaises(ValueError):
            project.prepare_project(self.workspace)
        with patch.object(project, "is_link", side_effect=lambda path: path == self.workspace / "Sources/PrepaPilot" or real(path)), self.assertRaises(ValueError):
            project.prepare_project(self.workspace)

    def test_private_file_inside_native_runtime_blocks_publish(self):
        self.put("Application/PrepaPilot/_internal/data/mpsi.sqlite3", "secret")
        with self.assertRaises(ValueError):
            project.prepare_project(self.workspace)
        self.assertFalse((self.workspace / "Partage/PrepaPilot-Projet").exists())

    def test_missing_required_file_preserves_existing_distribution(self):
        result = project.prepare_project(self.workspace)
        previous = result.with_suffix(".zip").read_bytes()
        (self.workspace / "Sources/PrepaPilot/requirements.txt").unlink()
        with self.assertRaises(ValueError):
            project.prepare_project(self.workspace)
        self.assertEqual(result.with_suffix(".zip").read_bytes(), previous)
        sharing.verify_folder(result, "project", project.project_allowed)

    def test_hash_extra_file_and_manifest_count_tampering_rejected(self):
        result = project.prepare_project(self.workspace)
        old = (result / "LIRE-MOI.md").read_bytes()
        (result / "LIRE-MOI.md").write_text("TAMPERED")
        with self.assertRaises(ValueError):
            sharing.verify_folder(result, "project", project.project_allowed)
        (result / "LIRE-MOI.md").write_bytes(old)
        with ZipFile(result.with_suffix(".zip"), "a") as bundle:
            bundle.writestr("PrepaPilot-Projet/data/mpsi.sqlite3", b"unexpected")
        with self.assertRaises(ValueError):
            sharing.verify_zip(result.with_suffix(".zip"), result.name, "project", project.project_allowed)
        manifest_path = result / sharing.MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["file_count"] += 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sharing.verify_folder(result, "project", project.project_allowed)

    def test_publish_failure_restores_previous_folder_zip(self):
        result = project.prepare_project(self.workspace)
        old_zip = result.with_suffix(".zip").read_bytes()
        old_guide = (result / "LIRE-MOI.md").read_bytes()
        self.put("LIRE-MOI.md", "NEW")
        rename = Path.rename
        def fail_once(path, target):
            if path.name == "PrepaPilot-Projet.zip" and path.parent.name.startswith(".projet-"):
                raise OSError("simulated blocked archive")
            return rename(path, target)
        with patch.object(Path, "rename", fail_once), self.assertRaises(OSError):
            project.prepare_project(self.workspace)
        self.assertEqual(result.with_suffix(".zip").read_bytes(), old_zip)
        self.assertEqual((result / "LIRE-MOI.md").read_bytes(), old_guide)
        sharing.verify_folder(result, "project", project.project_allowed)

    def test_windows_archive_has_app_only_guide_and_no_personal_data(self):
        self.put("Application/PrepaPilot/data/mpsi.sqlite3", b"private")
        archive = sharing.create_distribution(self.workspace)
        manifest = sharing.verify_zip(archive, "PrepaPilot", "windows", sharing.app_allowed)
        self.assertEqual(set(manifest["files"]), {"PrepaPilot.exe", "_internal/runtime.dll", "GUIDE.md", "VERIFICATION.md"})
        with ZipFile(archive) as bundle:
            guide = bundle.read("PrepaPilot/GUIDE.md").decode("utf-8")
            self.assertIn("PrepaPilot.exe", guide)
            self.assertNotIn("Ouvrir PrepaPilot.cmd", guide)
        self.assertTrue((self.workspace / "Application/PrepaPilot/data/mpsi.sqlite3").exists())

    def test_optional_english_guide_is_preserved_in_both_distributions(self):
        guide = "# Install PrépaPilot\nChoose English or Français when you first open the app.\n"
        original = self.put("Application/PrepaPilot/GUIDE.en.md", guide).read_bytes()
        archive = sharing.create_distribution(self.workspace)
        with ZipFile(archive) as bundle:
            self.assertEqual(bundle.read("PrepaPilot/GUIDE.en.md"), original)
        result = project.prepare_project(self.workspace)
        with ZipFile(result.with_suffix(".zip")) as bundle:
            self.assertEqual(bundle.read("PrepaPilot-Projet/Application/PrepaPilot/GUIDE.en.md"), original)
        self.assertEqual((result / "Application/PrepaPilot/GUIDE.en.md").read_text(encoding="utf-8"), guide)

    def test_unsafe_names_rejected(self):
        for name in ("../secret.py", "/absolute.py", "C:/secret.py", "Outils\\secret.py", "Sources/PrepaPilot/.env", "Application/PrepaPilot/data/secret", "a//b.py", "Outils/CON.py", "Sources/PrepaPilot/README.md."):
            with self.subTest(name=name), self.assertRaises(ValueError):
                sharing.safe_name(name)


if __name__ == "__main__":
    main()
