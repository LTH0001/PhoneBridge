package com.phonebridge.app;

import android.content.Context;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 传感器流 + GPS. SENSOR_EVENT payload: s32 type, f32 x, f32 y, f32 z (LE)
 */
public final class SensorStreamer {
    private static final String TAG = "PB.Sensor";

    private final Context ctx;
    private final OutputStream out;
    private final AtomicLong sequence = new AtomicLong(0);
    private final SensorManager sm;
    private final LocationManager lm;
    private final android.os.HandlerThread sensorThread = new android.os.HandlerThread("pb-sensors");
    private final android.os.Handler sensorHandler;
    private final Map<String, Reg> regs = new ConcurrentHashMap<>();

    private static class Reg {
        final int type; final AtomicBoolean active = new AtomicBoolean(false);
        final AtomicLong events = new AtomicLong(0); volatile long lastCount = 0, lastTime = 0; volatile float rate;
        Reg(int t) { type = t; }
    }

    private final SensorEventListener listener = new SensorEventListener() {
        @Override public void onSensorChanged(SensorEvent e) {
            Reg r = regs.get(String.valueOf(e.sensor.getType()));
            if (r == null || !r.active.get()) return;
            sendSensorEvent(e.sensor.getType(), e.values, e.timestamp, e.accuracy);
            r.events.incrementAndGet();
            long now = SystemClock.elapsedRealtime();
            if (now - r.lastTime >= 1000) {
                r.rate = (r.events.get() - r.lastCount) * 1000f / Math.max(1, now - r.lastTime);
                r.lastTime = now; r.lastCount = r.events.get();
            }
        }
        @Override public void onAccuracyChanged(Sensor s, int a) { }
    };

    public SensorStreamer(Context ctx, OutputStream out) {
        this.ctx = ctx;
        this.out = out;
        this.sm = (SensorManager) ctx.getSystemService(Context.SENSOR_SERVICE);
        this.lm = (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
        sensorThread.start();
        sensorHandler = new android.os.Handler(sensorThread.getLooper());
    }

    public Map<String, Float> rates() {
        Map<String, Float> m = new ConcurrentHashMap<>();
        for (Map.Entry<String, Reg> e : regs.entrySet()) if (e.getValue().active.get()) m.put(e.getKey(), e.getValue().rate);
        return m;
    }
    public Map<String, Long> counts() {
        Map<String, Long> m = new ConcurrentHashMap<>();
        for (Map.Entry<String, Reg> e : regs.entrySet()) m.put(e.getKey(), e.getValue().events.get());
        return m;
    }

    public void start(int sensorType, int rateHz) {
        Sensor s = sm.getDefaultSensor(sensorType);
        if (s == null) {
            throw new IllegalArgumentException("SENSOR_NOT_FOUND: type " + sensorType);
        }
        if (rateHz < 1 || rateHz > 1000) throw new IllegalArgumentException("rateHz must be 1..1000");
        stop(sensorType);
        Reg r = regs.computeIfAbsent(String.valueOf(sensorType), k -> new Reg(sensorType));
        if (r.active.compareAndSet(false, true)) {
            int us = rateHz > 0 ? Math.max(1000000 / rateHz, s.getMinDelay()) : SensorManager.SENSOR_DELAY_FASTEST;
            r.lastTime = SystemClock.elapsedRealtime(); r.lastCount = r.events.get();
            if (!sm.registerListener(listener, s, us, sensorHandler)) {
                r.active.set(false);
                throw new IllegalStateException("SENSOR_REGISTER_FAILED");
            }
        }
    }

    public void stop(int sensorType) {
        Reg r = regs.get(String.valueOf(sensorType));
        if (r != null && r.active.compareAndSet(true, false)) {
            Sensor s = sm.getDefaultSensor(sensorType);
            if (s != null) sm.unregisterListener(listener, s);
        }
    }

    private void sendSensorEvent(int type, float[] v, long timestampNs, int accuracy) {
        try {
            org.json.JSONObject event = new org.json.JSONObject();
            org.json.JSONArray values = new org.json.JSONArray();
            for (float x : v) values.put(Float.isFinite(x) ? x : 0f);
            event.put("type", type).put("accuracy", accuracy).put("values", values)
                    .put("timestamp_ns", timestampNs);
            byte[] frame = Proto.frame(Proto.T_SENSOR_EVENT, 4, sequence.incrementAndGet(),
                    timestampNs, Proto.F_TIMESTAMP_VALID, Proto.jsonBytes(event.toString()));
            synchronized (out) { out.write(frame); out.flush(); }
        } catch (Exception e) { Log.e(TAG, "write", e); close(); }
    }

    // ---- GPS ----
    private final AtomicBoolean gpsActive = new AtomicBoolean(false);
    private final LocationListener locListener = new LocationListener() {
        @Override public void onLocationChanged(Location loc) {
            try {
                org.json.JSONObject o = new org.json.JSONObject();
                o.put("lat", loc.getLatitude());
                o.put("lon", loc.getLongitude());
                o.put("accuracy", loc.getAccuracy());
                o.put("altitude", loc.getAltitude());
                o.put("speed", loc.getSpeed());
                o.put("bearing", loc.getBearing());
                o.put("provider", loc.getProvider());
                byte[] frame = Proto.frame(Proto.T_GPS_EVENT, 4, sequence.incrementAndGet(),
                        SystemClock.elapsedRealtimeNanos(), Proto.F_TIMESTAMP_VALID, Proto.jsonBytes(o.toString()));
                synchronized (out) { out.write(frame); out.flush(); }
            } catch (Throwable t) { }
        }
        @Override public void onStatusChanged(String provider, int status, Bundle extras) { }
        @Override public void onProviderEnabled(String provider) { }
        @Override public void onProviderDisabled(String provider) { }
    };

    public void gpsStart() {
        if (gpsActive.compareAndSet(false, true)) {
            try {
                if (ctx.checkSelfPermission("android.permission.ACCESS_FINE_LOCATION")
                        == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                    lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0f, locListener, sensorThread.getLooper());
                } else {
                    sendError("PERMISSION_DENIED: LOCATION");
                }
            } catch (Throwable t) { sendError("GPS_ERROR: " + t.getMessage()); }
        }
    }

    public void gpsStop() {
        if (gpsActive.compareAndSet(true, false)) {
            try { lm.removeUpdates(locListener); } catch (Throwable t) { }
        }
    }

    private void sendError(String msg) {
        try {
            org.json.JSONObject o = new org.json.JSONObject();
            o.put("code", "SENSOR_ERROR"); o.put("message", msg);
            byte[] frame = Proto.frame(Proto.T_ERROR, 4, sequence.incrementAndGet(),
                    SystemClock.elapsedRealtimeNanos(), 0, Proto.jsonBytes(o.toString()));
            synchronized (out) { out.write(frame); out.flush(); }
        } catch (Throwable t) { }
    }

    public void close() {
        for (Map.Entry<String, Reg> e : regs.entrySet()) stop(e.getValue().type);
        gpsStop();
        sensorThread.quitSafely();
    }
}
