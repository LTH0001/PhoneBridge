import unittest
from phonebridge.desktop_style import device_label
from phonebridge.desktop_style import BG,CARD,TEXT,MUTED,ACCENT

class DesktopLabelTests(unittest.TestCase):
    def test_light_palette_retains_readable_contrast(self):
        def light(color):
            channels=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            channels=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in channels]
            return sum(c*w for c,w in zip(channels,(.2126,.7152,.0722)))
        def contrast(a,b):
            values=sorted((light(a),light(b)))
            return (values[1]+.05)/(values[0]+.05)
        self.assertGreater(light(BG),.85)
        self.assertGreaterEqual(contrast(TEXT,BG),7)
        self.assertGreaterEqual(contrast(MUTED,BG),4.5)
        self.assertGreaterEqual(contrast(ACCENT,CARD),4.5)

    def test_authorized_model(self):
        label=device_label({'serial':'sample','state':'device','detail':'model:Pixel_9 device:tokay'})
        self.assertIn('Pixel 9',label)
        self.assertIn('已授权',label)
        self.assertTrue(label.endswith('sample'))

    def test_authorization_is_not_hidden(self):
        self.assertIn('请在手机允许调试',device_label({'serial':'sample','state':'unauthorized'}))

    def test_native_is_experimental(self):
        self.assertIn('实验',device_label({'serial':'usb:sample','state':'device','transport':'accessory'}))
