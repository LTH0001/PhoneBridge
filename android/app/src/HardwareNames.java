package com.phonebridge.app;

/** Short display labels only; the full detected identity remains in detail data. */
final class HardwareNames {
    static String compact(String value,String fallback){
        if(value==null)return fallback;
        String name=value.replace("(R)","").replace("(TM)","").replace("™","").replace("®","")
            .replace("NVIDIA GeForce ","").replace("Intel ","").replace("AMD Ryzen ","Ryzen ")
            .trim().replaceAll("\\s+"," ");
        return name.isEmpty()||"CPU".equals(name)?fallback:name;
    }
}
