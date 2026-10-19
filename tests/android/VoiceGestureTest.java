package com.phonebridge.app;
public final class VoiceGestureTest {
    private static int count;
    private static void test(String expected,float x,float y,float density){
        String actual=VoiceGesture.classify(x,y,density);
        if(!expected.equals(actual))throw new AssertionError(expected+" != "+actual);count++;
    }
    public static void main(String[] args){
        test("stop",0,61,1);test("confirm",61,0,1);
        test("",0,-100,1);test("",-100,0,1);
        test("",70,70,1);test("",-70,70,1);
        test("confirm",80,40,1);test("stop",40,80,1);
        test("",60,0,1);test("",0,60,1);
        test("stop",10,183,3);test("confirm",183,10,3);
        test("",0,30,1);test("",100,0,0);test("",100,0,-1);
        test("",Float.NaN,90,1);test("",90,Float.POSITIVE_INFINITY,1);
        test("",90,0,Float.NaN);test("",90,0,Float.POSITIVE_INFINITY);
        if(!"stop".equals(VoiceGesture.classify(0,60,3,18)))throw new AssertionError("bottom toolbar stop unreachable");count++;
        if(!"".equals(VoiceGesture.classify(0,30,3,18)))throw new AssertionError("small bottom motion triggered stop");count++;
        if(!"confirm".equals(VoiceGesture.classify(183,0,3,18)))throw new AssertionError("bottom right confirm changed");count++;
        System.out.println("PASS "+count+" voice gesture classification cases");
    }
}
