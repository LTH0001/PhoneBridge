import asyncio
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from phonebridge.api import LocalAPI
from phonebridge.music import MusicController,choose_qq_session
from phonebridge.telemetry import HostTelemetry

class DashboardTests(unittest.TestCase):
    def test_music_target_never_falls_back_to_browser(self):
        browser=SimpleNamespace(source_app_user_model_id='Chrome.exe')
        qq=SimpleNamespace(source_app_user_model_id='QQMusic.exe')
        lookalike=SimpleNamespace(source_app_user_model_id='Browser-QQMusic.exe')
        self.assertIs(choose_qq_session([browser,qq],browser),qq)
        self.assertIsNone(choose_qq_session([browser,lookalike],browser))

    def test_telemetry_snapshot_is_independent(self):
        sampler=HostTelemetry.__new__(HostTelemetry)
        sampler.lock=threading.Lock(); sampler.value={'cpu':{'temperature_c':None},'gpus':[{'index':0}]}
        status=sampler.status(); status['gpus'][0]['index']=999
        self.assertEqual(sampler.status()['gpus'][0]['index'],0)
        self.assertIsNone(sampler.status()['cpu']['temperature_c'])

    def test_invalid_music_action_rejected_without_background_dispatch(self):
        controller=MusicController.__new__(MusicController)
        with self.assertRaises(Exception): controller.action('shell')

    def test_panel_pauses_video_preserves_scene_and_enables_touch(self):
        scene={'desktop_width':800,'layout':'below-left','quality':'sharp','touch':False}
        bridge=SimpleNamespace(lock=threading.RLock(),connected=True,panel_visible=False,
                               desktop=Mock(),request=Mock(),adb=Mock(),desired_display=scene.copy(),
                               display_start=Mock(return_value={'running':True}),config={})
        api=LocalAPI.__new__(LocalAPI); api.bridge=bridge; api.port=8765
        api.closed=threading.Event()
        with patch('phonebridge.api.windows.return_phone_cursor_to_main'):
            api.enter_panel()
        self.assertTrue(bridge.panel_visible)
        bridge.desktop.stop.assert_called_once()
        self.assertEqual(bridge.desired_display,scene)
        api.enter_panel(); bridge.desktop.stop.assert_called_once()
        api.resume_desktop()
        self.assertTrue(bridge.display_start.call_args.kwargs['touch'])
        self.assertEqual(bridge.display_start.call_args.kwargs['desktop_width'],800)

    def test_dashboard_endpoints_require_token(self):
        bridge=Mock(config={},connected=True,panel_visible=False,lock=threading.RLock())
        bridge.status.return_value={}
        with tempfile.TemporaryDirectory() as directory:
            with patch('phonebridge.api.ROOT',Path(directory)),patch('phonebridge.api.HostTelemetry') as telemetry,patch('phonebridge.api.MusicController') as music,patch('phonebridge.api.SystemInfo'),patch('phonebridge.api.PlaybackController') as playback:
                playback.return_value.status.return_value={}
                telemetry.return_value.status.return_value={'cpu':{'temperature_c':None}}
                music.return_value.status.return_value={'available':True,'source_app_id':'QQMusic.exe'}
                music.return_value.action.return_value={'ok':True}
                api=LocalAPI(bridge,0)
                try:
                    url=f'http://127.0.0.1:{api.port}'
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(url+'/api/dashboard/status')
                    self.assertEqual(error.exception.code,401)
                    headers={'Authorization':'Bearer '+api.token,'Content-Type':'application/json'}
                    request=urllib.request.Request(url+'/api/dashboard/status',headers=headers)
                    with urllib.request.urlopen(request) as response:
                        self.assertIsNone(json.load(response)['host']['cpu']['temperature_c'])
                    action=urllib.request.Request(url+'/api/music/control',data=b'{"action":"toggle","source_app_id":"QQMusic.exe"}',headers=headers)
                    with urllib.request.urlopen(action) as response: self.assertTrue(json.load(response)['ok'])
                    music.return_value.action.assert_called_once_with(action='toggle',source_app_id='QQMusic.exe')
                finally: api.close()

class MusicAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_source_never_controls_session(self):
        controller=MusicController.__new__(MusicController); controller.action_lock=asyncio.Lock()
        session=Mock(source_app_user_model_id='QQMusic.exe'); controller._session=Mock(return_value=session)
        with self.assertRaises(Exception): await controller._action('toggle','Chrome.exe')
        session.try_toggle_play_pause_async.assert_not_called()
