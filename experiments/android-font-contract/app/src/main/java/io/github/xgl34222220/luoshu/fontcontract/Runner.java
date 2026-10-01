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
import org.json.JSONArray;
import java.io.*;
import java.lang.reflect.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
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
            File config=new File(root,"fixed-fonts.xml");Files.write(config.toPath(),xml.toString().getBytes(StandardCharsets.UTF_8));
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
    private Typeface expectedSystemRole(String role) throws Exception {
        String path=arguments.getString("expected"+role+"Path","");
        if(path.isEmpty())return face(asset("composite.ttf"),400,true);
        Font.Builder builder=new Font.Builder(new File(path))
            .setTtcIndex(Integer.parseInt(arguments.getString("expected"+role+"Face","0")))
            .setWeight(400).setSlant(FontStyle.FONT_SLANT_UPRIGHT);
        String raw=arguments.getString("expected"+role+"Axes","");
        if(!raw.isEmpty()) {
            ArrayList<android.graphics.fonts.FontVariationAxis> axes=new ArrayList<>();
            for(String item:raw.split(",")) {String[] pair=item.split("=",2);axes.add(new android.graphics.fonts.FontVariationAxis(pair[0],Float.parseFloat(pair[1])));}
            builder.setFontVariationSettings(axes.toArray(new android.graphics.fonts.FontVariationAxis[0]));
        }
        return new Typeface.CustomFallbackBuilder(new FontFamily.Builder(builder.build()).build()).setSystemFallback("sans-serif").build();
    }
    private String fontBufferHash(Font font) throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");java.nio.ByteBuffer data=font.getBuffer().duplicate();data.rewind();digest.update(data);
        StringBuilder result=new StringBuilder();for(byte value:digest.digest())result.append(String.format(Locale.ROOT,"%02x",value&255));return result.toString();
    }
    private Typeface variableFamily(Font normal,Font italic) throws Exception {
        FontFamily.Builder builder=new FontFamily.Builder(normal);if(italic!=null)builder.addFont(italic);
        FontFamily family=builder.buildVariableFamily();require(family!=null,"variable matching family rejected");
        return new Typeface.CustomFallbackBuilder(family).setSystemFallback("sans-serif").build();
    }
    private JSONObject fixedMatchingAxisProof() throws Exception {
        require(Build.VERSION.SDK_INT>=35,"matching experiment requires public API35");
        File normal=asset("normal-weight-match.ttf"),cjkMatch=asset("cjk-weight-match.ttf");
        File original=new File("/system/fonts/Roboto-Regular.ttf");
        Font italic=new Font.Builder(original).setWeight(400).setSlant(FontStyle.FONT_SLANT_ITALIC)
            .setFontVariationSettings(new android.graphics.fonts.FontVariationAxis[]{new android.graphics.fonts.FontVariationAxis("ital",1),new android.graphics.fonts.FontVariationAxis("wdth",100)}).build();
        String originalSha=fontBufferHash(italic);
        Typeface normalFamily=variableFamily(new Font.Builder(normal).setWeight(400).setSlant(0).build(),italic);
        Typeface cjkFamily=variableFamily(new Font.Builder(cjkMatch).setWeight(400).setSlant(0).build(),null);
        JSONArray evidence=new JSONArray();
        for(int weight:new int[]{1,100,400,450,520,700,900,1000})for(boolean slant:new boolean[]{false,true})for(String sample:new String[]{"A","1","中"}) {
            boolean han=sample.equals("中"),kept=slant&&!han;
            File reference=kept?original:asset(han?"cjk-fixed-reference.ttf":"normal-fixed-reference.ttf");
            Font.Builder rb=new Font.Builder(reference).setWeight(weight).setSlant(kept?1:0);
            if(kept)rb.setFontVariationSettings(new android.graphics.fonts.FontVariationAxis[]{new android.graphics.fonts.FontVariationAxis("wght",weight),new android.graphics.fonts.FontVariationAxis("ital",1),new android.graphics.fonts.FontVariationAxis("wdth",100)});
            Typeface expected=new Typeface.CustomFallbackBuilder(new FontFamily.Builder(rb.build()).build())
                .setSystemFallback("sans-serif").setStyle(new FontStyle(weight,slant?1:0)).build();
            Typeface actual=Typeface.create(han?cjkFamily:normalFamily,weight,slant);
            String raster=draw(actual,sample,null);require(raster.equals(draw(expected,sample,null)),"constant-match/italic raster differs: "+sample+"/"+weight+"/"+slant);
            Paint p=new Paint();p.setTypeface(actual);p.setTextSize(72);
            android.graphics.text.PositionedGlyphs run=android.graphics.text.TextRunShaper.shapeTextRun(sample,0,sample.length(),0,sample.length(),0,0,false,p);
            require(run.glyphCount()==1,"unexpected matching glyph split");Font selected=run.getFont(0);
            String expectedPath=(kept?original:han?cjkMatch:normal).toString();
            require(String.valueOf(selected.getFile()).equals(expectedPath),"constant-match selected wrong source");
            String expectedSha=kept?originalSha:hash(Files.readAllBytes((han?cjkMatch:normal).toPath()));
            require(fontBufferHash(selected).equals(expectedSha),"constant-match source bytes differ");
            JSONObject item=new JSONObject();item.put("sample",sample);item.put("weight",weight);item.put("italic",slant);
            item.put("file",expectedPath);item.put("sha256",expectedSha);item.put("raster",raster);item.put("kind",kept?"original-italic-variation":"fixed-selected-outline");evidence.put(item);
        }
        JSONObject result=new JSONObject();result.put("status","passed");result.put("cases",evidence);
        result.put("scope","App-only public variable-family selection; no system XML or module activation");
        result.put("normalShapeResponse","constant; matching axis is not donor weight variation");return result;
    }
    private void styleMatrixPhase() throws Exception {
        JSONArray cases=new JSONArray(new String(Base64.getDecoder().decode(arguments.getString("styleCases")),StandardCharsets.UTF_8));
        require(cases.length()>0&&cases.length()<=64,"invalid style matrix size");
        JSONArray results=new JSONArray();boolean allVerified=true;int failures=0;
        report.put("cases",results);
        for(int c=0;c<cases.length();c++) {
            JSONObject item=cases.getJSONObject(c);int weight=item.getInt("weight");boolean italic=item.getBoolean("italic");
            String family=item.getString("family"),sample=item.getString("sample");
            require(weight>=1&&weight<=1000,"invalid style matrix weight");
            require(Arrays.asList("sans-serif","sans-serif-condensed","roboto").contains(family),"unsupported matrix family");
            require(Arrays.asList("A","1","中","Ω","😀").contains(sample),"unsupported matrix sample");
            Typeface selected=Typeface.create(Typeface.create(family,Typeface.NORMAL),weight,italic);
            String raster=draw(selected,sample,null);Paint paint=new Paint();paint.setTypeface(selected);paint.setTextSize(72);
            android.graphics.text.PositionedGlyphs glyphs=android.graphics.text.TextRunShaper.shapeTextRun(sample,0,sample.length(),0,sample.length(),0,0,false,paint);
            require(glyphs.glyphCount()>0,"empty matrix glyph run");JSONArray actual=new JSONArray();
            for(int g=0;g<glyphs.glyphCount();g++) {
                Font font=glyphs.getFont(g);JSONObject found=new JSONObject();
                found.put("file",String.valueOf(font.getFile()));found.put("face",font.getTtcIndex());
                found.put("weight",font.getStyle().getWeight());found.put("slant",font.getStyle().getSlant());
                found.put("sha256",fontBufferHash(font));found.put("glyphId",glyphs.getGlyphId(g));
                JSONObject axes=new JSONObject();if(font.getAxes()!=null)for(android.graphics.fonts.FontVariationAxis axis:font.getAxes())axes.put(axis.getTag(),axis.getStyleValue());
                found.put("axes",axes);actual.put(found);
            }
            JSONObject result=new JSONObject(item.toString());result.put("raster",raster);result.put("actualFonts",actual);
            results.put(result);report.put("activeCase",result);
            JSONObject expected=item.optJSONObject("expected");
            if(expected==null){allVerified=false;result.put("verification","observation-only");}
            else try {
                require(actual.length()==1,"unexpected matrix glyph splitting");JSONObject font=actual.getJSONObject(0);
                require(font.getString("file").equals(expected.getString("path")),"matrix source path differs: "+item);
                require(font.getString("sha256").equals(expected.getString("sha256")),"matrix source bytes differ: "+item);
                require(font.getInt("face")==expected.getInt("face"),"matrix face differs: "+item);
                require(font.getInt("weight")==expected.getInt("fontWeight"),"matrix declared font weight differs: "+item);
                require(font.getInt("slant")==expected.getInt("fontSlant"),"matrix declared font slant differs: "+item);
                if(expected.has("raster"))require(raster.equals(expected.getString("raster")),"matrix preserved raster differs: "+item);
                else {
                    Font.Builder builder=new Font.Builder(new File(expected.getString("path"))).setTtcIndex(expected.getInt("face"))
                        .setWeight(expected.getInt("fontWeight")).setSlant(expected.getInt("fontSlant"));
                    JSONObject coordinates=expected.getJSONObject("axes");ArrayList<android.graphics.fonts.FontVariationAxis> axes=new ArrayList<>();
                    for(Iterator<String> it=coordinates.keys();it.hasNext();){String tag=it.next();axes.add(new android.graphics.fonts.FontVariationAxis(tag,(float)coordinates.getDouble(tag)));}
                    builder.setFontVariationSettings(axes.toArray(new android.graphics.fonts.FontVariationAxis[0]));
                    Typeface reference=new Typeface.CustomFallbackBuilder(new FontFamily.Builder(builder.build()).build())
                        .setStyle(new FontStyle(weight,italic?FontStyle.FONT_SLANT_ITALIC:FontStyle.FONT_SLANT_UPRIGHT)).build();
                    require(raster.equals(draw(reference,sample,null)),"matrix expected glyph/shape differs: "+item);
                }
                result.put("verification","passed");
            } catch(AssertionError error) {
                failures++;result.put("verification","failed");result.put("error",error.getMessage());
            }
        }
        report.remove("activeCase");report.put("failedCaseCount",failures);
        report.put("status",failures>0?"failed-style-matrix":allVerified?"passed-style-matrix":"observed-style-matrix");
        Files.write(new File(root,"report-style-matrix.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
        Bundle output=new Bundle();output.putString("stream",report.toString());finish(Activity.RESULT_OK,output);
    }
    private String drawOriginalAxis(JSONObject item,double value) throws Exception {
        Font font=new Font.Builder(new File(item.getString("path"))).setTtcIndex(item.getInt("face"))
            .setWeight(400).setSlant(FontStyle.FONT_SLANT_UPRIGHT)
            .setFontVariationSettings(new android.graphics.fonts.FontVariationAxis[]{
                new android.graphics.fonts.FontVariationAxis(item.getString("tag"),(float)value)}).build();
        require(fontBufferHash(font).equals(item.getString("sha256")),"OEM axis probe bytes changed");
        Bitmap bitmap=Bitmap.createBitmap(192,128,Bitmap.Config.ARGB_8888);
        Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);paint.setTextSize(72);paint.setColor(Color.BLACK);paint.setHinting(Paint.HINTING_OFF);
        new Canvas(bitmap).drawGlyphs(new int[]{item.getInt("glyphId")},0,new float[]{24,96},0,1,font,paint);
        int[] pixels=new int[192*128];bitmap.getPixels(pixels,0,192,0,0,192,128);
        ByteArrayOutputStream raw=new ByteArrayOutputStream();DataOutputStream bytes=new DataOutputStream(raw);boolean ink=false;
        for(int pixel:pixels){bytes.writeInt(pixel);ink|=(pixel>>>24)!=0;}
        bitmap.recycle();require(ink,"empty OEM axis probe");return hash(raw.toByteArray());
    }
    private void stockAxisPhase() throws Exception {
        JSONArray cases=new JSONArray(new String(Base64.getDecoder().decode(arguments.getString("axisCases")),StandardCharsets.UTF_8));
        require(cases.length()<=64,"too many OEM axis probe cases");JSONArray proofs=new JSONArray();
        for(int i=0;i<cases.length();i++) {
            JSONObject item=cases.getJSONObject(i);
            require(item.getString("path").startsWith("/system/fonts/"),"OEM probe escaped system font scope");
            String requested=drawOriginalAxis(item,item.getDouble("requested"));
            String endpoint=drawOriginalAxis(item,item.getDouble("effective"));
            String opposite=drawOriginalAxis(item,item.getDouble("opposite"));
            require(requested.equals(endpoint),"OEM out-of-range coordinate differs from boundary: "+item);
            require(!endpoint.equals(opposite),"OEM axis probe was not discriminating: "+item);
            JSONObject proof=new JSONObject(item.toString());proof.put("requestedRaster",requested);proof.put("endpointRaster",endpoint);
            proof.put("oppositeRaster",opposite);proofs.put(proof);
        }
        report.put("cases",proofs);report.put("status","passed-stock-axis-gate");
        Files.write(new File(root,"report-stock-axis.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
        Bundle output=new Bundle();output.putString("stream",report.toString());finish(Activity.RESULT_OK,output);
    }
    private void systemPhase(String phase) throws Exception {
        JSONObject renders=new JSONObject();
        for(String text:new String[]{"A","1","中","Ω","😀"})renders.put(text,draw(Typeface.DEFAULT,text,null));
        report.put("renders",renders);
        JSONObject actualFonts=new JSONObject();
        for(String sample:new String[]{"A","1","中","Ω","😀"}){
            Paint inspect=new Paint();inspect.setTypeface(Typeface.DEFAULT);inspect.setTextSize(72);
            android.graphics.text.PositionedGlyphs glyphs=android.graphics.text.TextRunShaper.shapeTextRun(sample,0,sample.length(),0,sample.length(),0,0,false,inspect);
            org.json.JSONArray paths=new org.json.JSONArray();
            for(int i=0;i<glyphs.glyphCount();i++){
                android.graphics.fonts.Font font=glyphs.getFont(i);
                JSONObject entry=new JSONObject();entry.put("file",String.valueOf(font.getFile()));entry.put("ttcIndex",font.getTtcIndex());entry.put("style",font.getStyle().toString());entry.put("sha256",fontBufferHash(font));entry.put("glyphId",glyphs.getGlyphId(i));paths.put(entry);
            }
            actualFonts.put(sample,paths);
        }
        report.put("actualDefaultFonts",actualFonts);
        File baseline=new File(root,"system-baseline.json");
        if(phase.equals("system-baseline"))Files.write(baseline.toPath(),renders.toString().getBytes(StandardCharsets.UTF_8));
        else {
            JSONObject old=new JSONObject(new String(Files.readAllBytes(baseline.toPath()),StandardCharsets.UTF_8));
            for(String text:new String[]{"Ω","😀"})require(old.getString(text).equals(renders.getString(text)),"system fallback changed "+text);
            if(phase.equals("system-applied")) {
                String[] samples={"A","1","中"};String[] roles={"Latin","Digit","Cjk"};
                for(int i=0;i<samples.length;i++){
                    String text=samples[i];Typeface selected=expectedSystemRole(roles[i]);
                    require(draw(selected,text,null).equals(renders.getString(text)),"system default did not take selected glyph "+text);
                    String expected=arguments.getString("expected"+roles[i]+"Path","");
                    if(!expected.isEmpty())require(expected.equals(actualFonts.getJSONArray(text).getJSONObject(0).getString("file")),"unexpected actual default font path "+text);
                }
                require(!old.getString("A").equals(renders.getString("A")),"system mutation was not discriminating");
            } else if(phase.equals("system-restored")) {
                for(String text:new String[]{"A","1","中"})require(old.getString(text).equals(renders.getString(text)),"system restoration differs "+text);
            } else throw new AssertionError("unknown system phase");
        }
        report.put("renders",renders);report.put("status","passed-system-gate");
        report.put("systemConfigurationChanged",phase.equals("system-applied"));report.put("systemFontConfigMutated",phase.equals("system-applied"));
        Files.write(new File(root,"report-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
        Bundle output=new Bundle();output.putString("stream",report.toString());finish(Activity.RESULT_OK,output);
    }
    @Override public void onStart() {
        int resultCode=Activity.RESULT_CANCELED;
        String phase=arguments==null?"before":arguments.getString("phase","before");
        try {
            context=getTargetContext();root=context.getFilesDir();report=new JSONObject();
            report.put("phase",phase);report.put("sdk",Build.VERSION.SDK_INT);report.put("fingerprint",Build.FINGERPRINT);
            report.put("moduleMountTested",false);report.put("systemFontConfigMutated",false);report.put("hookUsed",false);
            if(phase.equals("stock-axis")){stockAxisPhase();return;}
            if(phase.equals("style-matrix")){styleMatrixPhase();return;}
            if(phase.startsWith("system-")){systemPhase(phase);return;}
            JSONObject fixture;try(InputStream in=context.getAssets().open("fixture.json")){fixture=new JSONObject(new String(in.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8));}
            File composite=asset("composite.ttf"),latin=asset("latin.ttf"),digit=asset("digit.ttf"),cjk=asset("cjk.ttf");
            Typeface mixed=face(composite,400,true);JSONObject renders=new JSONObject();
            String[] text={"A","1","中"};File[] donor={asset("expected-latin.ttf"),asset("expected-digit.ttf"),asset("expected-cjk.ttf")};
            for(int i=0;i<text.length;i++){
                String mixedHash=draw(mixed,text[i],"role-"+i+".png");
                require(mixedHash.equals(draw(face(donor[i],400,false),text[i],null)),"aligned donor identity mismatch "+text[i]);
                renders.put(text[i],mixedHash);
            }
            require(!draw(mixed,"A",null).equals(draw(face(cjk,400,false),"A",null)),"identity check is not discriminating");
            for(int w=100;w<=900;w+=100)require(draw(face(composite,w,true),"A1中",null).equals(draw(mixed,"A1中",null)),"fixed selection changed at "+w);
            for(String untouched:new String[]{"Ω","😀"}){
                String value=draw(mixed,untouched,null);
                require(value.equals(draw(Typeface.DEFAULT,untouched,null)),"fallback changed "+untouched);
                renders.put(untouched,value);
            }
            report.put("nativeCombinedHash",draw(mixed,"A1中",null));report.put("nativeStaticRoleIdentity","passed");report.put("fixedWeights100to900","passed");
            report.put("emojiAndUnknownScriptFallback","passed");report.put("renders",renders);
            // Fresh generation paths avoid mutating bytes under a cached Typeface.
            Typeface alternate=face(cjk,400,true);require(!draw(alternate,"A",null).equals(draw(mixed,"A",null)),"alternate asset not visible");
            require(draw(face(composite,400,true),"A",null).equals(renders.getString("A")),"rollback asset differs");
            report.put("immutablePathSwitchAndReturn","passed");
            File baseline=new File(root,"baseline.json");
            if(phase.equals("before"))Files.write(baseline.toPath(),renders.toString().getBytes(StandardCharsets.UTF_8));
            else {JSONObject old=new JSONObject(new String(Files.readAllBytes(baseline.toPath()),StandardCharsets.UTF_8));for(String key:text)require(old.getString(key).equals(renders.getString(key)),"reboot raster changed");report.put("emulatorRebootPersistence","passed");}
            report.put("frameworkXmlConsumer",frameworkXml(composite,fixture.getString("postScriptName")));
            report.put("fixedMatchingAxisProof",fixedMatchingAxisProof());
            report.put("status","passed-native-data-gate");resultCode=Activity.RESULT_OK;
        } catch(Throwable error) {
            if(report==null)report=new JSONObject();
            try{report.put("status","failed");report.put("error",error.toString());StringWriter trace=new StringWriter();error.printStackTrace(new PrintWriter(trace));report.put("trace",trace.toString());}catch(Exception ignored){}
        }
        try{Files.write(new File(root,"report-"+phase+".json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));}catch(Exception ignored){}
        Bundle output=new Bundle();output.putString("stream",report.toString());finish(resultCode,output);
    }
}
