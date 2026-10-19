package com.phonebridge.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Handler;
import android.widget.Button;
import android.widget.Toast;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

/** Current playback endpoint only; no microphone or global media keys. */
final class PanelPlayback {
    private final Activity activity;
    private final Handler ui=new Handler();
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private JSONObject state=new JSONObject();
    private final Button device,mute;
    private boolean pending,closed;
    private VolumeLayout hud;private boolean previewing;private int gestureBase;private String gestureDevice="";
    PanelPlayback(Activity activity,Button device,Button mute) {
        this.activity=activity;this.device=device;this.mute=mute;
        device.setOnClickListener(v -> choose());mute.setOnClickListener(v -> send("mute",!state.optBoolean("muted"),state.optString("default_id")));
        update(state);
    }
    void attach(VolumeLayout layout){hud=layout;layout.attach(this);}
    private void feedback(String text,boolean hold,int value){if(hud!=null)hud.showVolume(value,state.optBoolean("muted"),text,hold);}
    void beginGesture(){gestureBase=(int)Math.round(state.optDouble("volume_percent",0));gestureDevice=state.optString("default_id");}
    void preview(int delta){if(pending||!state.optBoolean("available"))return;previewing=true;feedback("预览",true,gestureBase+delta);}
    void cancelGesture(){previewing=false;feedback("音量",false,(int)Math.round(state.optDouble("volume_percent",0)));}
    void update(JSONObject data) {
        int old=(int)Math.round(state.optDouble("volume_percent",-1));boolean oldMuted=state.optBoolean("muted");
        if(data!=null)state=data;
        String name=state.optString("default_name","播放设备");
        name=name.replaceFirst("^(扬声器|耳机|耳机式耳麦|Speakers|Speaker)\\s*[（(](.*)[）)]$","$2");
        String volume=state.isNull("volume_percent") ? "—" : String.format(Locale.US,"%.0f%%",state.optDouble("volume_percent"));
        device.setMaxLines(1);device.setEllipsize(android.text.TextUtils.TruncateAt.END);
        device.setText(name+" · "+volume+" ▾");mute.setText(state.optBoolean("muted")?"取消静音":"静音");
        boolean available=state.optBoolean("available");device.setEnabled(available&&!pending);mute.setEnabled(available&&!pending);
        if(data!=null&&available&&old>=0&&!previewing&&!pending&&(old!=(int)Math.round(state.optDouble("volume_percent"))||oldMuted!=state.optBoolean("muted")))feedback("音量",false,(int)Math.round(state.optDouble("volume_percent")));
    }
    void delta(int percent) {
        previewing=false;
        if(pending || !state.optBoolean("available") || percent==0){cancelGesture();return;}
        if(!gestureDevice.equals(state.optString("default_id"))){cancelGesture();return;}
        feedback("设置中",true,gestureBase+percent);
        send("delta",Math.max(-15,Math.min(15,percent)),gestureDevice);
    }
    private void choose() {
        JSONArray items=state.optJSONArray("devices");if(items==null||items.length()==0)return;
        String[] names=new String[items.length()],ids=new String[items.length()];int selected=-1;
        for(int i=0;i<items.length();i++) {
            JSONObject item=items.optJSONObject(i);names[i]=item.optString("name");ids[i]=item.optString("id");
            if(item.optBoolean("default"))selected=i;
        }
        new AlertDialog.Builder(activity).setTitle("电脑播放设备 · 不更改通话设备")
            .setSingleChoiceItems(names,selected,(dialog,which) -> {dialog.dismiss();send("device",null,ids[which]);})
            .setNegativeButton("取消",null).show();
    }
    private void send(String action,Object value,String id) {
        if(pending||closed)return;pending=true;update(null);
        worker.execute(() -> {
            try {
                JSONObject body=new JSONObject().put("action",action).put("device_id",id);
                if(value!=null)body.put("value",value);
                JSONObject result=PanelConnection.request(activity,"/api/playback/control",body);
                ui.post(() -> {
                    if(closed)return;pending=false;update(result.optJSONObject("playback"));
                    feedback("音量",false,(int)Math.round(state.optDouble("volume_percent")));
                });
            } catch(Exception error) {
                ui.post(() -> {if(closed)return;pending=false;update(null);cancelGesture();Toast.makeText(activity,"未完成："+error.getMessage(),Toast.LENGTH_LONG).show();});
            }
        });
    }
    void close(){closed=true;worker.shutdownNow();ui.removeCallbacksAndMessages(null);}
}
