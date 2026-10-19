package com.phonebridge.app;

import android.content.Context;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.SystemClock;
import java.io.OutputStream;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/** PCM16, 48 kHz mono, 10 ms packets. Initialization errors are synchronous. */
public final class AudioStreamer {
    private final Context ctx;
    private final OutputStream out;
    private final AtomicLong sequence = new AtomicLong();
    private final AtomicLong packets = new AtomicLong();
    private final AtomicBoolean running = new AtomicBoolean();
    private Thread thread;
    private volatile AudioRecord record;
    public volatile int sampleRate = 48000, channels = 1;
    public volatile float rate;

    public AudioStreamer(Context ctx, OutputStream out) { this.ctx = ctx; this.out = out; }
    public long packetsCount() { return packets.get(); }
    public boolean isRunning() { return running.get(); }

    public void start(int sr, int ch) {
        stop();
        if (sr != 48000 || ch != 1) throw new IllegalArgumentException("Supported: 48000 Hz mono PCM16");
        if (ctx.checkSelfPermission("android.permission.RECORD_AUDIO") != android.content.pm.PackageManager.PERMISSION_GRANTED)
            throw new SecurityException("PERMISSION_DENIED: RECORD_AUDIO");
        int min = AudioRecord.getMinBufferSize(sr, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        if (min <= 0) throw new IllegalStateException("AUDIO_FORMAT_UNSUPPORTED");
        record = new AudioRecord(MediaRecorder.AudioSource.MIC, sr, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, Math.max(min * 2, 8192));
        if (record.getState() != AudioRecord.STATE_INITIALIZED) {
            record.release(); record = null;
            throw new IllegalStateException("AUDIO_INITIALIZATION_FAILED");
        }
        record.startRecording();
        if (record.getRecordingState() != AudioRecord.RECORDSTATE_RECORDING) {
            record.release(); record = null;
            throw new IllegalStateException("AUDIO_RECORDING_FAILED");
        }
        packets.set(0); rate = 0; running.set(true);
        final AudioRecord mine = record;
        thread = new Thread(() -> runLoop(mine), "pb-audio");
        thread.start();
    }

    private void runLoop(AudioRecord mine) {
        byte[] buffer = new byte[4800];
        int pending = 0;
        long lastCount = 0, lastTime = SystemClock.elapsedRealtime();
        try {
            while (running.get() && record == mine) {
                int n = mine.read(buffer, pending, 3840);
                if (n < 0) throw new IllegalStateException("AudioRecord.read: " + n);
                if (n == 0) continue;
                int total = pending + n;
                int off = 0;
                long firstTs = SystemClock.elapsedRealtimeNanos() - total / 2L * 1000000000L / 48000;
                while (off + 960 <= total) {
                    byte[] frame = Proto.frame(Proto.T_AUDIO_PACKET, 3, sequence.incrementAndGet(),
                            firstTs + off / 2L * 1000000000L / 48000, Proto.F_TIMESTAMP_VALID,
                            Arrays.copyOfRange(buffer, off, off + 960));
                    synchronized (out) { out.write(frame); out.flush(); }
                    packets.incrementAndGet(); off += 960;
                }
                pending = total - off;
                System.arraycopy(buffer, off, buffer, 0, pending);
                long now = SystemClock.elapsedRealtime();
                if (now - lastTime >= 1000) {
                    rate = (packets.get() - lastCount) * 1000f / Math.max(1, now - lastTime);
                    lastTime = now; lastCount = packets.get();
                }
            }
        } catch (Throwable t) {
            if (running.get()) {
                try {
                    org.json.JSONObject error = new org.json.JSONObject().put("code", "AUDIO_ERROR").put("message", t.toString());
                    synchronized (out) { out.write(Proto.frame(Proto.T_ERROR, 3, sequence.incrementAndGet(),
                            SystemClock.elapsedRealtimeNanos(), 0, Proto.jsonBytes(error.toString()))); out.flush(); }
                } catch (Throwable ignored) { }
            }
        } finally {
            running.set(false);
            mine.release();
            if (record == mine) record = null;
        }
    }

    public void stop() {
        running.set(false);
        AudioRecord current = record;
        try { if (current != null) current.stop(); } catch (Throwable ignored) { }
        try { if (thread != null && thread != Thread.currentThread()) thread.join(2000); } catch (InterruptedException ignored) { }
        thread = null;
    }
}
