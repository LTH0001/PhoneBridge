package com.phonebridge.app;
import org.json.*;
import java.util.Locale;

/** Typed fields: retain unavailable rows, booleans and zero without coercion. */
final class HardwareFields {
    static String format(JSONObject data){
        JSONArray rows=data.optJSONArray("fields");if(rows==null||rows.length()==0)return "";
        StringBuilder text=new StringBuilder();String section="";
        for(int i=0;i<rows.length();i++){
            JSONObject row=rows.optJSONObject(i);if(row==null)continue;
            String next=row.optString("section","概览");if(!next.equals(section)){if(text.length()>0)text.append("\n");text.append("▎ ").append(next).append("\n");section=next;}
            text.append(row.optString("label")).append("   ");Object value=row.opt("value");
            if(value==null||value==JSONObject.NULL)text.append("不可用 · ").append(row.optString("note","系统未提供"));
            else if(value instanceof Boolean)text.append((Boolean)value?"是 / 已启用":"否 / 未启用");
            else if(value instanceof Number){double number=((Number)value).doubleValue();text.append(Double.isFinite(number)?String.format(Locale.US,Math.abs(number-Math.rint(number))<.00001?"%.0f":"%.3f",number):"不可用");}
            else text.append(value.toString());
            if(value!=null&&value!=JSONObject.NULL&&!row.optString("unit").isEmpty())text.append(" ").append(row.optString("unit"));
            text.append("\n");
        }
        text.append("\n").append(data.optString("note"));return text.toString();
    }
}
