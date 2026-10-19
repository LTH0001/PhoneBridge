package com.phonebridge.app;

import android.content.Context;
import android.content.Intent;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import org.json.JSONObject;

/** Authenticated loopback-only API through the authorized ADB USB tunnel. */
public final class PanelConnection {
    public static void configure(Context context, Intent intent) {
        String url=intent.getStringExtra("api_url"), token=intent.getStringExtra("api_token");
        if (url == null || token == null) return;
        if (!url.matches("http://127\\.0\\.0\\.1:[0-9]{1,5}") || !token.matches("[A-Za-z0-9_-]{20,128}"))
            throw new IllegalArgumentException("仅允许本机 USB 隧道 API");
        int port=Integer.parseInt(url.substring(url.lastIndexOf(':')+1));
        if (port<1024 || port>65535) throw new IllegalArgumentException("无效 API 端口");
        context.getSharedPreferences("pc_api",Context.MODE_PRIVATE).edit().putString("url",url).putString("token",token).apply();
    }
    public static JSONObject request(Context context,String path,JSONObject body) throws Exception {
        if(AccessoryLink.active())return AccessoryLink.request(path,body);
        if(WirelessLink.active())return WirelessLink.request(path,body);
        android.content.SharedPreferences preferences=context.getSharedPreferences("pc_api",Context.MODE_PRIVATE);
        String base=preferences.getString("url",""), token=preferences.getString("token","");
        if(base.isEmpty() || token.isEmpty()) throw new IllegalStateException("请先从电脑打开控制面板");
        if(!path.startsWith("/api/")) throw new IllegalArgumentException("无效 API 路径");
        HttpURLConnection connection=(HttpURLConnection)new URL(base+path).openConnection();
        connection.setConnectTimeout(2500); connection.setReadTimeout(15000);
        connection.setRequestProperty("Authorization","Bearer "+token);
        connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
        try {
            if(body!=null) {
                connection.setRequestMethod("POST"); connection.setDoOutput(true);
                byte[] data=body.toString().getBytes("UTF-8"); connection.setFixedLengthStreamingMode(data.length);
                try(java.io.OutputStream output=connection.getOutputStream()) { output.write(data); }
            }
            int code=connection.getResponseCode();
            InputStream stream=code<400 ? connection.getInputStream() : connection.getErrorStream();
            if(stream==null) throw new IllegalStateException("电脑 API 返回 "+code);
            ByteArrayOutputStream data=new ByteArrayOutputStream();
            try(InputStream input=stream) {
                byte[] buffer=new byte[4096]; int count;
                while((count=input.read(buffer))!=-1) {
                    if(data.size()+count>2*1024*1024) throw new IllegalStateException("API 响应过大");
                    data.write(buffer,0,count);
                }
            }
            JSONObject result=new JSONObject(data.toString("UTF-8"));
            if(code>=400) throw new IllegalStateException(result.optString("error","API 错误 "+code));
            return result;
        } finally { connection.disconnect(); }
    }
    public static byte[] artwork(Context context,String key) throws Exception {
        if(!key.matches("[a-f0-9]{24}"))throw new IllegalArgumentException("无效歌曲标识");
        if(AccessoryLink.active())return android.util.Base64.decode(AccessoryLink.request("/api/music/art?key="+key,null).optString("art"),android.util.Base64.DEFAULT);
        if(WirelessLink.active()){String bytes=WirelessLink.request("/api/music/art?key="+key,null).optString("art");return android.util.Base64.decode(bytes,android.util.Base64.DEFAULT);}
        android.content.SharedPreferences p=context.getSharedPreferences("pc_api",Context.MODE_PRIVATE);
        HttpURLConnection c=(HttpURLConnection)new URL(p.getString("url","")+"/api/music/art?key="+key).openConnection();
        c.setConnectTimeout(2500);c.setReadTimeout(4000);c.setRequestProperty("Authorization","Bearer "+p.getString("token",""));
        try {
            if(c.getResponseCode()!=200)return new byte[0];
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try(InputStream stream=c.getInputStream()){
                byte[] buffer=new byte[4096];int count;
                while((count=stream.read(buffer))!=-1){if(bytes.size()+count>256*1024)throw new IllegalStateException("封面过大");bytes.write(buffer,0,count);}
            }
            return bytes.toByteArray();
        } finally{c.disconnect();}
    }
}
