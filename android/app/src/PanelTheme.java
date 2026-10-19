package com.phonebridge.app;

import android.app.*;
import android.content.*;
import android.content.res.Configuration;
import android.graphics.Paint;
import android.view.ContextThemeWrapper;
import android.widget.Button;
import java.util.WeakHashMap;

/** Local-only appearance preference; no device or computer permission changes. */
final class PanelTheme {
    private static volatile boolean dark;
    private static final WeakHashMap<Activity,Boolean> applied=new WeakHashMap<>();
    static String mode(Context c){return c.getSharedPreferences("appearance",Context.MODE_PRIVATE).getString("theme","light");}
    private static boolean resolve(Context c){String mode=mode(c);return "dark".equals(mode)||"system".equals(mode)&&(c.getResources().getConfiguration().uiMode&Configuration.UI_MODE_NIGHT_MASK)==Configuration.UI_MODE_NIGHT_YES;}
    static void apply(Activity a){dark=resolve(a);if(!applied.containsKey(a))applied.put(a,dark);
        a.setTheme(dark?android.R.style.Theme_Material_NoActionBar:android.R.style.Theme_Material_Light_NoActionBar);
        a.getWindow().setBackgroundDrawable(new android.graphics.drawable.ColorDrawable(background()));
        a.getWindow().setStatusBarColor(background());a.getWindow().setNavigationBarColor(background());}
    static boolean refresh(Activity a){boolean next=resolve(a);Boolean previous=applied.get(a);if(previous!=null&&previous!=next){dark=next;a.recreate();return true;}return false;}
    static boolean dark(){return dark;}
    static int color(int value){return PanelPalette.color(value,dark);}
    static int background(){return dark?0xff0b1018:0xfff7f8fa;}
    static int surface(){return dark?0xff151e2b:0xffffffff;}
    static int text(){return dark?0xffe7edf7:0xff252c38;}
    static int muted(){return dark?0xffa6b6ce:0xff647082;}
    static int grid(){return dark?0xff33465f:0xffdde3ec;}
    static int accent(){return dark?0xff8bb7ff:0xff376bc1;}
    static int[] colors(int[] values){int[] copy=values.clone();for(int i=0;i<copy.length;i++)copy[i]=color(copy[i]);return copy;}
    static void primaryText(Button b){b.setTextColor(0xffffffff);}
    static void transportInk(Paint p,boolean playing){p.setColor(playing?0xffffffff:color(0xff294858));}
    static int primary(){return dark?0xff3665bb:0xff376bc1;}
    static int[] cockpitColors(){return dark?new int[]{0xff0b1018,0xff142035,0xff0c131e}:new int[]{0xfffafcfe,0xffeef3f9,0xfff6f8fc};}
    static int[] musicColors(){return dark?new int[]{0xff102338,0xff171a2e,0xff2a1c2a}:new int[]{0xffcdeaff,0xffeff4f0,0xffffe7d5};}
    static AlertDialog.Builder dialog(Context c){return new AlertDialog.Builder(new ContextThemeWrapper(c,dark?android.R.style.Theme_Material_Dialog_Alert:android.R.style.Theme_Material_Light_Dialog_Alert));}
    static void choose(Activity a){
        String[] modes={"light","dark","system"},labels={"浅色 · 白色","深色 · 黑色","跟随系统"};String current=mode(a);int selected=0;for(int i=0;i<modes.length;i++)if(modes[i].equals(current))selected=i;
        dialog(a).setTitle("外观主题").setSingleChoiceItems(labels,selected,(d,index)->{d.dismiss();if(!modes[index].equals(current)){a.getSharedPreferences("appearance",Context.MODE_PRIVATE).edit().putString("theme",modes[index]).apply();dark=resolve(a);a.recreate();}}).setNegativeButton("取消",null).show();
    }
}
