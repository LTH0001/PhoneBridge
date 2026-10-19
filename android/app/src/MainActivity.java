package com.phonebridge.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * V1 极简 UI (任务书第二十五节): 状态 + 启动/停止
 */
public class MainActivity extends Activity {
    private TextView tvStatus;
    private TextView connectionTitle, connectionNote, cameraState, microphoneState, trafficState;
    private Handler ui = new Handler(Looper.getMainLooper());
    private final android.content.BroadcastReceiver usbPermission=new android.content.BroadcastReceiver(){public void onReceive(android.content.Context c,Intent intent){if("com.phonebridge.app.USB_PERMISSION".equals(intent.getAction())&&intent.getBooleanExtra(android.hardware.usb.UsbManager.EXTRA_PERMISSION_GRANTED,false))AccessoryLink.attached(MainActivity.this);}};

    private static final String[] PERMS = {
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.POST_NOTIFICATIONS
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);PanelTheme.apply(this);
        registerReceiver(usbPermission,new android.content.IntentFilter("com.phonebridge.app.USB_PERMISSION"));

        buildHome();

        java.util.ArrayList<String> missing = new java.util.ArrayList<>();
        for (String p : PERMS) {
            if (p.equals(Manifest.permission.POST_NOTIFICATIONS) && android.os.Build.VERSION.SDK_INT < 33) continue;
            if ((p.equals(Manifest.permission.BLUETOOTH_SCAN) || p.equals(Manifest.permission.BLUETOOTH_CONNECT))
                    && android.os.Build.VERSION.SDK_INT < 31) continue;
            if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) missing.add(p);
        }
        if (!missing.isEmpty()) requestPermissions(missing.toArray(new String[0]), 1);
        // 自动启动桥接服务 (exported=false 的服务只能由本应用启动)
        startService(new Intent(this, BridgeService.class));
        ui.postDelayed(statusTicker, 1000);
    }

    private int dp(int n){return HomeStyle.dp(this,n);}
    private TextView text(String value,int size,int color){
        TextView view=new TextView(this);view.setText(value);view.setTextSize(size);view.setTextColor(PanelTheme.color(color));
        view.setLineSpacing(dp(3),1);return view;
    }
    private LinearLayout column(){LinearLayout view=new LinearLayout(this);view.setOrientation(LinearLayout.VERTICAL);return view;}
    private LinearLayout card(LinearLayout parent){
        LinearLayout view=column();view.setPadding(dp(20),dp(20),dp(20),dp(20));
        android.graphics.drawable.GradientDrawable bg=new android.graphics.drawable.GradientDrawable();
        bg.setColor(PanelTheme.color(0xffffffff));bg.setCornerRadius(dp(14));bg.setStroke(dp(1),PanelTheme.color(0xffe1e5ec));view.setBackground(bg);
        LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(-1,-2);layout.bottomMargin=dp(16);parent.addView(view,layout);return view;
    }
    private void button(LinearLayout parent,String title,boolean primary,View.OnClickListener click){
        Button view=HomeStyle.button(this,title,false,click);view.setTextSize(14);if(primary)HomeStyle.primary(view);
        LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(-1,dp(52));layout.topMargin=dp(12);parent.addView(view,layout);
    }
    private void buildHome(){
        getWindow().setStatusBarColor(HomeStyle.BG);getWindow().setNavigationBarColor(HomeStyle.BG);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setBackgroundColor(PanelTheme.color(HomeStyle.BG));
        LinearLayout root=column();root.setPadding(dp(24),dp(24),dp(24),dp(28));scroll.addView(root);
        LinearLayout brand=new LinearLayout(this);brand.setGravity(Gravity.CENTER_VERTICAL);
        android.widget.ImageView mark=new android.widget.ImageView(this);
        mark.setImageDrawable(getDrawable(getResources().getIdentifier("ic_brand","drawable",getPackageName())));
        mark.setContentDescription("PhoneBridge 手机与电脑连接标志");brand.addView(mark,new LinearLayout.LayoutParams(dp(44),dp(44)));
        LinearLayout heading=column();LinearLayout.LayoutParams headingLayout=new LinearLayout.LayoutParams(0,-2,1);headingLayout.leftMargin=dp(12);brand.addView(heading,headingLayout);
        TextView name=text("PhoneBridge",22,HomeStyle.TEXT);name.setTypeface(null,android.graphics.Typeface.BOLD);heading.addView(name);
        heading.addView(text("手机外设管理",12,HomeStyle.MUTED));root.addView(brand);
        android.widget.Space gap=new android.widget.Space(this);root.addView(gap,new LinearLayout.LayoutParams(-1,dp(24)));
        LinearLayout hero=card(root);
        connectionTitle=text("●  正在准备连接",20,HomeStyle.ACCENT);connectionTitle.setTypeface(null,android.graphics.Typeface.BOLD);hero.addView(connectionTitle);
        connectionNote=text("启动桥接服务后，在电脑端选择手机并连接。",14,HomeStyle.MUTED);connectionNote.setPadding(0,dp(10),0,dp(18));hero.addView(connectionNote);
        TextView model=text(android.os.Build.MODEL+"  /  Android "+android.os.Build.VERSION.RELEASE,12,HomeStyle.TEXT);hero.addView(model);
        trafficState=text("尚无传输",12,HomeStyle.MUTED);trafficState.setPadding(0,dp(6),0,0);hero.addView(trafficState);
        LinearLayout media=card(root);media.addView(text("外设状态",12,HomeStyle.MUTED));
        LinearLayout row=new LinearLayout(this);row.setPadding(0,dp(14),0,0);
        cameraState=text("摄像头\n未启动",17,HomeStyle.TEXT);microphoneState=text("麦克风\n未启动",17,HomeStyle.TEXT);
        row.addView(cameraState,new LinearLayout.LayoutParams(0,-2,1));row.addView(microphoneState,new LinearLayout.LayoutParams(0,-2,1));media.addView(row);
        LinearLayout panel=card(root);TextView title=text("电脑控制面板",17,HomeStyle.TEXT);title.setTypeface(null,android.graphics.Typeface.BOLD);panel.addView(title);
        panel.addView(text("查看歌词和硬件状态，调节电脑音量。",13,HomeStyle.MUTED));
        button(panel,"打开控制面板",true,v -> {
            if(!AccessoryLink.active()&&!WirelessLink.active()&&getSharedPreferences("pc_api",MODE_PRIVATE).getString("token","").isEmpty()){
                PanelTheme.dialog(this).setTitle("先从电脑打开一次")
                    .setMessage("连接电脑后，在桌面端点击“打开手机控制面板”，建立安全连接。之后即可从这里进入。")
                    .setPositiveButton("知道了",null).show();return;
            }
            startActivity(new Intent(this,DashboardActivity.class));
        });
        LinearLayout guide=card(root);guide.addView(text("USB 有线连接  /  推荐",16,HomeStyle.TEXT));
        TextView steps=text("01  用数据线连接手机与电脑\n02  开启 USB 调试，允许自己的电脑\n03  电脑端选择已授权的手机，点击连接",13,HomeStyle.MUTED);steps.setPadding(0,dp(10),0,0);guide.addView(steps);
        button(guide,"启动 / 恢复桥接服务",false,v -> startService(new Intent(this,BridgeService.class)));
        LinearLayout advanced=card(root);advanced.addView(text("更多连接与诊断",16,HomeStyle.TEXT));
        final LinearLayout options=column();options.setVisibility(View.GONE);
        button(advanced,"展开实验功能与诊断",false,v -> {boolean show=options.getVisibility()!=View.VISIBLE;options.setVisibility(show?View.VISIBLE:View.GONE);((Button)v).setText(show?"收起实验功能与诊断":"展开实验功能与诊断");});
        advanced.addView(options);
        TextView warning=text("无线与免调试 USB 尚属实验能力。\n日常使用推荐 USB 调试连接。",12,HomeStyle.MUTED);warning.setPadding(0,dp(14),0,0);options.addView(warning);
        button(options,"扫描电脑配对二维码",false,v -> startActivityForResult(new Intent(this,PairScanActivity.class),9));
        button(options,"输入无线配对信息",false,v -> pairWireless());
        button(options,"重试 USB 外设连接（实验）",false,v -> AccessoryLink.retry(this));
        button(options,"断开无线连接",false,v -> WirelessLink.close());
        button(options,"查看手机硬件能力",false,v -> new Thread(() -> {
            String json=CapabilityScanner.scan(this).toString();ui.post(() -> append(pretty(json)));
        },"pb-capabilities").start());
        button(options,"停止桥接服务",false,v -> PanelTheme.dialog(this).setTitle("停止连接？")
            .setMessage("将中断正在使用的手机外设。之后可以重新启动服务。")
            .setNegativeButton("取消",null).setPositiveButton("停止",(d,w) -> {Intent stop=new Intent(this,BridgeService.class);stop.setAction(BridgeService.ACTION_STOP);startService(stop);}).show());
        tvStatus=text("诊断信息仅保留在本页。",11,HomeStyle.MUTED);tvStatus.setTextIsSelectable(true);tvStatus.setPadding(0,dp(14),0,0);options.addView(tvStatus);
        button(options,"外观主题 · 浅色 / 深色 / 跟随系统",false,v -> PanelTheme.choose(this));
        TextView privacy=text("相机与麦克风按需开启，权限由你确认。",11,HomeStyle.MUTED);privacy.setGravity(Gravity.CENTER);privacy.setPadding(0,dp(6),0,dp(14));root.addView(privacy);
        setContentView(scroll);
    }

    @Override public void onDestroy() {
        unregisterReceiver(usbPermission);
        ui.removeCallbacks(statusTicker);
        super.onDestroy();
    }

    @Override protected void onResume(){super.onResume();if(PanelTheme.refresh(this))return;AccessoryLink.attached(this);}
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);if(android.hardware.usb.UsbManager.ACTION_USB_ACCESSORY_ATTACHED.equals(intent.getAction()))AccessoryLink.retry(this);}

    private String pretty(String json) {
        try { return new org.json.JSONObject(json).toString(2); } catch (Throwable t) { return json; }
    }

    private void pairWireless(){
        android.widget.EditText code=new android.widget.EditText(this);code.setHint("粘贴电脑显示的 pbw1: 配对信息");code.setTextColor(PanelTheme.color(0xff203646));code.setHintTextColor(PanelTheme.color(0xff657987));code.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);code.setMaxLines(4);
        code.setImeOptions(android.view.inputmethod.EditorInfo.IME_FLAG_NO_EXTRACT_UI);code.setTextSize(14);
        android.app.AlertDialog dialog=PanelTheme.dialog(this).setTitle("连接自己的电脑")
            .setMessage("手机和电脑需在可互通的 Wi-Fi。电脑点击无线配对，生成后输入/粘贴完整信息。也可使用主页面的扫码按钮。配对会允许此电脑使用已授权的外设；请勿使用陌生人的配对信息。")
            .setView(code).setNegativeButton("取消",(d,w) -> WirelessLink.close()).setPositiveButton("连接",null).create();
        dialog.setOnCancelListener(d -> WirelessLink.close());
        dialog.setOnShowListener(d -> dialog.getButton(-1).setOnClickListener(v -> {
            String invitation=code.getText().toString();dialog.getButton(-1).setEnabled(false);
            new Thread(() -> {try{WirelessLink.pair(this,invitation);ui.post(dialog::dismiss);}
                catch(Exception e){ui.post(() -> {dialog.getButton(-1).setEnabled(true);dialog.setMessage("无线配对失败："+e.getMessage()+"\n检查电脑防火墙、所选网卡、配对有效期后重试。");});}},"pb-pair").start();
        }));dialog.show();
    }

    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==9&&result==RESULT_OK&&data!=null){
        String invitation=data.getStringExtra("invitation");
        PanelTheme.dialog(this).setTitle("连接这台电脑？").setMessage("仅连接你自己的电脑。配对允许使用已授权的摄像头、麦克风、触屏及控制面板；可随时断开。")
            .setNegativeButton("取消",null).setPositiveButton("确认连接",(d,w) -> new Thread(() -> {try{WirelessLink.pair(this,invitation);}catch(Exception e){ui.post(() -> android.widget.Toast.makeText(this,"配对失败，请检查网络和配对有效期",1).show());}},"pb-qr-pair").start()).show();
    }}

    private void append(String s) {
        tvStatus.append(s + "\n");
    }

    private final Runnable statusTicker = new Runnable() {
        @Override public void run() {
            try {
                BridgeService svc = BridgeService.instance;
                org.json.JSONObject s=svc==null?new org.json.JSONObject():svc.statusJson();
                boolean running=s.optBoolean("service_running"),connected=s.optInt("clients")>0;
                connectionTitle.setText(connected?"●  已连接电脑":running?"●  等待电脑连接":"○  桥接服务已停止");
                connectionTitle.setTextColor(PanelTheme.color(connected?HomeStyle.ACCENT:HomeStyle.TEXT));
                connectionNote.setText(connected?(AccessoryLink.active()?"USB 外设通道已建立":WirelessLink.active()?"无线安全通道已建立":"USB 调试通道已建立"):
                    running?"手机已就绪。请在电脑端选择手机，点击连接。":"点击下方“启动 / 恢复桥接服务”重新连接。");
                trafficState.setText(String.format(java.util.Locale.CHINA,"发送 %.1f MB    接收 %.1f MB",s.optLong("tx_bytes")/1048576.0,s.optLong("rx_bytes")/1048576.0));
                org.json.JSONObject camera=s.optJSONObject("camera"),mic=s.optJSONObject("microphone");
                boolean camOn=camera!=null&&camera.optBoolean("running"),micOn=mic!=null&&mic.optBoolean("running");
                cameraState.setText("摄像头\n"+(camOn?String.format(java.util.Locale.CHINA,"%.0f FPS · 采集中",camera.optDouble("fps")):"未启动"));
                microphoneState.setText("麦克风\n"+(micOn?"采集中":"未启动"));
                cameraState.setTextColor(PanelTheme.color(camOn?HomeStyle.ACCENT:HomeStyle.TEXT));microphoneState.setTextColor(PanelTheme.color(micOn?HomeStyle.ACCENT:HomeStyle.TEXT));
            } catch (Throwable t) { }
            ui.postDelayed(this, 1000);
        }
    };
}
