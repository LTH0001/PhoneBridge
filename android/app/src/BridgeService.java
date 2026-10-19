package com.phonebridge.app;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.SystemClock;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 前台服务: 四通道 TCP 服务 (127.0.0.1:27183-27186) + 命令分发 + 流管理
 * 端口: Control 27183 / Video 27184 / Audio 27185 / Sensor 27186 (与 PC 侧 adb forward 对应)
 */
public class BridgeService extends Service {
    private static final String TAG = "PB.Service";
    public static final String ACTION_START = "com.phonebridge.app.START";
    public static final String ACTION_STOP = "com.phonebridge.app.STOP";

    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicInteger clientCount = new AtomicInteger(0);
    private final AtomicLong txBytes = new AtomicLong(0);
    private final AtomicLong rxBytes = new AtomicLong(0);

    private volatile CameraStreamer camera;
    private volatile AudioStreamer audio;
    private volatile SensorStreamer sensors;
    public volatile DisplayReceiver display;
    private volatile OutputStream sensorOutput;
    private final java.util.concurrent.ExecutorService inputExecutor = java.util.concurrent.Executors.newSingleThreadExecutor();
    private Actuators actuators;
    private CapabilityScanner scanner;
    private final AtomicLong seq = new AtomicLong(0);

    private Thread[] acceptThreads = new Thread[4];
    private final ServerSocket[] listeners = new ServerSocket[4];
    private final Socket[] clients = new Socket[4];

