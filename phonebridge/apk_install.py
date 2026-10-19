"""Single bounded APK installation job. Never accepts a path or shell command."""
import threading
import time
from .transport import BridgeError

class ApkInstaller:
    def __init__(self,bridge):
        self.bridge=bridge
        self.lock=threading.Lock()
        self.job={'state':'idle','message':'选择手机后，可通过 USB 发起安装。'}

    def devices(self):
        # Network ADB and emulators are not presented as physical USB phones.
        return [d for d in self.bridge.detect() if ':' not in d['serial']
                and not d['serial'].startswith(('emulator-','usb:','usb-error:'))
                and '_adb-tls-' not in d['serial'] and not d['serial'].endswith('._tcp')]

    def status(self):
        with self.lock:return dict(self.job)

    def start(self,serial,confirmed=False):
        if confirmed is not True:raise BridgeError('请先确认只向自己的手机安装 PhoneBridge')
        if not isinstance(serial,str) or len(serial)>256:raise BridgeError('无效的设备选择')
        with self.lock:
            if self.job['state']=='installing':raise BridgeError('已有安装任务，请等待手机确认，不要重复点击')
            if not any(d['serial']==serial and d['state']=='device' for d in self.devices()):
                raise BridgeError('手机未连接或未授权。请插线、开启 USB 调试，并允许自己的电脑')
            self.job={'state':'installing','serial':serial,'started_at':time.time(),
                      'message':'已发起安装，请解锁手机并确认安装。系统风险检查可能需要一些时间。'}
        threading.Thread(target=self._install,args=(serial,),daemon=True,name='pb-apk-install').start()
        return self.status()

    def _install(self,serial):
        try:
            result=self.bridge.install(serial=serial)
            value={'state':'success','message':'PhoneBridge 安装成功。请打开手机 App，然后在电脑端连接。'}
        except Exception as exc:
            raw=str(exc)
            if any(s in raw for s in ('USER_RESTRICTED','User rejected','INSTALL_FAILED_ABORTED')):
                message='手机拒绝了安装或未完成确认。请解锁手机检查安装页；也可下载 APK 手动安装。不会自动重试。'
            elif 'UPDATE_INCOMPATIBLE' in raw:
                message='手机现有 App 与此安装包签名不同，不能覆盖。请先备份设置并核对来源，不会自动卸载旧版。'
            elif isinstance(exc,TimeoutError) or 'timed out' in raw:
                message='安装等待超时。请先检查手机是否已安装成功，再决定是否重试。'
            else:message='安装失败：'+raw[:600]
            value={'state':'error','message':message}
        with self.lock:self.job.update(value)
