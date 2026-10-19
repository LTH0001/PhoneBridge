import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from phonebridge.gui import ControlCenter

class ScreenControlsTests(unittest.TestCase):
    def test_panel_return_preserves_previous_display(self):
        ui=SimpleNamespace(bridge=SimpleNamespace(panel_visible=True,desired_display={'desktop_width':800}),
            api=SimpleNamespace(resume_desktop=Mock()),start_native_display=Mock())
        action=ControlCenter.display_primary_action(ui)
        self.assertIs(action,ui.api.resume_desktop)
        ui.start_native_display.assert_not_called()

    def test_panel_without_previous_scene_starts_configured_display(self):
        start=Mock()
        ui=SimpleNamespace(bridge=SimpleNamespace(panel_visible=True,desired_display=None),
            api=SimpleNamespace(resume_desktop=Mock()),start_native_display=Mock(return_value=start))
        self.assertIs(ControlCenter.display_primary_action(ui),start)
        ui.start_native_display.assert_called_once()

    def test_summary_uses_actual_selections(self):
        ui=SimpleNamespace(layout_choice=Mock(),desktop_size=Mock(),quality_choice=Mock(),touch=Mock(),display_summary=Mock())
        ui.layout_choice.get.return_value='主屏左下方（底部对齐）';ui.desktop_size.get.return_value='800 · 大字'
        ui.quality_choice.current.return_value=0;ui.touch.get.return_value=True
        ControlCenter.update_display_summary(ui)
        summary=ui.display_summary.set.call_args.args[0]
        self.assertIn('桌面宽度 800',summary);self.assertIn('触控开启',summary);self.assertNotIn('底部对齐',summary)

    def test_foldouts_default_closed(self):
        import tkinter as tk
        from phonebridge.desktop_style import Foldout,apply_theme
        try:root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        root.withdraw()
        try:
            apply_theme(root);fold=Foldout(root,'显示设置')
            self.assertFalse(fold.expanded);self.assertEqual(fold.body.winfo_manager(),'')
            fold.toggle();self.assertTrue(fold.expanded);self.assertEqual(fold.body.winfo_manager(),'pack')
            fold.toggle();self.assertFalse(fold.expanded);self.assertEqual(fold.body.winfo_manager(),'')
        finally:root.destroy()
