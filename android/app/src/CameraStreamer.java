package com.phonebridge.app;

import android.content.Context;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.Log;
import android.view.Surface;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Camera2 -> MediaCodec(硬件 H.264, Surface 输入) -> VIDEO_FRAME 帧流
 * 默认 1280x720@30, 6 Mbps CBR, I 帧间隔 1s, 无 B 帧
 */
public final class CameraStreamer {
    private static final String TAG = "PB.Camera";

    private final Context ctx;
    private final OutputStream out;
    private final AtomicLong sequence = new AtomicLong(0);
    private final AtomicLong frameCount = new AtomicLong(0);
    private final AtomicBoolean running = new AtomicBoolean(false);

    private CameraDevice camera;
    private CameraCaptureSession session;
    private MediaCodec encoder;
    private Surface inputSurface;
    private HandlerThread thread;
    private Handler handler;
    private byte[] csd; // SPS+PPS
    private volatile float fps = 0;
    private long lastFpsTime = 0, lastFpsCount = 0;

    public volatile String currentCameraId = "0";
    public volatile int width = 1280, height = 720, fpsTarget = 30, bitrate = 6000000;

    public CameraStreamer(Context ctx, OutputStream out) {
        this.ctx = ctx;
        this.out = out;
    }

    public float fps() { return fps; }
    public long frames() { return frameCount.get(); }
    public boolean isRunning() { return running.get(); }

    public void start(final String cameraId, int w, int h, int fpsT, int bitrateKbps) {
        close();
        if (!checkSelfPermission()) throw new SecurityException("PERMISSION_DENIED: CAMERA");
        if (w < 160 || h < 96 || w > 7680 || h > 7680 || fpsT < 1 || fpsT > 240 || bitrateKbps < 128 || bitrateKbps > 100000)
            throw new IllegalArgumentException("INVALID_CAMERA_CONFIGURATION");
        frameCount.set(0); lastFpsCount = 0; lastFpsTime = SystemClock.elapsedRealtime();
        width = w; height = h; fpsTarget = fpsT; bitrate = bitrateKbps * 1000;
        currentCameraId = cameraId;
        thread = new HandlerThread("pb-camera");
        thread.start();
        handler = new Handler(thread.getLooper());
        running.set(true);
        handler.post(() -> {
            try { openCameraAndStart(); }
            catch (Throwable t) {
                Log.e(TAG, "start failed", t);
                sendError("CAMERA_OPEN_FAILED: " + t.getMessage());
                close();
            }
        });
    }

    public void switchCamera(String cameraId) {
        start(cameraId, width, height, fpsTarget, bitrate / 1000);
    }

