"""Small dependency-free SDK for applications using the local PhoneBridge host."""
import json
import urllib.request
from pathlib import Path

class PhoneBridgeClient:
    def __init__(self, url, token):
        self.url = url.rstrip('/')
        self.token = token

    @classmethod
    def local(cls, credentials=None):
        from .config import data_root
        path = Path(credentials) if credentials else data_root()/'runtime/api.json'
        return cls(**json.loads(path.read_text('utf-8')))

    def request(self, path, data=None):
        payload = json.dumps(data).encode('utf-8') if data is not None else None
        req = urllib.request.Request(self.url+path, data=payload,
                  headers={'Authorization': 'Bearer '+self.token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)

    def status(self): return self.request('/api/status')
    def capabilities(self): return self.request('/api/capabilities')
    def sensors(self): return self.request('/api/sensors')
    def sensor_start(self, sensor=4, rate=100): return self.request('/api/sensor/start', {'sensor': sensor, 'rate': rate})
    def sensor_stop(self, sensor=4): return self.request('/api/sensor/stop', {'sensor': sensor})
    def camera_start(self, camera_id=None, width=1280, height=720, virtual=True):
        options = {'width': width, 'height': height, 'virtual': virtual}
        if camera_id is not None:
            options['camera_id'] = camera_id
        return self.request('/api/camera/start', options)
    def camera_stop(self): return self.request('/api/camera/stop', {})
    def mic_start(self, device=-1): return self.request('/api/mic/start', {'device': device})
    def mic_stop(self): return self.request('/api/mic/stop', {})
    def display_start(self, touch=True, max_width=3840, fps=30, desktop_width=640, layout='below-left',quality='sharp',dpi_scale=None):
        return self.request('/api/display/native-start',{'extended':True,'touch':touch,'max_width':max_width,'fps':fps,
                            'desktop_width':desktop_width,'layout':layout,'quality':quality,'dpi_scale':dpi_scale})
    def display_stop(self): return self.request('/api/display/native-stop',{})
    def files(self, path='/sdcard'): return self.request('/api/files/list',{'path':path})
    def download(self, path, destination): return self.request('/api/files/download',{'path':path,'destination':destination})
    def permissions(self): return self.request('/api/permissions')
    def dashboard(self): return self.request('/api/dashboard/status')
    def dashboard_start(self): return self.request('/api/dashboard/start',{})
    def dashboard_desktop(self): return self.request('/api/dashboard/desktop',{})
    def hardware_detail(self,kind,index=0):return self.request('/api/dashboard/detail',{'kind':kind,'index':index})
    def system_info(self,query='',page=0,limit=40,sort='memory'):return self.request('/api/system/status',{'query':query,'page':page,'limit':limit,'sort':sort})
    def playback(self):return self.request('/api/playback/status')
    def playback_control(self,action,device_id=None,value=None):return self.request('/api/playback/control',{'action':action,'device_id':device_id,'value':value})
    def lyrics(self,allow_network=False,retry=False):return self.request('/api/music/lyrics',{'allow_network':allow_network,'retry':retry})
    def music_control(self,action,source_app_id=None):
        return self.request('/api/music/control',{'action':action,'source_app_id':source_app_id})

