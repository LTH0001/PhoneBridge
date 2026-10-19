package com.phonebridge.app;

/** Pure Java color policy, also exercised without Android hardware. */
final class PanelPalette {
    static int color(int value,boolean dark){
        if(!dark || (value>>>24)<160)return value;
        int rgb=value&0xffffff,alpha=value&0xff000000;
        switch(rgb){
            case 0x376bc1:case 0x247dae:case 0x4b9cc2:case 0x5277bb:return alpha|0x8bb7ff;
            case 0xa84e48:case 0xcf4e50:return alpha|0xff9d95;
            case 0xf7f8fa:return alpha|0x0b1018;
            case 0xeef0f4:case 0xeef3f9:return alpha|0x101925;
        }
        int r=(rgb>>>16)&255,g=(rgb>>>8)&255,b=rgb&255;
        int hi=Math.max(r,Math.max(g,b)),lo=Math.min(r,Math.min(g,b));
        if(lo>=175 && hi-lo<=65)return alpha|(lo>=238?0x151e2b:0x29384e);
        if(hi<=150 && hi-lo<=72)return alpha|(hi<100?0xe7edf7:0xa6b6ce);
        return value;
    }
}
