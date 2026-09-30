package io.github.xgl34222220.luoshu.fontcontract;

import android.app.Instrumentation;
import android.app.Activity;
import android.content.Context;
import android.graphics.*;
import android.graphics.fonts.Font;
import android.graphics.fonts.FontFamily;
import android.graphics.fonts.FontStyle;
import android.os.*;
import org.json.JSONObject;
import java.io.*;
import java.lang.reflect.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** CI-only native rendering/configuration probe. Never changes system settings. */
public final class Runner extends Instrumentation {
    private Bundle arguments;
    private Context context;
    private File root;
    private JSONObject report;
    @Override public void onCreate(Bundle args) { arguments=args; super.onCreate(args); start(); }
    private static void require(boolean condition,String message) { if(!condition)throw new AssertionError(message); }
    private static String hash(byte[] bytes) throws Exception {
        StringBuilder b=new StringBuilder();
        for(byte x:MessageDigest.getInstance("SHA-256").digest(bytes))b.append(String.format(Locale.ROOT,"%02x",x&255));
        return b.toString();
    }
    private File asset(String name) throws Exception {
        byte[] bytes;
        try(InputStream in=context.getAssets().open(name)){ bytes=in.readAllBytes(); }
        File file=new File(root,hash(bytes).substring(0,24)+".ttf");
        if(!file.exists())Files.write(file.toPath(),bytes);
        require(hash(Files.readAllBytes(file.toPath())).equals(hash(bytes)),"immutable asset changed");
        return file;
    }
    private Typeface face(File file,int weight,boolean allWeights) throws Exception {
        FontFamily.Builder family=null;
        for(int w=allWeights?100:400;w<=(allWeights?900:400);w+=100){
            Font font=new Font.Builder(file).setWeight(w).setSlant(FontStyle.FONT_SLANT_UPRIGHT).build();
            require(font.getAxes()==null||font.getAxes().length==0,"fixed asset unexpectedly variable");
            if(family==null)family=new FontFamily.Builder(font);else family.addFont(font);
        }
        return new Typeface.CustomFallbackBuilder(family.build()).setSystemFallback("sans-serif")
            .setStyle(new FontStyle(weight,FontStyle.FONT_SLANT_UPRIGHT)).build();
    }
    private String draw(Typeface typeface,String text,String output) throws Exception {
        Bitmap bitmap=Bitmap.createBitmap(192,128,Bitmap.Config.ARGB_8888);
        Canvas canvas=new Canvas(bitmap);Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setTypeface(typeface);paint.setTextSize(72);paint.setColor(Color.BLACK);paint.setHinting(Paint.HINTING_OFF);
        canvas.drawText(text,24,96,paint);
        int[] pixels=new int[192*128];bitmap.getPixels(pixels,0,192,0,0,192,128);
        boolean ink=false;ByteArrayOutputStream raw=new ByteArrayOutputStream();DataOutputStream data=new DataOutputStream(raw);
        for(int value:pixels){if((value>>>24)!=0)ink=true;data.writeInt(value);}require(ink,"empty render: "+text);
        if(output!=null)try(FileOutputStream out=new FileOutputStream(new File(root,output))){bitmap.compress(Bitmap.CompressFormat.PNG,100,out);}
        bitmap.recycle();return hash(raw.toByteArray());
    }
    private JSONObject frameworkXml(File source,String psName) {
        JSONObject result=new JSONObject();
        try {
            StringBuilder xml=new StringBuilder("<?xml version=\"1.0\"?><familyset><family name=\"sans-serif\">");
            for(int w=100;w<=900;w+=100)xml.append("<font weight=\"").append(w).append("\" style=\"normal\" index=\"0\" postScriptName=\"")
                .append(psName).append("\">").append(source.getName()).append("</font>");
            xml.append("</family></familyset>");
            File config=new File(root,"fixed-fonts.xml");Files.writeString(config.toPath(),xml.toString());
            Class<?> parser=Class.forName("android.graphics.FontListParser");Method parse=null;
            for(Method m:parser.getMethods()) {
                Class<?>[] p=m.getParameterTypes();
                if(m.getName().equals("parse")&&p.length==7&&p[0]==String.class&&p[1]==String.class&&p[2]==String.class&&p[3]==String.class&&p[5]==long.class&&p[6]==int.class){parse=m;break;}
            }
            if(parse==null)throw new NoSuchMethodException("public seven-argument FontListParser.parse not exposed");
            Object configObject=parse.invoke(null,config.getAbsolutePath(),root.getAbsolutePath()+"/",null,null,null,0L,0);
            Class<?> systemFonts=Class.forName("android.graphics.fonts.SystemFonts");Method build=null;
            for(Method m:systemFonts.getMethods())if(m.getName().equals("buildSystemFallback")&&m.getParameterCount()==1){build=m;break;}
            if(build==null)throw new NoSuchMethodException("SystemFonts.buildSystemFallback not exposed");
            Object map=build.invoke(null,configObject);Object families=((Map<?,?>)map).get("sans-serif");
            require(families!=null&&Array.getLength(families)>0,"framework did not construct family");
            FontFamily first=(FontFamily)Array.get(families,0);
            Typeface fromXml=new Typeface.CustomFallbackBuilder(first).setSystemFallback("sans-serif").build();
            require(draw(fromXml,"A1中",null).equals(draw(face(source,400,true),"A1中",null)),"framework XML raster differs");
            result.put("status","passed");result.put("consumer","platform FontListParser + SystemFonts + native renderer");
        } catch(Throwable error) {
            try{boolean inaccessible=error instanceof NoSuchMethodException||error instanceof ClassNotFoundException||error instanceof IllegalAccessException||error instanceof SecurityException||error instanceof LinkageError;result.put("status",inaccessible?"unavailable":"failed");result.put("reason",error.getClass().getSimpleName()+": "+error.getMessage());}catch(Exception ignored){}
        }
        return result;
    }
    @Override public void onStart() {
        int resultCode=Activity.RESULT_CANCELED;
        String phase=arguments==null?"before":arguments.getString("phase","before");
        try {
            context=getTargetContext();root=context.getFilesDir();report=new JSONObject();
            report.put("phase",phase);report.put("sdk",Build.VERSION.SDK_INT);report.put("fingerprint",Build.FINGERPRINT);
            report.put("moduleMountTested",false);report.put("systemFontConfigMutated",false);report.put("hookUsed",false);
            JSONObject fixture;try(InputStream in=context.getAssets().open("fixture.json")){fixture=new JSONObject(new String(in.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8));}
            File composite=asset("composite.ttf"),latin=asset("latin.ttf"),digit=asset("digit.ttf"),cjk=asset("cjk.ttf");
            Typeface mixed=face(composite,400,true);JSONObject renders=new JSONObject();
            String[] text={"A","1","中"};File[] donor={latin,digit,cjk};
            for(int i=0;i<text.length;i++){
                String mixedHash=draw(mixed,text[i],"role-"+i+".png");
                require(mixedHash.equals(draw(face(donor[i],400,false),text[i],null)),"donor identity mismatch "+text[i]);
                renders.put(text[i],mixedHash);
            }
            require(!draw(mixed,"A",null).equals(draw(face(cjk,400,false),"A",null)),"identity check is not discriminating");
            for(int w=100;w<=900;w+=100)require(draw(face(composite,w,true),"A1中",null).equals(draw(mixed,"A1中",null)),"fixed selection changed at "+w);
            for(String untouched:new String[]{"Ω","😀"}){
                String value=draw(mixed,untouched,null);
                require(value.equals(draw(Typeface.DEFAULT,untouched,null)),"fallback changed "+untouched);
                renders.put(untouched,value);
            }
            report.put("nativeStaticRoleIdentity","passed");report.put("fixedWeights100to900","passed");
            report.put("emojiAndUnknownScriptFallback","passed");report.put("renders",renders);
            // Fresh generation paths avoid mutating bytes under a cached Typeface.
            Typeface alternate=face(cjk,400,true);require(!draw(alternate,"A",null).equals(draw(mixed,"A",null)),"alternate asset not visible");
            require(draw(face(composite,400,true),"A",null).equals(renders.getString("A")),"rollback asset differs");
            report.put("immutablePathSwitchAndReturn","passed");
            File baseline=new File(root,"baseline.json");
            if(phase.equals("before"))Files.writeString(baseline.toPath(),renders.toString());
            else {JSONObject old=new JSONObject(Files.readString(baseline.toPath()));for(String key:text)require(old.getString(key).equals(renders.getString(key)),"reboot raster changed");report.put("emulatorRebootPersistence","passed");}
            report.put("frameworkXmlConsumer",frameworkXml(composite,fixture.getString("postScriptName")));
            report.put("status","passed-native-data-gate");resultCode=Activity.RESULT_OK;
        } catch(Throwable error) {
            if(report==null)report=new JSONObject();
            try{report.put("status","failed");report.put("error",error.toString());StringWriter trace=new StringWriter();error.printStackTrace(new PrintWriter(trace));report.put("trace",trace.toString());}catch(Exception ignored){}
        }
        try{Files.writeString(new File(root,"report-"+phase+".json").toPath(),report.toString(2));}catch(Exception ignored){}
        Bundle output=new Bundle();output.putString("stream",report.toString());finish(resultCode,output);
    }
}
