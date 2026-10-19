from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from release_source import allowed


class ReadmeScreenshotsTests(unittest.TestCase):
    def test_preview_images_exist_and_are_public_source_assets(self):
        readme=(ROOT/'README.md').read_text(encoding='utf-8')
        links=re.findall(r'!\[[^\]]*\]\((docs/screenshots/[^)]+)\)',readme)
        self.assertEqual(len(links),3)
        for link in links:
            self.assertTrue((ROOT/link).is_file())
            self.assertTrue(allowed(link))

    def test_screenshot_allowlist_is_limited_to_image_files(self):
        for path in ('docs/screenshots/private.exe','docs/screenshots/token.json','docs/screenshots/nested/file.jpg','docs/screenshots/../secret.jpg'):
            self.assertFalse(allowed(path),path)
