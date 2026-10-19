"""Read fresh CPU-only snapshots from the separately elevated local sampler."""
import json
import math
import os
import subprocess
import time
from pathlib import Path
from .config import ROOT

CACHE = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'PhoneBridge/Telemetry/cpu.json'

def unavailable(note):
    return {'temperature_c': None, 'temperature_source': '', 'temperature_note': note, 'cores': []}

def read_temperature(path=CACHE, now=None):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            return unavailable('CPU 温度数据过大')
        data = json.loads(raw)
        if not isinstance(data, dict) or type(data.get('schema')) is not int or data.get('schema') != 1:
            return unavailable('CPU 温度数据格式不兼容')
        current = time.time() if now is None else now
        updated = data.get('updated_at')
        if isinstance(updated, bool) or not isinstance(updated, (int, float)) or not math.isfinite(updated) or not -2 <= current-updated <= 5:
            return unavailable('CPU 温度采集已停止，请在电脑版启用 CPU 温度')
        value, source = data.get('temperature_c'), data.get('temperature_source')
        if value is None:
            return unavailable('CPU 传感器未返回温度：'+str(data.get('temperature_note', '未知原因'))[:180])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 150:
            return unavailable('CPU 温度数值无效')
        if source not in ('CPU Package', 'Core Max'):
            return unavailable('拒绝将非 CPU 封装/核心温度作为 CPU 温度')
        cores = []
        for item in data.get('cores', [])[:128]:
            if not isinstance(item, dict): continue
            name = str(item.get('name', ''))[:60]
            if 'distance' in name.lower() or not name.startswith(('P-Core #','E-Core #','CPU Core #')):
                continue
            temp = item.get('temperature_c')
            if isinstance(temp, (int, float)) and not isinstance(temp, bool) and math.isfinite(temp) and 0 < temp <= 150:
                cores.append({'name': name, 'temperature_c': round(temp, 1)})
        return {'temperature_c': round(value, 1), 'temperature_source': source,
                'temperature_note': '', 'cores': cores}
    except FileNotFoundError:
        return unavailable('请在电脑版点击“启用 CPU 温度（管理员）”')
    except (OSError, ValueError, TypeError):
        return unavailable('CPU 温度读取失败，等待下一次采样')

def start_sampler():
    # Only a direct local GUI action requests UAC; never expose elevation via API.
    script = ROOT/'scripts/cpu-temperature.ps1'
    executable = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(executable), '-NoProfile', '-ExecutionPolicy', 'Bypass',
                             '-File', str(script), '-OwnerPid', str(os.getpid()), '-InstallDriver'],
                            capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('温度采集未启动：请确认管理员弹窗；详情见采集器 setup.log')
    return {'requested': True, 'note': '请确认管理员弹窗；温度将在面板自动刷新'}
