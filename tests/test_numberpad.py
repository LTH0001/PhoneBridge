import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

class NumberPadIntegrationTests(unittest.TestCase):
    def test_controls_are_below_work_area_not_header(self):
        source=(ROOT/'android/app/src/InputActivity.java').read_text('utf-8')
        self.assertNotIn('header.addView(button(',source)
        self.assertGreater(source.index('root.addView(actions)'),source.index('root.addView(pad,area)'))
        for text in ('返回面板','数字键盘','返回上页','显示桌面','按住说话','启用输入'):self.assertIn(text,source)
    def test_numeric_touch_is_isolated_and_only_committed_on_valid_up(self):
        source=(ROOT/'android/app/src/TouchpadView.java').read_text('utf-8')
        self.assertIn('if(numberMode)return numberTouch(e)',source)
        self.assertIn('numberCancelled=true;numberKey=null',source)
        self.assertIn('numberAt(event.getX(),event.getY())==numberKey',source)
        self.assertIn('void numberMode(boolean value){release();',source)
        self.assertIn('.put("kind","key")',source)
    def test_pad_shares_streaming_voice_and_suspends_mouse_session(self):
        source=(ROOT/'android/app/src/InputActivity.java').read_text('utf-8')
        self.assertIn('new HoldToTalk(this,voice,shell,this::suspendForVoice,this::resumeAfterVoice)',source)
        self.assertNotIn('voicePage',source);self.assertNotIn('SpeechRecognizer',source)
        self.assertIn('voiceBusy=true;stop()',source)
        self.assertIn('if(active&&restore)enable()',source)
        self.assertIn('holdToTalk.pause()',source)
    def test_numberpad_starts_hidden_and_is_hidden_when_disabled(self):
        source=(ROOT/'android/app/src/InputActivity.java').read_text('utf-8')
        self.assertIn('setNumberMode(false);enabled(false);setContentView(shell)',source)
        self.assertIn('if(!value)setNumberMode(false)',source)
        self.assertIn('numbers.setEnabled(value&&!voiceBusy)',source)
        self.assertIn('if(!session.isEmpty()&&!voiceBusy)setNumberMode(!numberMode)',source)
    def test_voice_button_is_between_equal_width_control_groups(self):
        source=(ROOT/'android/app/src/InputActivity.java').read_text('utf-8')
        self.assertIn('actions.addView(leftControls,new LinearLayout.LayoutParams(0,dp(44),1))',source)
        self.assertIn('actions.addView(rightControls,new LinearLayout.LayoutParams(0,dp(44),1))',source)
        self.assertLess(source.index('actions.addView(leftControls'),source.index('actions.addView(voice,voiceSlot)'))
        self.assertLess(source.index('actions.addView(voice,voiceSlot)'),source.index('actions.addView(rightControls'))
    def test_back_is_pc_previous_window_and_phone_system_back_stays_local(self):
        source=(ROOT/'android/app/src/InputActivity.java').read_text('utf-8')
        self.assertIn('back=button("返回上页",v -> returnPrevious())',source)
        self.assertIn('private void returnPrevious(){windowCommand("previous");}',source)
        self.assertIn('private void returnLocal(){if(numberMode){setNumberMode(false);return;}finish();}',source)
        self.assertIn('onBackPressed(){returnLocal();}',source)
        self.assertIn('back.setEnabled(!voiceBusy&&!desktopPending)',source)
        self.assertNotIn('navigation("back")',source)
        self.assertIn('"/api/input/"+action',source)
        self.assertIn('desktop.setEnabled(!voiceBusy&&!desktopPending)',source)
