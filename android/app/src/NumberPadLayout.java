package com.phonebridge.app;

/** Pure, span-aware layout shared by drawing, hit testing and desktop JDK tests. */
final class NumberPadLayout {
    static final class Key {
        final String label,value;final int column,row,columns,rows;
        Key(String label,String value,int column,int row,int columns,int rows){this.label=label;this.value=value;this.column=column;this.row=row;this.columns=columns;this.rows=rows;}
    }
    static final Key[] KEYS={
        new Key("⌫","backspace",0,0,1,1),new Key("÷","/",1,0,1,1),new Key("×","*",2,0,1,1),new Key("−","-",3,0,1,1),
        new Key("1","1",0,1,1,1),new Key("2","2",1,1,1,1),new Key("3","3",2,1,1,1),new Key("+","+",3,1,1,2),
        new Key("4","4",0,2,1,1),new Key("5","5",1,2,1,1),new Key("6","6",2,2,1,1),
        new Key("7","7",0,3,1,1),new Key("8","8",1,3,1,1),new Key("9","9",2,3,1,1),new Key("↵","enter",3,3,1,2),
        new Key("0","0",0,4,2,1),new Key(".",".",2,4,1,1)
    };
    static float[] bounds(Key key,float width,float height,float inset,float gap){
        float cellW=(width-2*inset)/4,cellH=(height-2*inset)/5;
        return new float[]{inset+key.column*cellW+gap,inset+key.row*cellH+gap,
            inset+(key.column+key.columns)*cellW-gap,inset+(key.row+key.rows)*cellH-gap};
    }
    static Key hit(float x,float y,float width,float height,float inset,float gap){
        if(width<=2*inset||height<=2*inset||Float.isNaN(x)||Float.isNaN(y))return null;
        for(Key key:KEYS){float[] b=bounds(key,width,height,inset,gap);if(x>=b[0]&&x<b[2]&&y>=b[1]&&y<b[3])return key;}
        return null;
    }
}
