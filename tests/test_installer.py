from pathlib import Path
import importlib.util
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_per_user_install_has_directory_and_shortcut_controls(self):
        text=(ROOT/'scripts/phonebridge-setup.iss').read_text(encoding='utf-8')
        for value in ('PrivilegesRequired=lowest','DisableDirPage=no','Name: desktopicon','{autoprograms}\\PhoneBridge','UninstallDisplayIcon={app}\\PhoneBridge.exe'):
            self.assertIn(value,text)

    def test_installer_does_not_delete_settings_or_install_drivers(self):
        text=(ROOT/'scripts/phonebridge-setup.iss').read_text(encoding='utf-8')
        for value in ('[UninstallDelete]','[Registry]','runascurrentuser','registerserver','schtasks','powershell.exe'):
            self.assertNotIn(value,text)
        self.assertIn('skipifsilent',text)
        self.assertIn('CloseApplications=no',text)

    def test_installer_sources_are_in_public_allowlist(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from release_source import allowed
        self.assertTrue(allowed('scripts/build-installer.py'))
        self.assertTrue(allowed('scripts/phonebridge-setup.iss'))
        self.assertFalse(allowed('runtime/build-installer/payload.exe'))

    def test_onefile_validation_rejects_non_bundle(self):
        spec=importlib.util.spec_from_file_location('installer_build',ROOT/'scripts/build-installer.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertTrue(callable(module.validate_bundle))
        text=(ROOT/'scripts/build-installer.py').read_text(encoding='utf-8')
        self.assertIn('Embedded APK differs',text)
        self.assertIn('Missing or stale embedded notice',text)


if __name__=='__main__':unittest.main()
