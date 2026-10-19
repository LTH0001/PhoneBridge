package com.phonebridge.app;
import android.content.Context;
import android.graphics.*;
import android.os.SystemClock;
import android.view.View;

/** Digital motorsport cluster: open LED arc and large type, not a pressure gauge. */
final class InstrumentGauge extends View {
    private final Paint p=new Paint(3);private final int color;private final String name;private final boolean main;
    private double from,target;private boolean valid;private String detail="";private long changed;
    InstrumentGauge(Context c,String name,int color){super(c);this.name=name;this.color=color;main="CPU".equals(name);}
    void update(Double value,String detail){long now=SystemClock.uptimeMillis();from=animated(now);valid=value!=null&&Double.isFinite(value);target=valid?Math.max(0,Math.min(100,value)):0;
        this.detail=detail;changed=Math.abs(target-from)>.02?now:now-400;
        setContentDescription(name+" 占用 "+(valid?Math.round(target)+"%":"不可用")+"，"+detail+"，点击查看详情");invalidate();}
    private float dp(float n){return n*getResources().getDisplayMetrics().density;}
    private double animated(long now){double t=Math.min(1,Math.max(0,(now-changed)/400.0));return from+(target-from)*(1-Math.pow(1-t,3));}
    private void text(Canvas c,String text,float x,float y,float size,int color,boolean bold){p.setShader(null);p.setStyle(Paint.Style.FILL);p.setTypeface(Typeface.create(bold?"sans-serif-condensed":"sans-serif",bold?Typeface.BOLD_ITALIC:Typeface.NORMAL));p.setTextSize(dp(size));p.setColor(color);p.setTextAlign(Paint.Align.CENTER);c.drawText(text,x,y,p);}
    @Override protected void onDraw(Canvas c){super.onDraw(c);long now=SystemClock.uptimeMillis();double value=animated(now);float w=getWidth(),h=getHeight(),cx=w/2;
        int accent=main?0xff376bc1:name.endsWith("1")?0xff237e8b:0xffaa6a30;
        text(c,name,cx,dp(16),main?13:11,0xff304157,true);
        if(main){
            float cy=h*.49f,r=Math.min(w*.46f,h*.39f);if(r<=0)return;RectF arc=new RectF(cx-r,cy-r,cx+r,cy+r);
            p.setStyle(Paint.Style.STROKE);p.setStrokeCap(Paint.Cap.BUTT);p.setStrokeWidth(dp(7));
            for(int i=0;i<60;i++){boolean lit=valid&&i<value*.6;p.setColor(lit?(i>=51?0xffd94c59:accent):(i>=51?0xffe8cbd2:0xffd2deed));c.drawArc(arc,145+i*(250f/60),3.1f,false,p);}
            p.setStrokeWidth(dp(.6f));p.setColor(0xffbdcce0);RectF inner=new RectF(cx-r+dp(9),cy-r+dp(9),cx+r-dp(9),cy+r-dp(9));c.drawArc(inner,145,250,false,p);
            for(int i=0;i<=5;i++){double a=Math.toRadians(145+i*50);float nr=r-dp(17);text(c,Integer.toString(i*20),cx+(float)Math.cos(a)*nr,cy+(float)Math.sin(a)*nr+dp(2),7,0xff70849e,false);}
            text(c,"PROCESSOR",cx,cy-dp(22),8,0xff70849e,false);
            text(c,valid?Long.toString(Math.round(value)):"—",cx,cy+dp(18),44,0xff24364e,true);
            text(c,"UTILIZATION  %",cx,cy+dp(34),8,accent,false);
        }else{
            text(c,"GRAPHICS ENGINE",cx,h*.25f,7.5f,0xff70849e,false);
            text(c,valid?Long.toString(Math.round(value)):"—",cx-dp(3),h*.51f,48,0xff24364e,true);
            text(c,"% LOAD",cx,h*.61f,8,accent,false);
            float left=w*.12f,right=w*.88f,segment=(right-left)/20;
            p.setStyle(Paint.Style.FILL);
            for(int i=0;i<20;i++){p.setColor(valid&&i<value/5?(i>=17?0xffd94c59:accent):0xffd2deed);c.drawRoundRect(left+i*segment,h*.70f,left+(i+1)*segment-dp(1),h*.70f+dp(6),dp(.7f),dp(.7f),p);}
        }
        String[] lines=detail.split("\n",2);
        for(int i=0;i<lines.length;i++){String line=lines[i];float size=9;while(size>6&&measure(line,size)>w-dp(8))size-=.5f;text(c,line,cx,h-dp(lines.length==2?(i==0?20:6):8),size,0xff647890,false);}
        if(valid&&now-changed<400&&isShown())postInvalidateOnAnimation();
    }
    private float measure(String text,float size){p.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));p.setTextSize(dp(size));return p.measureText(text);}
}
