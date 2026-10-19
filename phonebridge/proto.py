"""PhoneBridge 协议 (protocol/protocol.md) - Windows 侧实现"""
import struct
import json

MAGIC = b'PB01'
HEADER = struct.Struct('<4sHH I Q Q I I')  # 36 bytes
assert HEADER.size == 36

T_PING, T_PONG = 0x0001, 0x0002
T_GET_CAPABILITIES, T_CAPABILITIES = 0x0010, 0x0011
T_GET_STATUS, T_STATUS = 0x0012, 0x0013
T_CAMERA_LIST, T_CAMERA_LIST_RESULT = 0x0020, 0x0021
T_CAMERA_OPEN, T_CAMERA_OPEN_RESULT = 0x0022, 0x0023
T_CAMERA_CLOSE = 0x0024
T_CAMERA_SWITCH, T_CAMERA_SWITCH_RESULT = 0x0025, 0x0026
T_MIC_START, T_MIC_START_RESULT, T_MIC_STOP = 0x0030, 0x0031, 0x0032
T_SENSOR_START, T_SENSOR_START_RESULT, T_SENSOR_STOP = 0x0040, 0x0041, 0x0042
T_GPS_START, T_GPS_STOP = 0x0050, 0x0051
T_TORCH_ON, T_TORCH_OFF = 0x0060, 0x0061
T_VIBRATE = 0x0070
T_IR_SEND, T_IR_SEND_RESULT = 0x0080, 0x0081
T_BLE_SCAN, T_BLE_SCAN_RESULT = 0x0090, 0x0091
T_VIDEO_FRAME = 0x1001
T_AUDIO_PACKET = 0x1002
T_SENSOR_EVENT = 0x1003
T_GPS_EVENT = 0x1004
T_ERROR = 0xFFFF

F_KEY_FRAME = 1
F_START_OF_STREAM = 2
F_END_OF_STREAM = 4
F_TIMESTAMP_VALID = 16

STREAMS = {1: 'control', 2: 'video', 3: 'audio', 4: 'sensor'}
PORTS = {1: 27183, 2: 27184, 3: 27185, 4: 27186}

SENSORS = {'accel': 1, 'mag': 2, 'gyro': 4, 'light': 5, 'prox': 8, 'rot': 11}


def frame(t: int, stream_id: int, seq: int, ts_ns: int, flags: int, payload: bytes) -> bytes:
    return HEADER.pack(MAGIC, 1, t, stream_id, seq, ts_ns, flags, len(payload)) + payload


def frame_json(t: int, stream_id: int, seq: int, obj) -> bytes:
    return frame(t, stream_id, seq, 0, 0, json.dumps(obj).encode('utf-8'))


class Frame:
    __slots__ = ('version', 'type', 'stream_id', 'seq', 'ts_ns', 'flags', 'payload')

    def json(self):
        return json.loads(self.payload.decode('utf-8', errors='replace'))


class FrameReader:
    """从 socket 字节流切帧"""

    def __init__(self):
        self.buf = b''

    def feed(self, data: bytes, out: list):
        self.buf += data
        while len(self.buf) >= HEADER.size:
            if self.buf[:4] != MAGIC:
                # 重新同步
                idx = self.buf.find(MAGIC, 1)
                self.buf = self.buf[idx:] if idx > 0 else b''
                if not self.buf:
                    return
                continue
            magic, ver, t, sid, seq, ts, flags, size = HEADER.unpack_from(self.buf)
            if size > (16 << 20) or size < 0:
                self.buf = self.buf[4:]
                continue
            if len(self.buf) < HEADER.size + size:
                return
            f = Frame()
            f.version, f.type, f.stream_id, f.seq, f.ts_ns, f.flags = ver, t, sid, seq, ts, flags
            f.payload = self.buf[HEADER.size:HEADER.size + size]
            self.buf = self.buf[HEADER.size + size:]
            out.append(f)
