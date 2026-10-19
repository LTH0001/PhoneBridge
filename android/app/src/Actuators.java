package com.phonebridge.app;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.Context;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.ConsumerIrManager;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.Surface;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;
import java.util.concurrent.CountDownLatch;

/**
 * 执行器: Torch / Vibrator / IR / BLE Scan
 */
public final class Actuators {
    private final Context ctx;
    private final CameraManager cm;

    public Actuators(Context ctx) {
        this.ctx = ctx;
        this.cm = (CameraManager) ctx.getSystemService(Context.CAMERA_SERVICE);
    }

    private String flashCameraId() {
        try {
            for (String id : cm.getCameraIdList()) {
                CameraCharacteristics ch = cm.getCameraCharacteristics(id);
                Boolean flash = ch.get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
                Integer facing = ch.get(CameraCharacteristics.LENS_FACING);
                if (flash != null && flash && facing != null
                        && facing == CameraCharacteristics.LENS_FACING_BACK) return id;
            }
        } catch (Throwable t) { }
        return null;
    }

    /** Torch: 不用 setTorchMode (MTK 上会无限阻塞), 自开会话用 FLASH_MODE_TORCH */
    private CameraDevice torchCam;
    private CameraCaptureSession torchSession;
    private HandlerThread torchThread;
    private Handler torchHandler;
    private Surface torchSurface;
    private SurfaceTexture torchTexture;

    public synchronized JSONObject torch(boolean on) {
        JSONObject o = new JSONObject();
        try {
            String id = flashCameraId();
            if (id == null) { o.put("ok", false); o.put("error", "NO_FLASH"); return o; }
            if (on) {
                startTorchSession(id);
            } else {
                stopTorchSession();
            }
            o.put("ok", true); o.put("cameraId", id); o.put("on", on);
        } catch (Throwable t) {
            stopTorchSession();
            try { o.put("ok", false); o.put("error", String.valueOf(t.getMessage())); } catch (Throwable ig) { }
        }
        return o;
    }

