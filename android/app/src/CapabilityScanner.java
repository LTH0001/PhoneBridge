package com.phonebridge.app;

import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.hardware.Sensor;
import android.hardware.SensorManager;
import android.hardware.camera2.CameraMetadata;
import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import android.os.Build;
import android.util.Range;
import android.util.Size;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

/**
 * CapabilityScanner - 生成 capabilities.json (protocol.md §7 / 任务书第八节)
 */
public final class CapabilityScanner {

    public static JSONObject scan(Context ctx) {
        JSONObject root = new JSONObject();
        try {
            root.put("android", androidInfo());
            android.view.WindowManager wm = (android.view.WindowManager)ctx.getSystemService(Context.WINDOW_SERVICE);
            android.util.DisplayMetrics dm = new android.util.DisplayMetrics();
            wm.getDefaultDisplay().getRealMetrics(dm);
            root.put("display", new JSONObject().put("width",dm.widthPixels).put("height",dm.heightPixels)
                .put("xdpi",dm.xdpi).put("ydpi",dm.ydpi).put("density_dpi",dm.densityDpi));
            root.put("usb", new JSONObject().put("note", "filled by host probe"));
            root.put("camera", cameraList(ctx));
            root.put("microphone", micInfo());
            root.put("video_encoders", encoders());
            root.put("audio_encoders", new JSONArray());
            root.put("sensors", sensorList(ctx));
            root.put("gps", feature(ctx, PackageManager.FEATURE_LOCATION_GPS));
            JSONObject bt = new JSONObject();
            bt.put("classic", feature(ctx, PackageManager.FEATURE_BLUETOOTH));
            bt.put("le", feature(ctx, PackageManager.FEATURE_BLUETOOTH_LE));
            root.put("bluetooth", bt);
            root.put("nfc", feature(ctx, PackageManager.FEATURE_NFC));
            JSONObject ir = new JSONObject();
            android.hardware.ConsumerIrManager irm = (android.hardware.ConsumerIrManager) ctx.getSystemService(Context.CONSUMER_IR_SERVICE);
            ir.put("hasIrEmitter", irm != null && irm.hasIrEmitter());
            root.put("infrared", ir);
            root.put("torch", feature(ctx, PackageManager.FEATURE_CAMERA_FLASH));
            JSONObject vib = new JSONObject();
            vib.put("supported", ctx.getSystemService(Context.VIBRATOR_SERVICE) != null);
            root.put("vibrator", vib);
            root.put("usb_accessory", feature(ctx, PackageManager.FEATURE_USB_ACCESSORY));
            root.put("usb_host", feature(ctx, PackageManager.FEATURE_USB_HOST));
        } catch (Throwable t) {
            // 任何单项失败不影响整体
        }
        return root;
    }

    private static JSONObject feature(Context ctx, String f) {
        JSONObject o = new JSONObject();
        try { o.put("supported", ctx.getPackageManager().hasSystemFeature(f)); } catch (Throwable t) { }
        return o;
    }

    private static JSONObject androidInfo() {
        JSONObject o = new JSONObject();
        try {
            o.put("release", Build.VERSION.RELEASE);
            o.put("sdk", Build.VERSION.SDK_INT);
            o.put("model", Build.MODEL);
            o.put("manufacturer", Build.MANUFACTURER);
            o.put("device", Build.DEVICE);
            o.put("board", Build.BOARD);
            o.put("hardware", Build.HARDWARE);
            o.put("abi", Build.SUPPORTED_ABIS[0]);
        } catch (Throwable t) { }
        return o;
    }

