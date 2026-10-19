package com.phonebridge.app;
import android.app.Activity;
import android.content.Intent;
import org.json.JSONObject;
import javax.net.ssl.*;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.net.InetSocketAddress;
import java.io.*;

/** TLS with an out-of-band, user-entered per-computer certificate fingerprint. */
final class WirelessLink {
    private static volatile WirelessLink current;
    private final String host,pin;private final int port;private String token;
    private final SSLContext tls;private final java.util.List<SSLSocket> sockets=new java.util.ArrayList<>();private volatile boolean closed;
    static boolean active(){return current!=null;}
    private WirelessLink(String invitation)throws Exception{
        String[] parts=invitation.trim().split(":");
        if(parts.length!=5||!parts[0].equals("pbw1")||!parts[1].matches("[0-9.]{7,15}")||!parts[3].matches("[a-f0-9]{64}")||!parts[4].matches("[A-Za-z0-9_-]{43}"))throw new IOException("无效配对信息");
        host=parts[1];port=Integer.parseInt(parts[2]);if(port<1024||port>65535)throw new IOException("无效端口");pin=parts[3];token=parts[4];
        TrustManager manager=new X509TrustManager(){
            public X509Certificate[] getAcceptedIssuers(){return new X509Certificate[0];}
            public void checkClientTrusted(X509Certificate[] chain,String auth)throws java.security.cert.CertificateException{throw new java.security.cert.CertificateException("Not a server");}
            public void checkServerTrusted(X509Certificate[] chain,String auth)throws java.security.cert.CertificateException{
                try{if(chain.length!=1)throw new IOException("证书链不符");chain[0].checkValidity();chain[0].verify(chain[0].getPublicKey());
                    byte[] bytes=MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded());StringBuilder hex=new StringBuilder();for(byte b:bytes)hex.append(String.format(java.util.Locale.US,"%02x",b&255));
                    if(!MessageDigest.isEqual(pin.getBytes("US-ASCII"),hex.toString().getBytes("US-ASCII")))throw new IOException("电脑证书不匹配，请重新配对");
                }catch(Exception e){throw new java.security.cert.CertificateException("电脑证书验证失败",e);}
            }
        };
        tls=SSLContext.getInstance("TLS");tls.init(null,new TrustManager[]{manager},new java.security.SecureRandom());
    }
    private SSLSocket open(int sid)throws Exception{
        SSLSocket socket=(SSLSocket)tls.getSocketFactory().createSocket();
        synchronized(sockets){if(closed){socket.close();throw new IOException("配对已取消");}sockets.add(socket);}
        try{socket.setEnabledProtocols(new String[]{"TLSv1.2"});socket.connect(new InetSocketAddress(host,port),3500);socket.setSoTimeout(5000);socket.setTcpNoDelay(true);socket.startHandshake();
            if(closed)throw new IOException("配对已取消");write(socket,new JSONObject().put("sid",sid).put("token",token));JSONObject reply=read(socket,8192);
            if(!reply.optBoolean("ok"))throw new IOException("配对已失效或连接被拒绝");
            if(closed)throw new IOException("配对已取消");if(sid==0)token=reply.getString("session");return socket;
        }catch(Exception e){synchronized(sockets){sockets.remove(socket);}socket.close();throw e;}
    }
    static void pair(Activity activity,String invitation)throws Exception{
        close();WirelessLink link=new WirelessLink(invitation);current=link;
        try{
            SSLSocket pairing=link.open(0);try{pairing.close();}finally{synchronized(link.sockets){link.sockets.remove(pairing);}}
            BridgeService service=BridgeService.instance;if(service==null)throw new IOException("请先启动 PhoneBridge 服务");
            for(int sid:new int[]{2,3,4,1}){SSLSocket socket=link.open(sid);socket.setSoTimeout(0);service.acceptWireless(socket,sid);}
            // PC opens the panel only after all channels and capabilities are ready.
        }catch(Exception e){close();throw e;}
    }
    static JSONObject request(String path,JSONObject body)throws Exception{
        WirelessLink link=current;if(link==null)throw new IOException("无线未连接");
        SSLSocket socket=link.open(5);try{socket.setSoTimeout(18000);JSONObject request=new JSONObject().put("path",path);if(body!=null)request.put("body",body);write(socket,request);
            JSONObject result=read(socket,3*1024*1024);if(result.has("error"))throw new IOException(result.optString("error"));return result;}
        finally{synchronized(link.sockets){link.sockets.remove(socket);}socket.close();}
    }
    static synchronized void close(){WirelessLink link=current;current=null;if(link!=null){link.closed=true;java.util.List<SSLSocket> copy;synchronized(link.sockets){copy=new java.util.ArrayList<>(link.sockets);link.sockets.clear();}for(SSLSocket socket:copy)try{socket.close();}catch(Exception ignored){}link.token="";}}
    private static void write(SSLSocket socket,JSONObject object)throws Exception{socket.getOutputStream().write((object.toString()+"\n").getBytes("UTF-8"));socket.getOutputStream().flush();}
    private static JSONObject read(SSLSocket socket,int limit)throws Exception{ByteArrayOutputStream bytes=new ByteArrayOutputStream();InputStream input=socket.getInputStream();
        while(bytes.size()<=limit){int next=input.read();if(next<0)throw new EOFException("无线连接中断");if(next==10)return new JSONObject(bytes.toString("UTF-8"));bytes.write(next);}throw new IOException("无线响应过大");}
}
