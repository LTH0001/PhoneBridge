package com.phonebridge.app;

import android.app.Activity;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.*;
import android.view.*;
import android.widget.*;

/** Shared native visual language. No bitmap-scaled text or desktop CSS. */
final class PanelStyle {
    static final int BG=HomeStyle.BG,TEXT=HomeStyle.TEXT,MUTED=HomeStyle.MUTED,ACCENT=HomeStyle.ACCENT;
    static int dp(Context context,int value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    static Drawable background(){return new ColorDrawable(BG);}
    static Drawable card(Context c,int accent){
        GradientDrawable g=new GradientDrawable();g.setColor(0xffffffff);g.setCornerRadius(dp(c,14));g.setStroke(dp(c,1),0xffe1e5ec);
        return new RippleDrawable(ColorStateList.valueOf(0x16376bc1),g,null);
    }
    static Button button(Context c,String text,boolean light,View.OnClickListener action){
        Button b=HomeStyle.button(c,text,false,action);b.setTextSize(12);b.setMinWidth(0);b.setMinimumWidth(0);return b;
    }
    static void primary(Button b){HomeStyle.primary(b);}
    static void immersive(Activity a){
        if(a.getActionBar()!=null)a.getActionBar().hide();
        a.getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        if(android.os.Build.VERSION.SDK_INT>=30){WindowInsetsController ctl=a.getWindow().getInsetsController();if(ctl!=null){ctl.hide(WindowInsets.Type.systemBars());ctl.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);}}
    }
}
