package com.phonebridge.app;

import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Soft cyan/cream/peach with optional tiny, blurred SMTC album art. */
final class MusicBackdrop extends Drawable {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);
    private Bitmap art;
    void setArt(Bitmap bitmap){art=bitmap==null?null:Bitmap.createScaledBitmap(bitmap,24,24,true);invalidateSelf();}
    @Override public void draw(Canvas c){
        Rect r=getBounds();float w=r.width(),h=r.height();
        paint.setShader(new LinearGradient(0,h,w,0,PanelTheme.musicColors(),null,Shader.TileMode.CLAMP));c.drawRect(r,paint);
        paint.setShader(null);
        if(art!=null){paint.setAlpha(38);c.drawBitmap(art,null,new RectF(r),paint);paint.setAlpha(255);}
        paint.setShader(new RadialGradient(w*.56f,h*.44f,w*.58f,PanelTheme.colors(new int[]{0xbffffcf0,0x00fffdf6}),null,Shader.TileMode.CLAMP));c.drawRect(r,paint);paint.setShader(null);
    }
    @Override public void setAlpha(int value){}
    @Override public void setColorFilter(ColorFilter filter){}
    @Override public int getOpacity(){return PixelFormat.OPAQUE;}
}
