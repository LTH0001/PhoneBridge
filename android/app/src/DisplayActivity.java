package com.phonebridge.app;

import android.app.Activity;
import android.os.Bundle;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.TextView;

/** Edge-to-edge phone-aspect desktop, including the camera-cutout region. */
public final class DisplayActivity extends Activity {
    private SurfaceView video;
    private DisplayReceiver receiver;
    private boolean touch;
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        PanelConnection.configure(this,getIntent());
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON | WindowManager.LayoutParams.FLAG_FULLSCREEN);
        if (android.os.Build.VERSION.SDK_INT >= 28) {
            WindowManager.LayoutParams attrs = getWindow().getAttributes();
            attrs.layoutInDisplayCutoutMode = android.os.Build.VERSION.SDK_INT >= 30 ? 3 : 1;
            getWindow().setAttributes(attrs);
        }
        immersive();
        BridgeService service = BridgeService.instance;
        if (service == null || service.display == null) { finish(); return; }
        receiver = service.display;
        touch = getIntent().getBooleanExtra("touch", false);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(0xff000000);
        video = new SurfaceView(this);
        FrameLayout.LayoutParams layout = new FrameLayout.LayoutParams(-1, -1, Gravity.CENTER);
        root.addView(video, layout);
        // Host uses the actual phone aspect. Fill the entire view; no 16:9 bars.
        // Very small even-pixel aspect rounding is stretched, never cropped.
        video.getHolder().setFixedSize(receiver.width,receiver.height);
        video.getHolder().addCallback(new SurfaceHolder.Callback() {
            @Override public void surfaceCreated(SurfaceHolder holder) { receiver.attach(holder.getSurface()); }
            @Override public void surfaceChanged(SurfaceHolder holder, int format, int w, int h) {
                receiver.surfaceWidth=w; receiver.surfaceHeight=h;
            }
            @Override public void surfaceDestroyed(SurfaceHolder holder) { receiver.stop(); }
        });
        video.setOnTouchListener((view, event) -> {
            if (!touch || BridgeService.instance == null) return true;
            int action = event.getActionMasked();
            if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_MOVE || action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
                try {
                    org.json.JSONObject input = new org.json.JSONObject()
                        .put("action", action == MotionEvent.ACTION_DOWN ? "down" : action == MotionEvent.ACTION_MOVE ? "move" : "up")
                        .put("x", Math.max(0, Math.min(1, event.getX()/view.getWidth())))
                        .put("y", Math.max(0, Math.min(1, event.getY()/view.getHeight())));
                    BridgeService.instance.sendPCInput(input.toString());
                } catch (Throwable ignored) { }
            }
            return true;
        });
        android.widget.Button panel=new android.widget.Button(this);
        panel.setText("控制面板"); panel.setTextSize(12); panel.setTextColor(0xffeefcff);
        panel.setBackgroundColor(0xbb172735);
        FrameLayout.LayoutParams panelLayout=new FrameLayout.LayoutParams(dp(106),dp(36),Gravity.TOP|Gravity.END);
        panelLayout.setMargins(dp(8),dp(8),dp(8),0);
        root.addView(panel,panelLayout);
        panel.setOnClickListener(v -> {
            startActivity(new android.content.Intent(this,DashboardActivity.class)
                .addFlags(android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP|android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP));
            finish();
        });
        setContentView(root);
        root.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob) -> {
            receiver.viewWidth=r-l; receiver.viewHeight=b-t;
        });
    }
    private void immersive() {
        PanelStyle.immersive(this);
    }
    private int dp(int value) { return Math.round(value*getResources().getDisplayMetrics().density); }
    @Override public void onWindowFocusChanged(boolean focused) { super.onWindowFocusChanged(focused); if(focused) immersive(); }
    @Override public void onDestroy() { if (receiver != null) receiver.stop(); super.onDestroy(); }
}
