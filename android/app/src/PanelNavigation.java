package com.phonebridge.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Rect;
import android.view.*;
import android.widget.ScrollView;
import android.widget.Toast;
import org.json.JSONObject;

/** Cancels child input before capturing multi-finger navigation: no volume side effects. */
final class PanelNavigation {
    interface Dispatch{boolean send(MotionEvent event);}
    private final Activity activity;private final Runnable back,panel,desktop;
    private boolean consuming,edge,scrolled;private int count;
    private float startX,startY,lastY,dx,dy;private ScrollView scroll;
    PanelNavigation(Activity activity,Runnable back,Runnable panel,Runnable desktop){this.activity=activity;this.back=back;this.panel=panel;this.desktop=desktop;}
    private float center(MotionEvent event,boolean x){float sum=0;for(int i=0;i<event.getPointerCount();i++)sum+=x?event.getX(i):event.getY(i);return sum/event.getPointerCount();}
    private void cancelChild(MotionEvent event,Dispatch original){MotionEvent cancel=MotionEvent.obtain(event);cancel.setAction(MotionEvent.ACTION_CANCEL);original.send(cancel);cancel.recycle();}
    private ScrollView scrollAt(View view,int x,int y){
        Rect rectangle=new Rect();if(!view.getGlobalVisibleRect(rectangle)||!rectangle.contains(x,y))return null;
        if(view instanceof ScrollView)return (ScrollView)view;
        if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){ScrollView found=scrollAt(group.getChildAt(i),x,y);if(found!=null)return found;}}
        return null;
    }
    boolean touch(MotionEvent e,Dispatch original){
        int action=e.getActionMasked();float density=activity.getResources().getDisplayMetrics().density;
        if(action==MotionEvent.ACTION_DOWN){consuming=false;scrolled=false;count=1;startX=e.getX();startY=lastY=e.getY();dx=dy=0;edge=startX<24*density;scroll=scrollAt(activity.getWindow().getDecorView(),(int)e.getRawX(),(int)e.getRawY());return false;}
        if(action==MotionEvent.ACTION_POINTER_DOWN){
            if(!consuming)cancelChild(e,original);consuming=true;count=Math.max(count,e.getPointerCount());
            startX=center(e,true);startY=lastY=center(e,false);dx=dy=0;scrolled=false;return true;
        }
        if(action==MotionEvent.ACTION_MOVE){
            if(consuming&&e.getPointerCount()<count)return true;
            float x=center(e,true),y=center(e,false);dx=x-startX;dy=y-startY;
            if(!consuming&&edge&&"back".equals(PanelGesture.classify(1,dx,dy,density,true))){cancelChild(e,original);consuming=true;}
            if(consuming&&count==2&&e.getPointerCount()==2&&scroll!=null&&(scrolled||Math.abs(dy)>24*density&&Math.abs(dy)>Math.abs(dx)*1.5f)){scroll.scrollBy(0,Math.round(lastY-y));scrolled=true;}
            lastY=y;return consuming;
        }
        if(action==MotionEvent.ACTION_UP){
            boolean captured=consuming;consuming=false;
            if(captured&&!scrolled){String chosen=PanelGesture.classify(count,dx,dy,density,edge);if(chosen.equals("back"))back.run();else if(chosen.equals("panel"))panel.run();else if(chosen.equals("desktop"))desktop.run();}
            return captured;
        }
        if(action==MotionEvent.ACTION_CANCEL){boolean captured=consuming;consuming=false;return captured;}
        return consuming;
    }
    static void panel(Activity activity){activity.startActivity(new Intent(activity,DashboardActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP));}
    static void desktop(Activity activity){
        new Thread(() -> {try{PanelConnection.request(activity,"/api/dashboard/desktop",new JSONObject());activity.runOnUiThread(() -> activity.finish());}
            catch(Exception error){activity.runOnUiThread(() -> Toast.makeText(activity,"返回副屏失败："+error.getMessage(),Toast.LENGTH_LONG).show());}},"pb-nav-desktop").start();
    }
    static void help(Activity activity){PanelTheme.dialog(activity).setTitle("触控板式导航")
        .setMessage("双指右滑 / 左边缘右滑：返回上页\n三指上滑：控制面板主页\n三指下滑：电脑触控副屏\n详情双指上下滑：滚动参数\n单指上下滑：面板/歌词页音量\n\n若 vivo 三指截屏抢占手势，请使用页面按钮，或在手机自行关闭三指截屏。手势只在 PhoneBridge 面板页面生效。")
        .setPositiveButton("知道了",null).show();}
}
