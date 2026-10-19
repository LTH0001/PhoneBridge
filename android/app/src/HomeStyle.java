package com.phonebridge.app;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.View;
import android.widget.Button;

/** Light setup surfaces, independent of the dark instrument panel. */
final class HomeStyle {
    static final int BG=0xfff7f8fa,TEXT=0xff252c38,MUTED=0xff647082,ACCENT=0xff376bc1;
    static int dp(Context c,int n){return PanelStyle.dp(c,n);}
    static Button button(Context c,String text,boolean unused,View.OnClickListener click){
        Button b=new Button(c);b.setText(text);b.setTextSize(14);b.setAllCaps(false);
        b.setTextColor(PanelTheme.color(TEXT));b.setPadding(dp(c,12),0,dp(c,12),0);b.setElevation(0);
        GradientDrawable shape=new GradientDrawable();shape.setColor(PanelTheme.color(0xfff3f5f8));
        shape.setCornerRadius(dp(c,10));shape.setStroke(dp(c,1),PanelTheme.color(0xffe1e5ec));
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(PanelTheme.color(0x19376bc1)),shape,null));
        b.setOnClickListener(click);return b;
    }
    static void primary(Button b){
        GradientDrawable shape=new GradientDrawable();shape.setColor(PanelTheme.primary());shape.setCornerRadius(dp(b.getContext(),10));
        PanelTheme.primaryText(b);b.setTypeface(null,Typeface.BOLD);
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(PanelTheme.color(0x22ffffff)),shape,null));
    }
}
