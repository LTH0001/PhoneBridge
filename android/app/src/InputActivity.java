package com.phonebridge.app;
import android.app.Activity;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;

/** Full-area touchpad, explicitly shown NumberPad and shared inline streaming dictation. */
public final class InputActivity extends Activity {
    private final Handler ui=new Handler();private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final ArrayDeque<JSONObject> queue=new ArrayDeque<>();
    private String session="";private boolean busy,active,starting,numberMode,voiceBusy,restoreInput,desktopPending;private int generation;
    private TextView status,padHint;private Button enable,numbers,back,desktop;private TouchpadView pad;private HoldToTalk holdToTalk;private long lastSend;
    private int dp(int n){return HomeStyle.dp(this,n);}
    private Button button(String title,View.OnClickListener click){return HomeStyle.button(this,title,false,click);}
    private TextView text(String title,int size){TextView v=new TextView(this);v.setText(title);v.setTextSize(size);v.setTextColor(HomeStyle.MUTED);return v;}
    @Override public void onCreate(Bundle state){
        super.onCreate(state);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_FULLSCREEN);
        if(Build.VERSION.SDK_INT>=28){WindowManager.LayoutParams attributes=getWindow().getAttributes();attributes.layoutInDisplayCutoutMode=Build.VERSION.SDK_INT>=30?3:1;getWindow().setAttributes(attributes);}
        PanelStyle.immersive(this);PanelConnection.configure(this,getIntent());
        FrameLayout shell=new FrameLayout(this);
        LinearLayout root=new LinearLayout(this);root.setOrientation(1);root.setPadding(dp(18),dp(12),dp(18),dp(12));root.setBackgroundColor(HomeStyle.BG);shell.addView(root,new FrameLayout.LayoutParams(-1,-1));
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);
        TextView title=text("电脑触控板",17);title.setTextColor(HomeStyle.TEXT);header.addView(title,new LinearLayout.LayoutParams(0,dp(30),1));
        status=text("尚未启用电脑键鼠输入",12);status.setPadding(dp(14),0,0,0);header.addView(status,new LinearLayout.LayoutParams(0,-2,1));root.addView(header);
        pad=new TouchpadView(this,this::enqueue);pad.setEnabled(false);
        LinearLayout.LayoutParams area=new LinearLayout.LayoutParams(-1,0,1);area.topMargin=dp(12);area.bottomMargin=dp(8);root.addView(pad,area);
        padHint=text("",11);root.addView(padHint);
        LinearLayout actions=new LinearLayout(this);actions.setGravity(Gravity.CENTER_VERTICAL);actions.setPadding(0,dp(10),0,0);
        enable=button("启用输入",v -> {if(session.isEmpty())enable();else stop();});HomeStyle.primary(enable);
        numbers=button("数字键盘",v -> {if(!session.isEmpty()&&!voiceBusy)setNumberMode(!numberMode);});
        back=button("返回上页",v -> returnPrevious());desktop=button("显示桌面",v -> showDesktop());
        back.setContentDescription("切换到电脑上一个使用的窗口，相当于 Alt+Tab；手机返回请用返回面板");
        Button voice=button("按住说话",null);
        LinearLayout leftControls=new LinearLayout(this),rightControls=new LinearLayout(this);
        actions.addView(leftControls,new LinearLayout.LayoutParams(0,dp(44),1));
        LinearLayout.LayoutParams voiceSlot=new LinearLayout.LayoutParams(dp(138),dp(44));voiceSlot.leftMargin=dp(8);voiceSlot.rightMargin=dp(8);actions.addView(voice,voiceSlot);
        actions.addView(rightControls,new LinearLayout.LayoutParams(0,dp(44),1));
        for(Button control:new Button[]{button("返回面板",v -> finish()),enable,numbers,back,desktop}){
            control.setTextSize(12);control.setMinWidth(0);control.setMinimumWidth(0);control.setMinHeight(0);control.setMinimumHeight(0);control.setStateListAnimator(null);
            LinearLayout.LayoutParams slot=new LinearLayout.LayoutParams(0,dp(44),1);slot.leftMargin=dp(3);slot.rightMargin=dp(3);(control==back||control==desktop?rightControls:leftControls).addView(control,slot);
        }
        voice.setTextSize(13);voice.setMinWidth(0);voice.setMinimumWidth(0);voice.setStateListAnimator(null);
        root.addView(actions);
        holdToTalk=new HoldToTalk(this,voice,shell,this::suspendForVoice,this::resumeAfterVoice);
        setNumberMode(false);enabled(false);setContentView(shell);
    }
    private void setNumberMode(boolean value){
        numberMode=value;pad.numberMode(value);numbers.setText(value?"收起数字键盘":"数字键盘");
        if(!session.isEmpty())status.setText(value?"已启用 · 数字键盘":"已启用 · 触控板");
        padHint.setText(value?"点按数字输入 · 回车可能发送消息 · 数字区可随时收起":"单指移动 · 双指滚动 · 长按拖动 · 三指上滑桌面 / 下滑返回 · 按住说话");
    }
    private void enabled(boolean value){
        if(!value)setNumberMode(false);
        pad.setEnabled(value&&!voiceBusy);enable.setText(value?"停用输入":"启用输入");
        enable.setEnabled(!voiceBusy);numbers.setEnabled(value&&!voiceBusy);refreshNavigation();
        status.setText(value?(numberMode?"已启用 · 数字键盘":"已启用 · 触控板"):"尚未启用电脑键鼠输入");
    }
    private void suspendForVoice(){restoreInput=!session.isEmpty();voiceBusy=true;stop();status.setText("语音输入中 · 触控板暂时停用");}
    private void resumeAfterVoice(){boolean restore=restoreInput;restoreInput=false;voiceBusy=false;enabled(!session.isEmpty());if(active&&restore)enable();}
    private void enable(){
        if(starting||voiceBusy||!active)return;starting=true;final int expected=generation;
        worker.execute(() -> {try{
            JSONObject result=PanelConnection.request(this,"/api/input/begin",new JSONObject().put("confirmed",true));String key=result.getString("session");
            ui.post(() -> {starting=false;if(active&&!voiceBusy&&generation==expected){session=key;enabled(true);}else if(!worker.isShutdown())worker.execute(() -> end(key));});
        }catch(Exception error){ui.post(() -> {starting=false;status.setText("启用失败："+error.getMessage());});}});
    }
    private void end(String key){try{PanelConnection.request(this,"/api/input/end",new JSONObject().put("session",key));}catch(Exception ignored){}}
    private void stop(){
        generation++;pad.release();String old=session;session="";queue.clear();enabled(false);
        if(!old.isEmpty()&&!worker.isShutdown())worker.execute(() -> end(old));
    }
    private void enqueue(JSONObject event){
        if(event.optString("kind").equals("navigation")){if(event.optString("action").equals("back"))returnPrevious();else if(event.optString("action").equals("desktop"))showDesktop();return;}
        if(session.isEmpty()||voiceBusy){status.setText("请先启用输入");return;}
        if(queue.size()>100){stop();status.setText("输入积压，已安全停用，请重新启用");return;}
        JSONObject last=queue.peekLast();String kind=event.optString("kind");
        if(last!=null&&(kind.equals("move")||kind.equals("scroll"))&&kind.equals(last.optString("kind"))){
            try{if(kind.equals("move"))last.put("dx",Math.max(-900,Math.min(900,last.optDouble("dx")+event.optDouble("dx"))));last.put("dy",Math.max(-900,Math.min(900,last.optDouble("dy")+event.optDouble("dy"))));}catch(Exception ignored){}
        }else queue.add(event);
    }
    private void refreshNavigation(){back.setEnabled(!voiceBusy&&!desktopPending);desktop.setEnabled(!voiceBusy&&!desktopPending);}
    private void returnLocal(){if(numberMode){setNumberMode(false);return;}finish();}
    private void returnPrevious(){windowCommand("previous");}
    private void showDesktop(){windowCommand("desktop");}
    private void windowCommand(String action){
        if(!active||voiceBusy||desktopPending)return;
        final boolean previous=action.equals("previous");
        desktopPending=true;refreshNavigation();status.setText(previous?"正在切回电脑上一窗口…":"正在显示电脑桌面…");
        worker.execute(() -> {try{
            PanelConnection.request(this,"/api/input/"+action,new JSONObject().put("confirmed",true));
            ui.post(() -> {if(active)status.setText(previous?"已发送切换上一窗口指令":"已发送显示电脑桌面指令");});
        }catch(Exception error){ui.post(() -> {if(active)status.setText("电脑窗口操作失败："+error.getMessage());});}
        finally{ui.post(() -> {desktopPending=false;if(active)refreshNavigation();});}});
    }
    private final Runnable tick=new Runnable(){public void run(){
        if(!active)return;
        if(!session.isEmpty()&&!voiceBusy&&!busy&&(!queue.isEmpty()||SystemClock.elapsedRealtime()-lastSend>500)){
            JSONArray events=new JSONArray();while(!queue.isEmpty()&&events.length()<32)events.put(queue.removeFirst());
            final String key=session;busy=true;lastSend=SystemClock.elapsedRealtime();
            worker.execute(() -> {try{PanelConnection.request(InputActivity.this,"/api/input/events",new JSONObject().put("session",key).put("events",events));}
                catch(Exception error){ui.post(() -> {if(session.equals(key)){stop();status.setText("连接中断，输入已停用");}});}
                finally{ui.post(() -> busy=false);}});
        }
        ui.postDelayed(this,30);
    }};
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){super.onRequestPermissionsResult(request,permissions,results);if(request==HoldToTalk.PERMISSION)holdToTalk.permissionResult(results.length>0&&results[0]==android.content.pm.PackageManager.PERMISSION_GRANTED);}
    @Override public void onWindowFocusChanged(boolean focus){super.onWindowFocusChanged(focus);if(focus)PanelStyle.immersive(this);}
    @Override public void onBackPressed(){returnLocal();}
    @Override protected void onResume(){super.onResume();active=true;holdToTalk.resume();refreshNavigation();ui.removeCallbacks(tick);ui.post(tick);}
    @Override protected void onPause(){active=false;restoreInput=false;holdToTalk.pause();stop();ui.removeCallbacks(tick);super.onPause();}
    @Override protected void onDestroy(){holdToTalk.close();ui.removeCallbacksAndMessages(null);worker.shutdown();super.onDestroy();}
}
