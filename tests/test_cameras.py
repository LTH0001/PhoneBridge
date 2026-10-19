import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from phonebridge.cameras import preferred_camera, camera_label
from phonebridge import config
from phonebridge.sdk import PhoneBridgeClient


class CameraSelectionTests(unittest.TestCase):
    def setUp(self):
        self.cameras = [{'id': 'back-5', 'facing': 'BACK'}, {'id': 'front-8', 'facing': 'FRONT'}]

    def test_default_front_without_assuming_id(self):
        self.assertEqual(preferred_camera(self.cameras)['id'], 'front-8')
        self.assertEqual(camera_label(self.cameras[1]), 'front-8 前置')

    def test_saved_back_preference(self):
        self.assertEqual(preferred_camera(self.cameras, 'back')['id'], 'back-5')

    def test_missing_facing_and_no_camera(self):
        self.assertEqual(preferred_camera(self.cameras[:1])['id'], 'back-5')
        self.assertIsNone(preferred_camera([]))
        self.assertIsNone(preferred_camera([{'facing': 'FRONT'}]))

    def test_preference_survives_reload_and_preserves_other_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.local.json'
            path.write_text(json.dumps({'api_port': 9000, 'serial': 'keep'}), 'utf-8')
            with patch.object(config, 'CONFIG_FILE', path):
                self.assertEqual(config.load()['default_camera_facing'], 'FRONT')
                config.save_camera_facing('BACK')
                self.assertEqual(config.load()['default_camera_facing'], 'BACK')
                self.assertEqual(config.load()['serial'], 'keep')
                self.assertEqual(config.load()['api_port'], 9000)
                config.save_camera_facing('FRONT')
                self.assertEqual(config.load()['default_camera_facing'], 'FRONT')
                with self.assertRaises(ValueError): config.save_camera_facing('invalid')
                self.assertEqual(config.load()['default_camera_facing'], 'FRONT')

    def test_sdk_default_and_explicit_camera(self):
        client = PhoneBridgeClient('http://localhost', '')
        with patch.object(client, 'request', return_value={}) as request:
            client.camera_start()
            self.assertNotIn('camera_id', request.call_args.args[1])
            client.camera_start(camera_id='back-5')
            self.assertEqual(request.call_args.args[1]['camera_id'], 'back-5')

    def test_core_uses_front_for_default_but_keeps_explicit_id(self):
        from phonebridge.core import Bridge
        bridge = Bridge.__new__(Bridge)
        bridge.lock = threading.RLock()
        bridge.caps = {'camera': self.cameras}
        bridge.config = {}
        bridge.camera = Mock(frames=1, error='')
        bridge.camera_stop = Mock()
        bridge.request = Mock()
        bridge.log = Mock()
        bridge.async_errors = {}
        bridge.camera_start()
        self.assertEqual(bridge.request.call_args.args[1]['cameraId'], 'front-8')
        self.assertEqual(bridge.desired_camera['camera_id'], 'front-8')
        bridge.camera_start(camera_id='back-5')
        self.assertEqual(bridge.request.call_args.args[1]['cameraId'], 'back-5')

    def test_gui_remembers_selection_and_refreshes_default(self):
        from phonebridge.gui import ControlCenter
        selection = Mock()
        selection.get.return_value = 'back-5 后置'
        # Plain test doubles exercise handlers without opening or controlling UI.
        gui = SimpleNamespace(camera_choice=selection, footer=Mock(),
                              bridge=SimpleNamespace(caps={'camera': self.cameras},
                                                     config={}, desired_camera=None))
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(config, 'CONFIG_FILE', Path(directory) / 'config.local.json'):
                ControlCenter.remember_camera(gui)
                self.assertEqual(config.load()['default_camera_facing'], 'BACK')
                self.assertEqual(gui.bridge.config['default_camera_facing'], 'BACK')
        class Choice(dict):
            def set(self, value): self.value = value
        gui.camera_choice = Choice()
        ControlCenter.refresh_cameras(gui)
        self.assertEqual(gui.camera_choice.value, 'back-5 后置')
        gui.bridge.config = {}
        ControlCenter.refresh_cameras(gui)
        self.assertEqual(gui.camera_choice.value, 'front-8 前置')
        gui.bridge.desired_camera = {'camera_id': 'back-5'}
        ControlCenter.refresh_cameras(gui)
        self.assertEqual(gui.camera_choice.value, 'back-5 后置')
