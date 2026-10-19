package com.phonebridge.app;
public final class PanelPaletteTest {
    static int count;
    static double luminance(int color){double[] c={(color>>16&255)/255.,(color>>8&255)/255.,(color&255)/255.};for(int i=0;i<3;i++)c[i]=c[i]<=.04045?c[i]/12.92:Math.pow((c[i]+.055)/1.055,2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;}
    static void contrast(int a,int b,double minimum){double x=luminance(a),y=luminance(b),ratio=(Math.max(x,y)+.05)/(Math.min(x,y)+.05);if(ratio<minimum)throw new AssertionError("Low contrast: "+ratio);count++;}
    public static void main(String[] args){
        for(boolean dark:new boolean[]{false,true}){
            int bg=PanelPalette.color(0xfff7f8fa,dark),card=PanelPalette.color(0xffffffff,dark);
            contrast(PanelPalette.color(0xff252c38,dark),bg,7);
            contrast(PanelPalette.color(0xff647082,dark),bg,4.5);
            contrast(PanelPalette.color(0xff252c38,dark),card,7);
            contrast(PanelPalette.color(0xff647082,dark),card,4.5);
        }
        if(PanelPalette.color(0x12376bc1,true)!=0x12376bc1)throw new AssertionError("Alpha changed");count++;
        if(PanelPalette.color(0xfff7f8fa,false)!=0xfff7f8fa)throw new AssertionError("Light changed");count++;
        contrast(0xffffffff,0xff3665bb,4.5);
        System.out.println("PASS "+count+" theme contrast/palette cases");
    }
}
