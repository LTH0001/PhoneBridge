import queue
import unittest
from unittest.mock import Mock,patch
from PIL import Image
from phonebridge.media import CameraSink

class MediaBackendTests(unittest.TestCase):
    def test_native_camera_does_not_require_old_softcam_binary(self):
        sink=CameraSink('missing-unverified-softcam.dll',Mock())
        sink.virtual_requested=True
        frame=Mock(width=1280,height=720)
        frame.to_image.return_value=Image.new('RGB',(32,18))
        codec=Mock();codec.decode.return_value=[frame]
        writer=Mock()
        observed=[]
        def sent(value):
            observed.append(sink.status()['virtual'])
            sink.stop_event.set()
        writer.send.side_effect=sent
        sink.queue.put(b'synthetic')
        with patch('av.CodecContext.create',return_value=codec), \
                patch('phonebridge.mf_camera.installed',return_value=True), \
                patch('phonebridge.mf_camera.FrameWriter',return_value=writer), \
                patch('ctypes.WinDLL') as old_dll:
            sink._run()
        old_dll.assert_not_called()
        writer.send.assert_called_once_with(frame)
        writer.close.assert_called_once()
        self.assertEqual(observed,[True])
        self.assertEqual(sink.error,'')

if __name__=='__main__':
    unittest.main()
