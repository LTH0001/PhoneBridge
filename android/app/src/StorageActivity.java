package com.phonebridge.app;

import android.app.Activity;
import android.os.*;
import android.view.*;
import android.widget.*;
import android.graphics.*;
import org.json.*;
import java.util.Locale;
import java.util.concurrent.*;

/** Physical-disk I/O, latency and mounted-volume capacity. All read-only. */
public final class StorageActivity extends Activity {
    private final Handler ui=new Handler();private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private boolean active;private int selected=-1;private PanelNavigation navigation;
    private LinearLayout drives;private TextView title,note,metrics;private TrafficGraph graph;private String driveSignature="";
    @Override public void onCreate(Bundle state){
        super.onCreate(state);PanelTheme.apply(this);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_FULLSCREEN);
        if(Build.VERSION.SDK_INT>=28){WindowManager.LayoutParams a=getWindow().getAttributes();a.layoutInDisplayCutoutMode=Build.VERSION.SDK_INT>=30?3:1;getWindow().setAttributes(a);}
        PanelStyle.immersive(this);build();navigation=new PanelNavigation(this,() -> finish(),() -> PanelNavigation.panel(this),() -> PanelNavigation.desktop(this));
    }
    private int dp(int n){return PanelStyle.dp(this,n);}
    private TextView label(String value,int size,int color){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(PanelTheme.color(color));t.setGravity(Gravity.CENTER_VERTICAL);return t;}
    private String number(JSONObject obj,String key,String unit){return obj.has(key)&&!obj.isNull(key)?String.format(Locale.US,"%.1f",obj.optDouble(key))+unit:"—";}
    private void build(){
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(16),dp(8),dp(16),dp(8));root.setBackground(PanelStyle.background());
        LinearLayout header=new LinearLayout(this);header.addView(PanelStyle.button(this,"‹ 返回面板",false,v -> finish()),new LinearLayout.LayoutParams(dp(110),dp(40)));
        title=label("存储 / 磁盘",19,PanelStyle.TEXT);title.setPadding(dp(14),0,0,0);header.addView(title,new LinearLayout.LayoutParams(0,dp(40),1));
        header.addView(PanelStyle.button(this,"手势说明",false,v -> PanelNavigation.help(this)),new LinearLayout.LayoutParams(dp(92),dp(40)));header.addView(PanelStyle.button(this,"电脑副屏",false,v -> PanelNavigation.desktop(this)),new LinearLayout.LayoutParams(dp(110),dp(40)));root.addView(header);
        note=label("每秒采样 · 60 秒读写曲线 · 容量约 10 秒更新",11,PanelStyle.MUTED);root.addView(note,new LinearLayout.LayoutParams(-1,dp(27)));
        LinearLayout body=new LinearLayout(this);root.addView(body,new LinearLayout.LayoutParams(-1,0,1));
        ScrollView list=new ScrollView(this);drives=new LinearLayout(this);drives.setOrientation(LinearLayout.VERTICAL);list.addView(drives);body.addView(list,new LinearLayout.LayoutParams(dp(192),-1));
        LinearLayout right=new LinearLayout(this);right.setOrientation(LinearLayout.VERTICAL);LinearLayout.LayoutParams rightLayout=new LinearLayout.LayoutParams(0,-1,1);rightLayout.leftMargin=dp(14);body.addView(right,rightLayout);
        graph=new TrafficGraph();graph.setBackground(PanelStyle.card(this,PanelStyle.ACCENT));right.addView(graph,new LinearLayout.LayoutParams(-1,0,.53f));
        ScrollView detail=new ScrollView(this);metrics=label("读取硬盘数据…",12,PanelStyle.TEXT);metrics.setGravity(Gravity.TOP);metrics.setPadding(dp(10),dp(8),dp(10),0);detail.addView(metrics);right.addView(detail,new LinearLayout.LayoutParams(-1,0,.47f));setContentView(root);
    }
    private void update(JSONArray devices,JSONObject detail){
        if(devices==null||devices.length()==0){note.setText("Windows 磁盘性能计数器暂不可用；未修改系统设置");return;}
        StringBuilder signature=new StringBuilder();for(int i=0;i<devices.length();i++)signature.append(devices.optJSONObject(i).optInt("index")).append(',');
        if(!driveSignature.equals(signature.toString())){
            driveSignature=signature.toString();drives.removeAllViews();
            for(int i=0;i<devices.length();i++){JSONObject d=devices.optJSONObject(i);final int id=d.optInt("index");
                Button b=PanelStyle.button(this,d.optString("name"),false,v -> {selected=id;driveSignature="";});b.setTag(id);b.setGravity(Gravity.LEFT|Gravity.CENTER_VERTICAL);b.setPadding(dp(12),0,dp(12),0);b.setTextSize(11);
                LinearLayout.LayoutParams slot=new LinearLayout.LayoutParams(-1,dp(78));slot.bottomMargin=dp(8);drives.addView(b,slot);
            }
        }
        for(int i=0;i<devices.length();i++){JSONObject d=devices.optJSONObject(i);Button b=(Button)drives.getChildAt(i);b.setText(d.optString("name")+"\n读 "+number(d,"read_mbps","")+" / 写 "+number(d,"write_mbps","")+" MiB/s\n可用 "+number(d,"free_gb"," GiB"));b.setTextColor(PanelTheme.color(d.optInt("index")==selected?PanelStyle.ACCENT:PanelStyle.TEXT));}
        if(detail==null)return;JSONObject d=detail.optJSONObject("metric");if(d==null)return;
        title.setText(d.optString("name")+" · 存储详情");
        StringBuilder text=new StringBuilder();text.append("读取  ").append(number(d,"read_mbps"," MiB/s")).append("       写入  ").append(number(d,"write_mbps"," MiB/s"));
        text.append("\n读延迟  ").append(d.isNull("read_latency_ms")?d.optDouble("read_iops",-1)==0?"本周期无读取":"暂不可用":number(d,"read_latency_ms"," ms"));
        text.append("       写延迟  ").append(d.isNull("write_latency_ms")?d.optDouble("write_iops",-1)==0?"本周期无写入":"暂不可用":number(d,"write_latency_ms"," ms"));
        text.append("\n活动时间  ").append(number(d,"load_percent","%")).append("       排队请求  ").append(number(d,"queue_length",""));
        JSONArray volumes=d.optJSONArray("volumes");if(volumes!=null)for(int i=0;i<volumes.length();i++){JSONObject v=volumes.optJSONObject(i);text.append("\n").append(v.optString("mount")).append("   可用 ").append(number(v,"free_gb"," GiB")).append(" / 总 ").append(number(v,"total_gb"," GiB"));}
        text.append("\n\n延迟为本采样周期已完成 I/O 的平均值，非瞬时最坏延迟。容量仅统计已挂载分区。");String complete=HardwareFields.format(detail);metrics.setText(complete.isEmpty()?text:complete);graph.points=detail.optJSONArray("history");graph.invalidate();
    }
    private final Runnable poll=new Runnable(){public void run(){if(!active)return;worker.execute(() -> {
        try{JSONObject status=PanelConnection.request(StorageActivity.this,"/api/dashboard/status",null);JSONArray disks=status.optJSONObject("host").optJSONArray("disks");
            int target=selected;boolean exists=false;if(disks!=null)for(int i=0;i<disks.length();i++)if(disks.optJSONObject(i).optInt("index")==target)exists=true;
            if(!exists&&disks!=null&&disks.length()>0)target=disks.optJSONObject(0).optInt("index");final int chosen=target;
            JSONObject detail=target<0?null:PanelConnection.request(StorageActivity.this,"/api/dashboard/detail",new JSONObject().put("kind","disk").put("index",target));
            ui.post(() -> {if(active){if(selected<0||!driveExists(disks,selected))selected=chosen;if(selected==chosen)update(disks,detail);}});
        }catch(Exception e){ui.post(() -> {if(active)note.setText("磁盘数据暂不可用："+e.getMessage());});}
        finally{ui.post(() -> {if(active)ui.postDelayed(poll,1000);});}
    });}};
    private boolean driveExists(JSONArray disks,int id){if(disks==null)return false;for(int i=0;i<disks.length();i++)if(disks.optJSONObject(i).optInt("index")==id)return true;return false;}
    private final class TrafficGraph extends View{
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);JSONArray points;
        TrafficGraph(){super(StorageActivity.this);}
        @Override protected void onDraw(Canvas c){super.onDraw(c);if(points==null)return;float max=1;
            for(int i=0;i<points.length();i++){JSONObject p=points.optJSONObject(i);max=Math.max(max,(float)Math.max(p.optDouble("read_mbps",0),p.optDouble("write_mbps",0))*1.15f);}
            float left=dp(44),right=getWidth()-dp(12),top=dp(31),bottom=getHeight()-dp(25);
            paint.setColor(PanelTheme.color(0xffdde3ec));paint.setStrokeWidth(dp(1));for(int i=0;i<=4;i++){float y=top+(bottom-top)*i/4;c.drawLine(left,y,right,y,paint);}for(int i=0;i<=6;i++){float x=left+(right-left)*i/6;c.drawLine(x,top,x,bottom,paint);}
            paint.setColor(PanelTheme.color(PanelStyle.MUTED));paint.setTextSize(dp(9));c.drawText(String.format(Locale.US,"%.1f",max),dp(6),top+dp(3),paint);c.drawText("MiB/s",dp(4),top+dp(16),paint);c.drawText("60 秒",left,bottom+dp(17),paint);c.drawText("现在",right-dp(23),bottom+dp(17),paint);
            String[] keys={"read_mbps","write_mbps"};int[] colors={0xff5277bb,0xffa97a47};String[] labels={"读取","写入"};
            for(int k=0;k<2;k++){Path path=new Path();boolean started=false;for(int i=0;i<points.length();i++){JSONObject p=points.optJSONObject(i);if(p==null||p.isNull(keys[k])||!p.has(keys[k])){started=false;continue;}float x=right-(59-(60-points.length()+i))*(right-left)/59;float y=bottom-(bottom-top)*(float)p.optDouble(keys[k])/max;if(!started){path.moveTo(x,y);started=true;}else path.lineTo(x,y);}paint.setColor(PanelTheme.color(colors[k]));paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(2));c.drawPath(path,paint);paint.setStyle(Paint.Style.FILL);paint.setTextSize(dp(11));c.drawText("● "+labels[k],left+k*dp(70),dp(20),paint);}
        }
    }
    @Override public boolean dispatchTouchEvent(MotionEvent e){if(navigation!=null&&navigation.touch(e,event -> super.dispatchTouchEvent(event)))return true;return super.dispatchTouchEvent(e);}
    @Override protected void onResume(){super.onResume();if(PanelTheme.refresh(this))return;active=true;ui.removeCallbacks(poll);ui.post(poll);}
    @Override protected void onPause(){active=false;ui.removeCallbacks(poll);super.onPause();}
    @Override public void onWindowFocusChanged(boolean focus){super.onWindowFocusChanged(focus);if(focus)PanelStyle.immersive(this);}
    @Override protected void onDestroy(){active=false;ui.removeCallbacksAndMessages(null);worker.shutdownNow();super.onDestroy();}
}
