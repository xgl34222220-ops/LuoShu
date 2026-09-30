package io.github.xgl34222220.luoshu.fontcontract;

import android.graphics.*;
import android.graphics.fonts.FontFamily;
import java.io.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.*;
import org.json.JSONObject;

/** Framework command-line probe in the existing adb-shell domain. No root or policy edits. */
public final class PlatformXmlProbe {
    public static void main(String[] args) throws Exception {
        JSONObject report=new JSONObject();
        report.put("context","adb-shell-app_process");
        report.put("systemConfigurationChanged",false);
        try {
            File source=new File(args[0]), config=new File(args[1]);
            StringBuilder xml=new StringBuilder("<familyset><family name=\"sans-serif\">");
            for(int w=100;w<=900;w+=100)xml.append("<font weight=\"").append(w)
                .append("\" style=\"normal\" index=\"0\" postScriptName=\"").append(args[2])
                .append("\">").append(source.getName()).append("</font>");
            xml.append("</family></familyset>");
            Files.write(config.toPath(),xml.toString().getBytes(StandardCharsets.UTF_8));
            Class<?> parser=Class.forName("android.graphics.FontListParser");
            Method parse=parser.getMethod("parse",String.class,String.class,String.class,String.class,Map.class,long.class,int.class);
            Object parsed=parse.invoke(null,config.getAbsolutePath(),source.getParent()+"/",null,null,null,0L,0);
            Method builder=null;
            for(Method m:Class.forName("android.graphics.fonts.SystemFonts").getMethods())
                if(m.getName().equals("buildSystemFallback")&&m.getParameterCount()==1){builder=m;break;}
            if(builder==null)throw new NoSuchMethodException("SystemFonts.buildSystemFallback");
            Object familyArray=((Map<?,?>)builder.invoke(null,parsed)).get("sans-serif");
            if(familyArray==null||Array.getLength(familyArray)==0)throw new AssertionError("empty parsed family");
            FontFamily family=(FontFamily)Array.get(familyArray,0);
            Typeface face=new Typeface.CustomFallbackBuilder(family).setSystemFallback("sans-serif").build();
            Bitmap bitmap=Bitmap.createBitmap(192,128,Bitmap.Config.ARGB_8888);
            Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);paint.setTypeface(face);paint.setTextSize(72);
            paint.setColor(Color.BLACK);paint.setHinting(Paint.HINTING_OFF);
            new Canvas(bitmap).drawText("A1中",24,96,paint);
            int[] pixels=new int[192*128];bitmap.getPixels(pixels,0,192,0,0,192,128);
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream data=new DataOutputStream(bytes);
            for(int pixel:pixels)data.writeInt(pixel);
            StringBuilder sha=new StringBuilder();
            for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes.toByteArray()))sha.append(String.format(Locale.ROOT,"%02x",b&255));
            report.put("rasterSha256",sha.toString());report.put("status","passed");
            report.put("declaredFonts",family.getSize());
        } catch(Throwable error) {
            report.put("status","blocked");report.put("error",error.toString());
            StringWriter trace=new StringWriter();error.printStackTrace(new PrintWriter(trace));report.put("trace",trace.toString());
        }
        System.out.println(report.toString());
        if(!report.optString("status").equals("passed"))System.exit(1);
    }
}
