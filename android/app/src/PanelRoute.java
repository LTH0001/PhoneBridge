package com.phonebridge.app;

/** Tracks the real control channel, not merely an open/pending USB accessory. */
final class PanelRoute {
    private Object owner;
    private String transport="";
    synchronized void activate(Object connection,String mode) {
        if(connection==null || !("usb".equals(mode)||"wireless".equals(mode)||"accessory".equals(mode)))
            throw new IllegalArgumentException("Invalid control transport");
        owner=connection;transport=mode;
    }
    synchronized void deactivate(Object connection) {
        if(owner==connection){owner=null;transport="";}
    }
    synchronized String current(){return transport;}
    static String choose(String control,boolean accessory,boolean wireless) {
        if("usb".equals(control))return "usb";
        if("accessory".equals(control)) {
            if(!accessory)throw new IllegalStateException("USB 外设连接已断开，请在电脑重新连接");
            return "accessory";
        }
        if("wireless".equals(control)) {
            if(!wireless)throw new IllegalStateException("无线连接已断开，请重新配对");
            return "wireless";
        }
        if(control!=null&&!control.isEmpty())throw new IllegalArgumentException("Unknown control transport");
        // Compatibility while no control channel has been accepted yet.
        if(accessory)return "accessory";
        if(wireless)return "wireless";
        return "usb";
    }
    static String errorMessage(Throwable error) {
        if(error==null)return "未知面板错误";
        for(int i=0;i<8&&error.getCause()!=null&&error.getCause()!=error;i++)error=error.getCause();
        if(error instanceof java.util.concurrent.TimeoutException || error instanceof java.net.SocketTimeoutException)
            return "控制面板请求超时，请从电脑重新打开控制面板";
        if(error instanceof java.net.ConnectException)
            return "电脑 API 无法访问，请检查 USB 连接并从电脑重新打开控制面板";
        String message=error.getMessage();
        if(message==null||message.trim().isEmpty()||"null".equals(message.trim()))return error.getClass().getSimpleName();
        return message;
    }
}
