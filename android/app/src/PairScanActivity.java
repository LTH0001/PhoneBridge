package com.phonebridge.app;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.*;
import android.media.Image;
import android.media.ImageReader;
import android.os.*;
import android.view.*;
import android.widget.*;
import com.google.zxing.*;
import com.google.zxing.common.HybridBinarizer;
import java.util.*;

/** Local QR decode only: no photos are saved or sent to the computer. */
public final class PairScanActivity extends Activity {
    private TextureView preview;private TextView hint;private CameraDevice camera;private CameraCaptureSession session;
    private ImageReader reader;private HandlerThread thread;private Handler handler;private boolean closed,found;private long last;
    @Override public void onCreate(Bundle state){super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);LinearLayout root=new LinearLayout(this);root.setOrientation(1);root.setBackgroundColor(0xff0b1520);
        hint=new TextView(this);hint.setText("对准电脑 PhoneBridge 的配对二维码 · 不保存照片");hint.setTextColor(0xffe9f1fb);hint.setTextSize(16);root.addView(hint);
        preview=new TextureView(this);root.addView(preview,new LinearLayout.LayoutParams(-1,0,1));
        root.addView(PanelStyle.button(this,"取消扫码",false,v -> finish()));setContentView(root);
        if(checkSelfPermission(android.Manifest.permission.CAMERA)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{android.Manifest.permission.CAMERA},8);return;}
        startPreview();
    }
    @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] results){super.onRequestPermissionsResult(code,permissions,results);if(code==8&&results.length>0&&results[0]==PackageManager.PERMISSION_GRANTED)startPreview();else finish();}
    private void startPreview(){closed=false;thread=new HandlerThread("pb-qr-camera");thread.start();handler=new Handler(thread.getLooper());
        preview.setSurfaceTextureListener(new TextureView.SurfaceTextureListener(){
            public void onSurfaceTextureAvailable(SurfaceTexture texture,int w,int h){open(texture);}
            public void onSurfaceTextureSizeChanged(SurfaceTexture t,int w,int h){}
            public boolean onSurfaceTextureDestroyed(SurfaceTexture t){release();return true;}
            public void onSurfaceTextureUpdated(SurfaceTexture t){}
        });if(preview.isAvailable())open(preview.getSurfaceTexture());
    }
    private void open(SurfaceTexture texture){
        try{CameraManager manager=(CameraManager)getSystemService(CAMERA_SERVICE);String id=null;android.util.Size size=null;
            for(String candidate:manager.getCameraIdList()){CameraCharacteristics info=manager.getCameraCharacteristics(candidate);Integer facing=info.get(CameraCharacteristics.LENS_FACING);
                if(facing!=null&&facing==CameraCharacteristics.LENS_FACING_BACK){id=candidate;android.util.Size[] sizes=info.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP).getOutputSizes(android.graphics.ImageFormat.YUV_420_888);
                    for(android.util.Size s:sizes)if(s.getWidth()<=1280&&s.getHeight()<=960&&(size==null||s.getWidth()*s.getHeight()>size.getWidth()*size.getHeight()))size=s;
                    break;}}
            if(id==null||size==null)throw new Exception("没有可用后置摄像头");
            reader=ImageReader.newInstance(size.getWidth(),size.getHeight(),android.graphics.ImageFormat.YUV_420_888,2);reader.setOnImageAvailableListener(this::decode,handler);texture.setDefaultBufferSize(size.getWidth(),size.getHeight());
            manager.openCamera(id,new CameraDevice.StateCallback(){
                public void onOpened(CameraDevice device){if(closed){device.close();return;}camera=device;
                    try{Surface surface=new Surface(texture);CaptureRequest.Builder request=device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);request.addTarget(surface);request.addTarget(reader.getSurface());request.set(CaptureRequest.CONTROL_AF_MODE,CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE);
                        device.createCaptureSession(Arrays.asList(surface,reader.getSurface()),new CameraCaptureSession.StateCallback(){
                            public void onConfigured(CameraCaptureSession s){if(closed){s.close();return;}session=s;try{s.setRepeatingRequest(request.build(),null,handler);}catch(Exception e){failure();}}
                            public void onConfigureFailed(CameraCaptureSession s){failure();}
                        },handler);
                    }catch(Exception e){failure();}}
                public void onDisconnected(CameraDevice device){device.close();failure();}
                public void onError(CameraDevice device,int error){device.close();failure();}
            },handler);
        }catch(Exception e){failure();}
    }
    private void decode(ImageReader source){Image image=null;
        try{image=source.acquireLatestImage();if(image==null||closed||found||SystemClock.elapsedRealtime()-last<250)return;last=SystemClock.elapsedRealtime();
            Image.Plane plane=image.getPlanes()[0];java.nio.ByteBuffer buffer=plane.getBuffer();int w=image.getWidth(),h=image.getHeight(),stride=plane.getRowStride(),pixel=plane.getPixelStride();byte[] luminance=new byte[w*h];
            for(int y=0;y<h;y++)for(int x=0;x<w;x++)luminance[y*w+x]=buffer.get(y*stride+x*pixel);
            BinaryBitmap bitmap=new BinaryBitmap(new HybridBinarizer(new PlanarYUVLuminanceSource(luminance,w,h,0,0,w,h,false)));
            Map<DecodeHintType,Object> hints=new EnumMap<>(DecodeHintType.class);hints.put(DecodeHintType.POSSIBLE_FORMATS,Collections.singletonList(BarcodeFormat.QR_CODE));hints.put(DecodeHintType.TRY_HARDER,Boolean.TRUE);
            String code=new MultiFormatReader().decode(bitmap,hints).getText();if(!code.startsWith("pbw1:")||code.length()>256)return;found=true;
            runOnUiThread(() -> {setResult(RESULT_OK,new Intent().putExtra("invitation",code));finish();});
        }catch(Exception ignored){}finally{if(image!=null)image.close();}
    }
    private void failure(){runOnUiThread(() -> hint.setText("摄像头不可用，请停止外设摄像头后重试，或返回粘贴配对信息"));}
    private synchronized void release(){closed=true;if(session!=null)session.close();if(camera!=null)camera.close();if(reader!=null)reader.close();if(thread!=null)thread.quitSafely();}
    @Override protected void onPause(){release();super.onPause();}
}
