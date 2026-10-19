import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from phonebridge.music_window import MusicWindow
from phonebridge.system_info import SystemInfo

class WindowTests(unittest.TestCase):
    def window(self,visible=True,minimized=False):
        control=MusicWindow.__new__(MusicWindow);control.lock=threading.Lock();control.path=Path('C:/Example/QQMusic.exe');control.user=Mock()
        control._windows=Mock(return_value=[{'handle':42,'pid':1,'visible':visible,'minimized':minimized}]);return control
    def test_toggle_visible_minimizes_only(self):
        c=self.window();self.assertEqual(c.action('window_toggle')['window_action'],'minimized')
        c.user.ShowWindowAsync.assert_called_once_with(42,6);c.user.SetForegroundWindow.assert_not_called()
    def test_toggle_minimized_restores_without_relaunch(self):
        c=self.window(minimized=True)
        with patch('subprocess.Popen') as launch:self.assertEqual(c.action('window_toggle')['window_action'],'shown');launch.assert_not_called()
        c.user.ShowWindowAsync.assert_called_once_with(42,9)
    def test_hidden_window_show_and_explicit_open_not_toggle(self):
        c=self.window(visible=False);c.action('window_toggle');c.user.ShowWindowAsync.assert_called_once_with(42,5)
        c=self.window();c.action('open');c.user.ShowWindowAsync.assert_called_once_with(42,5)
    def test_no_close_and_invalid_action_rejected(self):
        c=self.window()
        for action in ['close','kill','shell']:
            with self.assertRaises(ValueError):c.action(action)
        c.user.ShowWindowAsync.assert_not_called()
    def test_invalid_configured_executable_not_launched(self):
        c=self.window();c._windows.return_value=[];c.path=Path('C:/Windows/notepad.exe')
        with patch('subprocess.Popen') as launch:
            with self.assertRaises(ValueError):c.action('window_toggle')
            launch.assert_not_called()

class SystemTests(unittest.TestCase):
    def info(self):
        obj=SystemInfo.__new__(SystemInfo);obj.lock=threading.Lock();obj.value={'system':{'kernel':'Windows NT'},'processes':[
            {'pid':20,'name':'Unit.exe','memory_mb':12,'cpu_percent':3},
            {'pid':10,'name':'Other.exe','memory_mb':None,'cpu_percent':None},
            {'pid':30,'name':'UnitHelper.exe','memory_mb':25,'cpu_percent':1}],'updated_at':1,'error':''};return obj
    def test_search_sort_and_page(self):
        c=self.info();self.assertEqual(c.status()['processes'][0]['pid'],30)
        self.assertEqual(c.status(sort='cpu')['processes'][0]['pid'],20)
        self.assertEqual(c.status(query='10')['processes'][0]['pid'],10)
        self.assertEqual(c.status(query='UNIT',limit=1,page=1)['processes'][0]['pid'],20)
        self.assertEqual(c.status(sort='pid')['processes'][0]['pid'],10)
    def test_snapshot_independent_and_bounds(self):
        c=self.info();value=c.status();value['system']['kernel']='changed';self.assertEqual(c.status()['system']['kernel'],'Windows NT')
        for args in [{'limit':101},{'page':-1},{'page':True},{'query':'x'*81},{'sort':'terminate'}]:
            with self.assertRaises(ValueError):c.status(**args)
    def test_cpu_baseline_and_pid_reuse(self):
        from types import SimpleNamespace as S
        c=SystemInfo.__new__(SystemInfo);c.previous={(12,1):(10,20)};c.system={'boot_time':0}
        proc={'pid':12,'name':'Unit.exe','create_time':1,'cpu_seconds':24,'memory_mb':1}
        with patch('phonebridge.system_info.read_processes',return_value=[proc]),patch('time.monotonic',return_value=12),patch('psutil.cpu_count',return_value=2):
            self.assertEqual(c._sample()['processes'][0]['cpu_percent'],100)
            proc['create_time']=2;self.assertIsNone(c._sample()['processes'][0]['cpu_percent'])
    def test_detail_checks_creation_time_before_reading(self):
        c=self.info();c.value['processes'][0]['created_at']=1
        process=Mock();process.create_time.return_value=2
        with patch('psutil.Process',return_value=process):
            with self.assertRaises(ValueError):c.process_detail(20,1)
            process.as_dict.assert_not_called()
    def test_detail_rejects_invalid_identity(self):
        c=self.info()
        for pid,created in [(True,1),(0,1),(20,None),(20,float('nan')),(20,False)]:
            with self.assertRaises(ValueError):c.process_detail(pid,created)
    def test_native_metadata_structure_sizes(self):
        import ctypes
        from phonebridge.process_snapshot import Entry,Memory
        self.assertEqual(ctypes.sizeof(Entry),568 if ctypes.sizeof(ctypes.c_void_p)==8 else 556)
        self.assertEqual(ctypes.sizeof(Memory),80 if ctypes.sizeof(ctypes.c_void_p)==8 else 44)
