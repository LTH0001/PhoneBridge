package com.phonebridge.app;
import android.content.Context;
import android.graphics.*;
import android.view.View;

/** Compact E–F capacity dial. Missing capacity is never presented as empty. */
final class FuelGauge extends View {
    private final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final int color;private final boolean remaining;
    private Double percent;
    FuelGauge(Context context,int color,boolean remaining){super(context);this.color=color;this.remaining=remaining;}
    void update(Double value){percent=value!=null&&Double.isFinite(value)?Math.max(0,Math.min(100,value)):null;setContentDescription((remaining?"存储剩余":"内存已用")+(percent==null?"不可用":Math.round(percent)+"%"));invalidate();}
    private float dp(float n){return n*getResources().getDisplayMetrics().density;}
    @Override protected void onDraw(Canvas c){super.onDraw(c);
        float x=getWidth()/2f,y=getHeight()*.60f,r=Math.min(getWidth()*.37f,getHeight()*.46f);
        RectF bounds=new RectF(x-r,y-r,x+r,y+r);
        int ink=percent!=null&&(remaining?percent<15:percent>85)?0xffff6654:color;
        p.setStyle(Paint.Style.STROKE);p.setStrokeCap(Paint.Cap.BUTT);p.setStrokeWidth(dp(6));p.setShader(new LinearGradient(x-r,y-r,x+r,y,new int[]{0xffb3bfcd,0xfff9fbfd,0xffc6d2df},null,Shader.TileMode.CLAMP));c.drawArc(bounds,180,180,false,p);p.setShader(null);
        p.setStrokeWidth(dp(3));p.setColor(0xffe4e9f0);c.drawArc(bounds,180,180,false,p);
        if(percent!=null){p.setColor(ink);c.drawArc(bounds,180,(float)(percent*1.8),false,p);}
        p.setStrokeCap(Paint.Cap.BUTT);p.setStrokeWidth(dp(1));
        for(int i=0;i<=20;i++){double a=Math.toRadians(180+i*9);p.setColor((remaining?i<3:i>17)?0xffc95b5b:0xff8392a5);p.setStrokeWidth(dp(i%5==0?1:.5f));c.drawLine(x+(float)Math.cos(a)*(r-dp(i%5==0?6:3)),y+(float)Math.sin(a)*(r-dp(i%5==0?6:3)),x+(float)Math.cos(a)*(r+dp(2)),y+(float)Math.sin(a)*(r+dp(2)),p);}
        if(percent!=null){double a=Math.toRadians(180+percent*1.8);p.setStrokeWidth(dp(1.5f));p.setColor(0xffd3434a);c.drawLine(x,y,x+(float)Math.cos(a)*(r-dp(5)),y+(float)Math.sin(a)*(r-dp(5)),p);}
        p.setStyle(Paint.Style.FILL);p.setColor(ink);c.drawCircle(x,y,dp(2),p);
        p.setTypeface(Typeface.MONOSPACE);p.setTextSize(dp(7));p.setColor(0xff647082);p.setTextAlign(Paint.Align.CENTER);c.drawText("E",x-r-dp(4),y+dp(4),p);c.drawText("F",x+r+dp(4),y+dp(4),p);
        p.setTypeface(Typeface.create("sans-serif-condensed",Typeface.BOLD_ITALIC));p.setTextSize(dp(11));p.setColor(ink);c.drawText(percent==null?"—":Math.round(percent)+"%",x,getHeight()-dp(2),p);
    }
}
