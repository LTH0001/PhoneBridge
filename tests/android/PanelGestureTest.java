package com.phonebridge.app;
public final class PanelGestureTest {
    private static int count;
    private static void test(String expected,int fingers,float x,float y,float density,boolean edge){
        String actual=PanelGesture.classify(fingers,x,y,density,edge);if(!expected.equals(actual))throw new AssertionError(expected+" != "+actual);count++;
    }
    public static void main(String[] args){
        test("back",2,240,20,3,false);test("",2,-240,0,3,false);
        test("panel",3,20,-240,3,false);test("desktop",3,20,240,3,false);
        test("",4,0,300,3,false);test("",2,0,-300,3,false);
        test("",1,300,0,3,false);test("back",1,300,0,3,true);
        test("",3,100,100,3,false);test("",2,120,0,3,false);
        test("",3,0,300,0,false);test("",1,0,-300,3,true);
        System.out.println("PASS "+count+" gesture classification cases");
    }
}
