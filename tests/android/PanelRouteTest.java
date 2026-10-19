package com.phonebridge.app;
public final class PanelRouteTest {
    private static int count;
    private static void equal(String expected,String actual){if(!expected.equals(actual))throw new AssertionError(expected+" != "+actual);count++;}
    public static void main(String[] args){
        for(boolean accessory:new boolean[]{false,true})for(boolean wireless:new boolean[]{false,true})
            equal("usb",PanelRoute.choose("usb",accessory,wireless));
        equal("accessory",PanelRoute.choose("accessory",true,true));
        equal("wireless",PanelRoute.choose("wireless",true,true));
        equal("usb",PanelRoute.choose("",false,false));
        equal("accessory",PanelRoute.choose("",true,false));
        equal("wireless",PanelRoute.choose("",false,true));
        try{PanelRoute.choose("accessory",false,true);throw new AssertionError("silent fallback");}catch(IllegalStateException expected){count++;}
        try{PanelRoute.choose("wireless",true,false);throw new AssertionError("silent fallback");}catch(IllegalStateException expected){count++;}
        PanelRoute route=new PanelRoute();Object old=new Object(), current=new Object();
        route.activate(old,"accessory");route.activate(current,"usb");route.deactivate(old);equal("usb",route.current());
        route.deactivate(current);equal("",route.current());
        equal("控制面板请求超时，请从电脑重新打开控制面板",PanelRoute.errorMessage(new java.util.concurrent.TimeoutException()));
        equal("控制面板请求超时，请从电脑重新打开控制面板",PanelRoute.errorMessage(new java.util.concurrent.ExecutionException(new java.net.SocketTimeoutException())));
        equal("IOException",PanelRoute.errorMessage(new java.io.IOException()));
        equal("Exception",PanelRoute.errorMessage(new Exception("null")));
        equal("授权已过期",PanelRoute.errorMessage(new IllegalStateException("授权已过期")));
        System.out.println("PASS "+count+" panel route/error cases");
    }
}
