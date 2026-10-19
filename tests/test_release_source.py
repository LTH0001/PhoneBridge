import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import release_source

spec = importlib.util.spec_from_file_location('fetch_dependencies', SCRIPTS/'fetch-dependencies.py')
fetcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetcher)


class PublicSourceTests(unittest.TestCase):
    def test_private_and_generated_files_excluded(self):
        for name in ('config.local.json', 'runtime/api.json', 'android/app/build/debug.keystore',
                     'vendor/scrcpy/adb.exe', 'vendor/softcam.dll', 'scripts/accessory-driver.ps1',
                     'scripts/usb-bootstrap-driver.ps1', 'docs/VALIDATION.md',
                     'scripts/local/recovery.py', '../README.md', 'phonebridge/__pycache__/x.py'):
            with self.subTest(name=name):
                self.assertFalse(release_source.allowed(name))

    def test_sources_and_license_included(self):
        for name in ('LICENSE', 'phonebridge/core.py', 'android/app/src/PanelGesture.java',
                     '.github/workflows/ci.yml', 'scripts/dependencies.json', 'docs/BUILDING.md'):
            self.assertTrue(release_source.allowed(name), name)

    def test_repo_audit_passes(self):
        selected, problems = release_source.audit()
        self.assertTrue(selected)
        self.assertEqual(problems, [])

    def test_secrets_report_location_not_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'phonebridge').mkdir()
            secret = 'ghp_'+'A'*36
            (root/'phonebridge/test.py').write_text('token = '+repr(secret), encoding='utf-8')
            _, problems = release_source.audit(root)
            self.assertIn('phonebridge/test.py:1: github-token', problems)
            self.assertNotIn(secret, '\n'.join(problems))

    def test_dependency_target_cannot_escape_vendor(self):
        for name in ('../outside.jar', 'phonebridge/core.py', 'vendor/../../outside.jar'):
            with self.assertRaises(ValueError):
                fetcher.checked_target(release_source.ROOT, name)

    def test_bad_existing_asset_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'vendor').mkdir()
            target = root/'vendor/test.jar'
            target.write_bytes(b'local contents')
            with patch.object(fetcher, 'ROOT', root), patch.object(fetcher.urllib.request, 'urlopen') as network:
                with self.assertRaises(ValueError):
                    fetcher.fetch({'path':'vendor/test.jar', 'url':'https://example.com/a', 'sha256':'0'*64})
                network.assert_not_called()
            self.assertEqual(target.read_bytes(), b'local contents')

    def test_manifest_hashes_and_targets_well_formed(self):
        data = json.loads((SCRIPTS/'dependencies.json').read_text())
        self.assertEqual(data['schema'], 1)
        for item in data['downloads'].values():
            self.assertRegex(item['sha256'], r'^[0-9a-f]{64}$')
            self.assertTrue(item['url'].startswith('https://'))
            fetcher.checked_target(release_source.ROOT, item['path'])
