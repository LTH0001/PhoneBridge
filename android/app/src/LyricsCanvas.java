package com.phonebridge.app;

import android.content.Context;
import android.graphics.*;
import android.os.SystemClock;
import android.view.View;
import org.json.*;
import java.util.Locale;

/** Frame-paced local clock; LRC line timestamps are not word-level karaoke. */
final class LyricsCanvas extends View {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private JSONObject data=new JSONObject();private JSONArray lines=new JSONArray();
    private String key="";private double anchor,duration,rate=1,offset;
    private long received,lastFrame;private boolean playing;
    private float scroll=-1;
    private final boolean compact;
    LyricsCanvas(Context context){this(context,false);}
    LyricsCanvas(Context context,boolean compact){super(context);this.compact=compact;}
    void update(JSONObject value,long transitMs){
        String newKey=value.optString("track_key");
        boolean sameTrack=newKey.equals(key);double estimate=position();boolean wasPlaying=playing;
        if(!newKey.equals(key)){
            key=newKey;scroll=-1;offset=getContext().getSharedPreferences("lyrics_timing",Context.MODE_PRIVATE).getFloat(key,0);
        }
        data=value;lines=value.optJSONArray("lines");if(lines==null)lines=new JSONArray();
        playing=value.optBoolean("playing");rate=value.optDouble("playback_rate",1);duration=value.optDouble("duration_seconds");
        anchor=value.optDouble("position_seconds")+(playing?Math.min(200,transitMs)/2000.0*rate:0);
        if(sameTrack&&wasPlaying&&playing&&Math.abs(anchor-estimate)<.35)anchor=estimate+(anchor-estimate)*.5;
        received=SystemClock.elapsedRealtime();invalidate();
    }
    double offset(){return offset;}
    void shift(double delta,boolean reset){
        offset=reset?0:Math.max(-10,Math.min(10,Math.round((offset+delta)*10)/10.0));
        android.content.SharedPreferences p=getContext().getSharedPreferences("lyrics_timing",Context.MODE_PRIVATE);
        android.content.SharedPreferences.Editor edit=p.edit();
        if(p.getAll().size()>128)edit.clear();
        if(!key.isEmpty())edit.putFloat(key,(float)offset);edit.apply();invalidate();
    }
    private float dp(float v){return v*getResources().getDisplayMetrics().density;}
    private double position(){return Math.max(0,Math.min(duration,anchor+(playing?Math.min(2,(SystemClock.elapsedRealtime()-received)/1000.0)*rate:0)));}
    @Override protected void onDraw(Canvas c){
        super.onDraw(c);double position=position(),time=position+offset;
        paint.setTextAlign(Paint.Align.CENTER);
        long now=SystemClock.uptimeMillis();float elapsed=lastFrame==0?1:(now-lastFrame)/180f;lastFrame=now;
        int current=-1;for(int i=0;i<lines.length();i++){if(lines.optJSONObject(i).optDouble("time")<=time)current=i;else break;}
        int anchorIndex=Math.max(0,current);
        if(scroll<0||Math.abs(scroll-anchorIndex)>2)scroll=anchorIndex;
        else scroll+=(anchorIndex-scroll)*Math.min(1,elapsed);
        if(lines.length()==0){
            paint.setColor(compact?0xff647082:0xff647380);paint.setTextSize(dp(compact?11:17));
            String text="instrumental".equals(data.optString("state"))?"此曲为纯音乐，请欣赏":"loading".equals(data.optString("state"))?"正在寻找这首歌的同步歌词…":"暂无同步歌词，可在电脑导入 LRC";
            if(compact){text="instrumental".equals(data.optString("state"))?"纯音乐 · 静静欣赏":"loading".equals(data.optString("state"))?"正在寻找同步歌词…":"点击进入歌词页 / 导入 LRC";}
            c.drawText(text,getWidth()/2f,getHeight()/2f,paint);
        }else{
            c.save();c.clipRect(0,dp(6),getWidth(),getHeight()-dp(compact?18:34));
            int from=Math.max(0,(int)scroll-3),to=Math.min(lines.length()-1,(int)scroll+4);
            for(int i=from;i<=to;i++){
                float distance=Math.abs(i-scroll);if(distance>3.1f)continue;
                String text=lines.optJSONObject(i).optString("text");boolean selected=i==current;
                paint.setColor(compact?(selected?0xff376bc1:0xff647082):(selected?0xff247dae:0xff62717c));paint.setAlpha((int)(255*Math.max(.15,1-distance*.26)));
                paint.setTypeface(selected?Typeface.create("sans-serif-medium",Typeface.NORMAL):Typeface.create("sans-serif",Typeface.NORMAL));
                paint.setTextSize(dp(compact?(selected?17:12):(selected?24:17)));
                float width=getWidth()-dp(compact?12:120);
                while(paint.getTextSize()>dp(compact?10:13)&&paint.measureText(text)>width)paint.setTextSize(paint.getTextSize()-1);
                while(text.length()>4&&paint.measureText(text)>width)text=text.substring(0,text.length()-2)+"…";
                c.drawText(text,getWidth()/2f,(getHeight()-dp(compact?18:34))/2f+dp(6)+(i-scroll)*dp(compact?26:38),paint);
            }
            c.restore();
        }
        paint.setAlpha(255);paint.setTypeface(Typeface.DEFAULT);paint.setTextSize(dp(10));paint.setColor(0xff6c7d87);
        if(compact){if(isShown()&&(playing||Math.abs(scroll-anchorIndex)>.01))postInvalidateOnAnimation();return;}
        c.drawText(String.format(Locale.US,"%02d:%02d  /  %02d:%02d",(int)position/60,(int)position%60,(int)duration/60,(int)duration%60),getWidth()/2f,getHeight()-dp(4),paint);
        float left=dp(100),right=getWidth()-dp(100),y=getHeight()-dp(21);paint.setStrokeWidth(dp(2));
        paint.setColor(0x22446377);c.drawLine(left,y,right,y,paint);paint.setColor(0xff4b9cc2);
        if(duration>0)c.drawLine(left,y,left+(right-left)*(float)(position/duration),y,paint);
        if(isShown()&&(playing||Math.abs(scroll-anchorIndex)>.01))postInvalidateOnAnimation();
    }
}
