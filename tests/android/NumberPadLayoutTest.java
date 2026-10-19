package com.phonebridge.app;
public final class NumberPadLayoutTest {
    private static int count;
    private static void check(boolean condition){if(!condition)throw new AssertionError("NumberPad layout case "+count);count++;}
    public static void main(String[] args){
        for(float[] size:new float[][]{{2404,1080},{1280,480},{800,360}}){
            for(NumberPadLayout.Key key:NumberPadLayout.KEYS){float[] b=NumberPadLayout.bounds(key,size[0],size[1],8,2);
                check(b[0]>=8&&b[1]>=8&&b[2]<=size[0]-8&&b[3]<=size[1]-8&&b[2]>b[0]&&b[3]>b[1]);
                check(NumberPadLayout.hit((b[0]+b[2])/2,(b[1]+b[3])/2,size[0],size[1],8,2)==key);
                check(NumberPadLayout.hit(b[0]+1,b[3]-1,size[0],size[1],8,2)==key);
            }
            check(NumberPadLayout.hit(-1,50,size[0],size[1],8,2)==null);
            check(NumberPadLayout.hit(size[0],50,size[0],size[1],8,2)==null);
            check(NumberPadLayout.hit(9,9,size[0],size[1],8,2)==null);
            for(NumberPadLayout.Key key:NumberPadLayout.KEYS){if(key.value.length()==1&&Character.isDigit(key.value.charAt(0))){
                int digit=Integer.parseInt(key.value);check(key.row==(digit==0?4:1+(digit-1)/3));check(key.column==(digit==0?0:(digit-1)%3));}}
        }
        check(NumberPadLayout.hit(0,0,0,0,8,2)==null);
        check(NumberPadLayout.hit(Float.NaN,0,800,360,8,2)==null);
        System.out.println("PASS "+count+" NumberPad layout cases");
    }
}
