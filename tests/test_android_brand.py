import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
A='{http://schemas.android.com/apk/res/android}'

class AndroidBrandTests(unittest.TestCase):
    def test_launcher_resources_resolve_and_permissions_unchanged(self):
        manifest=ET.parse(ROOT/'android/app/AndroidManifest.xml').getroot()
        self.assertEqual(manifest.get(A+'versionName'),'0.8.10')
        self.assertEqual(manifest.find('application').get(A+'icon'),'@mipmap/ic_launcher')
        home=manifest.find("application/activity[@"+A+"name='.MainActivity']")
        self.assertEqual(home.get(A+'theme'),'@style/PhoneBridgeHomeTheme')
        icon=ET.parse(ROOT/'android/app/res/mipmap-anydpi-v26/ic_launcher.xml').getroot()
        self.assertEqual(icon.tag,'adaptive-icon')
        self.assertEqual(icon.find('foreground').get(A+'drawable'),'@drawable/ic_launcher_foreground')
        foreground=ET.parse(ROOT/'android/app/res/drawable/ic_launcher_foreground.xml').getroot()
        self.assertEqual(foreground.find('group').get(A+'scaleX'),'0.8')
        self.assertTrue(foreground.findall('.//path'))

    def test_home_keeps_experiments_separate_and_native_actions(self):
        source=(ROOT/'android/app/src/MainActivity.java').read_text('utf-8')
        for text in ('USB 有线连接  /  推荐','更多连接与诊断','打开控制面板','service_running','pc_api'):
            self.assertIn(text,source)
        self.assertNotIn('Start Bridge',source)
        self.assertIn('PackageManager.PERMISSION_GRANTED',source)
