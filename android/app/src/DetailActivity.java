package com.phonebridge.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

/** Native drill-down pages: task-manager-like metrics or cover-free synced lyrics. */
public final class DetailActivity extends Activity {
    private static final int TEXT=0xff252c38,MUTED=0xff647082,ACCENT=0xff376bc1;
    private final Handler ui=new Handler();
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private boolean active,pending,consentAsked;
    private String kind,lastTrack="",sourceId="";
    private int index;
    private PanelPlayback playback;
    private TextView title,note,metrics;
    private HistoryGraph graph;
    private LyricsCanvas lyrics;
    private MusicBackdrop backdrop;private String artKey="";private Button timing;
    private Button previous,toggle,next;
    private PanelNavigation navigation;
    private String graphField="load_percent";

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);kind=getIntent().getStringExtra("kind");index=getIntent().getIntExtra("index",0);
        if(!"music".equals(kind)&&!"cpu".equals(kind)&&!"memory".equals(kind)&&!"gpu".equals(kind)){finish();return;}
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_FULLSCREEN);
        if(android.os.Build.VERSION.SDK_INT>=28) {
            WindowManager.LayoutParams attributes=getWindow().getAttributes();attributes.layoutInDisplayCutoutMode=android.os.Build.VERSION.SDK_INT>=30?3:1;getWindow().setAttributes(attributes);
        }
        immersive();build();
        navigation=new PanelNavigation(this,() -> finish(),() -> PanelNavigation.panel(this),() -> PanelNavigation.desktop(this));
    }
    private void build() {
        boolean music="music".equals(kind);
        VolumeLayout root=new VolumeLayout(this,music,delta -> {if(playback!=null)playback.delta(delta);});
        if(music){backdrop=new MusicBackdrop();root.setBackground(backdrop);}else root.setBackground(PanelStyle.background());
        root.setPadding(dp(16),dp(8),dp(16),dp(8));
        LinearLayout header=new LinearLayout(this);
        Button back=button("‹ 返回面板",v -> finish());header.addView(back,new LinearLayout.LayoutParams(dp(110),dp(40)));
        title=label(music?"歌词模式":"实时性能详情",music?16:19,music?0xff2e4858:TEXT);title.setMaxLines(1);
        title.setEllipsize(android.text.TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams titleLayout=new LinearLayout.LayoutParams(0,dp(40),1);titleLayout.leftMargin=dp(14);header.addView(title,titleLayout);
        Button device=button("播放设备",null),mute=button("静音",null);
        if(music){timing=button("校准 0.0s",v -> calibrate());header.addView(timing,new LinearLayout.LayoutParams(dp(92),dp(40)));header.addView(button("重查歌词",v -> loadLyrics(false,true)),new LinearLayout.LayoutParams(dp(78),dp(40)));}
        header.addView(device,new LinearLayout.LayoutParams(dp(music?216:278),dp(40)));header.addView(mute,new LinearLayout.LayoutParams(dp(68),dp(40)));
        root.addView(header);playback=new PanelPlayback(this,device,mute);
        playback.attach(root);
        note=label(music?"↑ 加音量 · ↓ 减音量 · 校准可调整歌词时间":"约 60 秒历史 · 每秒采样 · 右侧详情可上下滚动",11,music?0xff647987:MUTED);
        root.addView(note,new LinearLayout.LayoutParams(-1,dp(27)));
        if("gpu".equals(kind)){
            LinearLayout modes=new LinearLayout(this);
            String[] names={"整体","3D / 渲染","视频编码","视频解码","复制"};String[] fields={"load_percent","three_d_percent","video_encode_percent","video_decode_percent","copy_percent"};
            for(int i=0;i<names.length;i++){final String field=fields[i],name=names[i];LinearLayout.LayoutParams slot=new LinearLayout.LayoutParams(0,dp(30),1);slot.setMargins(0,0,dp(6),dp(4));modes.addView(button(names[i],v -> {graphField=field;note.setText(name+" · 60 秒历史 · — 表示本机暂未提供该指标");graph.invalidate();}),slot);}root.addView(modes);
        }
        if(music) {
            lyrics=new LyricsCanvas(this);root.addView(lyrics,new LinearLayout.LayoutParams(-1,0,1));
            LinearLayout controls=new LinearLayout(this);controls.setGravity(Gravity.CENTER);
            previous=new TransportButton(this,-1,true);previous.setOnClickListener(v -> music("previous"));toggle=new TransportButton(this,0,true);toggle.setOnClickListener(v -> music("toggle"));next=new TransportButton(this,1,true);next.setOnClickListener(v -> music("next"));
            for(Button button:new Button[]{previous,toggle,next}) {
                LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(dp(48),dp(40));layout.setMargins(dp(8),0,dp(8),0);controls.addView(button,layout);
            }
            root.addView(controls);previous.setEnabled(false);toggle.setEnabled(false);next.setEnabled(false);
        } else {
            LinearLayout body=new LinearLayout(this);LinearLayout.LayoutParams bodyLayout=new LinearLayout.LayoutParams(-1,0,1);bodyLayout.topMargin=dp(4);root.addView(body,bodyLayout);
            graph=new HistoryGraph();body.addView(graph,new LinearLayout.LayoutParams(0,-1,.57f));
            ScrollView scroll=new ScrollView(this);LinearLayout.LayoutParams scrollLayout=new LinearLayout.LayoutParams(0,-1,.43f);scrollLayout.leftMargin=dp(18);body.addView(scroll,scrollLayout);
            metrics=label("读取数据…",14,TEXT);metrics.setGravity(Gravity.TOP);scroll.addView(metrics);
        }
        setContentView(root);
    }
    private void music(String action) {
        if(pending)return;pending=true;previous.setEnabled(false);toggle.setEnabled(false);next.setEnabled(false);
        worker.execute(() -> {
            try {PanelConnection.request(this,"/api/music/control",new JSONObject().put("action",action).put("source_app_id",sourceId));}
            catch(Exception error){ui.post(() -> note.setText("操作未确认："+error.getMessage()));}
            finally{ui.post(() -> pending=false);}
        });
    }
    private void loadLyrics(boolean allow) {
        loadLyrics(allow,false);
    }
    private void loadLyrics(boolean allow,boolean retry) {
        worker.execute(() -> {
            try {
                JSONObject data=PanelConnection.request(this,"/api/music/lyrics",new JSONObject().put("allow_network",allow).put("retry",retry));
                ui.post(() -> {if(active){lyrics.update(data,0);updateTiming();if("consent".equals(data.optString("state")))askConsent();}});
            } catch(Exception error){ui.post(() -> note.setText("歌词读取失败："+error.getMessage()));}
        });
    }
    private void askConsent() {
        if(consentAsked)return;consentAsked=true;
        new AlertDialog.Builder(this).setTitle("允许联网查询同步歌词？")
            .setMessage("向 LRCLIB 只查询当前歌曲名称和歌手，不发送音频、账户信息或播放历史。允许后以后进入歌词页也可查询；可在电脑版设置中关闭。查不到时可在电脑导入 LRC。")
            .setPositiveButton("允许",(d,w) -> loadLyrics(true)).setNegativeButton("仅本地歌词",null).show();
    }
    private final Runnable poll=new Runnable(){
        @Override public void run() {
            if(!active)return;
            worker.execute(() -> {
                try {
                    JSONObject overview=PanelConnection.request(DetailActivity.this,"/api/dashboard/status",null);
                    long requestStart=android.os.SystemClock.elapsedRealtime();
                    JSONObject data="music".equals(kind)?PanelConnection.request(DetailActivity.this,"/api/music/lyrics",null):
                        PanelConnection.request(DetailActivity.this,"/api/dashboard/detail",new JSONObject().put("kind",kind).put("index",index));
                    long transit=android.os.SystemClock.elapsedRealtime()-requestStart;
                    ui.post(() -> {
                        if(!active)return;playback.update(overview.optJSONObject("playback"));
                        if("music".equals(kind)) {
                            JSONObject media=overview.optJSONObject("music");
                            if(media!=null) {
                                sourceId=media.optString("source_app_id");title.setText(media.optString("title"));
                                String artwork=media.optString("artwork_key");
                                if(!artwork.equals(artKey)){artKey=artwork;backdrop.setArt(null);if(!artwork.isEmpty())loadArt(artwork);}
                                toggle.setText("playing".equals(media.optString("playback_status"))?"暂停":"播放");
                                boolean available=media.optBoolean("available")&&!pending;
                                previous.setEnabled(available&&media.optBoolean("can_previous"));toggle.setEnabled(available&&media.optBoolean("can_toggle"));next.setEnabled(available&&media.optBoolean("can_next"));
                            }
                            lyrics.update(data,transit);updateTiming();String key=data.optString("track_key");
                            if(!lastTrack.equals(key)){lastTrack=key;loadLyrics(false);}
                            note.setMaxLines(1);note.setEllipsize(android.text.TextUtils.TruncateAt.END);
                            note.setText(data.optString("note").isEmpty()?(media==null?"":media.optString("artist")+" · ")+"歌词来源："+data.optString("source")+" · ↑ 加音量 / ↓ 减音量":data.optString("note"));
                        } else hardware(data);
                    });
                }catch(Exception error){ui.post(() -> {if(active)note.setText("数据不可用："+error.getMessage());});}
                finally{ui.post(() -> {if(active)ui.postDelayed(poll,"music".equals(kind)?200:1000);});}
            });
        }
    };
    private String number(JSONObject object,String key,String unit) {
        return object.has(key)&&!object.isNull(key)?String.format(Locale.US,"%.1f",object.optDouble(key))+unit:"—";
    }
    private void hardware(JSONObject data) {
        JSONObject metric=data.optJSONObject("metric");if(metric==null)return;
        String name="cpu".equals(kind)?metric.optString("name","CPU"):"gpu".equals(kind)?metric.optString("name","GPU"):"内存";
        if("gpu".equals(kind))name="GPU "+(index+1)+" · "+name;
        title.setText(name+"  ·  "+number(metric,"load_percent","%"));
        StringBuilder text=new StringBuilder();text.append("当前占用   ").append(number(metric,"load_percent","%"));
        if("cpu".equals(kind)) {
            text.append("\n封装温度   ").append(number(metric,"temperature_c","°C"));
            if(!metric.optString("temperature_note").isEmpty())text.append("\n").append(metric.optString("temperature_note"));
            text.append("\n报告频率   ").append(number(metric,"frequency_mhz"," MHz"));
            text.append("\n物理核心   ").append(metric.optInt("physical_cores")).append("\n逻辑处理器   ").append(metric.optInt("logical_processors"));
            text.append("\n进程数   ").append(metric.optInt("process_count"));
            long uptime=metric.optLong("uptime_seconds");text.append(String.format(Locale.US,"\n运行时间   %d 天 %02d:%02d:%02d",uptime/86400,uptime/3600%24,uptime/60%60,uptime%60));
            JSONArray cores=metric.optJSONArray("cores");if(cores!=null&&cores.length()>0) {
                text.append("\n\n各核心温度");for(int i=0;i<cores.length();i++){JSONObject core=cores.optJSONObject(i);if(core!=null)text.append("\n").append(core.optString("name")).append("   ").append(number(core,"temperature_c","°C"));}
            }
            JSONArray loads=metric.optJSONArray("core_load_percent");if(loads!=null){text.append("\n\n各逻辑处理器占用");for(int i=0;i<loads.length();i++)text.append(String.format(Locale.US,"\n逻辑处理器 %d   %.0f%%",i+1,loads.optDouble(i)));}
        } else if("gpu".equals(kind)) {
            JSONObject e=metric.optJSONObject("engines");if(e!=null){text.append("\n\n引擎分项");for(String[] field:new String[][]{{"three_d_percent","3D / 游戏渲染"},{"video_encode_percent","视频编码 NVENC"},{"video_decode_percent","视频解码 NVDEC"},{"copy_percent","数据复制"},{"compute_percent","独立 Compute"}})text.append("\n").append(field[1]).append("   ").append(number(e,field[0],"%"));text.append("\n").append(e.optString("note"));}
            text.append("\nGPU 温度   ").append(number(metric,"temperature_c","°C"));
            text.append("\n显存使用   ").append(number(metric,"memory_used_mb"," MiB"));
            text.append("\n显存总量   ").append(number(metric,"memory_total_mb"," MiB"));
            text.append("\n功耗   ").append(number(metric,"power_w"," W"));
            text.append("\n核心频率   ").append(number(metric,"core_clock_mhz"," MHz"));
            text.append("\n显存频率   ").append(number(metric,"memory_clock_mhz"," MHz"));
            text.append("\n显存读写忙碌度   ").append(number(metric,"memory_load_percent","%"));
            text.append("\n\n3D/复制来自 Windows 引擎计数器，视频来自 NVML。3D 也可能包含计算任务；各引擎百分比不可相加。整体占用与各分项口径不同。Intel 核显尚未接入。");
        } else {
            text.append("\n已使用   ").append(number(metric,"used_gb"," GiB"));text.append("\n物理内存   ").append(number(metric,"total_gb"," GiB"));
            text.append("\n可用内存   ").append(number(metric,"available_gb"," GiB"));
            text.append("\n分页文件报告使用   ").append(number(metric,"swap_used_gb"," GiB"));
            text.append("\n分页文件报告总量   ").append(number(metric,"swap_total_gb"," GiB"));
            text.append("\n\n数据来源 psutil；与任务管理器的压缩/已提交内存不是完全相同的指标。");
        }
        metrics.setText(text);graph.update(data.optJSONArray("history"));
    }
    private final class HistoryGraph extends View {
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);private JSONArray points=new JSONArray();
        HistoryGraph(){super(DetailActivity.this);}
        void update(JSONArray data){if(data!=null)points=data;invalidate();}
        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);float left=dp(32),top=dp(18),right=getWidth()-dp(8),bottom=getHeight()-dp(28);
            paint.setColor(0xfff3f5f8);paint.setStyle(Paint.Style.FILL);canvas.drawRect(left,top,right,bottom,paint);
            paint.setColor(0xffdde3ec);paint.setStrokeWidth(dp(1));
            for(int i=0;i<=6;i++){float x=left+(right-left)*i/6;canvas.drawLine(x,top,x,bottom,paint);}
            for(int i=0;i<=4;i++){float y=top+(bottom-top)*i/4;canvas.drawLine(left,y,right,y,paint);}
            paint.setColor(MUTED);paint.setTextSize(dp(10));canvas.drawText("100%",0,top+dp(4),paint);canvas.drawText("0",dp(17),bottom,paint);
            canvas.drawText("60 秒",left,bottom+dp(19),paint);canvas.drawText("现在",right-dp(25),bottom+dp(19),paint);
            Path path=new Path();boolean started=false;
            for(int i=0;i<points.length();i++) {
                JSONObject point=points.optJSONObject(i);JSONObject series=point;
                if(!"load_percent".equals(graphField)&&point!=null)series=point.optJSONObject("engines");
                if(series==null||!series.has(graphField)||series.isNull(graphField)){started=false;continue;}
                float x=right-(59-(60-points.length()+i))*(right-left)/59;
                float value=(float)Math.max(0,Math.min(100,series.optDouble(graphField)));
                float y=bottom-(bottom-top)*value/100;
                if(!started){path.moveTo(x,y);started=true;}else path.lineTo(x,y);
            }
            paint.setColor(ACCENT);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(2));canvas.drawPath(path,paint);paint.setStyle(Paint.Style.FILL);
        }
    }
    private void updateTiming(){if(timing!=null)timing.setText(String.format(Locale.US,"校准 %+.1fs",lyrics.offset()));}
    private void calibrate(){
        LinearLayout options=new LinearLayout(this);options.setOrientation(LinearLayout.VERTICAL);options.setPadding(dp(20),dp(6),dp(20),dp(6));
        TextView help=label("正值让歌词提前，负值让歌词延后；只记住当前歌曲。",12,0xff526778);help.setMaxLines(2);options.addView(help);
        TextView amount=label(String.format(Locale.US,"当前偏移 %+.1f 秒",lyrics.offset()),18,0xff247dae);options.addView(amount);
        for(String text:new String[]{"歌词提前 0.2 秒","歌词延后 0.2 秒","恢复默认"}){
            Button b=button(text,v -> {lyrics.shift(text.startsWith("歌词提前")?.2:-.2,text.equals("恢复默认"));amount.setText(String.format(Locale.US,"当前偏移 %+.1f 秒",lyrics.offset()));updateTiming();});options.addView(b);
        }
        new AlertDialog.Builder(this).setTitle("歌词时间校准").setView(options).setNegativeButton("完成",null).show();
    }
    private void loadArt(String key){
        worker.execute(() -> {try{byte[] bytes=PanelConnection.artwork(this,key);android.graphics.Bitmap bitmap=android.graphics.BitmapFactory.decodeByteArray(bytes,0,bytes.length);
            ui.post(() -> {if(active&&key.equals(artKey))backdrop.setArt(bitmap);});}catch(Exception ignored){}});
    }
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView label(String text,int size,int color){TextView v=new TextView(this);v.setText(text);v.setTextSize(size);v.setTextColor(color);v.setGravity(Gravity.CENTER_VERTICAL);return v;}
    private Button button(String text,View.OnClickListener listener){return PanelStyle.button(this,text,"music".equals(kind),listener);}
    private void immersive(){PanelStyle.immersive(this);}
    @Override public void onWindowFocusChanged(boolean focused){super.onWindowFocusChanged(focused);if(focused)immersive();}
    @Override public boolean dispatchTouchEvent(android.view.MotionEvent event){if(navigation!=null&&navigation.touch(event,e -> super.dispatchTouchEvent(e)))return true;return super.dispatchTouchEvent(event);}
    @Override protected void onResume(){super.onResume();active=true;ui.removeCallbacks(poll);ui.postDelayed(poll,200);}
    @Override protected void onPause(){active=false;ui.removeCallbacks(poll);super.onPause();}
    @Override public void onDestroy(){active=false;ui.removeCallbacksAndMessages(null);worker.shutdownNow();if(playback!=null)playback.close();super.onDestroy();}
}
