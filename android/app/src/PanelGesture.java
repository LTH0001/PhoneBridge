package com.phonebridge.app;

/** Pure gesture classification, also exercised on the desktop JDK. */
final class PanelGesture {
    static String classify(int fingers,float dx,float dy,float density,boolean edge){
        if(density<=0)return "";float x=dx/density,y=dy/density;
        if((fingers==2||fingers==1&&edge)&&x>70&&x>Math.abs(y)*1.5f)return "back";
        if(fingers==3&&Math.abs(y)>70&&Math.abs(y)>Math.abs(x)*1.5f)return y<0?"panel":"desktop";
        return "";
    }
}
