package com.phonebridge.app;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

/**
 * PhoneBridge 统一协议头 (protocol/protocol.md)
 * magic(4) version(2) type(2) stream_id(4) sequence(8) timestamp_ns(8) flags(4) payload_size(4) = 36 bytes, LE
 */
public final class Proto {
    public static final byte[] MAGIC = { 'P', 'B', '0', '1' };
    public static final int HEADER_LEN = 36;
    public static final int VERSION = 1;

    // message types
    public static final int T_PING = 0x0001, T_PONG = 0x0002;
    public static final int T_GET_CAPABILITIES = 0x0010, T_CAPABILITIES = 0x0011;
    public static final int T_GET_STATUS = 0x0012, T_STATUS = 0x0013;
    public static final int T_CAMERA_LIST = 0x0020, T_CAMERA_LIST_RESULT = 0x0021;
    public static final int T_CAMERA_OPEN = 0x0022, T_CAMERA_OPEN_RESULT = 0x0023;
    public static final int T_CAMERA_CLOSE = 0x0024;
    public static final int T_CAMERA_SWITCH = 0x0025, T_CAMERA_SWITCH_RESULT = 0x0026;
    public static final int T_MIC_START = 0x0030, T_MIC_START_RESULT = 0x0031, T_MIC_STOP = 0x0032;
    public static final int T_SENSOR_START = 0x0040, T_SENSOR_START_RESULT = 0x0041, T_SENSOR_STOP = 0x0042;
    public static final int T_GPS_START = 0x0050, T_GPS_STOP = 0x0051;
    public static final int T_TORCH_ON = 0x0060, T_TORCH_OFF = 0x0061;
    public static final int T_VIBRATE = 0x0070;
    public static final int T_IR_SEND = 0x0080, T_IR_SEND_RESULT = 0x0081;
    public static final int T_BLE_SCAN = 0x0090, T_BLE_SCAN_RESULT = 0x0091;
    public static final int T_VIDEO_FRAME = 0x1001;
    public static final int T_AUDIO_PACKET = 0x1002;
    public static final int T_SENSOR_EVENT = 0x1003;
    public static final int T_GPS_EVENT = 0x1004;
    public static final int T_ERROR = 0xFFFF;

    // flags
    public static final int F_KEY_FRAME = 1;
    public static final int F_START_OF_STREAM = 2;
    public static final int F_END_OF_STREAM = 4;
    public static final int F_TIMESTAMP_VALID = 16;

    public static ByteBuffer header(int type, long sequence, long timestampNs, int flags, int payloadSize) {
        ByteBuffer b = ByteBuffer.allocate(HEADER_LEN).order(ByteOrder.LITTLE_ENDIAN);
        b.put(MAGIC);
        b.putShort((short) VERSION);
        b.putShort((short) type);
        b.putInt(0); // stream_id placeholder (filled per channel)
        b.putLong(sequence);
        b.putLong(timestampNs);
        b.putInt(flags);
        b.putInt(payloadSize);
        b.flip();
        return b;
    }

    public static void setStreamId(ByteBuffer header, int streamId) {
        header.putInt(8, streamId);
    }

    public static byte[] jsonBytes(String json) {
        return json.getBytes(StandardCharsets.UTF_8);
    }

    public static byte[] frame(int type, int streamId, long sequence, long timestampNs, int flags, byte[] payload) {
        ByteBuffer b = ByteBuffer.allocate(HEADER_LEN + payload.length).order(ByteOrder.LITTLE_ENDIAN);
        b.put(MAGIC);
        b.putShort((short) VERSION);
        b.putShort((short) type);
        b.putInt(streamId);
        b.putLong(sequence);
        b.putLong(timestampNs);
        b.putInt(flags);
        b.putInt(payload.length);
        b.put(payload);
        return b.array();
    }

    /** 从流中读取一帧; 返回 null 表示数据不足/流损坏 */
    public static Frame readFrame(byte[] buf, int off, int len) {
        if (len < HEADER_LEN) return null;
        if (buf[off] != 'P' || buf[off + 1] != 'B' || buf[off + 2] != '0' || buf[off + 3] != '1') return null;
        ByteBuffer b = ByteBuffer.wrap(buf, off, HEADER_LEN).order(ByteOrder.LITTLE_ENDIAN);
        b.getInt();
        int version = b.getShort() & 0xFFFF;
        int type = b.getShort() & 0xFFFF;
        int streamId = b.getInt();
        long sequence = b.getLong();
        long timestampNs = b.getLong();
        int flags = b.getInt();
        int payloadSize = b.getInt();
        if (payloadSize < 0 || payloadSize > (16 << 20)) return null;
        if (len - HEADER_LEN < payloadSize) return null; // need more data
        Frame f = new Frame();
        f.version = version; f.type = type; f.streamId = streamId;
        f.sequence = sequence; f.timestampNs = timestampNs;
        f.flags = flags; f.payload = new byte[payloadSize];
        System.arraycopy(buf, off + HEADER_LEN, f.payload, 0, payloadSize);
        f.totalLen = HEADER_LEN + payloadSize;
        return f;
    }

    public static class Frame {
        public int version, type, streamId, flags, totalLen;
        public long sequence, timestampNs;
        public byte[] payload;
        public String payloadJson() {
            return new String(payload, StandardCharsets.UTF_8);
        }
    }
}
