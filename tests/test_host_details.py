from pathlib import Path
import socket
from types import SimpleNamespace
import unittest
from phonebridge.host_details import BASELINE,fields,network_sample,merge_gpus,parse_dxdiag
from phonebridge.performance import build_disks


class HardwareDetailTests(unittest.TestCase):
    def test_virtual_dxgi_sentinel_is_not_a_physical_gpu(self):
        from phonebridge.gpu_identity import physical_pci
        self.assertTrue(physical_pci((2,0,0)))
        self.assertTrue(physical_pci((131,0,0)))
        self.assertFalse(physical_pci((4294967295,65535,65535)))

    def test_dashboard_model_labels_reach_visible_gauges(self):
        root=Path(__file__).resolve().parents[1]/'android/app/src'
        dashboard=(root/'DashboardActivity.java').read_text(encoding='utf-8')
        gauge=(root/'InstrumentGauge.java').read_text(encoding='utf-8')
        self.assertIn('card.gauge.setModel(title)',dashboard)
        self.assertIn('HardwareNames.compact',dashboard)
        self.assertIn('model.isEmpty()?name:model',gauge)

    def test_baseline_fields_are_never_omitted_when_unavailable(self):
        for kind,expected in BASELINE.items():
            rows=fields(kind,{})
            keys={r['key'] for r in rows}
            self.assertTrue(set(expected)<=keys,(kind,set(expected)-keys))
            for row in rows:
                if row['value'] is None:
                    self.assertFalse(row['available']);self.assertTrue(row['note'])

    def test_zero_false_and_unavailable_remain_distinct(self):
        rows={r['key']:r for r in fields('cpu',{'load_percent':0,'virtualization_enabled':False})}
        self.assertEqual(rows['load_percent']['value'],0)
        self.assertTrue(rows['load_percent']['available'])
        self.assertIs(rows['virtualization_enabled']['value'],False)
        self.assertTrue(rows['virtualization_enabled']['available'])
        self.assertIsNone(rows['thread_count']['value'])

    def counter(self,sent,received):
        return SimpleNamespace(bytes_sent=sent,bytes_recv=received,packets_sent=1,packets_recv=2,errin=0,errout=0,dropin=0,dropout=0)

    def test_network_warmup_and_units(self):
        states={'test':SimpleNamespace(isup=True,speed=1000,mtu=1500)}
        first,old=network_sample({},1,{'test':self.counter(0,0)},{},states)
        self.assertIsNone(first[0]['send_mbps'])
        second,_=network_sample(old,2,{'test':self.counter(125000,250000)},{},states)
        self.assertEqual(second[0]['send_mbps'],1)
        self.assertEqual(second[0]['receive_mbps'],2)

    def test_network_counter_reset_does_not_invent_negative_or_zero(self):
        values,_=network_sample({'test':(1,100,100)},2,{'test':self.counter(0,0)},{},{})
        self.assertIsNone(values[0]['send_mbps'])
        self.assertIsNone(values[0]['link_mbps'])

    def test_integrated_gpu_added_without_index_based_sensor_assignment(self):
        adapters=[{'name':'Intel test','vendor':0x8086,'pci':(0,2,0),'luid':(0,42),'dedicated_total_mb':128,'shared_total_mb':16000}]
        values=merge_gpus([],adapters,[],{(0,42,0):{'3d':7}},{(0,42,0):{'shared_mb':256}})
        self.assertEqual(values[0]['name'],'Intel test')
        self.assertEqual(values[0]['engines']['three_d_percent'],7)
        self.assertEqual(values[0]['shared_used_mb'],256)
        self.assertIsNone(values[0]['temperature_c'])

    def test_ambiguous_engine_or_driver_mapping_is_unavailable(self):
        adapters=[{'name':'test','vendor':0x8086,'pci':(0,2,0),'luid':(0,42)}]
        driver={'Bus':0,'Address':2<<16,'DriverVersion':'test'}
        value=merge_gpus([],adapters,[driver,driver],{(0,42,0):{'3d':5},(0,42,1):{'3d':9}},{})[0]
        self.assertIsNone(value['load_percent']);self.assertIsNone(value['driver_version'])

    def test_weighted_disk_latency_and_no_io(self):
        raw={'read_iops':{'0 C:':2},'write_iops':{'0 C:':6},'read_latency_ms':{'0 C:':.003},'write_latency_ms':{'0 C:':.007}}
        self.assertEqual(build_disks(raw,{})[0]['response_latency_ms'],6)
        self.assertIsNone(build_disks({'read_iops':{'0 C:':0},'write_iops':{'0 C:':0}}, {})[0]['response_latency_ms'])

    def test_dxdiag_extracts_only_public_hardware_fields(self):
        xml='<DxDiag><SystemInformation><MachineName>PRIVATE</MachineName><DirectXVersion>DirectX 12</DirectXVersion></SystemInformation><DisplayDevices><DisplayDevice><CardName>GPU</CardName><DriverModel>WDDM 3.2</DriverModel><DDIVersion>12</DDIVersion></DisplayDevice></DisplayDevices></DxDiag>'
        value=parse_dxdiag(xml)
        self.assertEqual(value['directx_version'],'DirectX 12')
        self.assertEqual(value['gpus'][0]['driver_model'],'WDDM 3.2')
        self.assertNotIn('PRIVATE',str(value))

    def test_missing_counter_reason_admits_unimplemented_provider(self):
        row=next(r for r in fields('memory',{}) if r['key']=='compressed_gb')
        self.assertIn('尚未接入',row['note'])

    def test_secondary_background_and_native_widgets_use_actual_theme(self):
        root=Path(__file__).resolve().parents[1]/'android/app/src'
        style=(root/'PanelStyle.java').read_text(encoding='utf-8')
        self.assertIn('new ColorDrawable(PanelTheme.background())',style)
        self.assertNotIn('new ColorDrawable(BG)',style)
        theme=(root/'PanelTheme.java').read_text(encoding='utf-8')
        self.assertIn('Theme_Material_NoActionBar',theme)
        self.assertIn('setBackgroundDrawable',theme)

    def test_catalog_and_detail_keep_network_npu_and_extra_gpu_accessible(self):
        root=Path(__file__).resolve().parents[1]/'android/app/src'
        source=(root/'HardwareActivity.java').read_text(encoding='utf-8')
        for name in ('gpus','networks','npus','disks'):self.assertIn('"'+name+'"',source)
        source=(root/'DetailActivity.java').read_text(encoding='utf-8')
        self.assertIn('HardwareFields.format(data)',source)
        self.assertIn('drawCores',source)
