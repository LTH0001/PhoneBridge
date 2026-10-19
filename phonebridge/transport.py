"""One owner per stream. Dynamic ADB forwarding and serialized commands."""
import json
import socket
import struct
import subprocess
import threading
import time
from . import proto

MAX_PAYLOAD = 16 * 1024 * 1024

class BridgeError(RuntimeError):
    pass

class CommandError(BridgeError):
    """A valid negative response, not a broken connection."""
    pass

def adb_run(adb, serial, *args, timeout=20):
    cmd = [str(adb)] + (['-s', serial] if serial else []) + list(args)
    p = subprocess.run(cmd, capture_output=True, timeout=timeout,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    out = p.stdout.decode('utf-8', errors='replace').strip()
    if p.returncode:
        raise BridgeError(p.stderr.decode('utf-8', errors='replace').strip() or out)
    return out

def devices(adb):
    result = []
    for line in adb_run(adb, '', 'devices', '-l').splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2:
            result.append({'serial': fields[0], 'state': fields[1], 'detail': ' '.join(fields[2:])})
    return result

def read_exact(sock, size):
    chunks = bytearray()
    while len(chunks) < size:
        part = sock.recv(size - len(chunks))
        if not part:
            raise BridgeError('手机通道已断开')
        chunks.extend(part)
    return bytes(chunks)

def read_frame(sock):
    magic, version, kind, stream, sequence, ts, flags, size = proto.HEADER.unpack(read_exact(sock, 36))
    if magic != proto.MAGIC or version != 1 or not 1 <= stream <= 4 or size > MAX_PAYLOAD:
        raise BridgeError('无效的 PhoneBridge 协议帧')
    return kind, stream, sequence, ts, flags, read_exact(sock, size)

class Transport:
    def __init__(self, adb, serial, on_frame, on_disconnect):
        self.adb, self.serial = adb, serial
        self.on_frame, self.on_disconnect = on_frame, on_disconnect
        self.socks, self.ports, self.threads = {}, [], []
        self.command_lock = threading.RLock()
        self.video_write_lock = threading.Lock()
        self.closed = threading.Event()
        self.seq = 0

    def connect(self):
        try:
            # Data channels are accepted before the first control command.
            for sid in (2, 3, 4, 1):
                port = int(adb_run(self.adb, self.serial, 'forward', 'tcp:0', f'tcp:{proto.PORTS[sid]}'))
                self.ports.append(port)
                sock = socket.create_connection(('127.0.0.1', port), timeout=8)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.settimeout(None if sid != 1 else 10)
                self.socks[sid] = sock
            self.start_readers()
            return self
        except Exception:
            self.close()
            raise

    def start_readers(self):
        self.request(proto.T_GET_STATUS, expect=proto.T_STATUS)
        for sid in (2,3,4):
            t=threading.Thread(target=self._reader,args=(sid,),daemon=True,name=f'pb-stream-{sid}')
            t.start();self.threads.append(t)

    def request(self, kind, obj=None, expect=None, timeout=15):
        # Do not retry side-effecting commands: a timeout does not mean failure.
        with self.command_lock:
            if self.closed.is_set():
                raise BridgeError('PhoneBridge 尚未连接')
            sock = self.socks[1]
            self.seq += 1
            payload = json.dumps(obj or {}).encode('utf-8')
            sock.settimeout(timeout)
            try:
                sock.sendall(proto.frame(kind, 1, self.seq, time.monotonic_ns(), 16, payload))
                frame = read_frame(sock)
                if frame[1] != 1 or frame[0] not in (expect, proto.T_ERROR):
                    raise BridgeError('控制响应不匹配；需要重新连接')
                data = json.loads(frame[5])
                if frame[0] == proto.T_ERROR or data.get('ok') is False:
                    raise CommandError(data.get('message', data.get('error', '手机操作失败')))
                return data
            except CommandError:
                raise
            except (OSError, BridgeError):
                # Any ambiguous response invalidates the connection, so a late
                # reply cannot accidentally satisfy a subsequent command.
                self.close()
                self.on_disconnect('控制通道中断或命令失败')
                raise

    def _reader(self, sid):
        try:
            while not self.closed.is_set():
                frame = read_frame(self.socks[sid])
                if frame[1] != sid:
                    raise BridgeError('数据通道不匹配')
                self.on_frame(frame)
        except Exception as exc:
            if not self.closed.is_set():
                self.close()
                self.on_disconnect(str(exc))

    def send_video(self, payload, sequence, timestamp_ns):
        with self.video_write_lock:
            if self.closed.is_set():
                raise BridgeError('副屏 USB 通道已断开')
            self.socks[2].sendall(proto.frame(0x2001, 2, sequence, timestamp_ns, 16, payload))

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        for sock in list(self.socks.values()):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        for port in self.ports:
            try:
                adb_run(self.adb, self.serial, 'forward', '--remove', f'tcp:{port}', timeout=3)
            except Exception:
                pass
        self.ports.clear()

