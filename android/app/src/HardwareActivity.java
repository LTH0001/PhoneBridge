package com.phonebridge.app;
import android.app.Activity;
import android.os.*;
import android.content.Intent;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.util.*;
import java.util.concurrent.*;

/** Complete adapter catalog, including additional GPUs, network adapters and NPU. */
public final class HardwareActivity extends Activity {
    private final Handler ui=new Handler();private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private boolean active;private LinearLayout list;private TextView note;private String signature="";
    private final Map<String,Button> buttons=new LinkedHashMap<>();
    @Override public void onCreate(Bundle state){super.onCreate(state);PanelTheme.apply(this);PanelStyle.immersive(this);
        LinearLayout root=new LinearLayout(this);root.setOrientation(1);root.setPadding(dp(16),dp(8),dp(16),dp(8));root.setBackground(PanelStyle.background());
        LinearLayout header=new LinearLayout(this);header.addView(PanelStyle.button(this,"‹ 返回面板",false,v -> finish()),new LinearLayout.LayoutParams(dp(110),dp(40)));
        TextView title=new TextView(this);title.setText("全部硬件 / 详细档案");title.setTextSize(19);title.setTextColor(PanelTheme.text());title.setGravity(Gravity.CENTER_VERTICAL);header.addView(title,new LinearLayout.LayoutParams(0,dp(40),1));root.addView(header);
        note=new TextView(this);note.setText("只读查询 · 保留不可用字段并注明原因 · 不扫描网络设备");note.setTextColor(PanelTheme.muted());note.setTextSize(11);root.addView(note);
        ScrollView scroll=new ScrollView(this);list=new LinearLayout(this);list.setOrientation(1);scroll.addView(list);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
    }
    private int dp(int n){return PanelStyle.dp(this,n);}
    private void open(String kind,int index){Intent intent=new Intent(this,DetailActivity.class).putExtra("kind",kind).putExtra("index",index);startActivity(intent);}
    private void update(JSONObject host){
        ArrayList<String[]> entries=new ArrayList<>();entries.add(new String[]{"cpu","0","CPU · "+host.optJSONObject("cpu").optString("name","处理器")});entries.add(new String[]{"memory","0","内存 · 提交量 / 分页池 / 内存条"});
        for(String[] group:new String[][]{{"gpus","gpu","GPU"},{"disks","disk","磁盘"},{"networks","network","网络"},{"npus","npu","NPU"}}){JSONArray devices=host.optJSONArray(group[0]);if(devices!=null)for(int i=0;i<devices.length();i++){JSONObject d=devices.optJSONObject(i);if(d!=null)entries.add(new String[]{group[1],String.valueOf(d.optInt("index")),group[2]+" "+d.optInt("index")+" · "+d.optString("name",d.optString("model","设备"))});}}
        StringBuilder shape=new StringBuilder();for(String[] entry:entries)shape.append(Arrays.toString(entry));if(shape.toString().equals(signature))return;signature=shape.toString();list.removeAllViews();buttons.clear();
        for(String[] entry:entries){final String kind=entry[0];final int index=Integer.parseInt(entry[1]);Button button=PanelStyle.button(this,entry[2],false,v -> open(kind,index));button.setGravity(Gravity.LEFT|Gravity.CENTER_VERTICAL);LinearLayout.LayoutParams slot=new LinearLayout.LayoutParams(-1,dp(48));slot.topMargin=dp(8);list.addView(button,slot);buttons.put(kind+index,button);}
    }
    private final Runnable poll=new Runnable(){public void run(){if(!active)return;worker.execute(() -> {try{JSONObject host=PanelConnection.request(HardwareActivity.this,"/api/dashboard/status",null).getJSONObject("host");ui.post(() -> {if(active)update(host);});}catch(Exception e){ui.post(() -> note.setText(PanelRoute.errorMessage(e)));}finally{ui.post(() -> {if(active)ui.postDelayed(poll,2000);});}});}};
    @Override protected void onResume(){super.onResume();if(PanelTheme.refresh(this))return;active=true;ui.post(poll);}
    @Override protected void onPause(){active=false;ui.removeCallbacksAndMessages(null);super.onPause();}
    @Override protected void onDestroy(){worker.shutdownNow();super.onDestroy();}
    @Override public void onWindowFocusChanged(boolean focus){super.onWindowFocusChanged(focus);if(focus)PanelStyle.immersive(this);}
}
