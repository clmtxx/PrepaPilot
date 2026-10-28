"""The portable builder embeds only an explicitly selected desktop identity."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('google_portable_build', ROOT / 'Sources' / 'PrepaPilot' / 'build_windows.py')
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)
CLIENT = {'installed': {'client_id': '123456789-publisher.apps.googleusercontent.com', 'client_secret': 'fixture-only'}}


class PortableGoogleBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.assets = self.root / 'source-assets'
        self.assets.mkdir()
        (self.assets / 'app.ico').write_bytes(b'icon')
        self.client = self.root / 'client.json'
        self.client.write_text(json.dumps({'installed': {**CLIENT['installed'], 'project_id': 'fixture'}}), encoding='utf-8')

    def tearDown(self):
        self.temporary.cleanup()

    def test_explicit_client_is_sanitized_in_staging_without_source_mutation(self):
        destination = self.root / 'staged'
        build.stage_assets(self.assets, destination, google_oauth_client=self.client, require_google_drive=True)
        self.assertEqual(json.loads((destination / build.GOOGLE_OAUTH_ASSET).read_text()), CLIENT)
        self.assertFalse((self.assets / build.GOOGLE_OAUTH_ASSET).exists())
        self.assertEqual(set(path.name for path in destination.iterdir()), {'app.ico', build.GOOGLE_OAUTH_ASSET})

    def test_existing_asset_is_validated_and_normalized(self):
        source = self.assets / build.GOOGLE_OAUTH_ASSET
        source.write_bytes(self.client.read_bytes())
        before = source.read_bytes()
        destination = build.stage_assets(self.assets, self.root / 'normalized', require_google_drive=True)
        self.assertEqual(json.loads((destination / build.GOOGLE_OAUTH_ASSET).read_text()), CLIENT)
        self.assertEqual(source.read_bytes(), before)
        source.write_text(json.dumps({'installed': {**CLIENT['installed'], 'refresh_token': 'PRIVATE'}}), encoding='utf-8')
        with self.assertRaises(ValueError):
            build.stage_assets(self.assets, self.root / 'invalid')
        self.assertFalse((self.root / 'invalid').exists())

    def test_required_client_fails_before_copying_or_compiling(self):
        with self.assertRaises(ValueError):
            build.stage_assets(self.assets, self.root / 'absent', require_google_drive=True)
        self.assertFalse((self.root / 'absent').exists())
        source = self.root / 'Sources' / 'PrepaPilot'
        (source / 'assets').mkdir(parents=True)
        with patch.object(build, 'ROOT', source), patch.object(build, 'WORKSPACE', self.root), \
                patch.object(build.sys, 'argv', ['build_windows.py', '--output', str(self.root / 'output'), '--require-google-drive']), \
                patch.object(build.subprocess, 'run') as compile, patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                build.main()
            compile.assert_not_called()
        self.assertFalse((self.root / 'output').exists())


if __name__ == '__main__':
    unittest.main()
