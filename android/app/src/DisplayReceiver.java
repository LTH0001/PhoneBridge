package com.phonebridge.app;

import android.media.MediaCodec;
import android.media.MediaFormat;
import android.view.Surface;
import java.nio.ByteBuffer;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/** Windows H.264 -> Android MediaCodec -> Surface, no browser or external app. */
public final class DisplayReceiver {
    public final int width, height;
    private final ArrayBlockingQueue<byte[]> packets = new ArrayBlockingQueue<>(90);
    private final AtomicBoolean running = new AtomicBoolean();
    private final AtomicLong received = new AtomicLong(), rendered = new AtomicLong();
    private Thread thread;
    public volatile String error = "";
    public volatile int viewWidth,viewHeight,surfaceWidth,surfaceHeight;
    public DisplayReceiver(int w, int h) { width = w; height = h; }
    public void feed(byte[] data) {
        received.incrementAndGet();
        if (!packets.offer(data)) { packets.clear(); packets.offer(data); }
    }
    public synchronized void attach(Surface surface) {
        stop();
        running.set(true);
        thread = new Thread(() -> decode(surface), "pb-display-decoder");
        thread.start();
    }
    private void decode(Surface surface) {
        MediaCodec decoder = null;
        try {
            decoder = MediaCodec.createDecoderByType("video/avc");
            MediaFormat format = MediaFormat.createVideoFormat("video/avc", width, height);
            format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 4 * 1024 * 1024);
            decoder.configure(format, surface, null, 0);
            decoder.start();
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            long pts = 0;
            byte[] pending = null;
            while (running.get() && surface.isValid()) {
                if (pending == null) pending = packets.poll(5, TimeUnit.MILLISECONDS);
                if (pending != null) {
                    int index = decoder.dequeueInputBuffer(1000);
                    if (index >= 0) {
                        ByteBuffer input = decoder.getInputBuffer(index);
                        input.clear();
                        if (input.remaining() < pending.length) throw new IllegalStateException("DISPLAY_PACKET_TOO_LARGE");
                        input.put(pending);
                        decoder.queueInputBuffer(index, 0, pending.length, pts, 0);
                        pts += 33333;
                        pending = null;
                    }
                }
                for (;;) {
                    int index = decoder.dequeueOutputBuffer(info, 0);
                    if (index < 0) break;
                    decoder.releaseOutputBuffer(index, true);
                    rendered.incrementAndGet();
                }
            }
        } catch (Throwable t) { error = t.toString(); }
        finally {
            if (decoder != null) { try { decoder.stop(); decoder.release(); } catch (Throwable ignored) { } }
            running.set(false);
        }
    }
    public synchronized void stop() {
        running.set(false);
        try { if (thread != null && thread != Thread.currentThread()) thread.join(2000); } catch (InterruptedException ignored) { }
        thread = null;
    }
    public org.json.JSONObject status() {
        org.json.JSONObject s = new org.json.JSONObject();
        try { s.put("running", running.get()).put("received", received.get()).put("rendered", rendered.get()).put("error", error)
            .put("view_width",viewWidth).put("view_height",viewHeight).put("surface_width",surfaceWidth).put("surface_height",surfaceHeight); }
        catch (org.json.JSONException ignored) { }
        return s;
    }
}
