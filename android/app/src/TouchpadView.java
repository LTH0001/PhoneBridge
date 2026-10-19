package com.phonebridge.app;
import android.content.Context;
import android.graphics.*;
import android.os.Handler;
import android.view.*;
import org.json.JSONObject;

/** Relative pointer surface, intentionally independent of volume/navigation gestures. */
final class TouchpadView extends View {
    interface Sender{void send(JSONObject event);}
    private final Sender sender;private final Paint paint=new Paint(3);private final Handler ui=new Handler();
    private float lastX,lastY,startX,startY,total;private int fingers;private long began;private boolean lifted,dragging,cancelled;
    private boolean numberMode,numberCancelled;private NumberPadLayout.Key numberKey;
    private final Runnable hold=() -> {if(isEnabled()&&fingers==1&&!lifted&&total<8){dragging=true;event("button",true);invalidate();}};
    TouchpadView(Context c,Sender sender){super(c);this.sender=sender;setContentDescription("电脑触控板：单指移动，轻点左键，双指滚动和轻点右键，长按拖动，三指上下滑显示桌面或返回");}
    private float dp(float n){return n*getResources().getDisplayMetrics().density;}
    private void event(String kind,boolean down){try{sender.send(new JSONObject().put("kind",kind).put("down",down));}catch(Exception ignored){}}
    private void click(String button){try{sender.send(new JSONObject().put("kind","click").put("button",button));}catch(Exception ignored){}}
    void numberMode(boolean value){release();numberMode=value;setContentDescription(value?"数字键盘：0 至 9、小数点、四则运算、退格、回车；回车可能发送消息":"电脑触控板：单指移动、轻点左键，双指滚动和轻点右键，长按拖动");invalidate();}
    private NumberPadLayout.Key numberAt(float x,float y){return NumberPadLayout.hit(x,y,getWidth(),getHeight(),dp(8),dp(2));}
    private void drawNumbers(Canvas c){
        for(NumberPadLayout.Key key:NumberPadLayout.KEYS){float[] b=NumberPadLayout.bounds(key,getWidth(),getHeight(),dp(8),dp(2));
            boolean special=key.value.equals("enter"),pressed=key==numberKey&&!numberCancelled;
            paint.setStyle(Paint.Style.FILL);paint.setColor(!isEnabled()?0xffedf0f4:pressed?0xffd3e5ff:special?0xffe1ecfd:0xfff9fbfe);c.drawRoundRect(b[0],b[1],b[2],b[3],dp(9),dp(9),paint);
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(1));paint.setColor(special?0xffa2bfeb:0xffdce4ef);c.drawRoundRect(b[0],b[1],b[2],b[3],dp(9),dp(9),paint);
            paint.setStyle(Paint.Style.FILL);paint.setColor(isEnabled()?(special?HomeStyle.ACCENT:HomeStyle.TEXT):HomeStyle.MUTED);paint.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));paint.setTextAlign(Paint.Align.CENTER);
            paint.setTextSize(Math.min(dp(24),(b[3]-b[1])*.55f));Paint.FontMetrics f=paint.getFontMetrics();c.drawText(key.label,(b[0]+b[2])/2,(b[1]+b[3]-f.ascent-f.descent)/2,paint);
        }
        paint.setTypeface(Typeface.DEFAULT);
    }
    @Override protected void onDraw(Canvas c){
        paint.setColor(isEnabled()?0xffffffff:0xffeef1f5);c.drawRoundRect(0,0,getWidth(),getHeight(),dp(16),dp(16),paint);
        paint.setColor(0xffe0e5ed);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(1));c.drawRoundRect(dp(1),dp(1),getWidth()-dp(1),getHeight()-dp(1),dp(16),dp(16),paint);paint.setStyle(Paint.Style.FILL);
        if(numberMode){drawNumbers(c);return;}
        paint.setTextAlign(Paint.Align.CENTER);paint.setTextSize(dp(18));paint.setColor(HomeStyle.TEXT);
        c.drawText(!isEnabled()?"启用后在此移动电脑鼠标":dragging?"正在拖动":"触控板",getWidth()/2f,getHeight()/2f-dp(8),paint);
        paint.setTextSize(dp(12));paint.setColor(HomeStyle.MUTED);c.drawText("单指移动 / 轻点点击    双指滚动 / 轻点右键",getWidth()/2f,getHeight()/2f+dp(22),paint);
    }
    @Override public boolean onTouchEvent(MotionEvent e){
        if(!isEnabled())return true;
        if(numberMode)return numberTouch(e);
        int a=e.getActionMasked();float density=getResources().getDisplayMetrics().density;
        if(a==MotionEvent.ACTION_DOWN){fingers=1;lifted=dragging=cancelled=false;total=0;began=e.getEventTime();lastX=startX=e.getX();lastY=startY=e.getY();ui.postDelayed(hold,500);getParent().requestDisallowInterceptTouchEvent(true);return true;}
        if(a==MotionEvent.ACTION_POINTER_DOWN){ui.removeCallbacks(hold);if(dragging){event("button",false);dragging=false;cancelled=true;}fingers=Math.max(fingers,e.getPointerCount());lastX=e.getX();lastY=e.getY();startX=lastX;startY=lastY;total=0;return true;}
        if(a==MotionEvent.ACTION_POINTER_UP){lifted=true;ui.removeCallbacks(hold);return true;}
        if(a==MotionEvent.ACTION_MOVE&&!lifted&&!cancelled){
            float x=e.getX(),y=e.getY(),dx=(x-lastX)/density,dy=(y-lastY)/density;total+=Math.abs(dx)+Math.abs(dy);lastX=x;lastY=y;
            if(total>8)ui.removeCallbacks(hold);
            try{
                if(fingers==1)sender.send(new JSONObject().put("kind","move").put("dx",dx*1.7f).put("dy",dy*1.7f));
                else if(fingers==2)sender.send(new JSONObject().put("kind","scroll").put("dy",dy*5));
            }catch(Exception ignored){}return true;
        }
        if(a==MotionEvent.ACTION_UP||a==MotionEvent.ACTION_CANCEL){
            ui.removeCallbacks(hold);
            if(dragging){event("button",false);dragging=false;}
            else if(a==MotionEvent.ACTION_UP&&!cancelled){
                if(total<8&&e.getEventTime()-began<350){if(fingers==1)click("left");else if(fingers==2)click("right");}
                else if(fingers==3&&Math.abs(lastY-startY)>dp(60)){try{sender.send(new JSONObject().put("kind","navigation").put("action",lastY<startY?"desktop":"back"));}catch(Exception ignored){}}
            }
            fingers=0;lifted=true;invalidate();performClick();getParent().requestDisallowInterceptTouchEvent(false);return true;
        }
        return true;
    }
    private boolean numberTouch(MotionEvent event){
        int action=event.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){numberKey=numberAt(event.getX(),event.getY());numberCancelled=false;startX=event.getX();startY=event.getY();getParent().requestDisallowInterceptTouchEvent(true);invalidate();}
        else if(action==MotionEvent.ACTION_MOVE){if(Math.abs(event.getX()-startX)+Math.abs(event.getY()-startY)>dp(12)||numberAt(event.getX(),event.getY())!=numberKey)numberCancelled=true;invalidate();}
        else if(action==MotionEvent.ACTION_POINTER_DOWN||action==MotionEvent.ACTION_CANCEL){numberCancelled=true;numberKey=null;if(action==MotionEvent.ACTION_CANCEL)getParent().requestDisallowInterceptTouchEvent(false);invalidate();}
        else if(action==MotionEvent.ACTION_UP){
            if(!numberCancelled&&numberKey!=null&&numberAt(event.getX(),event.getY())==numberKey){
                try{sender.send(new JSONObject().put("kind","key").put("key",numberKey.value));performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);}catch(Exception ignored){}
                performClick();
            }
            numberKey=null;numberCancelled=true;getParent().requestDisallowInterceptTouchEvent(false);invalidate();
        }
        return true;
    }
    void release(){ui.removeCallbacks(hold);if(dragging)event("button",false);dragging=false;lifted=true;numberKey=null;numberCancelled=true;invalidate();}
    @Override public boolean performClick(){super.performClick();return true;}
    @Override protected void onDetachedFromWindow(){release();super.onDetachedFromWindow();}
}