    public static volatile BridgeService instance;

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        actuators = new Actuators(this);
        startForegroundCompat();
    }

    private void startForegroundCompat() {
        String chId = "pb_service";
        NotificationChannel ch = new NotificationChannel(chId, "PhoneBridge Bridge",
                NotificationManager.IMPORTANCE_LOW);
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(ch);
        Intent ni = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, ni,
                Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0);
        Notification n = new Notification.Builder(this, chId)
                .setSmallIcon(getResources().getIdentifier("ic_notification","drawable",getPackageName()))
                .setContentTitle("PhoneBridge")
                .setContentText("Bridge service running (ADB 27183-27186)")
                .setContentIntent(pi)
                .build();
        startForeground(1, n);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopBridge();
            stopSelf();
            return START_NOT_STICKY;
        }
        startBridge();
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    public void startBridge() {
        if (!running.compareAndSet(false, true)) return;
        Log.i(TAG, "startBridge");
        final int[] ports = { 27183, 27184, 27185, 27186 };
        final int[] streamIds = { 1, 2, 3, 4 };
        for (int i = 0; i < 4; i++) {
            final int port = ports[i], sid = streamIds[i];
            acceptThreads[i] = new Thread(() -> acceptLoop(port, sid), "pb-accept-" + port);
            acceptThreads[i].start();
        }
    }

    private void acceptLoop(int port, int streamId) {
        try (ServerSocket ss = new ServerSocket(port, 8, InetAddress.getLoopbackAddress())) {
            synchronized (listeners) {
                listeners[streamId - 1] = ss;
                if (!running.get()) { ss.close(); return; }
            }
            while (running.get()) {
                try {
                    Socket s = ss.accept();
                    synchronized (clients) {
                        if (clients[streamId - 1] != null) { s.close(); continue; }
                        clients[streamId - 1] = s;
                    }
                    clientCount.incrementAndGet();
                    new Thread(() -> handleChannel(s, streamId), "pb-ch-" + port).start();
                } catch (IOException e) {
                    if (running.get()) Log.w(TAG, "accept " + port, e);
                }
            }
        } catch (IOException e) {
            Log.e(TAG, "listen " + port, e);
        }
    }

    private void handleChannel(Socket socket, int streamId) {
        try {
            socket.setTcpNoDelay(true);
            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();
            switch (streamId) {
                case 1: controlLoop(in, out); break;
                case 2: {
                    // video: 接受连接即建立 CameraStreamer, 控制命令经 control 通道下达
                    final CameraStreamer mine = new CameraStreamer(this, out);
                    camera = mine;
                    try { pcVideoLoop(in); }
                    finally {
                        mine.close(); if (camera == mine) camera = null;
                        if (display != null) { display.stop(); display = null; }
                    }
                    break;
                }
                case 3: {
                    final AudioStreamer mine = new AudioStreamer(this, out);
                    audio = mine;
                    try { drainUntilClosed(in, out); }
                    finally { mine.stop(); if (audio == mine) audio = null; }
                    break;
                }
                case 4: {
                    final SensorStreamer mine = new SensorStreamer(this, out);
                    sensorOutput = out;
                    sensors = mine;
                    try { drainUntilClosed(in, out); }
                    finally { mine.close(); if (sensors == mine) { sensors = null; sensorOutput = null; } }
                    break;
                }
            }
        } catch (Throwable t) {
            Log.w(TAG, "channel " + streamId, t);
        } finally {
            try { socket.close(); } catch (IOException ig) { }
            synchronized (clients) {
                if (clients[streamId - 1] == socket) clients[streamId - 1] = null;
            }
            clientCount.decrementAndGet();
            if(WirelessLink.active() && streamId==1)WirelessLink.close();
        }
    }

    void acceptWireless(Socket socket,int sid)throws IOException{
        synchronized(clients){if(clients[sid-1]!=null)throw new IOException("已有 USB / 无线通道，请先断开");clients[sid-1]=socket;}
        clientCount.incrementAndGet();new Thread(() -> handleChannel(socket,sid),"pb-wireless-"+sid).start();
    }

    void serveAccessory(InputStream input,OutputStream output)throws Exception{
        synchronized(clients){if(clientCount.get()!=0)throw new IOException("请先断开其他传输");clientCount.incrementAndGet();}
        CameraStreamer mineCamera=new CameraStreamer(this,output);AudioStreamer mineAudio=new AudioStreamer(this,output);SensorStreamer mineSensors=new SensorStreamer(this,output);
        camera=mineCamera;audio=mineAudio;sensors=mineSensors;sensorOutput=output;
        try{while(running.get()&&AccessoryLink.active()){
            byte[] header=new byte[36];readFully(input,header);java.nio.ByteBuffer h=java.nio.ByteBuffer.wrap(header).order(java.nio.ByteOrder.LITTLE_ENDIAN);
            int size=h.getInt(32),sid=h.getInt(8);if(h.getInt(0)!=0x31304250||h.getShort(4)!=1||size<0||size>16*1024*1024||sid<1||sid>5)throw new IOException("无效 USB 帧");
            byte[] packet=new byte[36+size];System.arraycopy(header,0,packet,0,36);byte[] payload=new byte[size];readFully(input,payload);System.arraycopy(payload,0,packet,36,size);Proto.Frame frame=Proto.readFrame(packet,0,packet.length);
            if(sid==1)dispatch(frame,output);else if(sid==2&&frame.type==0x2001){DisplayReceiver receiver=display;if(receiver!=null)receiver.feed(payload);}
            else if(sid==5&&frame.type==0xc1)AccessoryLink.response(frame);else throw new IOException("USB 通道不匹配");
        }}finally{mineCamera.close();mineAudio.stop();mineSensors.close();camera=null;audio=null;sensors=null;sensorOutput=null;if(display!=null){display.stop();display=null;}clientCount.decrementAndGet();}
    }

    /** 阻塞读, 统计 rx 字节; 连接关闭时返回 */
    private void drainUntilClosed(InputStream in, OutputStream out) throws IOException {
        byte[] buf = new byte[16384];
        while (running.get()) {
            int n = in.read(buf);
            if (n < 0) break;
            rxBytes.addAndGet(n);
        }
    }

    private void controlLoop(InputStream in, OutputStream out) {
        byte[] acc = new byte[0];
        byte[] tmp = new byte[65536];
        try {
            while (running.get()) {
                int n = in.read(tmp);
                if (n < 0) break;
                rxBytes.addAndGet(n);
                byte[] merged = new byte[acc.length + n];
                System.arraycopy(acc, 0, merged, 0, acc.length);
                System.arraycopy(tmp, 0, merged, acc.length, n);
                acc = merged;
                // 逐个解析帧
                int off = 0;
                while (off < acc.length) {
                    Proto.Frame f = Proto.readFrame(acc, off, acc.length - off);
                    if (f == null) break;
                    off += f.totalLen;
                    dispatch(f, out);
                }
                if (off > 0) {
                    byte[] rest = new byte[acc.length - off];
                    System.arraycopy(acc, off, rest, 0, rest.length);
                    acc = rest;
                }
                if (acc.length > (16 << 20)) acc = new byte[0]; // 防御
            }
        } catch (Throwable t) {
            Log.w(TAG, "control loop", t);
        }
    }

    private void pcVideoLoop(InputStream in) throws IOException {
        byte[] header = new byte[Proto.HEADER_LEN];
        while (running.get()) {
            readFully(in, header);
            java.nio.ByteBuffer h = java.nio.ByteBuffer.wrap(header).order(java.nio.ByteOrder.LITTLE_ENDIAN);
            if (h.getInt(0) != 0x31304250) throw new IOException("Invalid frame header");
            int kind = h.getShort(6) & 0xffff, size = h.getInt(32);
            if (size < 0 || size > 16*1024*1024) throw new IOException("Invalid frame size");
            byte[] payload = new byte[size]; readFully(in, payload);
            rxBytes.addAndGet(size + 36);
            DisplayReceiver current = display;
            if (kind == 0x2001 && current != null) current.feed(payload);
        }
    }
    private static void readFully(InputStream in, byte[] data) throws IOException {
        int pos = 0;
        while (pos < data.length) {
            int n = in.read(data, pos, data.length-pos);
            if (n < 0) throw new java.io.EOFException();
            pos += n;
        }
    }
    public void sendPCInput(String json) {
        inputExecutor.execute(() -> {
            OutputStream out = sensorOutput;
            try { if (out != null) send(out, 4, 0x2002, json); }
            catch (IOException e) { Log.w(TAG, "touch send", e); }
        });
    }

    private void dispatch(Proto.Frame f, OutputStream out) throws IOException, org.json.JSONException {
        long ts = SystemClock.elapsedRealtimeNanos();
        switch (f.type) {
            case 0xb0: {
                JSONObject request=new JSONObject(f.payloadJson());String page=request.optString("page");
                Class<?> target="panel".equals(page)?DashboardActivity.class:"display".equals(page)?DisplayActivity.class:"main".equals(page)?MainActivity.class:null;
                if(target==null){send(out,1,0xb1,"{\"ok\":false}");break;}
                Intent intent=new Intent(this,target).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
                intent.putExtra("touch",request.optBoolean("touch"));
                new android.os.Handler(getMainLooper()).post(() -> startActivity(intent));send(out,1,0xb1,"{\"ok\":true}");break;
            }
            case 0x00a0: {
                JSONObject req = new JSONObject(f.payloadJson());
                int w = req.optInt("width", 1280), h = req.optInt("height", 720);
                if (w < 160 || h < 96 || w > 4096 || h > 4096) {
                    send(out, 1, 0x00a1, "{\"ok\":false,\"error\":\"INVALID_DISPLAY_SIZE\"}"); break;
                }
                if (display != null) display.stop();
                display = new DisplayReceiver(w, h);
                send(out, 1, 0x00a1, "{\"ok\":true}"); break;
            }
            case 0x00a2:
                if (display != null) display.stop();
                display = null;
                send(out, 1, 0x00a1, "{\"ok\":true}"); break;
            case Proto.T_PING:
                send(out, 1, Proto.T_PONG, "{\"ok\":true}");
                break;
            case Proto.T_GET_CAPABILITIES: {
                scanner = new CapabilityScanner();
                JSONObject caps = CapabilityScanner.scan(this);
                send(out, 1, Proto.T_CAPABILITIES, caps.toString());
                break;
            }
            case Proto.T_GET_STATUS: {
                JSONObject s = statusJson();
                send(out, 1, Proto.T_STATUS, s.toString());
                break;
            }
            case Proto.T_CAMERA_LIST: {
                JSONArray arr = CapabilityScanner.scan(this).optJSONArray("camera");
                JSONObject o = new JSONObject();
                o.put("cameras", arr != null ? arr : new JSONArray());
                send(out, 1, Proto.T_CAMERA_LIST_RESULT, o.toString());
                break;
            }
            case Proto.T_CAMERA_OPEN: {
                JSONObject o = new JSONObject();
                try {
                    JSONObject req = new JSONObject(f.payloadJson());
                    if (camera == null) {
                        o.put("ok", false); o.put("error", "VIDEO_CHANNEL_NOT_CONNECTED");
                    } else {
                        camera.start(req.optString("cameraId", "0"),
                                req.optInt("width", 1280), req.optInt("height", 720),
                                req.optInt("fps", 30), req.optInt("bitrateKbps", 6000));
                        o.put("ok", true);
                    }
                } catch (Throwable t) { o.put("ok", false); o.put("error", String.valueOf(t.getMessage())); }
                send(out, 1, Proto.T_CAMERA_OPEN_RESULT, o.toString());
                break;
            }
            case Proto.T_CAMERA_CLOSE:
                if (camera != null) camera.close();
                send(out, 1, Proto.T_CAMERA_OPEN_RESULT, "{\"ok\":true}");
                break;
            case Proto.T_CAMERA_SWITCH: {
                JSONObject o = new JSONObject();
                try {
                    JSONObject req = new JSONObject(f.payloadJson());
                    if (camera == null) { o.put("ok", false); o.put("error", "VIDEO_CHANNEL_NOT_CONNECTED"); }
                    else { camera.switchCamera(req.optString("cameraId", "0")); o.put("ok", true); }
                } catch (Throwable t) { o.put("ok", false); o.put("error", String.valueOf(t.getMessage())); }
                send(out, 1, Proto.T_CAMERA_SWITCH_RESULT, o.toString());
                break;
            }
            case Proto.T_MIC_START: {
                JSONObject o = new JSONObject();
                try {
                    JSONObject req = new JSONObject(f.payloadJson());
                    if (audio == null) { o.put("ok", false); o.put("error", "AUDIO_CHANNEL_NOT_CONNECTED"); }
                    else {
                        audio.start(req.optInt("sampleRate", 48000), req.optInt("channels", 1));
                        o.put("ok", true);
                    }
                } catch (Throwable t) { o.put("ok", false); o.put("error", String.valueOf(t.getMessage())); }
                send(out, 1, Proto.T_MIC_START_RESULT, o.toString());
                break;
            }
            case Proto.T_MIC_STOP:
                if (audio != null) audio.stop();
                send(out, 1, Proto.T_MIC_START_RESULT, "{\"ok\":true}");
                break;
            case Proto.T_SENSOR_START: {
                JSONObject o = new JSONObject();
                try {
                    JSONObject req = new JSONObject(f.payloadJson());
                    if (sensors == null) { o.put("ok", false); o.put("error", "SENSOR_CHANNEL_NOT_CONNECTED"); }
                    else {
                        sensors.start(req.optInt("sensor", 4), req.optInt("rateHz", 100));
                        o.put("ok", true);
                    }
                } catch (Throwable t) { o.put("ok", false); o.put("error", String.valueOf(t.getMessage())); }
                send(out, 1, Proto.T_SENSOR_START_RESULT, o.toString());
                break;
            }
            case Proto.T_SENSOR_STOP: {
                try {
                    JSONObject req = new JSONObject(f.payloadJson());
                    if (sensors != null) sensors.stop(req.optInt("sensor", 4));
                } catch (Throwable t) { }
                send(out, 1, Proto.T_SENSOR_START_RESULT, "{\"ok\":true}");
                break;
            }
            case Proto.T_GPS_START:
                if (sensors != null) sensors.gpsStart();
                send(out, 1, Proto.T_SENSOR_START_RESULT, "{\"ok\":true}");
                break;
            case Proto.T_GPS_STOP:
                if (sensors != null) sensors.gpsStop();
                send(out, 1, Proto.T_SENSOR_START_RESULT, "{\"ok\":true}");
                break;
            case Proto.T_TORCH_ON:
            case Proto.T_TORCH_OFF: {
                final boolean on = f.type == Proto.T_TORCH_ON;
                if (on && camera != null && camera.isRunning()) {
                    send(out, 1, Proto.T_SENSOR_START_RESULT, "{\"ok\":false,\"error\":\"RESOURCE_BUSY: CAMERA\"}");
                    break;
                }
                // setTorchMode 在 MTK 上会阻塞, 必须在独立线程执行
                new Thread(() -> {
                    JSONObject o = actuators.torch(on);
                    synchronized (out) { try { send(out, 1, Proto.T_SENSOR_START_RESULT, o.toString()); } catch (Throwable t) { } }
                }, "pb-torch-cmd").start();
                break;
            }
            case Proto.T_VIBRATE: {
                JSONObject o = new JSONObject();
                try {
                    JSONObject req = new JSONObject(f.payloadJson());
                    o = actuators.vibrate(req.optLong("duration_ms", 200));
                } catch (Throwable t) { }
                send(out, 1, Proto.T_SENSOR_START_RESULT, o.toString());
                break;
            }
            case Proto.T_IR_SEND: {
                JSONObject o = new JSONObject();
                try {
                    JSONObject req = new JSONObject(f.payloadJson());
                    JSONArray pat = req.optJSONArray("pattern_us");
                    int[] p = new int[pat != null ? pat.length() : 0];
                    if (pat != null) for (int i = 0; i < p.length; i++) p[i] = pat.optInt(i);
                    o = actuators.irSend(req.optInt("carrier_hz", 38000), p);
                } catch (Throwable t) { try { o.put("ok", false); o.put("error", "BAD_REQUEST"); } catch (Throwable ig) { } }
                send(out, 1, Proto.T_IR_SEND_RESULT, o.toString());
                break;
            }
            case Proto.T_BLE_SCAN: {
                // BLE 扫描含 Thread.sleep, 异步执行避免阻塞控制通道
                final JSONObject req;
                try { req = new JSONObject(f.payloadJson()); }
                catch (Throwable t) { send(out, 1, Proto.T_BLE_SCAN_RESULT, "{\"ok\":false,\"error\":\"BAD_REQUEST\"}"); break; }
                new Thread(() -> {
                    JSONObject o = actuators.bleScan(req.optLong("duration_ms", 5000));
                    synchronized (out) { try { send(out, 1, Proto.T_BLE_SCAN_RESULT, o.toString()); } catch (Throwable t) { } }
                }, "pb-ble-cmd").start();
                break;
            }
            default:
                send(out, 1, Proto.T_ERROR, "{\"code\":\"NOT_SUPPORTED\",\"message\":\"type " + f.type + "\"}");
        }
    }

    private void send(OutputStream out, int streamId, int type, String json) throws IOException {
        byte[] frame = Proto.frame(type, streamId, seq.incrementAndGet(), SystemClock.elapsedRealtimeNanos(), 0,
                Proto.jsonBytes(json));
        synchronized (out) {
            out.write(frame);
            out.flush();
        }
        txBytes.addAndGet(frame.length);
    }

    public JSONObject statusJson() {
        JSONObject o = new JSONObject();
        try {
            o.put("service_running", running.get());
            o.put("clients", clientCount.get());
            o.put("tx_bytes", txBytes.get());
            o.put("rx_bytes", rxBytes.get());
            o.put("uptime_ms", SystemClock.elapsedRealtime() - startTime);
            if (display != null) o.put("display", display.status());
            if (camera != null) {
                o.put("camera", new JSONObject()
                        .put("running", camera.isRunning())
                        .put("camera_id", camera.currentCameraId)
                        .put("fps", camera.fps())
                        .put("frames", camera.frames()));
            }
            if (audio != null) {
                o.put("microphone", new JSONObject()
                        .put("running", audio.isRunning())
                        .put("packets", audio.packetsCount())
                        .put("rate", audio.rate));
            }
            if (sensors != null) {
                JSONObject sr = new JSONObject();
                for (String k : sensors.rates().keySet()) sr.put(k, sensors.rates().get(k));
                o.put("sensor_rates", sr);
            }
        } catch (Throwable t) { }
        return o;
    }

    private long startTime = SystemClock.elapsedRealtime();

    public void stopBridge() {
        running.set(false);
        WirelessLink.close();
        AccessoryLink.close();
        synchronized (listeners) {
            for (ServerSocket s : listeners) { try { if (s != null) s.close(); } catch (IOException e) { } }
        }
        synchronized (clients) {
            for (Socket s : clients) { try { if (s != null) s.close(); } catch (IOException e) { } }
        }
        try { if (camera != null) camera.close(); } catch (Throwable t) { }
        try { if (audio != null) audio.stop(); } catch (Throwable t) { }
        try { if (sensors != null) sensors.close(); } catch (Throwable t) { }
        try { if (actuators != null) actuators.close(); } catch (Throwable t) { }
        try { if (display != null) display.stop(); } catch (Throwable t) { }
        inputExecutor.shutdownNow();
        for (Thread t : acceptThreads) { if (t != null) t.interrupt(); }
    }

    @Override
    public void onDestroy() {
        stopBridge();
        instance = null;
        super.onDestroy();
    }
}
