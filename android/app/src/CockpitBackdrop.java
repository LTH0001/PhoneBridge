package com.phonebridge.app;
import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Light alloy cockpit surface; static, native drawing, no continuous animation. */
final class CockpitBackdrop extends Drawable {
    private final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
    @Override public void draw(Canvas c){Rect r=getBounds();float w=r.width(),h=r.height();
        p.setShader(new LinearGradient(0,0,w,h,new int[]{0xfffafcfe,0xffeef3f9,0xfff6f8fc},null,Shader.TileMode.CLAMP));c.drawRect(r,p);p.setShader(null);
        p.setColor(0x06ffffff);p.setStrokeWidth(1);for(float x=-h;x<w;x+=18)c.drawLine(x,0,x+h,h,p);
        p.setShader(new RadialGradient(w*.62f,h*.44f,w*.55f,new int[]{0x10376bc1,0x00376bc1},null,Shader.TileMode.CLAMP));c.drawRect(r,p);p.setShader(null);
        p.setColor(0xff376bc1);c.drawRect(w*.018f,0,w*.12f,3,p);p.setColor(0xffcf4e50);c.drawRect(w*.123f,0,w*.15f,3,p);
    }
    @Override public void setAlpha(int alpha){}@Override public void setColorFilter(ColorFilter f){}@Override public int getOpacity(){return PixelFormat.OPAQUE;}
}
