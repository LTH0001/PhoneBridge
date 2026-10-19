"""Explicit, interface-bound TLS pairing. No ADB, discovery broadcast or public HTTP."""
import base64
import datetime
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import ssl
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from .transport import Transport, BridgeError

GET = {'/api/dashboard/status','/api/playback/status','/api/music/lyrics'}
POST = {'/api/dashboard/enter','/api/dashboard/desktop','/api/dashboard/detail',
        '/api/speech/recognize',
        '/api/speech/start','/api/speech/chunk','/api/speech/finish',
        '/api/input/begin','/api/input/end','/api/input/events','/api/input/text',
        '/api/input/desktop',
        '/api/input/previous',
        '/api/music/control','/api/playback/control','/api/music/lyrics',
        '/api/system/status','/api/system/process'}

def local_addresses():
    import psutil
    result=[]
    for name, addresses in psutil.net_if_addrs().items():
        if any(word in name.lower() for word in ('tailscale','loopback','bluetooth')): continue
        for a in addresses:
            if a.family == socket.AF_INET:
                ip=ipaddress.ip_address(a.address)
                if ip.is_private and not ip.is_loopback and not ip.is_link_local:
                    result.append((name,a.address))
    return result

def tls_context():
    key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'PhoneBridge local pairing')])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
          .not_valid_after(now+datetime.timedelta(days=1)).sign(key,hashes.SHA256()))
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    # Private key is ephemeral, and temporary files are removed immediately after load.
    with tempfile.TemporaryDirectory(prefix='PhoneBridge-TLS-') as folder:
        p=Path(folder)
        (p/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (p/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        context.load_cert_chain(p/'cert.pem',p/'key.pem')
    der=cert.public_bytes(serialization.Encoding.DER)
    return context,der,hashlib.sha256(der).hexdigest()

def receive(sock,limit=8192,chunked=False):
    data=bytearray()
    while len(data)<=limit:
        part=sock.recv(min(4096,limit+1-len(data)) if chunked else 1)
        if not part:raise BridgeError('无线连接中断')
        if chunked and b'\n' in part:
            line,tail=part.split(b'\n',1)
            if tail:raise BridgeError('无效请求尾部')
            data.extend(line)
            if len(data)>limit:raise BridgeError('无线请求过大')
            return json.loads(data)
        if part==b'\n':return json.loads(data)
        data.extend(part)
    raise BridgeError('无线请求过大')

def send(sock,data):
    sock.sendall(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()+b'\n')

class WirelessServer:
    def __init__(self,api,address):
        ip=ipaddress.ip_address(address)
        allowed={item[1] for item in local_addresses()}
        if address not in allowed and not ip.is_loopback:raise ValueError('请选择电脑的本地网卡 IPv4 地址')
        self.api,self.bridge=api,api.bridge
        self.context,self.certificate,self.pin=tls_context()
        self.invite=secrets.token_urlsafe(32);self.expires=time.monotonic()+120
        self.session='';self.channels={};self.pending=set();self.lock=threading.Lock()
        self.closed=threading.Event();self.limit=threading.BoundedSemaphore(12)
        self.listener=socket.socket();self.listener.bind((address,0 if ip.is_loopback else 27187));self.listener.listen(8);self.listener.settimeout(.5)
        self.address=address;self.port=self.listener.getsockname()[1]
        threading.Thread(target=self._accept,daemon=True,name='pb-wireless').start()

    def invitation(self):
        return f'pbw1:{self.address}:{self.port}:{self.pin}:{self.invite}'

    def _accept(self):
        while not self.closed.is_set():
            try:sock,_=self.listener.accept()
            except socket.timeout:continue
            except OSError:break
            if not self.limit.acquire(False):sock.close();continue
            with self.lock:self.pending.add(sock)
            threading.Thread(target=self._client,args=(sock,),daemon=True).start()

    def _client(self,raw):
        sock=raw;owned=False
        try:
            raw.settimeout(5);sock=self.context.wrap_socket(raw,server_side=True)
            with self.lock:self.pending.discard(raw);self.pending.add(sock)
            hello=receive(sock)
            sid=hello.get('sid')
            if type(sid) is not int or sid not in range(6):raise BridgeError('无效无线通道')
            credential=hello.get('token','')
            if not isinstance(credential,str) or len(credential)>128:raise BridgeError('无效凭据')
            with self.lock:
                if self.closed.is_set():raise BridgeError('无线已关闭')
                if sid==0:
                    if self.session or time.monotonic()>self.expires or not hmac.compare_digest(credential,self.invite):raise BridgeError('配对已失效')
                    if self.bridge.connected:raise BridgeError('请先断开 USB，再发起无线配对')
                    self.session=secrets.token_urlsafe(32);self.invite='';self.expires=time.monotonic()+20
                    send(sock,{'ok':True,'session':self.session})
                    threading.Thread(target=self._assembly_timeout,daemon=True).start()
                    return
                if not self.session or not hmac.compare_digest(credential,self.session):raise BridgeError('无线未授权')
                if sid in (1,2,3,4):
                    if sid in self.channels or time.monotonic()>self.expires:raise BridgeError('通道已占用或配对超时')
                    send(sock,{'ok':True});sock.settimeout(None);self.channels[sid]=sock;owned=True
                    if len(self.channels)==4:threading.Thread(target=self._activate,daemon=True).start()
                    return
            send(sock,{'ok':True})
            request=receive(sock,700000,chunked=True)
            send(sock,self.rpc(request))
        except Exception:
            # Never put pairing credentials or arbitrary request contents in logs.
            pass
        finally:
            with self.lock:self.pending.discard(raw);self.pending.discard(sock)
            if not owned:
                try:sock.close()
                except OSError:pass
            self.limit.release()

    def _assembly_timeout(self):
        if not self.closed.wait(20):
            with self.lock:incomplete=len(self.channels)!=4
            if incomplete:self.close()

    def _activate(self):
        try:
            transport=Transport('', 'wireless',self.bridge._frame,self.bridge._disconnected)
            transport.socks=dict(self.channels)
            transport.start_readers()
            self.bridge.attach_wireless(transport)
            self.api.start_panel()
        except Exception as exc:
            self.bridge.log('无线连接失败：'+type(exc).__name__);self.close()

    def rpc(self,request):
        if not isinstance(request,dict):raise BridgeError('无效请求')
        path=request.get('path','');body=request.get('body')
        art=isinstance(path,str) and __import__('re').fullmatch(r'/api/music/art\?key=[a-f0-9]{24}',path)
        if (body is None and path not in GET and not art) or (body is not None and path not in POST):
            return {'error':'无线客户端无权访问该接口'}
        if body is not None and not isinstance(body,dict):return {'error':'无效参数'}
        req=Request(f'http://127.0.0.1:{self.api.port}'+path,
                    data=None if body is None else json.dumps(body).encode(),
                    headers={'Authorization':'Bearer '+self.api.token,'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=15) as response:
                content=response.read(2*1024*1024+1)
                if len(content)>2*1024*1024:raise BridgeError('响应过大')
                return {'art':base64.b64encode(content).decode()} if art else json.loads(content)
        except Exception:return {'error':'电脑接口执行失败，请检查电脑面板'}

    def close(self):
        self.closed.set();self.listener.close()
        with self.lock:
            self.invite=self.session=''
            sockets=list(self.channels.values())+list(self.pending);self.pending.clear()
        for sock in sockets:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            try:sock.close()
            except OSError:pass