    private void startTorchSession(final String id) throws Exception {
        stopTorchSession();
        final CountDownLatch opened = new CountDownLatch(1);
        torchThread = new HandlerThread("pb-torch");
        torchThread.start();
        torchHandler = new Handler(torchThread.getLooper());
        SurfaceTexture st = new SurfaceTexture(0);
        torchTexture = st;
        st.setDefaultBufferSize(320, 240);
        torchSurface = new Surface(st);
        cm.openCamera(id, new CameraDevice.StateCallback() {
            @Override public void onOpened(CameraDevice c) {
                torchCam = c;
                opened.countDown();
            }
            @Override public void onDisconnected(CameraDevice c) { c.close(); torchCam = null; opened.countDown(); }
            @Override public void onError(CameraDevice c, int e) { c.close(); torchCam = null; opened.countDown(); }
        }, torchHandler);
        if (!opened.await(8, java.util.concurrent.TimeUnit.SECONDS) || torchCam == null) {
            throw new IllegalStateException("camera open timeout");
        }
        final CountDownLatch configured = new CountDownLatch(1);
        torchCam.createCaptureSession(java.util.Arrays.asList(torchSurface),
                new CameraCaptureSession.StateCallback() {
                    @Override public void onConfigured(CameraCaptureSession s) {
                        torchSession = s;
                        try {
                            CaptureRequest.Builder b = torchCam.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
                            b.addTarget(torchSurface);
                            b.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO);
                            b.set(CaptureRequest.FLASH_MODE, CaptureRequest.FLASH_MODE_TORCH);
                            s.setRepeatingRequest(b.build(), null, torchHandler);
                        } catch (Throwable t) { }
                        configured.countDown();
                    }
                    @Override public void onConfigureFailed(CameraCaptureSession s) { configured.countDown(); }
                }, torchHandler);
        if (!configured.await(8, java.util.concurrent.TimeUnit.SECONDS) || torchSession == null) {
            throw new IllegalStateException("session configure timeout");
        }
    }

    private void stopTorchSession() {
        try { if (torchSession != null) torchSession.close(); } catch (Throwable t) { }
        try { if (torchCam != null) torchCam.close(); } catch (Throwable t) { }
        try { if (torchSurface != null) torchSurface.release(); } catch (Throwable t) { }
        try { if (torchTexture != null) torchTexture.release(); } catch (Throwable t) { }
        try { if (torchThread != null) torchThread.quitSafely(); } catch (Throwable t) { }
        torchSession = null; torchCam = null; torchSurface = null; torchTexture = null; torchThread = null; torchHandler = null;
    }

    public synchronized void close() { stopTorchSession(); }

    public JSONObject vibrate(long ms) {
        JSONObject o = new JSONObject();
        try {
            Vibrator v = (Vibrator) ctx.getSystemService(Context.VIBRATOR_SERVICE);
            if (v == null || !v.hasVibrator()) { o.put("ok", false); o.put("error", "UNSUPPORTED_HARDWARE"); return o; }
            v.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE));
            o.put("ok", true); o.put("duration_ms", ms);
        } catch (Throwable t) {
            try { o.put("ok", false); o.put("error", String.valueOf(t.getMessage())); } catch (Throwable ig) { }
        }
        return o;
    }

    /** IR: 无硬件时返回 UNSUPPORTED_HARDWARE, 绝不伪造成功 */
    public JSONObject irSend(int carrierHz, int[] patternUs) {
        JSONObject o = new JSONObject();
        try {
            ConsumerIrManager ir = (ConsumerIrManager) ctx.getSystemService(Context.CONSUMER_IR_SERVICE);
            if (ir == null || !ir.hasIrEmitter()) {
                o.put("ok", false);
                o.put("error", "UNSUPPORTED_HARDWARE");
                return o;
            }
            ir.transmit(carrierHz, patternUs);
            o.put("ok", true);
        } catch (Throwable t) {
            try { o.put("ok", false); o.put("error", String.valueOf(t.getMessage())); } catch (Throwable ig) { }
        }
        return o;
    }

    /** BLE 扫描 durationMs 毫秒, 收集结果返回 */
    public JSONObject bleScan(long durationMs) {
        JSONObject o = new JSONObject();
        try {
            BluetoothManager bm = (BluetoothManager) ctx.getSystemService(Context.BLUETOOTH_SERVICE);
            BluetoothAdapter adapter = bm != null ? bm.getAdapter() : null;
            if (adapter == null || !adapter.isEnabled()) {
                o.put("ok", false); o.put("error", "BT_OFF_OR_UNAVAILABLE");
                return o;
            }
            BluetoothLeScanner scanner = adapter.getBluetoothLeScanner();
            if (scanner == null) { o.put("ok", false); o.put("error", "NO_LE_SCANNER"); return o; }
            if (ctx.checkSelfPermission("android.permission.BLUETOOTH_SCAN")
                    != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                o.put("ok", false); o.put("error", "PERMISSION_DENIED: BLUETOOTH_SCAN");
                return o;
            }
            JSONArray results = new JSONArray();
            final Object lock = new Object();
            ScanCallback cb = new ScanCallback() {
                @Override public void onScanResult(int callbackType, ScanResult result) {
                    try {
                        BluetoothDevice d = result.getDevice();
                        JSONObject r = new JSONObject();
                        r.put("name", d.getName());
                        r.put("address", d.getAddress());
                        r.put("rssi", result.getRssi());
                        synchronized (lock) { results.put(r); }
                    } catch (Throwable t) { }
                }
            };
            scanner.startScan(cb);
            try { Thread.sleep(Math.min(durationMs, 30000)); } catch (InterruptedException ig) { }
            scanner.stopScan(cb);
            o.put("ok", true);
            o.put("results", results);
        } catch (Throwable t) {
            try { o.put("ok", false); o.put("error", String.valueOf(t.getMessage())); } catch (Throwable ig) { }
        }
        return o;
    }
}
