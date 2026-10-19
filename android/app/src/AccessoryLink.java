package com.phonebridge.app;
import android.app.*;
import android.content.*;
import android.hardware.usb.*;
import android.os.*;
import java.io.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;
import org.json.JSONObject;

/** Android USB Accessory, independent of USB debugging and network access. */
final class AccessoryLink {
    private static volatile AccessoryLink current;
    private static boolean permissionRequested;
    private final ParcelFileDescriptor descriptor;private final InputStream input;private final OutputStream output;
    private final ConcurrentHashMap<Long,CompletableFuture<JSONObject>> waiting=new ConcurrentHashMap<>();
    private final AtomicLong sequence=new AtomicLong();
    private AccessoryLink(ParcelFileDescriptor descriptor)throws IOException{this.descriptor=descriptor;
        // Accessory reads must drain an entire USB packet; buffer before PB framing.
        input=new BufferedInputStream(new FileInputStream(descriptor.getFileDescriptor()),65536);output=new FileOutputStream(descriptor.getFileDescriptor());}
    static boolean active(){return current!=null;}
    static boolean matches(UsbAccessory accessory){return accessory!=null&&"PhoneBridge".equals(accessory.getManufacturer())&&"PhoneBridge USB".equals(accessory.getModel());}
    static void open(Context context,UsbAccessory accessory)throws Exception{
        if(!matches(accessory))throw new IOException("不是 PhoneBridge USB 配件");
        UsbManager manager=(UsbManager)context.getSystemService(Context.USB_SERVICE);
        if(!manager.hasPermission(accessory))throw new SecurityException("请在手机确认 USB 外设权限");
        if(current!=null)return;
        ParcelFileDescriptor descriptor=manager.openAccessory(accessory);if(descriptor==null)throw new IOException("USB 外设打开失败");
        AccessoryLink link=new AccessoryLink(descriptor);current=link;
        new Thread(() -> {
            try{for(int i=0;i<30&&BridgeService.instance==null;i++)Thread.sleep(100);
                BridgeService service=BridgeService.instance;if(service==null)throw new IOException("服务未启动");
                service.serveAccessory(link.input,link.output);
            }catch(Exception e){android.util.Log.w("PB.Accessory","USB accessory disconnected: "+e.getClass().getSimpleName());}
            finally{if(current==link)close();}
        },"pb-usb-accessory").start();
    }
    static JSONObject request(String path,JSONObject body)throws Exception{
        AccessoryLink link=current;if(link==null)throw new IOException("USB 外设未连接");
        if(link.waiting.size()>=8)throw new IOException("USB 请求繁忙");
        long id=link.sequence.incrementAndGet();CompletableFuture<JSONObject> reply=new CompletableFuture<>();link.waiting.put(id,reply);
        try{JSONObject request=new JSONObject().put("path",path);if(body!=null)request.put("body",body);
            byte[] packet=Proto.frame(0xc0,5,id,0,0,request.toString().getBytes("UTF-8"));
            synchronized(link.output){link.output.write(packet);link.output.flush();}
            JSONObject result=reply.get(18,TimeUnit.SECONDS);if(result.has("error"))throw new IOException(result.optString("error"));return result;
        }finally{link.waiting.remove(id);}
    }
    static void response(Proto.Frame frame)throws Exception{AccessoryLink link=current;if(link==null)return;CompletableFuture<JSONObject> reply=link.waiting.get(frame.sequence);if(reply!=null)reply.complete(new JSONObject(frame.payloadJson()));}
    static synchronized void close(){AccessoryLink link=current;current=null;if(link!=null){
        for(CompletableFuture<JSONObject> reply:link.waiting.values())reply.completeExceptionally(new IOException("USB 已拔出"));link.waiting.clear();
        try{link.descriptor.close();}catch(Exception ignored){}
    }}
    static void attached(Activity activity){
        UsbManager manager=(UsbManager)activity.getSystemService(Context.USB_SERVICE);UsbAccessory[] accessories=manager.getAccessoryList();if(accessories==null)return;
        for(UsbAccessory accessory:accessories)if(matches(accessory)){
            if(manager.hasPermission(accessory)){try{open(activity,accessory);}catch(Exception e){android.widget.Toast.makeText(activity,e.getMessage(),1).show();}}
            else{if(permissionRequested)return;permissionRequested=true;Intent intent=new Intent("com.phonebridge.app.USB_PERMISSION").setPackage(activity.getPackageName());
                PendingIntent permission=PendingIntent.getBroadcast(activity,0,intent,PendingIntent.FLAG_MUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);manager.requestPermission(accessory,permission);}
            break;
        }
    }
    static void retry(Activity activity){permissionRequested=false;attached(activity);}
}
