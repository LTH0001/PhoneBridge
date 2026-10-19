package com.phonebridge.app;
import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Subtle alloy panel with clipped corners, not a car logo. */
final class SportPanel extends Drawable {
    private final Paint p=new Paint(3);private final int accent;private final float density;
    SportPanel(int accent,float density){this.accent=accent;this.density=density;}
    @Override public void draw(Canvas c){Rect b=getBounds();float l=b.left+1,t=b.top+1,r=b.right-1,bot=b.bottom-1,k=10*density;
        Path panel=new Path();panel.moveTo(l+k,t);panel.lineTo(r-k,t);panel.lineTo(r,t+k);panel.lineTo(r,bot-k);panel.lineTo(r-k,bot);panel.lineTo(l+k,bot);panel.lineTo(l,bot-k);panel.lineTo(l,t+k);panel.close();
        p.setStyle(Paint.Style.FILL);p.setShader(new LinearGradient(l,t,r,bot,new int[]{0xffffffff,0xfffafbfd,0xffedf1f6},null,Shader.TileMode.CLAMP));c.drawPath(panel,p);p.setShader(null);
        p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(density);p.setColor(0xffd7dee8);c.drawPath(panel,p);
        p.setStrokeWidth(2*density);p.setColor(accent);c.drawLine(l+k,t+1,l+k+28*density,t+1,p);
        p.setColor(0x55909eaf);p.setStrokeWidth(density);for(int i=0;i<3;i++){float x=r-k-(i*5)*density;c.drawLine(x,bot-5*density,x-3*density,bot-2*density,p);}p.setStyle(Paint.Style.FILL);
    }
    @Override public void setAlpha(int alpha){}@Override public void setColorFilter(ColorFilter filter){}@Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
}
