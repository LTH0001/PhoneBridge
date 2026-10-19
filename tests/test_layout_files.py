import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from phonebridge.layout import desktop_position, phone_desktop_size
from phonebridge.files import PhoneFiles, shared_path

class LayoutFilesTests(unittest.TestCase):
    def test_phone_aspect_and_large_text_modes(self):
        phone={'width':1080,'height':2404}
        self.assertEqual(phone_desktop_size(phone,800),(800,360))
        self.assertEqual(phone_desktop_size(phone,640),(640,288))
        self.assertEqual(phone_desktop_size(phone,2404),(2404,1080))
        self.assertEqual(phone_desktop_size({'width':2404,'height':1080},800),(800,360))
        with self.assertRaises(ValueError): phone_desktop_size(phone,0)

    def test_all_placements(self):
        main={'left':0,'top':0,'width':2560,'height':1440}
        self.assertEqual(desktop_position(main,800,360),(0,1440))
        self.assertEqual(desktop_position(main,800,360,'left-bottom'),(-800,1080))
        self.assertEqual(desktop_position(main,800,360,'left-top'),(-800,0))
        self.assertEqual(desktop_position(main,800,360,'right'),(2560,0))
        with self.assertRaises(ValueError): desktop_position(main,800,360,'unknown')

    def test_shared_storage_scope(self):
        self.assertEqual(shared_path('/sdcard/DCIM/../Pictures'),'/sdcard/Pictures')
        for path in ('/data/data','/sdcard/../data','/sdcard-other','/etc','/sdcard/\x00bad'):
            with self.assertRaises(ValueError): shared_path(path)

    def test_listing_preserves_names_and_quotes_path(self):
        actual="/storage/emulated/0/test ' ; echo injection"
        adb=Mock(side_effect=[actual,'f\x0012\x00'+actual+'/hello\n世界.jpg\x00d\x000\x00'+actual+'/folder\x00'])
        files=PhoneFiles(SimpleNamespace(connected=True,adb=adb))
        result=files.list("/sdcard/test ' ; echo injection")
        self.assertEqual(result['entries'][0]['name'],'folder')
        self.assertEqual(result['entries'][1]['name'],'hello\n世界.jpg')
        self.assertIn("'\"'\"'",adb.call_args_list[0].args[1])

    def test_symlink_escape_refused(self):
        files=PhoneFiles(SimpleNamespace(connected=True,adb=Mock(return_value='/data/data')))
        with self.assertRaises(ValueError): files.list('/sdcard/escape')

    def test_download_and_no_overwrite(self):
        def adb(*args,**kwargs):
            if args[0]=='pull': Path(args[2]).write_bytes(b'fixture'); return ''
            return '/storage/emulated/0/test.txt' if args[1].startswith('realpath ') else ''
        files=PhoneFiles(SimpleNamespace(connected=True,adb=Mock(side_effect=adb)))
        with tempfile.TemporaryDirectory() as directory:
            result=files.download('/sdcard/test.txt',directory)
            self.assertEqual(Path(result['path']).read_bytes(),b'fixture')
            with self.assertRaises(ValueError): files.download('/sdcard/test.txt',directory)
            self.assertEqual([p.resolve() for p in Path(directory).iterdir()],[Path(result['path'])])
