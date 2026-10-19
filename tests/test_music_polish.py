import io
import threading
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import urllib.error
from PIL import Image
from phonebridge.music import timeline_position,artwork_jpeg,MusicController
from phonebridge.lyrics import matching_record,LyricsController

class MusicPolishTests(unittest.TestCase):
    def test_timestamp_compensation_and_speed(self):
        self.assertAlmostEqual(timeline_position(20,120,True,1,100,101.75),21.75)
        self.assertEqual(timeline_position(20,120,True,2,100,102),24)
    def test_pause_never_extrapolates(self):
        self.assertEqual(timeline_position(20,120,False,1,100,102),20)
    def test_future_and_stale_timestamp_rejected(self):
        self.assertEqual(timeline_position(20,120,True,1,103,100),20)
        self.assertEqual(timeline_position(20,120,True,1,0,100),20)
    def test_seek_and_end_are_not_old_clock(self):
        self.assertEqual(timeline_position(5,120,True,1,100,100),5)
        self.assertEqual(timeline_position(119,120,True,1,100,102),120)
    def test_bad_rate_defaults_safely(self):
        for rate in [None,0,-1,float('nan'),20]:
            self.assertEqual(timeline_position(20,120,True,rate,100,101),21)
    def test_artwork_bound_and_conversion(self):
        raw=io.BytesIO();Image.new('RGBA',(1000,700),(30,60,100,255)).save(raw,'PNG')
        converted=artwork_jpeg(raw.getvalue())
        with Image.open(io.BytesIO(converted)) as image:
            self.assertEqual(image.format,'JPEG');self.assertLessEqual(max(image.size),512)
        self.assertEqual(artwork_jpeg(b'x'*(2*1024*1024+1)),b'')
    def test_artwork_key_does_not_leak_other_track(self):
        controller=MusicController.__new__(MusicController);controller.lock=threading.Lock();controller.art_key='current';controller.art=b'jpg'
        self.assertEqual(controller.artwork('old'),b'');self.assertEqual(controller.artwork('current'),b'jpg')
    def test_instrumental_still_requires_exact_artist_duration(self):
        item={'trackName':'Unit','artistName':'Artist','duration':120,'instrumental':True}
        media={'title':'Unit','artist':'Artist','duration_seconds':120}
        self.assertIs(matching_record([item],media),item)
        self.assertIsNone(matching_record([item],{**media,'artist':'Other'}))
    def test_transient_lyrics_server_failure_retries_once(self):
        controller=LyricsController(Mock());response=Mock();response.url='https://lrclib.net/api/search';response.read.return_value=b'[]'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        failure=urllib.error.HTTPError(response.url,503,'Unavailable',{},None)
        with patch('urllib.request.urlopen',side_effect=[failure,response]) as request,patch.object(controller.closed,'wait'):
            self.assertEqual(controller._read_online(Mock()),b'[]');self.assertEqual(request.call_count,2)
    def test_permanent_lyrics_failure_not_retried(self):
        controller=LyricsController(Mock());failure=urllib.error.HTTPError('https://lrclib.net',404,'Missing',{},None)
        with patch('urllib.request.urlopen',side_effect=failure) as request:
            with self.assertRaises(urllib.error.HTTPError):controller._read_online(Mock())
            self.assertEqual(request.call_count,1)
