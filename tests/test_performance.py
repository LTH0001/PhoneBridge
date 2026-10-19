import unittest
import threading
from phonebridge.performance import aggregate_engines,build_disks
from phonebridge.gpu_identity import match_adapter
from phonebridge.telemetry import HostTelemetry

class PerformanceTests(unittest.TestCase):
    def name(self,pid,engine=0,kind='3D',luid='12'):
        return f'pid_{pid}_luid_0x00000000_0x000000{luid}_phys_0_eng_{engine}_engtype_{kind}'
    def test_processes_sum_per_engine_but_independent_engines_use_max(self):
        result=aggregate_engines({self.name(1):30,self.name(2):25,self.name(1,1):80})
        self.assertEqual(result[(0,0x12,0)]['3d'],80)
    def test_percent_caps_after_sum_and_separates_physical_gpus(self):
        result=aggregate_engines({self.name(1):80,self.name(2):70,self.name(3,luid='13'):10})
        self.assertEqual(result[(0,0x12,0)]['3d'],100);self.assertEqual(result[(0,0x13,0)]['3d'],10)
    def test_bad_counters_do_not_become_zero(self):
        self.assertEqual(aggregate_engines({self.name(1):float('nan'),self.name(2):-1,'bad':20}),{})
    def test_pci_mapping_not_description_or_index(self):
        adapters=[{'vendor':0x10de,'pci':(2,0,0),'luid':(0,12)},{'vendor':0x10de,'pci':(131,0,0),'luid':(0,13)}]
        self.assertEqual(match_adapter('00000000:83:00.0',adapters),(0,13))
        self.assertIsNone(match_adapter('00000001:83:00.0',adapters));self.assertIsNone(match_adapter('bad',adapters))
        self.assertIsNone(match_adapter('00000000:83:00.0',adapters+[adapters[1]]))
    def test_disk_totals_not_counted_twice_and_capacity_is_partition_based(self):
        raw={'read_mbps':{'_Total':1048576*20,'1 C: D:':1048576*10},'write_mbps':{'1 C: D:':1048576},'idle_percent':{'1 C: D:':75}}
        volumes={'C:':{'mount':'C:','free_gb':20,'total_gb':100},'D:':{'mount':'D:','free_gb':30,'total_gb':200}}
        result=build_disks(raw,volumes);self.assertEqual(len(result),1);disk=result[0]
        self.assertEqual(disk['read_mbps'],10);self.assertEqual(disk['write_mbps'],1);self.assertEqual(disk['free_gb'],50);self.assertEqual(disk['total_gb'],300);self.assertEqual(disk['load_percent'],25)
    def test_latency_converts_seconds_and_idle_latency_is_unavailable(self):
        raw={'read_latency_ms':{'0 E:':.004},'read_iops':{'0 E:':2},'write_latency_ms':{'0 E:':0},'write_iops':{'0 E:':0}}
        d=build_disks(raw,{})[0];self.assertEqual(d['read_latency_ms'],4);self.assertIsNone(d['write_latency_ms']);self.assertIsNone(d['free_gb'])
    def test_partial_counter_warmup_remains_none(self):
        d=build_disks({'queue_length':{'0 E:':0}}, {})[0]
        self.assertIsNone(d['load_percent']);self.assertIsNone(d['read_mbps']);self.assertIsNone(d['read_latency_ms'])
    def test_disk_detail_keeps_history_isolated(self):
        s=HostTelemetry.__new__(HostTelemetry);s.lock=threading.Lock();s.value={'disks':[{'index':2,'read_mbps':3}],'error':''};s.history=[{'time':1,'disks':[{'index':2,'read_mbps':3}]}]
        data=s.detail('disk',2);data['history'][0]['read_mbps']=999
        self.assertEqual(s.detail('disk',2)['history'][0]['read_mbps'],3)
    def test_native_theme_has_no_actionbar(self):
        from pathlib import Path
        import xml.etree.ElementTree as ET
        root=Path(__file__).resolve().parent.parent
        theme=ET.parse(root/'android/app/res/values/styles.xml').getroot().find("style[@name='PhoneBridgeTheme']")
        values={i.attrib['name']:i.text for i in theme}
        self.assertEqual(values['android:windowActionBar'],'false');self.assertEqual(values['android:windowNoTitle'],'true')

