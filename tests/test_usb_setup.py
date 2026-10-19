import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from phonebridge.core import Bridge
from phonebridge.transport import BridgeError
from phonebridge import usb_setup


def phone(vid=0x2d95, pid=0x6012, bus=3, address=18, ports=(6,)):
    return SimpleNamespace(idVendor=vid, idProduct=pid, bus=bus,
                           address=address, port_numbers=ports)


class WiredSetupTests(unittest.TestCase):
    def test_failed_accessory_query_is_read_only_and_unambiguous(self):
        result = SimpleNamespace(returncode=0, stdout=b'{"instance":"example","problem":10}')
        with patch.object(usb_setup.os, 'name', 'nt'), patch.object(usb_setup.subprocess, 'run', return_value=result) as run:
            self.assertEqual(usb_setup.failed_local_accessory()['problem'], 10)
        script = run.call_args.args[0][-1]
        self.assertIn('$devices.Count -eq 1', script)
        self.assertIn('Get-PnpDeviceProperty', script)
        self.assertNotIn('Set-PnpDevice', script)
        self.assertNotIn('Restart-PnpDevice', script)
        self.assertNotRegex(script, r"\$id='USB")

    def test_discovery_does_not_open_or_probe_unrelated_devices(self):
        other = phone(0x1234, 0x5678)
        with patch.object(usb_setup, 'enumerate_usb', return_value=[other, phone()]), \
                patch.object(usb_setup, 'switch') as switch:
            found = usb_setup.discover()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['serial'], 'usb:2d95:6012:3:18')
        self.assertIn('初始化', found[0]['state'])
        switch.assert_not_called()

    def test_stale_selection_does_not_switch_new_device(self):
        with patch.object(usb_setup, 'supported_devices', return_value=[phone(address=19)]), \
                patch.object(usb_setup, 'switch') as switch, \
                patch.object(usb_setup, 'failed_local_accessory', return_value=None):
            with self.assertRaises(BridgeError):
                usb_setup.prepare('usb:2d95:6012:3:18')
            switch.assert_not_called()

    def test_ambiguous_devices_are_never_auto_selected(self):
        with patch.object(usb_setup, 'supported_devices', return_value=[phone(), phone(address=19)]), \
                patch.object(usb_setup, 'switch') as switch:
            with self.assertRaises(BridgeError):
                usb_setup.prepare()
            switch.assert_not_called()

    def test_existing_accessory_does_not_switch_or_use_adb(self):
        device = phone(0x18d1, 0x2d00)
        with patch.object(usb_setup, 'supported_devices', return_value=[device]), \
                patch.object(usb_setup, 'switch') as switch:
            self.assertIs(usb_setup.prepare(), device)
            switch.assert_not_called()

    def test_reenumeration_matches_original_port_not_other_phone(self):
        original = phone()
        wrong = phone(0x18d1, 0x2d01, ports=(7,))
        right = phone(0x18d1, 0x2d00, address=20)
        with patch.object(usb_setup, 'supported_devices', side_effect=[[original], [wrong], [wrong, right]]), \
                patch.object(usb_setup, 'switch') as switch, \
                patch('usb.util.dispose_resources') as dispose, patch.object(usb_setup.time, 'sleep'):
            self.assertIs(usb_setup.prepare(), right)
            switch.assert_called_once_with(original)
            dispose.assert_called_once_with(original)

    def test_inaccessible_mtp_reports_prerequisite_not_debug_authorization(self):
        with patch.object(usb_setup, 'supported_devices', return_value=[phone()]), \
                patch.object(usb_setup, 'switch', side_effect=OSError('blocked')), \
                patch('usb.util.dispose_resources') as dispose:
            with self.assertRaisesRegex(BridgeError, '未修改驱动'):
                usb_setup.prepare()
            dispose.assert_called_once()

    def test_native_connect_never_falls_back_to_adb(self):
        device = phone(0x18d1, 0x2d00)
        bridge = SimpleNamespace(lock=threading.RLock(), connected=False,
            detect_wired=Mock(return_value=[{'serial':'usb:18d1:2d00:3:18', 'transport':'accessory'}]),
            connect_accessory=Mock(return_value={'ok':True}), connect=Mock())
        with patch.object(usb_setup, 'prepare', return_value=device):
            self.assertEqual(Bridge.connect_wired(bridge), {'ok':True})
        bridge.connect_accessory.assert_called_once_with(device)
        bridge.connect.assert_not_called()

    def test_native_discovery_never_starts_adb(self):
        bridge = SimpleNamespace(detect=Mock())
        found = [{'serial':'usb:2d95:6012:3:18'}]
        with patch.object(usb_setup, 'discover', return_value=found):
            self.assertEqual(Bridge.detect_wired(bridge), found)
        bridge.detect.assert_not_called()

    def test_gui_can_show_authorized_adb_before_native_candidate(self):
        adb=[{'serial':'test-phone','state':'device'}]
        native=[{'serial':'usb:2d95:6013:3:18','transport':'accessory'}]
        bridge=SimpleNamespace(detect=Mock(return_value=adb))
        with patch.object(usb_setup,'discover',return_value=native):
            self.assertEqual(Bridge.detect_wired(bridge,include_adb=True),adb+native)

    def test_explicit_adb_selection_does_not_request_aoa_switch(self):
        bridge=SimpleNamespace(lock=threading.RLock(),connected=False,connect=Mock(return_value={'connected':True}),detect_wired=Mock())
        with patch.object(usb_setup,'prepare') as prepare:
            self.assertEqual(Bridge.connect_wired(bridge,'test-phone'),{'connected':True})
        bridge.connect.assert_called_once_with('test-phone')
        bridge.detect_wired.assert_not_called();prepare.assert_not_called()

    def test_gui_does_not_hide_adb_when_aoa_or_failed_aoa_is_present(self):
        adb = [{'serial':'authorized-test-phone', 'state':'device'}]
        for serial in ('usb:18d1:2d01:3:18', 'usb:18d1:2d00:3:18', 'usb-error:18d1:2d00'):
            with self.subTest(serial=serial):
                native = [{'serial':serial, 'transport':'accessory'}]
                bridge = SimpleNamespace(detect=Mock(return_value=adb))
                with patch.object(usb_setup, 'discover', return_value=native):
                    self.assertEqual(Bridge.detect_wired(bridge, include_adb=True), adb+native)
                bridge.detect.assert_called_once_with()

    def test_authorized_adb_is_first_but_unauthorized_entries_are_retained(self):
        pending = {'serial':'pending-test-phone', 'state':'unauthorized'}
        ready = {'serial':'authorized-test-phone', 'state':'device'}
        native = [{'serial':'usb:18d1:2d01:3:18', 'transport':'accessory'}]
        bridge = SimpleNamespace(detect=Mock(return_value=[pending, ready]))
        with patch.object(usb_setup, 'discover', return_value=native):
            self.assertEqual(Bridge.detect_wired(bridge, include_adb=True), [ready, pending]+native)

    def test_native_only_aoa_discovery_does_not_start_adb(self):
        bridge = SimpleNamespace(detect=Mock())
        native = [{'serial':'usb:18d1:2d01:3:18', 'transport':'accessory'}]
        with patch.object(usb_setup, 'discover', return_value=native):
            self.assertEqual(Bridge.detect_wired(bridge), native)
        bridge.detect.assert_not_called()

    def test_gui_keeps_adb_when_no_native_device_exists(self):
        adb = [{'serial':'authorized-test-phone', 'state':'device'}]
        bridge = SimpleNamespace(detect=Mock(return_value=adb))
        with patch.object(usb_setup, 'discover', return_value=[]):
            self.assertEqual(Bridge.detect_wired(bridge, include_adb=True), adb)

    def test_failed_start_is_visible_without_libusb_or_adb(self):
        failure={'instance':'verified-local-phone','problem':10}
        with patch.object(usb_setup,'supported_devices',return_value=[]), \
                patch.object(usb_setup,'failed_local_accessory',return_value=failure):
            found=usb_setup.discover()
            self.assertEqual(found[0]['serial'],'usb-error:18d1:2d00')
            self.assertIn('启动失败',found[0]['state'])
            with self.assertRaisesRegex(BridgeError,'代码 10'):
                usb_setup.prepare(found[0]['serial'])


if __name__ == '__main__':
    unittest.main()
