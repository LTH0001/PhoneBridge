from pathlib import Path
import unittest
from phonebridge.desktop_style import PALETTES,resolve_theme

ROOT=Path(__file__).resolve().parents[1]


class AppearanceTests(unittest.TestCase):
    def test_desktop_theme_modes_and_system_resolution(self):
        self.assertEqual(resolve_theme('light'),'light')
        self.assertEqual(resolve_theme('dark'),'dark')
        self.assertEqual(resolve_theme('system',lambda:True),'dark')
        self.assertEqual(resolve_theme('system',lambda:False),'light')
        with self.assertRaises(ValueError):resolve_theme('unknown')

    def test_both_desktop_palettes_have_readable_text(self):
        def light(color):
            channels=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            return sum((c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4)*w for c,w in zip(channels,(.2126,.7152,.0722)))
        for palette in PALETTES.values():
            for background in ('BG','CARD'):
                for foreground,minimum in (('TEXT',7),('MUTED',4.5)):
                    a,b=sorted((light(palette[background]),light(palette[foreground])))
                    self.assertGreaterEqual((b+.05)/(a+.05),minimum)

    def test_phone_preferences_local_and_all_modes_present(self):
        source=(ROOT/'android/app/src/PanelTheme.java').read_text(encoding='utf-8')
        for marker in ('"light","dark","system"','getSharedPreferences("appearance"','a.recreate()', 'UI_MODE_NIGHT_MASK'):
            self.assertIn(marker,source)
        self.assertNotIn('api_token',source)

    def test_panel_pages_follow_theme_without_video_recoloring(self):
        for name in ('MainActivity','DashboardActivity','DetailActivity','InputActivity','SystemActivity','StorageActivity'):
            source=(ROOT/f'android/app/src/{name}.java').read_text(encoding='utf-8')
            self.assertIn('PanelTheme.apply(this)',source,name)
            self.assertIn('PanelTheme.refresh(this)',source,name)
        display=(ROOT/'android/app/src/DisplayActivity.java').read_text(encoding='utf-8')
        self.assertNotIn('PanelTheme.color',display)

    def test_exe_onefile_is_opt_in_and_excludes_legacy_dll(self):
        source=(ROOT/'scripts/build-windows.py').read_text(encoding='utf-8')
        self.assertIn("parser.add_argument('--onefile'",source)
        self.assertNotIn("'vendor/softcam.dll'",source)
