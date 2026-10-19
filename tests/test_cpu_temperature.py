import json
import tempfile
import unittest
from pathlib import Path
from phonebridge.cpu_temperature import read_temperature

class CpuTemperatureTests(unittest.TestCase):
    def sample(self, **changes):
        data={'schema':1,'updated_at':1000,'temperature_c':45.5,
              'temperature_source':'CPU Package','temperature_note':'',
              'cores':[{'name':'P-Core #1','temperature_c':43}]}
        data.update(changes)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cpu.json'
            path.write_text(json.dumps(data),'utf-8')
            return read_temperature(path,now=1001)

    def test_package_and_core_fallback(self):
        self.assertEqual(self.sample()['temperature_c'],45.5)
        self.assertEqual(self.sample(temperature_source='Core Max')['temperature_source'],'Core Max')
        self.assertEqual(self.sample()['cores'][0]['temperature_c'],43)

    def test_stale_and_future_samples_hidden(self):
        for timestamp in (900,1004,float('nan'),True):
            with self.subTest(timestamp=timestamp):
                self.assertIsNone(self.sample(updated_at=timestamp)['temperature_c'])

    def test_invalid_temperature_hidden(self):
        for value in (True,0,-1,151,float('nan'),float('inf'),'45',None):
            with self.subTest(value=value):
                self.assertIsNone(self.sample(temperature_c=value)['temperature_c'])

    def test_acpi_and_distance_sensors_rejected(self):
        for source in ('ACPI Thermal Zone','Distance to TjMax','Motherboard',''):
            self.assertIsNone(self.sample(temperature_source=source)['temperature_c'])

    def test_missing_and_malformed_data_do_not_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cpu.json'
            self.assertIsNone(read_temperature(path)['temperature_c'])
            for raw in ('broken','[]','{}','x'*65537):
                path.write_text(raw,'utf-8')
                self.assertIsNone(read_temperature(path)['temperature_c'])

    def test_bad_cores_do_not_leak_invalid_metrics(self):
        result=self.sample(cores=[{'temperature_c':True},{'temperature_c':float('nan')},None,
                                 {'name':'P-Core #1 Distance to TjMax','temperature_c':65},
                                 {'name':'Motherboard','temperature_c':45}])
        self.assertEqual(result['cores'],[])
        self.assertEqual(result['temperature_c'],45.5)

    def test_boolean_schema_is_not_a_version(self):
        self.assertIsNone(self.sample(schema=True)['temperature_c'])