    private static JSONArray cameraList(Context ctx) {
        JSONArray arr = new JSONArray();
        try {
            CameraManager cm = (CameraManager) ctx.getSystemService(Context.CAMERA_SERVICE);
            for (String id : cm.getCameraIdList()) {
                try {
                    CameraCharacteristics ch = cm.getCameraCharacteristics(id);
                    JSONObject c = new JSONObject();
                    c.put("id", id);
                    Integer facing = ch.get(CameraCharacteristics.LENS_FACING);
                    c.put("facing", facing != null && facing == CameraCharacteristics.LENS_FACING_FRONT ? "FRONT" : "BACK");
                    Integer level = ch.get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL);
                    String levelName = "UNKNOWN";
                    if (level != null) {
                        switch (level) {
                            case CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LIMITED: levelName = "LIMITED"; break;
                            case CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_FULL: levelName = "FULL"; break;
                            case CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LEGACY: levelName = "LEGACY"; break;
                            case CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_3: levelName = "LEVEL_3"; break;
                            case CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_EXTERNAL: levelName = "EXTERNAL"; break;
                        }
                    }
                    c.put("level", levelName);
                    c.put("orientation", ch.get(CameraCharacteristics.SENSOR_ORIENTATION));
                    Boolean flash = ch.get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
                    c.put("flash", flash != null && flash);
                    int[] caps = ch.get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES);
                    JSONArray capNames = new JSONArray();
                    if (caps != null) {
                        for (int cap : caps) {
                            switch (cap) {
                                case CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_SENSOR: capNames.put("MANUAL_SENSOR"); break;
                                case CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_POST_PROCESSING: capNames.put("MANUAL_POST_PROCESSING"); break;
                                case CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_RAW: capNames.put("RAW"); break;
                                case CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_BURST_CAPTURE: capNames.put("BURST_CAPTURE"); break;
                                case CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_LOGICAL_MULTI_CAMERA: capNames.put("LOGICAL_MULTI_CAMERA"); break;
                                case CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_CONSTRAINED_HIGH_SPEED_VIDEO: capNames.put("CONSTRAINED_HIGH_SPEED_VIDEO"); break;
                                default: capNames.put("CAP_" + cap);
                            }
                        }
                    }
                    c.put("capabilities", capNames);
                    StreamConfigurationMap map = ch.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
                    JSONArray sizes = new JSONArray();
                    if (map != null) {
                        for (Size s : map.getOutputSizes(ImageFormat.JPEG)) {
                            JSONObject z = new JSONObject();
                            z.put("format", ImageFormat.JPEG); z.put("w", s.getWidth()); z.put("h", s.getHeight());
                            sizes.put(z);
                        }
                    }
                    c.put("outputSizes", sizes);
                    JSONArray fps = new JSONArray();
                    Range<Integer>[] ranges = ch.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES);
                    if (ranges != null) {
                        for (Range<Integer> r : ranges) {
                            JSONArray p = new JSONArray();
                            p.put(r.getLower()); p.put(r.getUpper());
                            fps.put(p);
                        }
                    }
                    c.put("fpsRanges", fps);
                    arr.put(c);
                } catch (Throwable t) { }
            }
        } catch (Throwable t) { }
        return arr;
    }

    private static JSONObject micInfo() {
        JSONObject o = new JSONObject();
        try {
            o.put("sampleRates", new JSONArray("[8000,16000,32000,44100,48000]"));
            o.put("formats", new JSONArray("[\"PCM_16\"]"));
            o.put("channels", new JSONArray("[\"MONO\",\"STEREO\"]"));
        } catch (Throwable t) { }
        return o;
    }

    private static JSONArray encoders() {
        JSONArray arr = new JSONArray();
        try {
            for (MediaCodecInfo info : new MediaCodecList(MediaCodecList.ALL_CODECS).getCodecInfos()) {
                if (!info.isEncoder()) continue;
                for (String type : info.getSupportedTypes()) {
                    if (!type.equals("video/avc") && !type.equals("video/hevc")) continue;
                    MediaCodecInfo.CodecCapabilities cap = info.getCapabilitiesForType(type);
                    MediaCodecInfo.VideoCapabilities vc = cap.getVideoCapabilities();
                    JSONObject o = new JSONObject();
                    o.put("name", info.getName());
                    o.put("mime", type);
                    o.put("hardware", !info.isSoftwareOnly());
                    o.put("maxW", vc.getSupportedWidths().getUpper());
                    o.put("maxH", vc.getSupportedHeights().getUpper());
                    o.put("maxFps", vc.getSupportedFrameRates().getUpper());
                    o.put("bitrateRange", new JSONArray("[" + vc.getBitrateRange().getLower() + "," + vc.getBitrateRange().getUpper() + "]"));
                    arr.put(o);
                }
            }
        } catch (Throwable t) { }
        return arr;
    }

    private static JSONArray sensorList(Context ctx) {
        JSONArray arr = new JSONArray();
        try {
            SensorManager sm = (SensorManager) ctx.getSystemService(Context.SENSOR_SERVICE);
            List<Sensor> list = sm.getSensorList(Sensor.TYPE_ALL);
            for (Sensor s : list) {
                JSONObject o = new JSONObject();
                o.put("type", s.getType());
                o.put("name", s.getName());
                o.put("vendor", s.getVendor());
                o.put("version", s.getVersion());
                o.put("maxRange", s.getMaximumRange());
                o.put("resolution", s.getResolution());
                o.put("minDelayUs", s.getMinDelay());
                o.put("powerMa", s.getPower());
                arr.put(o);
            }
        } catch (Throwable t) { }
        return arr;
    }
}
