package com.phonebridge.app;

import android.app.Activity;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.FrameLayout;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

/** Native touch panel: text is rendered on the phone, never a desktop bitmap. */
public final class DashboardActivity extends Activity {
    private final Handler ui=new Handler();
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private boolean active, pending;
    private TextView connection, song, artist, songTime, hint;
    private Button previous, toggle, next, open, desktop;
    private Card cpu,memory,disk,gpu0,gpu1;
    private String sourceId="";
    private boolean canToggle,canPrevious,canNext;
    private PanelPlayback playback;
    private PanelNavigation navigation;
    private HoldToTalk holdToTalk;
    private LyricsCanvas miniLyrics;private String lyricTrack="";
    private static final int TEXT=0xff252c38, MUTED=0xff647082, ACCENT=0xff376bc1;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);PanelTheme.apply(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_FULLSCREEN);
        if(android.os.Build.VERSION.SDK_INT>=28) {
            WindowManager.LayoutParams attributes=getWindow().getAttributes();
            attributes.layoutInDisplayCutoutMode=android.os.Build.VERSION.SDK_INT>=30 ? 3 : 1;
            getWindow().setAttributes(attributes);
        }
        immersive();
        navigation=new PanelNavigation(this,() -> onBackPressed(),() -> {},() -> command("/api/dashboard/desktop",new JSONObject(),true));
        try { PanelConnection.configure(this,getIntent()); }
        catch(Exception error) { android.widget.Toast.makeText(this,error.getMessage(),1).show(); finish(); return; }
        build();
        worker.execute(() -> {
            try { PanelConnection.request(this,"/api/dashboard/enter",new JSONObject()); }
            catch(Exception error) { ui.post(() -> failure(error)); }
        });
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent); setIntent(intent);
        try { PanelConnection.configure(this,intent); }
        catch(Exception error) { failure(error); }
    }

    private void build() {
        FrameLayout shell=new FrameLayout(this);
        VolumeLayout root=new VolumeLayout(this,true,delta -> {if(playback!=null)playback.delta(delta);});
        shell.addView(root,new FrameLayout.LayoutParams(-1,-1));
        root.setBackground(new CockpitBackdrop());root.setPadding(dp(14),dp(8),dp(14),dp(8));
        LinearLayout header=new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout brand=new LinearLayout(this);brand.setOrientation(1);brand.setGravity(Gravity.CENTER_VERTICAL);
        TextView title=label("性能座舱",16,TEXT);title.setTypeface(null,Typeface.BOLD);brand.addView(title);
        TextView subtitle=label("PHONEBRIDGE / LIVE TELEMETRY",7,MUTED);subtitle.setLetterSpacing(.12f);brand.addView(subtitle);
        header.addView(brand,new LinearLayout.LayoutParams(0,dp(34),1));
        connection=label("连接中",12,MUTED); header.addView(connection);
        Button appearance=button("外观",v -> PanelTheme.choose(this));
        LinearLayout.LayoutParams appearanceSlot=new LinearLayout.LayoutParams(dp(64),dp(34));appearanceSlot.leftMargin=dp(8);header.addView(appearance,appearanceSlot);
        Button padInput=button("触控板",v -> startActivity(new Intent(this,InputActivity.class).putExtra("tab","pad")));
        LinearLayout.LayoutParams padSlot=new LinearLayout.LayoutParams(dp(78),dp(34));padSlot.leftMargin=dp(8);header.addView(padInput,padSlot);
        Button voiceInput=button("按住说话",null);
        LinearLayout.LayoutParams voiceSlot=new LinearLayout.LayoutParams(dp(94),dp(34));voiceSlot.leftMargin=dp(8);header.addView(voiceInput,voiceSlot);
        holdToTalk=new HoldToTalk(this,voiceInput,shell);
        desktop=button("电脑副屏",v -> command("/api/dashboard/desktop",new JSONObject(),true));
        PanelStyle.primary(desktop);
        LinearLayout.LayoutParams desktopLayout=new LinearLayout.LayoutParams(dp(92),dp(34)); desktopLayout.leftMargin=dp(8);
        header.addView(desktop,desktopLayout); root.addView(header);
        LinearLayout output=new LinearLayout(this);
        Button outputDevice=button("播放设备",null),mute=button("静音",null);
        output.addView(outputDevice,new LinearLayout.LayoutParams(0,dp(28),1));
        output.addView(mute,new LinearLayout.LayoutParams(dp(64),dp(28)));
        TextView gesture=label("  ↑↓ 音量 · 导航手势 ⓘ",10,MUTED);gesture.setOnClickListener(v -> PanelNavigation.help(this));
        output.addView(gesture,new LinearLayout.LayoutParams(dp(174),dp(28)));root.addView(output);
        playback=new PanelPlayback(this,outputDevice,mute);
        playback.attach(root);

        LinearLayout body=new LinearLayout(this);
        LinearLayout.LayoutParams bodyLayout=new LinearLayout.LayoutParams(-1,0,1); bodyLayout.topMargin=dp(6); bodyLayout.bottomMargin=dp(3);
        root.addView(body,bodyLayout);
        LinearLayout player=box(); player.setPadding(dp(6),dp(10),dp(14),dp(5));
        LinearLayout.LayoutParams playerLayout=new LinearLayout.LayoutParams(0,-1,.26f); playerLayout.rightMargin=dp(6);
        body.addView(player,playerLayout);
        player.setOnClickListener(v -> detail("music",0));player.setContentDescription("音乐歌词模式");
        player.addView(label("正在播放 · QQ 音乐",11,MUTED));
        song=label("等待当前歌曲",23,TEXT); song.setTypeface(null,Typeface.BOLD); song.setMaxLines(2);
        song.setMaxLines(1);song.setAutoSizeTextTypeUniformWithConfiguration(11,15,1,android.util.TypedValue.COMPLEX_UNIT_SP);song.setEllipsize(android.text.TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams songLayout=new LinearLayout.LayoutParams(-1,dp(24)); songLayout.topMargin=dp(2);
        player.addView(song,songLayout);
        artist=label("",9,MUTED); artist.setMaxLines(1);artist.setEllipsize(android.text.TextUtils.TruncateAt.END); player.addView(artist);
        miniLyrics=new LyricsCanvas(this,true);miniLyrics.setOnClickListener(v -> detail("music",0));player.addView(miniLyrics,new LinearLayout.LayoutParams(-1,0,1));
        songTime=label("— : —",10,MUTED); player.addView(songTime);
        LinearLayout controls=new LinearLayout(this);
        controls.setGravity(Gravity.CENTER);
        previous=new TransportButton(this,-1,true);previous.setOnClickListener(v -> music("previous"));
        toggle=new TransportButton(this,0,true);toggle.setOnClickListener(v -> music("toggle"));
        next=new TransportButton(this,1,true);next.setOnClickListener(v -> music("next"));
        for(Button b:new Button[]{previous,toggle,next}) {
            LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(dp(48),dp(40)); layout.setMargins(dp(4),0,dp(4),0);
            controls.addView(b,layout);
        }
        player.addView(controls);
        open=button("显示 / 最小化 QQ 音乐",v -> music("window_toggle"));
        player.addView(open,new LinearLayout.LayoutParams(-1,dp(28)));

        LinearLayout metrics=new LinearLayout(this); metrics.setOrientation(LinearLayout.VERTICAL);
        body.addView(metrics,new LinearLayout.LayoutParams(0,-1,.74f));
        LinearLayout row0=new LinearLayout(this),row1=new LinearLayout(this);
        row0.setPadding(0,0,0,0);
        LinearLayout.LayoutParams row0Layout=new LinearLayout.LayoutParams(-1,0,.80f);row0Layout.bottomMargin=dp(3);
        metrics.addView(row0,row0Layout);metrics.addView(row1,new LinearLayout.LayoutParams(-1,0,.20f));
        cpu=new Card("CPU",ACCENT,true);memory=new Card("内存",0xff5277bb,false);
        disk=new Card("磁盘",0xffa97a47,false);disk.box.setOnClickListener(v -> startActivity(new Intent(this,StorageActivity.class)));
        gpu0=new Card("GPU 1",0xff397e8f,true);gpu1=new Card("GPU 2",0xffa87849,true);
        cpu.box.setOnClickListener(v -> detail("cpu",0));memory.box.setOnClickListener(v -> detail("memory",0));
        gpu0.box.setOnClickListener(v -> detail("gpu",0));gpu1.box.setOnClickListener(v -> detail("gpu",1));
        addCard(row0,gpu0,true);addCard(row0,cpu,true);addCard(row0,gpu1,false);
        ((LinearLayout.LayoutParams)cpu.box.getLayoutParams()).weight=1.45f;
        addCard(row1,memory,true);addCard(row1,disk,false);
        hint=label("每秒更新 · 只读硬件数据",10,MUTED);hint.setMaxLines(1);hint.setEllipsize(android.text.TextUtils.TruncateAt.END);
        LinearLayout footer=new LinearLayout(this);footer.addView(hint,new LinearLayout.LayoutParams(0,dp(24),1));
        footer.addView(button("全部硬件",v -> startActivity(new Intent(this,HardwareActivity.class))),new LinearLayout.LayoutParams(dp(96),dp(24)));
        footer.addView(button("系统 / PID",v -> startActivity(new Intent(this,SystemActivity.class))),new LinearLayout.LayoutParams(dp(112),dp(24)));root.addView(footer);
        setContentView(shell); refreshButtons();
    }

    private void addCard(LinearLayout row,Card card,boolean margin) {
        LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(0,-1,1);
        if(margin) layout.rightMargin=dp(8); row.addView(card.box,layout);
    }

    private final class Card {
        final LinearLayout box;final TextView title,value,detail;final ProgressBar bar;final InstrumentGauge gauge;final FuelGauge fuel;
        Card(String name,int color,boolean dial) {
            box=DashboardActivity.this.box();box.setPadding(dp(4),dp(2),dp(4),dp(2));
            title=label(name,10,MUTED);title.setMaxLines(1);title.setEllipsize(android.text.TextUtils.TruncateAt.END);
            value=label("—",22,color);value.setTypeface(android.graphics.Typeface.MONOSPACE);value.setMaxLines(1);
            value.setAutoSizeTextTypeUniformWithConfiguration(14,22,1,android.util.TypedValue.COMPLEX_UNIT_SP);
            detail=label("等待数据",9,MUTED);detail.setMaxLines(2);detail.setEllipsize(android.text.TextUtils.TruncateAt.END);
            gauge=dial?new InstrumentGauge(DashboardActivity.this,name,color):null;
            fuel=dial?null:new FuelGauge(DashboardActivity.this,color,"磁盘".equals(name));
            if(dial){box.setBackgroundColor(PanelTheme.color(android.graphics.Color.TRANSPARENT));box.addView(gauge,new LinearLayout.LayoutParams(-1,-1));}
            else {box.setOrientation(LinearLayout.HORIZONTAL);box.addView(fuel,new LinearLayout.LayoutParams(dp(77),-1));LinearLayout info=new LinearLayout(DashboardActivity.this);info.setOrientation(LinearLayout.VERTICAL);info.setGravity(Gravity.CENTER_VERTICAL);info.addView(title);info.addView(detail);box.addView(info,new LinearLayout.LayoutParams(0,-1,1));}
            bar=new ProgressBar(DashboardActivity.this,null,android.R.attr.progressBarStyleHorizontal);
            bar.setMax(100); bar.setProgressTintList(ColorStateList.valueOf(PanelTheme.color(color)));
            // Compact bands and analog dials already carry the meter; no duplicate bar.
        }
    }

    private LinearLayout box() {
        LinearLayout layout=new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackgroundColor(PanelTheme.color(android.graphics.Color.TRANSPARENT));return layout;
    }
    private TextView label(String text,int size,int color) {
        TextView view=new TextView(this); view.setText(text); view.setTextSize(size); view.setTextColor(PanelTheme.color(color));
        view.setGravity(Gravity.CENTER_VERTICAL); return view;
    }
    private Button button(String text,View.OnClickListener click) {
        Button b=PanelStyle.button(this,text,false,click);b.setStateListAnimator(null);b.setElevation(0);b.setPadding(dp(8),0,dp(8),0);b.setMinimumHeight(0);b.setMinHeight(0);
        GradientDrawable surface=new GradientDrawable();surface.setColor(PanelTheme.color(0x55ffffff));surface.setCornerRadius(dp(9));surface.setStroke(dp(1),PanelTheme.color(0x4096aac3));
        b.setBackground(new android.graphics.drawable.RippleDrawable(ColorStateList.valueOf(PanelTheme.color(0x18376bc1)),surface,null));return b;
    }
    private int dp(int number) { return Math.round(number*getResources().getDisplayMetrics().density); }

    private final Runnable poll=new Runnable() {
        @Override public void run() {
            if(!active) return;
            worker.execute(() -> {
                try {
                    JSONObject data=PanelConnection.request(DashboardActivity.this,"/api/dashboard/status",null);
                    ui.post(() -> { if(active) update(data); });
                } catch(Exception error) { ui.post(() -> { if(active) failure(error); }); }
                finally { ui.post(() -> { if(active) ui.postDelayed(poll,1000); }); }
            });
        }
    };
    private final Runnable lyricPoll=new Runnable(){public void run(){if(!active)return;worker.execute(() -> {
        try{long started=android.os.SystemClock.elapsedRealtime();JSONObject result=PanelConnection.request(DashboardActivity.this,"/api/music/lyrics",null);
            long transit=android.os.SystemClock.elapsedRealtime()-started;String key=result.optString("track_key");
            if(!key.equals(lyricTrack)){lyricTrack=key;PanelConnection.request(DashboardActivity.this,"/api/music/lyrics",new JSONObject().put("allow_network",false));}
            ui.post(() -> {if(active)miniLyrics.update(result,transit);});
        }catch(Exception ignored){}finally{ui.post(() -> {if(active)ui.postDelayed(lyricPoll,200);});}
    });}};

    private void update(JSONObject data) {
        if(playback!=null)playback.update(data.optJSONObject("playback"));
        boolean connected=data.optBoolean("connected");
        connection.setText(connected ? ("wireless".equals(data.optString("transport"))?"无线已连接":"USB 已连接") : "连接已断开");
        connection.setTextColor(PanelTheme.color(connected ? ACCENT : 0xffa84e48));
        JSONObject host=data.optJSONObject("host");
        if(host!=null) {
            JSONObject processor=host.optJSONObject("cpu"), ram=host.optJSONObject("memory");
            boolean hasTemperature=processor!=null && processor.has("temperature_c") && !processor.isNull("temperature_c");
            String cpuDetail=hasTemperature ? String.format(Locale.US,"%s %.0f°C", "Core Max".equals(processor.optString("temperature_source")) ? "核心最高" : "封装温度",processor.optDouble("temperature_c")) : "温度暂不可用";
            setMetric(cpu,processor,"CPU · "+HardwareNames.compact(processor==null?"":processor.optString("name"),"型号读取中"),cpuDetail);
            String memoryText=ram==null ? "不可用" : String.format(Locale.US,"%.1f / %.1f GiB",ram.optDouble("used_gb"),ram.optDouble("total_gb"));
            setMetric(memory,ram,"内存 · 已用",memoryText);
            JSONArray gpus=host.optJSONArray("gpus");
            gpu(gpu0,gpus!=null ? gpus.optJSONObject(0) : null,1);
            gpu(gpu1,gpus!=null ? gpus.optJSONObject(1) : null,2);
            JSONArray drives=host.optJSONArray("disks");double throughput=0,busy=0;boolean valid=false;
            if(drives!=null)for(int i=0;i<drives.length();i++){JSONObject d=drives.optJSONObject(i);if(d!=null&&!d.isNull("read_mbps")&&!d.isNull("write_mbps")){throughput+=d.optDouble("read_mbps")+d.optDouble("write_mbps");busy=Math.max(busy,d.optDouble("load_percent"));valid=true;}}
            double free=0,total=0;
            if(drives!=null)for(int i=0;i<drives.length();i++){JSONObject d=drives.optJSONObject(i);if(d!=null&&!d.isNull("free_gb")&&!d.isNull("total_gb")&&d.optDouble("total_gb")>0){free+=d.optDouble("free_gb");total+=d.optDouble("total_gb");}}
            disk.fuel.update(total>0?100*free/total:null);
            disk.title.setText("存储 · 剩余空间");disk.detail.setText((total>0?String.format(Locale.US,"%.0f / %.0f GiB",free,total):"容量不可用")+"\n"+(valid?String.format(Locale.US,"读写 %.1f MiB/s",throughput):"读写不可用"));disk.bar.setProgress((int)busy);
        }
        JSONObject media=data.optJSONObject("music");
        if(media!=null) {
            boolean available=media.optBoolean("available");
            sourceId=media.optString("source_app_id");
            JSONObject window=media.optJSONObject("window");open.setText(window!=null&&window.optBoolean("visible")?"最小化电脑 QQ 音乐":"打开 / 显示电脑 QQ 音乐");
            song.setText(media.optString("title","打开 QQ 音乐")); artist.setText(media.optString("artist"));
            toggle.setText("playing".equals(media.optString("playback_status")) ? "暂停" : "播放");
            songTime.setText(available ? clock(media.optDouble("position_seconds"))+" / "+clock(media.optDouble("duration_seconds")) : "没有音乐会话");
            canToggle=available && media.optBoolean("can_toggle"); canPrevious=available && media.optBoolean("can_previous"); canNext=available && media.optBoolean("can_next");
            String error=media.optString("error");
            String cpuNote=host!=null && host.optJSONObject("cpu")!=null ? host.optJSONObject("cpu").optString("temperature_note") : "";
            if(!pending) hint.setText(!error.isEmpty() ? error : !cpuNote.isEmpty() ? cpuNote : "实时监控 · GPU 分项 / 磁盘 / PID 均可点开 · 原生触屏");
            refreshButtons();
        }
    }

    private void setMetric(Card card,JSONObject value,String title,String detail) {
        card.title.setText(title); card.detail.setText(detail);
        if(card.gauge!=null)card.gauge.setModel(title);
        boolean valid=value!=null && !value.isNull("load_percent") && value.has("load_percent");
        double percent=valid ? value.optDouble("load_percent") : 0;
        card.value.setText(valid ? String.format(Locale.US,"%.0f%%",percent) : "—"); card.bar.setProgress((int)Math.max(0,Math.min(100,percent)));
        if(card.gauge!=null)card.gauge.update(valid?percent:null,detail);
        if(card.fuel!=null)card.fuel.update(valid?percent:null);
    }
    private void gpu(Card card,JSONObject value,int number) {
        String name=HardwareNames.compact(value==null?"":value.optString("name"),"未读取到显卡");
        String detail="温度不可用";
        if(value!=null) {
            detail=value.isNull("temperature_c") ? "温度不可用" : value.optInt("temperature_c")+"°C";
            JSONObject e=value.optJSONObject("engines");if(e!=null)detail+="\n3D "+engine(e,"three_d_percent")+" · 编 "+engine(e,"video_encode_percent")+" · 解 "+engine(e,"video_decode_percent");
        }
        setMetric(card,value,"GPU "+number+" · "+name,detail);
    }
    private String engine(JSONObject value,String key){return value.isNull(key)||!value.has(key)?"—":String.format(Locale.US,"%.0f%%",value.optDouble(key));}
    private String clock(double seconds) { long s=Math.max(0,(long)seconds); return String.format(Locale.US,"%02d:%02d",s/60,s%60); }
    private void refreshButtons() {
        previous.setEnabled(!pending && canPrevious); toggle.setEnabled(!pending && canToggle); next.setEnabled(!pending && canNext);
        open.setEnabled(!pending); desktop.setEnabled(!pending);
    }
    private void music(String action) {
        try { command("/api/music/control",new JSONObject().put("action",action).put("source_app_id",sourceId),false); }
        catch(Exception error) { failure(error); }
    }
    private void detail(String kind,int index) {
        Intent intent=new Intent(this,DetailActivity.class);intent.putExtra("kind",kind);intent.putExtra("index",index);startActivity(intent);
    }
    private void command(String path,JSONObject body,boolean returnDesktop) {
        if(pending) return;
        pending=true; refreshButtons(); hint.setText(returnDesktop ? "正在恢复触控副屏…" : "正在操作 QQ 音乐…");
        if(returnDesktop) { active=false; ui.removeCallbacks(poll); }
        worker.execute(() -> {
            try {
                PanelConnection.request(this,path,body);
                ui.post(() -> { pending=false; refreshButtons(); if(returnDesktop) finish(); else hint.setText("操作完成"); });
            } catch(Exception error) {
                ui.post(() -> { pending=false; refreshButtons(); failure(error); if(returnDesktop) { active=true; ui.post(poll); } });
            }
        });
    }
    private void failure(Exception error) {
        if(hint!=null) {
            hint.setText("未完成："+PanelRoute.errorMessage(error)); connection.setText("面板请求失败"); connection.setTextColor(PanelTheme.color(0xffa84e48));
            canToggle=canPrevious=canNext=false; refreshButtons();
        }
    }
    private void immersive() {
        PanelStyle.immersive(this);
    }
    @Override public void onWindowFocusChanged(boolean focused) { super.onWindowFocusChanged(focused); if(focused) immersive(); }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){
        super.onRequestPermissionsResult(request,permissions,results);
        if(request==HoldToTalk.PERMISSION&&holdToTalk!=null)holdToTalk.permissionResult(results.length>0&&results[0]==android.content.pm.PackageManager.PERMISSION_GRANTED);
    }
    @Override protected void onResume() { super.onResume();if(PanelTheme.refresh(this))return; active=true;if(holdToTalk!=null)holdToTalk.resume(); ui.removeCallbacks(poll); ui.postDelayed(poll,200);ui.removeCallbacks(lyricPoll);ui.postDelayed(lyricPoll,250); }
    @Override protected void onPause() { active=false;if(holdToTalk!=null)holdToTalk.pause(); ui.removeCallbacks(poll);ui.removeCallbacks(lyricPoll); super.onPause(); }
    @Override public void onBackPressed() { command("/api/dashboard/desktop",new JSONObject(),true); }
    @Override public boolean dispatchTouchEvent(android.view.MotionEvent event){if(holdToTalk!=null&&holdToTalk.ownsGesture())return super.dispatchTouchEvent(event);if(navigation!=null&&navigation.touch(event,e -> super.dispatchTouchEvent(e)))return true;return super.dispatchTouchEvent(event);}
    @Override public void onDestroy() { active=false;if(holdToTalk!=null)holdToTalk.close(); ui.removeCallbacksAndMessages(null); worker.shutdownNow(); if(playback!=null)playback.close(); super.onDestroy(); }
}
