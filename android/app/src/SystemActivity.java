package com.phonebridge.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.util.Locale;
import java.util.concurrent.*;

/** Local OS/kernel metadata and paged read-only process snapshots. */
public final class SystemActivity extends Activity {
    private final Handler ui=new Handler();private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private PanelNavigation navigation;private boolean active,busy;private int page,total;
    private String query="",sort="memory";private TextView system,status,pageLabel;private EditText search;
    private LinearLayout rows;private Button prev,next,sorting;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);PanelTheme.apply(this);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_FULLSCREEN);
        if(Build.VERSION.SDK_INT>=28){WindowManager.LayoutParams a=getWindow().getAttributes();a.layoutInDisplayCutoutMode=Build.VERSION.SDK_INT>=30?3:1;getWindow().setAttributes(a);}
        immersive();build();navigation=new PanelNavigation(this,() -> finish(),() -> PanelNavigation.panel(this),() -> PanelNavigation.desktop(this));
    }
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private TextView text(String value,int size,int color){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(PanelTheme.color(color));t.setGravity(Gravity.CENTER_VERTICAL);return t;}
    private Button button(String label,View.OnClickListener action){return PanelStyle.button(this,label,false,action);}
    private void build(){
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(16),dp(8),dp(16),dp(8));root.setBackground(PanelStyle.background());
        LinearLayout header=new LinearLayout(this);header.addView(button("‹ 返回面板",v -> finish()),new LinearLayout.LayoutParams(dp(110),dp(40)));
        TextView title=text("系统 / 内核 / PID",19,0xff252c38);title.setPadding(dp(14),0,0,0);header.addView(title,new LinearLayout.LayoutParams(0,dp(40),1));
        header.addView(button("手势说明",v -> PanelNavigation.help(this)),new LinearLayout.LayoutParams(dp(92),dp(40)));
        header.addView(button("电脑副屏",v -> PanelNavigation.desktop(this)),new LinearLayout.LayoutParams(dp(110),dp(40)));root.addView(header);
        status=text("仅本机只读 · 不提权，不结束进程，不读取命令行或内核内存",11,0xff647082);root.addView(status,new LinearLayout.LayoutParams(-1,dp(27)));
        LinearLayout body=new LinearLayout(this);root.addView(body,new LinearLayout.LayoutParams(-1,0,1));
        ScrollView osScroll=new ScrollView(this);system=text("读取系统信息…",13,0xff465468);system.setGravity(Gravity.TOP);system.setPadding(0,dp(10),dp(12),0);osScroll.addView(system);body.addView(osScroll,new LinearLayout.LayoutParams(0,-1,.35f));
        LinearLayout right=new LinearLayout(this);right.setOrientation(LinearLayout.VERTICAL);body.addView(right,new LinearLayout.LayoutParams(0,-1,.65f));
        LinearLayout filters=new LinearLayout(this);search=new EditText(this);search.setSingleLine(true);search.setTextSize(12);search.setTextColor(PanelTheme.color(0xff252c38));search.setHintTextColor(PanelTheme.color(0xff647082));search.setHint("进程名称或 PID");search.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(80)});
        filters.addView(search,new LinearLayout.LayoutParams(0,dp(38),1));filters.addView(button("搜索",v -> {query=search.getText().toString().trim();page=0;refresh();((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(search.getWindowToken(),0);}),new LinearLayout.LayoutParams(dp(58),dp(38)));
        sorting=button("内存排序",v -> {sort=sort.equals("memory")?"cpu":sort.equals("cpu")?"pid":"memory";sorting.setText(sort.equals("memory")?"内存排序":sort.equals("cpu")?"CPU 排序":"PID 排序");page=0;refresh();});filters.addView(sorting,new LinearLayout.LayoutParams(dp(88),dp(38)));right.addView(filters);
        right.addView(row("进程名称","PID","CPU","内存 MiB",null),new LinearLayout.LayoutParams(-1,dp(32)));
        ScrollView list=new ScrollView(this);rows=new LinearLayout(this);rows.setOrientation(LinearLayout.VERTICAL);list.addView(rows);right.addView(list,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout pages=new LinearLayout(this);prev=button("上一页",v -> {if(page>0){page--;refresh();}});next=button("下一页",v -> {if((page+1)*40<total){page++;refresh();}});pageLabel=text("",11,0xff647082);pageLabel.setGravity(Gravity.CENTER);
        pages.addView(prev,new LinearLayout.LayoutParams(dp(78),dp(34)));pages.addView(pageLabel,new LinearLayout.LayoutParams(0,dp(34),1));pages.addView(next,new LinearLayout.LayoutParams(dp(78),dp(34)));right.addView(pages);setContentView(root);
    }
    private LinearLayout row(String name,String pid,String cpu,String memory,JSONObject process){
        LinearLayout line=new LinearLayout(this);line.setPadding(dp(4),0,dp(4),0);
        TextView n=text(name,12,0xff252c38);n.setMaxLines(1);n.setEllipsize(android.text.TextUtils.TruncateAt.END);line.addView(n,new LinearLayout.LayoutParams(0,-1,1));
        String[] values={pid,cpu,memory};int[] sizes={62,60,82};
        for(int i=0;i<3;i++){TextView t=text(values[i],11,i==1?0xff376bc1:0xffb2c3d8);t.setGravity(Gravity.CENTER_VERTICAL|Gravity.RIGHT);line.addView(t,new LinearLayout.LayoutParams(dp(sizes[i]),-1));}
        if(process!=null)line.setOnClickListener(v -> details(process));return line;
    }
    private String metric(JSONObject p,String key,String suffix){return p.isNull(key)||!p.has(key)?"—":String.format(Locale.US,"%.1f",p.optDouble(key))+suffix;}
    private void details(JSONObject p){
        worker.execute(() -> {try{
            JSONObject detail=PanelConnection.request(this,"/api/system/process",new JSONObject().put("pid",p.optInt("pid")).put("created_at",p.opt("created_at")));
            ui.post(() -> {if(active)showDetails(detail);});
        }catch(Exception error){ui.post(() -> {if(active)Toast.makeText(this,"进程可能已退出或受保护："+error.getMessage(),Toast.LENGTH_LONG).show();});}});
    }
    private void showDetails(JSONObject p){
        String started=p.isNull("created_at")?"不可读":new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss",Locale.getDefault()).format(new java.util.Date((long)(p.optDouble("created_at")*1000)));
        PanelTheme.dialog(this).setTitle(p.optString("name")).setMessage("PID  "+p.optInt("pid")+"\n父 PID  "+(p.isNull("ppid")?"不可读":p.optInt("ppid"))+"\n状态  "+p.optString("status","不可读")+"\n启动时间  "+started+"\n线程数  "+(p.isNull("threads")?"不可读":p.optInt("threads"))+"\n句柄数  "+(p.isNull("handles")?"不可读":p.optInt("handles"))+"\nCPU  "+metric(p,"cpu_percent","%")+"\n工作集  "+metric(p,"memory_mb"," MiB")+"\n\n只读快照；进程可能已退出。此处不能结束或修改进程。")
            .setPositiveButton("返回",null).show();
    }
    private void refresh(){if(!active||busy)return;ui.removeCallbacks(poll);ui.post(poll);}
    private final Runnable poll=new Runnable(){@Override public void run(){
        if(!active||busy)return;busy=true;final String requestedQuery=query,requestedSort=sort;final int requestedPage=page;
        worker.execute(() -> {try{
            JSONObject result=PanelConnection.request(SystemActivity.this,"/api/system/status",new JSONObject().put("query",requestedQuery).put("sort",requestedSort).put("page",requestedPage));
            ui.post(() -> {if(!active||!query.equals(requestedQuery)||!sort.equals(requestedSort)||page!=requestedPage)return;
                JSONObject os=result.optJSONObject("system");if(os!=null){long seconds=os.optLong("uptime_seconds");system.setText("内核   "+os.optString("kernel")+"\n版本   "+os.optString("kernel_version")+"\n架构   "+os.optString("architecture")+"\n逻辑处理器   "+os.optInt("logical_processors")+String.format(Locale.US,"\n运行时间   %d天 %02d:%02d:%02d",seconds/86400,seconds/3600%24,seconds/60%60,seconds%60)+"\n进程数   "+os.optInt("process_count")+"\n\n点击右侧 PID 查看父进程、线程、句柄与状态。\n\n"+os.optString("note"));}
                total=result.optInt("total");pageLabel.setText((page+1)+" / "+Math.max(1,(total+39)/40)+" · "+total+" 项");prev.setEnabled(page>0);next.setEnabled((page+1)*40<total);
                rows.removeAllViews();JSONArray processes=result.optJSONArray("processes");if(processes!=null)for(int i=0;i<processes.length();i++){JSONObject p=processes.optJSONObject(i);if(p!=null)rows.addView(row(p.optString("name"),Integer.toString(p.optInt("pid")),metric(p,"cpu_percent","%"),metric(p,"memory_mb",""),p),new LinearLayout.LayoutParams(-1,dp(32)));}
                status.setText(result.optString("error").isEmpty()?"只读 · 每秒更新 · 点进程查看父 PID / 线程 / 句柄等详情":result.optString("error"));
            });
        }catch(Exception e){ui.post(() -> {if(active)status.setText("系统信息暂不可用："+e.getMessage());});}
        finally{ui.post(() -> {busy=false;if(active)ui.postDelayed(poll,1000);});}});
    }};
    private void immersive(){PanelStyle.immersive(this);}
    @Override public void onWindowFocusChanged(boolean focus){super.onWindowFocusChanged(focus);if(focus)immersive();}
    @Override public boolean dispatchTouchEvent(MotionEvent e){if(navigation!=null&&navigation.touch(e,event -> super.dispatchTouchEvent(event)))return true;return super.dispatchTouchEvent(e);}
    @Override protected void onResume(){super.onResume();if(PanelTheme.refresh(this))return;active=true;ui.removeCallbacks(poll);ui.post(poll);}
    @Override protected void onPause(){active=false;ui.removeCallbacks(poll);super.onPause();}
    @Override protected void onDestroy(){active=false;ui.removeCallbacksAndMessages(null);worker.shutdownNow();super.onDestroy();}
}