    private void openCameraAndStart() throws Exception {
        CameraManager cm = (CameraManager) ctx.getSystemService(Context.CAMERA_SERVICE);
        if (checkSelfPermission()) {
            cm.openCamera(currentCameraId, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice c) {
                    if (!running.get()) { c.close(); return; }
                    camera = c;
                    try { setupEncoderAndSession(); } catch (Throwable t) { Log.e(TAG, "session", t); sendError(String.valueOf(t)); }
                }
                @Override public void onDisconnected(CameraDevice c) { close(); }
                @Override public void onError(CameraDevice c, int e) { close(); }
            }, handler);
        } else {
            sendError("PERMISSION_DENIED: CAMERA");
        }
    }

    private boolean checkSelfPermission() {
        return ctx.checkSelfPermission("android.permission.CAMERA") == android.content.pm.PackageManager.PERMISSION_GRANTED;
    }

    private void setupEncoderAndSession() throws Exception {
        MediaFormat fmt = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, width, height);
        fmt.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        fmt.setInteger(MediaFormat.KEY_BIT_RATE, bitrate);
        fmt.setInteger(MediaFormat.KEY_FRAME_RATE, fpsTarget);
        fmt.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
        fmt.setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR);
        try { fmt.setInteger(MediaFormat.KEY_MAX_B_FRAMES, 0); } catch (Throwable t) { Log.w(TAG, "KEY_MAX_B_FRAMES unsupported"); }
        try { fmt.setInteger(MediaFormat.KEY_LATENCY, 1); } catch (Throwable t) { Log.w(TAG, "KEY_LATENCY unsupported (记录, 非失败)"); }

        encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
        encoder.setCallback(new MediaCodec.Callback() {
            @Override public void onInputBufferAvailable(MediaCodec mc, int index) { }
            @Override public void onOutputBufferAvailable(MediaCodec mc, int index, MediaCodec.BufferInfo info) {
                drainOutput(index, info);
            }
            @Override public void onError(MediaCodec mc, MediaCodec.CodecException e) {
                Log.e(TAG, "codec error", e); sendError("CODEC_ERROR: " + e.getMessage());
            }
            @Override public void onOutputFormatChanged(MediaCodec mc, MediaFormat f) {
                ByteBuffer sps = f.getByteBuffer("csd-0");
                ByteBuffer pps = f.getByteBuffer("csd-1");
                if (sps != null) {
                    int spsLen = sps.remaining(), ppsLen = pps != null ? pps.remaining() : 0;
                    csd = new byte[spsLen + ppsLen];
                    sps.get(csd, 0, spsLen);
                    if (pps != null) pps.get(csd, spsLen, ppsLen);
                }
            }
        }, handler);
        encoder.configure(fmt, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        inputSurface = encoder.createInputSurface();
        encoder.start();

        // camera 已由 openCameraAndStart 的 onOpened 打开
        camera.createCaptureSession(Arrays.asList(inputSurface), new CameraCaptureSession.StateCallback() {
            @Override public void onConfigured(CameraCaptureSession s) {
                if (!running.get() || camera == null) { s.close(); return; }
                session = s;
                try {
                    CaptureRequest.Builder b = camera.createCaptureRequest(CameraDevice.TEMPLATE_RECORD);
                    b.addTarget(inputSurface);
                    b.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO);
                    b.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, new android.util.Range<>(fpsTarget, fpsTarget));
                    session.setRepeatingRequest(b.build(), null, handler);
                } catch (Throwable t) {
                    sendError(String.valueOf(t));
                }
            }
            @Override public void onConfigureFailed(CameraCaptureSession s) { sendError("SESSION_CONFIGURE_FAILED"); }
        }, handler);
    }

    private void drainOutput(int index, MediaCodec.BufferInfo info) {
        if (index < 0 || encoder == null) return;
        if (info.size <= 0) { encoder.releaseOutputBuffer(index, false); return; }
        ByteBuffer buf = encoder.getOutputBuffer(index);
        if (buf == null) return;
        byte[] nal = new byte[info.size];
        buf.position(info.offset);
        buf.limit(info.offset + info.size);
        buf.get(nal);
        encoder.releaseOutputBuffer(index, false);

        boolean key = (info.flags & MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0;
        int flags = key ? Proto.F_KEY_FRAME : 0;
        long seq = sequence.incrementAndGet();
        long ts = SystemClock.elapsedRealtimeNanos();
        byte[] payload;
        if (key && csd != null) {
            payload = new byte[csd.length + nal.length];
            System.arraycopy(csd, 0, payload, 0, csd.length);
            System.arraycopy(nal, 0, payload, csd.length, nal.length);
        } else {
            payload = nal;
        }
        byte[] frame = Proto.frame(Proto.T_VIDEO_FRAME, 2, seq, ts, flags | Proto.F_TIMESTAMP_VALID, payload);
        synchronized (out) {
            try { out.write(frame); out.flush(); } catch (IOException e) { Log.e(TAG, "write", e); close(); }
        }
        frameCount.incrementAndGet();
        long now = SystemClock.elapsedRealtime();
        if (now - lastFpsTime >= 1000) {
            fps = (frameCount.get() - lastFpsCount) * 1000f / (float) Math.max(1L, now - lastFpsTime);
            lastFpsTime = now; lastFpsCount = frameCount.get();
        }
    }

    private void reconfigure() {
        close();
        try { openCameraAndStart(); } catch (Throwable t) { sendError(String.valueOf(t)); }
    }

    private void sendError(String msg) {
        try {
            org.json.JSONObject o = new org.json.JSONObject();
            o.put("code", "CODEC_ERROR"); o.put("message", msg);
            byte[] frame = Proto.frame(Proto.T_ERROR, 2, sequence.incrementAndGet(),
                    SystemClock.elapsedRealtimeNanos(), 0, Proto.jsonBytes(o.toString()));
            synchronized (out) { out.write(frame); out.flush(); }
        } catch (Throwable t) { }
    }

    public void close() {
        running.set(false);
        try { if (session != null) session.close(); } catch (Throwable t) { }
        try { if (camera != null) camera.close(); } catch (Throwable t) { }
        try { if (encoder != null) { encoder.stop(); encoder.release(); } } catch (Throwable t) { }
        session = null; camera = null; encoder = null; csd = null;
        try { if (inputSurface != null) inputSurface.release(); } catch (Throwable t) { }
        inputSurface = null;
        try { if (thread != null) thread.quitSafely(); } catch (Throwable t) { }
        thread = null; handler = null;
    }
}
