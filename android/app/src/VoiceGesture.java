package com.phonebridge.app;

/** Single-finger, direction-locked voice commands; independent of navigation/volume. */
final class VoiceGesture {
    static String classify(float dx,float dy,float density){
        return classify(dx,dy,density,60);
    }
    static String classify(float dx,float dy,float density,float stopDistance){
        if(density<=0||Float.isNaN(density)||Float.isInfinite(density)||Float.isNaN(dx)||Float.isNaN(dy)||Float.isInfinite(dx)||Float.isInfinite(dy))return "";
        float x=dx/density,y=dy/density;
        if(y>Math.max(12,Math.min(60,stopDistance))&&y>Math.abs(x)*1.25f)return "stop";
        if(x>60&&x>Math.abs(y)*1.25f)return "confirm";
        return "";
    }
}
