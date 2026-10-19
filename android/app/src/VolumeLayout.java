package com.phonebridge.app;

import android.content.Context;
import android.graphics.Rect;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.SeekBar;

/** Up/down gestures commit once on release. Buttons retain normal taps. */
final class VolumeLayout extends LinearLayout {
    interface Adjust { void apply(int delta); }
    private final Adjust adjust;
    private final boolean gestures;
    private float startX,startY;
    private boolean blocked,sliding;
    private PanelPlayback playback;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private int volume;private boolean muted;private String message="";
    private float hudAlpha;private long fadeStart;private boolean holding;
    private final Runnable hide=() -> {holding=false;fadeStart=android.os.SystemClock.uptimeMillis();postInvalidateOnAnimation();};
    VolumeLayout(Context context,boolean gestures,Adjust adjust) {
        super(context);this.gestures=gestures;this.adjust=adjust;setOrientation(VERTICAL);
    }
    void attach(PanelPlayback value){playback=value;}
    void showVolume(int value,boolean mute,String label,boolean hold) {
        volume=Math.max(0,Math.min(100,value));muted=mute;message=label;holding=hold;hudAlpha=1;fadeStart=0;
        removeCallbacks(hide);if(!hold)postDelayed(hide,1400);postInvalidateOnAnimation();
    }
    private int delta(MotionEvent event){return Math.max(-15,Math.min(15,Math.round((startY-event.getY())/getResources().getDisplayMetrics().density/8)));}
    private boolean interactive(View view,int x,int y) {
        Rect rectangle=new Rect();if(!view.getGlobalVisibleRect(rectangle)||!rectangle.contains(x,y))return false;
        if(view instanceof Button || view instanceof SeekBar)return true;
        if(view instanceof ViewGroup) {
            ViewGroup group=(ViewGroup)view;
            for(int i=0;i<group.getChildCount();i++)if(interactive(group.getChildAt(i),x,y))return true;
        }
        return false;
    }
    @Override public boolean onInterceptTouchEvent(MotionEvent event) {
        if(!gestures)return false;
        if(event.getActionMasked()==MotionEvent.ACTION_DOWN) {
            startX=event.getX();startY=event.getY();sliding=false;
            blocked=interactive(this,(int)event.getRawX(),(int)event.getRawY());
            if(playback!=null)playback.beginGesture();
        }
        if(event.getPointerCount()>1){if(sliding&&playback!=null)playback.cancelGesture();blocked=true;sliding=false;return false;}
        float dy=Math.abs(event.getY()-startY),dx=Math.abs(event.getX()-startX);
        if(event.getActionMasked()==MotionEvent.ACTION_MOVE && !blocked && dy>36*getResources().getDisplayMetrics().density && dy>dx*1.5f)sliding=true;
        return sliding;
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        if(!gestures||blocked)return super.onTouchEvent(event);
        if(event.getActionMasked()==MotionEvent.ACTION_DOWN){startX=event.getX();startY=event.getY();sliding=false;if(playback!=null)playback.beginGesture();}
        if(event.getActionMasked()==MotionEvent.ACTION_MOVE && Math.abs(event.getY()-startY)>36*getResources().getDisplayMetrics().density && Math.abs(event.getY()-startY)>Math.abs(event.getX()-startX)*1.5f)sliding=true;
        if(event.getPointerCount()>1){sliding=false;if(playback!=null)playback.cancelGesture();return true;}
        if(event.getActionMasked()==MotionEvent.ACTION_MOVE && sliding && playback!=null)playback.preview(delta(event));
        if(event.getActionMasked()==MotionEvent.ACTION_UP) {
            float dy=startY-event.getY();
            if(Math.abs(dy)>36*getResources().getDisplayMetrics().density && Math.abs(dy)>Math.abs(event.getX()-startX)*1.5f)
                adjust.apply(delta(event));
            else if(playback!=null)playback.cancelGesture();
            sliding=false;
        }
        if(event.getActionMasked()==MotionEvent.ACTION_CANCEL){sliding=false;if(playback!=null)playback.cancelGesture();}
        return true;
    }
    @Override protected void dispatchDraw(Canvas canvas) {
        super.dispatchDraw(canvas);if(hudAlpha<=0)return;
        if(fadeStart>0){hudAlpha=Math.max(0,1-(android.os.SystemClock.uptimeMillis()-fadeStart)/220f);if(hudAlpha<=0)return;}
        float d=getResources().getDisplayMetrics().density,w=48*d,h=190*d;
        float x=getWidth()-w-12*d,y=(getHeight()-h)/2;
        paint.setColor(0xfaffffff);paint.setAlpha((int)(235*hudAlpha));canvas.drawRoundRect(new RectF(x,y,x+w,y+h),24*d,24*d,paint);
        float top=y+28*d,bottom=y+h-48*d,left=x+17*d,right=x+w-17*d;
        paint.setColor(0xffdce4ef);paint.setAlpha((int)(255*hudAlpha));canvas.drawRoundRect(new RectF(left,top,right,bottom),7*d,7*d,paint);
        paint.setColor(muted?0xff647082:0xff376bc1);paint.setAlpha((int)(255*hudAlpha));canvas.drawRoundRect(new RectF(left,bottom-(bottom-top)*volume/100f,right,bottom),7*d,7*d,paint);
        paint.setTextAlign(Paint.Align.CENTER);paint.setTextSize(12*d);paint.setColor(0xff252c38);paint.setAlpha((int)(255*hudAlpha));
        canvas.drawText(volume+"%",x+w/2,y+h-28*d,paint);paint.setTextSize(9*d);canvas.drawText(muted?"已静音":message,x+w/2,y+h-12*d,paint);
        if(fadeStart>0)postInvalidateOnAnimation();
    }
    @Override protected void onDetachedFromWindow(){removeCallbacks(hide);super.onDetachedFromWindow();}
}
