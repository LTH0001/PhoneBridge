import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from phonebridge.lyrics import LyricsController,parse_lrc,matching_record,track_key,artist_variants
from phonebridge.playback import PlaybackController
from phonebridge.telemetry import HostTelemetry
from phonebridge.mf_camera import FrameWriter,SIZE,HEADER

class LyricsTests(unittest.TestCase):
    def media(self):return {'available':True,'source_app_id':'QQMusic.exe','title':'Unit Song','artist':'Artist','duration_seconds':120,'position_seconds':3}
    def test_multiple_timestamps_and_offset(self):
        lines=parse_lrc('[offset:500]\n[00:01.00][00:03.25]Synthetic test line\n[ti:Unit]')
        self.assertEqual([x['time'] for x in lines],[1.5,3.75])
    def test_matching_rejects_wrong_version_artist_and_duration(self):
        base={'trackName':'Unit Song','artistName':'Artist','duration':120,'syncedLyrics':'[00:01]Unit'}
        self.assertIs(matching_record([base],self.media()),base)
        for changes in ({'trackName':'Unit Song Live'},{'artistName':'Other'},{'duration':130}):
            self.assertIsNone(matching_record([{**base,**changes}],self.media()))
    def test_no_network_without_consent(self):
        with tempfile.TemporaryDirectory() as directory,patch('phonebridge.lyrics.ROOT',Path(directory)),patch('threading.Thread') as thread:
            controller=LyricsController(Mock(status=Mock(return_value=self.media())))
            self.assertEqual(controller.request()['state'],'consent');thread.assert_not_called()
    def test_current_line_and_track_changes(self):
        media=self.media();music=Mock(status=Mock(side_effect=lambda:media));controller=LyricsController(music)
        controller.cache[track_key(media)]={'lines':parse_lrc('[00:01]Unit one\n[00:05]Unit two'),'state':'ready'}
        self.assertEqual(controller.status()['current_index'],0)
        media['title']='Other song';self.assertEqual(controller.status()['lines'],[])
    def test_invalid_lrc_is_bounded(self):
        with self.assertRaises(ValueError):parse_lrc('x'*524289)
        self.assertEqual(parse_lrc('[99:99]x'),[])

    def test_parenthetical_artist_alias_is_a_strict_match(self):
        media=self.media();media['artist']='Real Name (Stage Name)'
        record={'trackName':'Unit Song','artistName':'Stage Name','duration':120,'syncedLyrics':'[00:01]Unit'}
        self.assertIs(matching_record([record],media),record)
        self.assertEqual(artist_variants('Game/Artist'),['Artist','Game'])

    def test_lyrics_retry_clears_failure_but_not_local_import(self):
        media=self.media();controller=LyricsController(Mock(status=Mock(return_value=media)),network_allowed=True)
        key=track_key(media);controller.cache[key]={'state':'unavailable','lines':[],'source':''}
        with tempfile.TemporaryDirectory() as directory,patch('phonebridge.lyrics.ROOT',Path(directory)),patch('threading.Thread') as thread:
            controller.request(retry=True);thread.assert_called_once()
        controller.cache[key]={'state':'ready','lines':[],'source':'本地 LRC'}
        with patch('threading.Thread') as thread:
            self.assertEqual(controller.request(retry=True)['source'],'本地 LRC');thread.assert_not_called()

class PlaybackTests(unittest.TestCase):
    def controller(self):
        obj=PlaybackController.__new__(PlaybackController);obj.lock=threading.Lock()
        obj._snapshot=Mock(return_value={'devices':[{'id':'speaker'},{'id':'headphone'}],'default_id':'speaker'})
        return obj
    def test_delta_clamps_but_never_unmutes(self):
        obj=self.controller();speaker=SimpleNamespace(volume_percent=98,EndpointVolume=Mock())
        with patch('pycaw.pycaw.AudioUtilities.GetSpeakers',return_value=speaker):
            obj._action('delta','speaker',5)
        self.assertEqual(speaker.volume_percent,100);speaker.EndpointVolume.SetMute.assert_not_called()
    def test_invalid_volume_and_stale_endpoint_rejected(self):
        obj=self.controller()
        for action,device,value in [('delta','old',2),('volume','speaker',101),('delta','speaker',16),('volume','speaker',True),('volume','speaker',float('nan'))]:
            with self.subTest(action=action,value=value),patch('pycaw.pycaw.AudioUtilities.GetSpeakers',return_value=SimpleNamespace(volume_percent=34)):
                with self.assertRaises(ValueError):obj._action(action,device,value)
    def test_capture_device_cannot_be_selected(self):
        obj=self.controller()
        with patch('pycaw.pycaw.AudioUtilities.SetDefaultDevice') as switch:
            with self.assertRaises(ValueError):obj._action('device','microphone')
            switch.assert_not_called()
    def test_only_console_and_multimedia_roles_are_changed(self):
        from pycaw.constants import ERole
        obj=self.controller();enum=Mock();enum.GetDefaultAudioEndpoint.return_value.GetId.return_value='old'
        with patch('pycaw.pycaw.AudioUtilities.GetDeviceEnumerator',return_value=enum),patch('pycaw.pycaw.AudioUtilities.SetDefaultDevice') as switch:
            obj._action('device','headphone')
        switch.assert_called_once_with('headphone',roles=[ERole.eConsole,ERole.eMultimedia])

class DetailTests(unittest.TestCase):
    def test_history_is_independent_and_gpu_lookup_is_by_index(self):
        sampler=HostTelemetry.__new__(HostTelemetry);sampler.lock=threading.Lock()
        sampler.value={'cpu':{'load_percent':3},'memory':{'load_percent':50},'gpus':[{'index':1,'load_percent':10}],'error':''}
        sampler.history=[{'time':1,'cpu':3,'memory':50,'gpus':[{'index':1,'load_percent':10}]}]
        result=sampler.detail('gpu',1);result['metric']['load_percent']=99
        self.assertEqual(sampler.detail('gpu',1)['metric']['load_percent'],10)
        self.assertEqual(sampler.detail('cpu')['history'][0]['load_percent'],3)
        with self.assertRaises(ValueError):sampler.detail('gpu',0)
        with self.assertRaises(ValueError):sampler.detail('shell')

class FrameTransportTests(unittest.TestCase):
    def test_fixed_size_writer_and_stop_clear(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'frame.bin';path.write_bytes(bytes(SIZE))
            writer=FrameWriter(path)
            fake=Mock();fake.reformat.return_value.to_ndarray.return_value=np.full((720,1280,4),7,dtype='uint8')
            writer.send(fake)
            self.assertEqual(writer.mapping[HEADER],7)
            writer.close();self.assertEqual(path.read_bytes(),bytes(SIZE))
    def test_invalid_buffer_size_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'frame.bin';path.write_bytes(b'bad')
            with self.assertRaises(ValueError):FrameWriter(path)
