"""Build-independent regressions for the native dashboard integration and safety gates.

These source contract checks complement Android compilation, not physical gesture tests.
"""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

class HoldToTalkTests(unittest.TestCase):
    def source(self,name):return (ROOT/'android/app/src'/name).read_text('utf-8')
    def test_dashboard_voice_is_inline_not_an_activity_launch(self):
        source=self.source('DashboardActivity.java')
        self.assertIn('new HoldToTalk(this,voiceInput,shell)',source)
        self.assertNotIn('new String[]{"pad","voice"}',source)
        self.assertIn('holdToTalk.ownsGesture()',source)
        self.assertIn('holdToTalk.pause()',source)
    def test_release_cancellation_permissions_and_no_enter(self):
        source=self.source('HoldToTalk.java')
        for gate in ('MotionEvent.ACTION_UP','MotionEvent.ACTION_CANCEL','MotionEvent.ACTION_POINTER_DOWN',
                     'finish(stop)','job.cancelled|=cancel','new ArrayBlockingQueue<>(8)',
                     'activity.requestPermissions','permissionResult(boolean granted)',
                     'while(job.held&&usable(job)', 'if(!usable(job))return;',
                     '"/api/input/end"','if(busy){ignoreTouch=true;'):
            self.assertIn(gate,source)
        self.assertEqual(source.count('"/api/input/text"'),0)
        for endpoint in ('/api/speech/start','/api/speech/chunk','/api/speech/finish'):self.assertIn(endpoint,source)
        self.assertNotIn('startActivity',source)
        self.assertNotIn('FileOutputStream',source)
        self.assertNotIn('KEYCODE_ENTER',source)
        self.assertIn('return pressed||ignoreTouch',source)
        self.assertIn('VoiceGesture.classify',source)
        self.assertIn('下滑停止',source);self.assertIn('右滑确认',source)
        self.assertNotIn('上滑停止',source)
    def test_cockpit_uses_actual_percent_and_bounded_animation(self):
        source=self.source('InstrumentGauge.java')
        self.assertIn('Double.isFinite(value)',source)
        self.assertIn('UTILIZATION  %',source)
        self.assertIn('now-changed<400',source)
        self.assertIn('new CockpitBackdrop()',self.source('DashboardActivity.java'))
        self.assertNotIn('new SportPanel(',self.source('DashboardActivity.java'))
        self.assertNotIn('drawCircle(',source)
        self.assertIn('GRAPHICS ENGINE',source)
    def test_unified_surface_and_enlarged_instrument_layout(self):
        dashboard=self.source('DashboardActivity.java');gauge=self.source('InstrumentGauge.java')
        self.assertNotIn('row0.setBackground(cluster)',dashboard)
        self.assertNotIn('PanelStyle.card(this,ACCENT)',dashboard)
        self.assertIn('0,-1,.74f',dashboard)
        self.assertIn('0,.80f',dashboard)
        self.assertIn('h*.39f',gauge)
        self.assertIn('44,0xff24364e',gauge)
