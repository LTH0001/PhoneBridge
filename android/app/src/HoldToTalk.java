package com.phonebridge.app;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.media.*;
import android.os.Handler;
import android.view.*;
import android.widget.*;
import java.io.ByteArrayOutputStream;
import java.util.concurrent.*;
import org.json.JSONObject;

/** Streaming dictation: bounded PCM queue, append-only PC typing, no page navigation. */
final class HoldToTalk {
    static final int PERMISSION=74;
    private final Activity activity;private final Button button;private final TextView overlay;
    private final Runnable beforeStart,afterComplete;private float stopDistance=60;
    private final Handler ui=new Handler();private final ExecutorService worker=Executors.newFixedThreadPool(2);
    private volatile boolean active,busy,closed;private boolean pressed,ignoreTouch;private float startX,startY;
    private volatile Job current;
    private static final class Job {volatile boolean held=true,cancelled,captureDone,submit;volatile String error="";final ArrayBlockingQueue<byte[]> chunks=new ArrayBlockingQueue<>(8);}
    HoldToTalk(Activity activity,Button button,FrameLayout host){
        this(activity,button,host,() -> {},() -> {});
    }
    HoldToTalk(Activity activity,Button button,FrameLayout host,Runnable beforeStart,Runnable afterComplete){
        this.activity=activity;this.button=button;this.beforeStart=beforeStart;this.afterComplete=afterComplete;
        overlay=new TextView(activity);overlay.setTextSize(17);overlay.setTextColor(HomeStyle.TEXT);
        overlay.setGravity(Gravity.CENTER);overlay.setPadding(dp(24),dp(18),dp(24),dp(18));
        overlay.setBackground(PanelStyle.card(activity,HomeStyle.ACCENT));overlay.setElevation(dp(10));overlay.setVisibility(View.GONE);
        FrameLayout.LayoutParams slot=new FrameLayout.LayoutParams(-2,-2,Gravity.CENTER);slot.leftMargin=dp(24);slot.rightMargin=dp(24);host.addView(overlay,slot);
        button.setText("按住说话");button.setContentDescription("按住说话，边说边输入电脑；下滑停止，右滑确认并按一次回车，聊天窗口可能发送消息");
        button.setOnClickListener(v -> message("按住说话 · ↓ 下滑停止 · → 右滑回车\n请先选中电脑文本框；右滑在聊天窗口可能发送消息"));
        button.setOnTouchListener((view,event) -> touch(event));
    }
    private int dp(int value){return HomeStyle.dp(activity,value);}
    private void message(String value){overlay.setText(value);overlay.setVisibility(View.VISIBLE);ui.removeCallbacks(hide);ui.postDelayed(hide,2400);}
    private final Runnable hide=() -> hideOverlay();
    private void hideOverlay(){if(!pressed&&!busy)overlay.setVisibility(View.GONE);}
    private final Runnable begin=() -> start();
    boolean ownsGesture(){return pressed||ignoreTouch;}
    private boolean touch(MotionEvent event){
        if(ignoreTouch){if(event.getActionMasked()==MotionEvent.ACTION_UP||event.getActionMasked()==MotionEvent.ACTION_CANCEL)ignoreTouch=false;return true;}
        switch(event.getActionMasked()){
            case MotionEvent.ACTION_DOWN:
                if(busy){ignoreTouch=true;message("正在识别上一段语音，请稍候");return true;}
                if(!active||closed)return true;
                pressed=true;startX=event.getRawX();startY=event.getRawY();button.setPressed(true);
                View decor=activity.getWindow().getDecorView();int[] location=new int[2];decor.getLocationOnScreen(location);
                float room=(location[1]+decor.getHeight()-startY)/activity.getResources().getDisplayMetrics().density;
                stopDistance=Math.max(12,Math.min(60,room*.55f));
                button.getParent().requestDisallowInterceptTouchEvent(true);ui.postDelayed(begin,200);return true;
            case MotionEvent.ACTION_MOVE:
                if(pressed){String action=VoiceGesture.classify(event.getRawX()-startX,event.getRawY()-startY,activity.getResources().getDisplayMetrics().density,stopDistance);
                    if(!action.isEmpty()){
                        boolean started=current!=null,stop=action.equals("stop");
                        if(started&&!stop)current.submit=true;
                        finish(stop);ignoreTouch=true;
                        button.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS);
                        if(started){overlay.setText(stop?"已停止后续输入\n已输入文字保留":"正在补齐语音尾段并回车…\n聊天窗口可能直接发送消息");overlay.setVisibility(View.VISIBLE);}
                        else message("尚未开始录音，请先按住说话");
                    }}
                return true;
            case MotionEvent.ACTION_POINTER_DOWN:finish(true);ignoreTouch=true;return true;
            case MotionEvent.ACTION_CANCEL:finish(true);return true;
            case MotionEvent.ACTION_UP:
                boolean quick=pressed&&current==null;finish(false);
                if(quick&&!busy)message("请按住说话 · ↓ 下滑停止 · → 右滑回车");return true;
        }
        return true;
    }
    private void start(){
        if(!pressed||!active||busy||closed)return;
        if(activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){
            finish(true);activity.requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},PERMISSION);return;
        }
        if(BridgeService.instance!=null){JSONObject mic=BridgeService.instance.statusJson().optJSONObject("microphone");
            if(mic!=null&&mic.optBoolean("running")){finish(true);message("请先停止手机麦克风串流，再按住说话");return;}}
        beforeStart.run();Job job=new Job();current=job;busy=true;ui.removeCallbacks(hide);
        button.setText("正在听…");overlay.setText("边说边输入…\n↓ 下滑停止 · → 右滑回车 · 松开仅结束");overlay.setVisibility(View.VISIBLE);
        worker.execute(() -> capture(job));
    }
    private void finish(boolean cancel){
        ui.removeCallbacks(begin);pressed=false;button.setPressed(false);button.getParent().requestDisallowInterceptTouchEvent(false);
        Job job=current;if(job!=null){job.cancelled|=cancel;job.held=false;button.setText(cancel?"已停止":"收尾中…");}
        else button.setText("按住说话");
    }
    private boolean usable(Job job){return active&&!closed&&!job.cancelled&&current==job;}
    private void capture(Job job){
        AudioRecord audio=null;boolean sending=false;
        try{
            if(!usable(job)||!job.held)return;
            int minimum=AudioRecord.getMinBufferSize(16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT);
            if(minimum<=0)throw new IllegalStateException("手机不支持此录音格式");
            audio=new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(minimum,64000));
            if(audio.getState()!=AudioRecord.STATE_INITIALIZED)throw new IllegalStateException("麦克风初始化失败");
            if(!usable(job)||!job.held)return;
            audio.startRecording();worker.execute(() -> send(job));sending=true;int total=0;byte[] buffer=new byte[8000];
            while(job.held&&usable(job)&&total<1920000){
                int count=audio.read(buffer,0,Math.min(buffer.length,1920000-total));
                if(count<0)throw new IllegalStateException("录音读取失败");
                if(count>0){total+=count;if(!job.chunks.offer(java.util.Arrays.copyOf(buffer,count)))throw new IllegalStateException("连接延迟过高，已停止，避免输入过时语音");}
            }
            if(total>=1920000){job.held=false;ui.post(() -> {if(current==job)overlay.setText("已达 60 秒上限，正在结束…");});}
        }catch(Exception error){job.error=error.getMessage();job.cancelled=true;}
        finally{
            if(audio!=null){try{audio.stop();}catch(Exception ignored){}audio.release();}
            job.captureDone=true;
            if(!sending)complete(job,job.error.isEmpty()?"已停止，未开始输入":"语音未开始："+job.error);
        }
    }
    private void send(Job job){
        String key="",outcome="已停止后续输入 · 已输入文字保留";int seq=0,characters=0;
        try{
            if(!usable(job))return;
            key=PanelConnection.request(activity,"/api/input/begin",new JSONObject().put("confirmed",true)).getString("session");
            if(!usable(job))return;
            PanelConnection.request(activity,"/api/speech/start",new JSONObject().put("session",key));
            while(usable(job)){
                byte[] bytes=job.chunks.poll(150,TimeUnit.MILLISECONDS);
                if(bytes==null){if(job.captureDone)break;continue;}
                JSONObject result=PanelConnection.request(activity,"/api/speech/chunk",new JSONObject().put("session",key).put("seq",seq)
                    .put("pcm",android.util.Base64.encodeToString(bytes,android.util.Base64.NO_WRAP)));
                seq=result.getInt("seq");characters=result.optInt("characters");
            }
            if(!usable(job))return;
            JSONObject result=PanelConnection.request(activity,"/api/speech/finish",new JSONObject().put("session",key).put("seq",seq).put("enter",job.submit));characters=result.optInt("characters");
            if(job.submit&&!result.has("submitted"))throw new IllegalStateException("电脑端需更新到 0.8.5，回车未确认");
            outcome=characters>0?(result.optBoolean("submitted")?"已输入 "+characters+" 字并回车确认":"已输入 "+characters+" 字 · 未按回车"):"未识别到清晰语音，没有输入文字或回车";
        }catch(Exception error){job.cancelled=true;outcome="语音已停止："+error.getMessage()+"；请检查已输入文字，勿重复输入";}
        finally{
            if(!key.isEmpty()&&job.cancelled)try{PanelConnection.request(activity,"/api/speech/finish",new JSONObject().put("session",key).put("seq",seq).put("cancelled",true));}catch(Exception ignored){}
            if(!key.isEmpty())try{PanelConnection.request(activity,"/api/input/end",new JSONObject().put("session",key));}catch(Exception ignored){}
            job.cancelled=true;job.chunks.clear();
            for(int i=0;i<100&&!job.captureDone;i++)try{Thread.sleep(10);}catch(InterruptedException ignored){Thread.currentThread().interrupt();break;}
            complete(job,job.error.isEmpty()?outcome:"语音已停止："+job.error+"；已输入文字保留");
        }
    }
    private void complete(Job job,String result){ui.post(() -> {if(current==job){current=null;busy=false;button.setText("按住说话");if(active&&!closed)message(result);else overlay.setVisibility(View.GONE);if(!closed)afterComplete.run();}});}
    void permissionResult(boolean granted){if(active)message(granted?"麦克风已允许，请再次按住说话":"未允许麦克风，不会录音");}
    void resume(){active=true;}
    void pause(){active=false;Job job=current;if(job!=null)job.cancelled=true;finish(true);ignoreTouch=false;ui.removeCallbacks(hide);overlay.setVisibility(View.GONE);}
    void close(){pause();closed=true;worker.shutdown();}
}
