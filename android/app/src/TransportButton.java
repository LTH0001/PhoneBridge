package com.phonebridge.app;
import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.content.res.ColorStateList;
import android.widget.Button;

/** Vector transport controls, with a full-size touch target and spoken labels. */
final class TransportButton extends Button {
    private final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);private final int action;private final boolean light;private boolean paused=true;
    TransportButton(Context context,int action,boolean light){super(context);this.action=action;this.light=light;
        setMinWidth(0);setMinimumWidth(0);setMinHeight(0);setMinimumHeight(0);setPadding(0,0,0,0);setStateListAnimator(null);
        GradientDrawable mask=new GradientDrawable();mask.setColor(PanelTheme.color(0xffffffff));mask.setCornerRadius(999);
        setBackground(new RippleDrawable(ColorStateList.valueOf(PanelTheme.color(0x3365c7ff)),null,mask));setText(action==0?"播放":action<0?"上一首":"下一首");
    }
    @Override public void setText(CharSequence text,BufferType type){paused=!"暂停".contentEquals(text==null?"":text);setContentDescription(text);super.setText("",type);invalidate();}
    private float dp(float n){return n*getResources().getDisplayMetrics().density;}
    @Override protected void onDraw(Canvas c){
        float x=getWidth()/2f,y=getHeight()/2f; p.setStyle(Paint.Style.FILL);p.setAlpha(isEnabled()?255:75);
        if(action==0){p.setColor(PanelTheme.color(light?0xff438ef5:0xff64dccf));p.setAlpha(isEnabled()?255:75);c.drawCircle(x,y,Math.min(dp(15),Math.min(getWidth(),getHeight())/2f-dp(2)),p);}
        PanelTheme.transportInk(p,action==0);p.setAlpha(isEnabled()?255:75);
        if(action==0&&!paused){c.drawRoundRect(x-dp(4),y-dp(5),x-dp(1),y+dp(5),dp(.5f),dp(.5f),p);c.drawRoundRect(x+dp(1),y-dp(5),x+dp(4),y+dp(5),dp(.5f),dp(.5f),p);}
        else {float direction=action<0?-1:1;Path triangle=new Path();triangle.moveTo(x+direction*dp(5),y);triangle.lineTo(x-direction*dp(4),y-dp(5));triangle.lineTo(x-direction*dp(4),y+dp(5));triangle.close();c.drawPath(triangle,p);
            if(action!=0){float bar=x+direction*dp(6);c.drawRect(bar-dp(1),y-dp(5),bar+dp(1),y+dp(5),p);}}
        p.setAlpha(255);
    }
}
