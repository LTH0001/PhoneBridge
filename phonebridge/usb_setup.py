"""Conservative wired discovery/bootstrap. Never installs or alters a driver.

Only explicitly supported phone IDs are eligible for the AOA mode switch.
Discovery reads cached USB descriptors, not strings/control requests on devices.
"""
import time
import json
import os
import subprocess
from .accessory import AOA_VENDOR, AOA_PRODUCTS, backend, switch
from .transport import BridgeError

# Verified local vivo configurations. This is NOT a universal Android VID list.
PHONE_IDS = {(0x2d95, pid) for pid in (0x6011, 0x6012, 0x6013)}

def failed_local_accessory():
    """Read-only fallback for one unambiguous failed no-debug AOA device.

    A failed-start AOA device may be absent from libusb's enumeration entirely.
    Never use this PnP record as a substitute handle or choose another device.
    """
    if os.name != 'nt':
        return None
    script = r'''[Console]::OutputEncoding=[Text.UTF8Encoding]::new();
$devices=@(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
Where-Object {$_.InstanceId -match '^USB\\VID_18D1&PID_2D00\\[^\\]+$'});
if($devices.Count -eq 1){$id=$devices[0].InstanceId;
$p=Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_ProblemCode -ErrorAction Stop;
@{instance=$id;problem=[int]$p.Data} | ConvertTo-Json -Compress}'''
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
            capture_output=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not result.stdout.strip():
            return None
        status=json.loads(result.stdout.decode('utf-8-sig'))
        return status if int(status.get('problem',0)) > 0 else None
    except (OSError,subprocess.TimeoutExpired,ValueError):
        return None

def startup_error(status):
    return BridgeError(f"手机已进入免调试 USB 外设模式，但 Windows 无法启动设备（代码 {status['problem']}）。"
        '这不是 USB 调试授权问题；驱动已配置不代表设备已启动。请尝试另一个 USB 插口后重试。')

def enumerate_usb():
    import usb.core
    return list(usb.core.find(find_all=True, backend=backend()))

def is_accessory(device):
    return device.idVendor == AOA_VENDOR and device.idProduct in AOA_PRODUCTS

def selector(device):
    return f'usb:{device.idVendor:04x}:{device.idProduct:04x}:{device.bus}:{device.address}'

def supported_devices():
    return [d for d in enumerate_usb()
            if is_accessory(d) or (d.idVendor, d.idProduct) in PHONE_IDS]

def discover():
    found = [{'serial': selector(d), 'transport': 'accessory',
             'state': 'USB 外设 · 待连接授权' if is_accessory(d) else 'vivo USB · 需要模式初始化',
             'detail': f'{d.idVendor:04x}:{d.idProduct:04x}'} for d in supported_devices()]
    if not found:
        failure=failed_local_accessory()
        if failure:
            found.append({'serial':'usb-error:18d1:2d00','transport':'accessory',
                          'state':f"免调试 USB · Windows 启动失败（{failure['problem']}）",'detail':failure['instance']})
    return found

def prepare(selected='', timeout=12):
    """Switch only the selected supported phone, then match its physical port.

    No ADB fallback, driver changes, USB resets or probes of unrelated devices.
    """
    import usb.util
    candidates = supported_devices()
    if selected:
        candidates = [d for d in candidates if selector(d) == selected]
    if len(candidates) != 1:
        if not candidates:
            failure=failed_local_accessory()
            if failure:
                raise startup_error(failure)
        raise BridgeError('请选择一台支持的 USB 手机；设备已变化时请先刷新。不会切换其他 USB 设备。')
    device = candidates[0]
    if is_accessory(device):
        return device
    location = (device.bus, tuple(device.port_numbers or ()))
    if not location[1]:
        raise BridgeError('无法确认手机所在 USB 端口，已停止自动切换；未修改设备或驱动')
    try:
        switch(device)
    except Exception as exc:
        raise BridgeError(
            f'已检测到手机 {device.idVendor:04x}:{device.idProduct:04x}，但 Windows 当前接口不允许 AOA 初始化。'
            '尚需配置免调试 USB 的初始接入方式；重复刷新或允许 USB 调试不是此模式的解决办法。'
            f'未修改驱动。底层错误：{exc}') from exc
    finally:
        usb.util.dispose_resources(device)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        matches = [d for d in supported_devices() if is_accessory(d)
                   and (d.bus, tuple(d.port_numbers or ())) == location]
        if len(matches) == 1:
            return matches[0]
        time.sleep(.25)
    failure=failed_local_accessory()
    if failure:
        raise startup_error(failure)
    raise BridgeError('已请求手机进入 USB 外设模式，但原 USB 端口未出现可访问的 AOA 设备；请检查手机提示后刷新重试')
