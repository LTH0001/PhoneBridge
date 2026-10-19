import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from phonebridge.config import data_root

class PackagePathTests(unittest.TestCase):
    def test_source_mode_preserves_developer_workspace(self):
        with patch.object(sys,'frozen',False,create=True):
            self.assertEqual(data_root(Path('example')),Path('example'))

    def test_frozen_mode_never_writes_into_installation(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sys,'frozen',True,create=True), \
                patch.dict('os.environ',{'LOCALAPPDATA':directory}):
            self.assertEqual(data_root(Path('readonly-assets')),Path(directory)/'PhoneBridge')

if __name__=='__main__':
    unittest.main()
