package io.github.xgl34222220.luoshu.globalfont;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.content.res.AssetFileDescriptor;
import android.content.res.AssetManager;
import android.content.res.Resources;
import android.graphics.Typeface;
import android.os.Build;
import android.os.ParcelFileDescriptor;
import android.provider.FontsContract;
import androidx.core.content.res.ResourcesCompat;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import io.github.xgl34222220.luoshu.globalfont.rules.FamilyVerdict;
import io.github.xgl34222220.luoshu.globalfont.rules.FontDecision;
import io.github.xgl34222220.luoshu.globalfont.rules.FontNameRules;
import io.github.xgl34222220.luoshu.globalfont.rules.SfntInspector;
import io.github.xgl34222220.luoshu.globalfont.test.R;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;
import org.junit.runner.RunWith;

/*
 * Runs on API 28/29/34/35 emulators without LSPosed. It cannot fire the hooks themselves; it proves
 * the things the hooks rely on, on each API level, with real framework objects:
 * <ul>
 *   <li>every method the hooks attach to exists there (incl. Android 9 hidden FontFamily API);</li>
 *   <li>res/font (Resources.getFont, ResourcesCompat.getFont = Compose Font(R.font.x)), assets,
 *       Typeface.Builder(AssetManager) and descriptor sources all load;</li>
 *   <li>the source naming the hooks use gives the expected keys for those real objects;</li>
 *   <li>the sfnt check and family verdict decide real font files as expected;</li>
 *   <li>the emulator's system monospace passes the fixed-pitch probe.</li>
 * </ul>
 */
@RunWith(AndroidJUnit4.class)
public class HookCoverageTest {
    private final Context test = InstrumentationRegistry.getInstrumentation().getContext();
    private final Context target = InstrumentationRegistry.getInstrumentation().getTargetContext();

    private static boolean hasMethod(Class<?> type, String name) {
        for (Method m : type.getDeclaredMethods()) if (m.getName().equals(name)) return true;
        return false;
    }

    private ByteBuffer asset(String path) throws Exception {
        try (InputStream in = test.getAssets().open(path)) {
            byte[] buf = new byte[64 * 1024];
            int n, total = 0;
            java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                total += n;
            }
            ByteBuffer direct = ByteBuffer.allocateDirect(total);
            direct.put(out.toByteArray());
            direct.flip();
            return direct;
        }
    }

    private File copyToCache(String assetPath, String name) throws Exception {
        File f = new File(target.getCacheDir(), name);
        try (InputStream in = test.getAssets().open(assetPath); OutputStream out = new FileOutputStream(f)) {
            byte[] buf = new byte[16 * 1024];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        }
        return f;
    }

    @Test
    public void hookTargetsExistOnThisApiLevel() throws Exception {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            Class<?> b = android.graphics.fonts.Font.Builder.class;
            assertNotNull(b.getConstructor(ByteBuffer.class));
            assertNotNull(b.getConstructor(File.class));
            assertNotNull(b.getConstructor(ParcelFileDescriptor.class));
            assertNotNull(b.getConstructor(AssetManager.class, String.class));
            assertNotNull(b.getConstructor(Resources.class, int.class));
            assertNotNull(b.getMethod("build"));
            assertNotNull(Typeface.CustomFallbackBuilder.class.getConstructor(android.graphics.fonts.FontFamily.class));
            assertNotNull(Typeface.CustomFallbackBuilder.class.getMethod("build"));
        } else {
            // Android 9: ResourcesImpl.loadFont / AndroidX TypefaceCompatApi26/28Impl path.
            Class<?> ff = Class.forName("android.graphics.FontFamily");
            assertTrue(hasMethod(ff, "addFontFromAssetManager"));
            assertTrue(hasMethod(ff, "addFontFromBuffer"));
            assertTrue(hasMethod(Typeface.class, "createFromFamiliesWithDefault"));
            assertNotNull(Typeface.Builder.class.getMethod("build"));
        }
        assertTrue(hasMethod(FontsContract.class, "fetchFonts"));
        assertTrue(hasMethod(FontsContract.class, "buildTypeface"));
        // AndroidX downloadable-font entry points (names as shipped when R8 keeps them).
        assertTrue(hasMethod(Class.forName("androidx.core.graphics.TypefaceCompat"), "createFromFontInfo"));
        Class<?> compat = Class.forName("androidx.core.provider.FontsContractCompat");
        Class<?> provider = Class.forName("androidx.core.provider.FontProvider");
        assertTrue(hasMethod(compat, "fetchFonts") || hasMethod(provider, "getFontFamilyResult"));
    }

    @Test
    public void resFontLoadsAndIsNamedByEntry() throws Exception {
        Resources res = test.getResources();
        assertNotNull(res.getFont(R.font.luoshu_body));
        assertNotNull(res.getFont(R.font.luoshu_family));
        // Compose Font(R.font.x) resolves through ResourcesCompat.getFont (AndroidFontLoader).
        assertNotNull(ResourcesCompat.getFont(test, R.font.luoshu_body));
        assertNotNull(ResourcesCompat.getFont(test, R.font.luoshu_family));
        String key = SourceKeys.named(new Object[] {res, R.font.luoshu_body}, null);
        assertEquals("res:luoshu_body", key);
        assertEquals(FontDecision.REPLACE_SANS, FontNameRules.classify(SourceKeys.nameOf(key)));
        assertEquals(FontDecision.KEEP, FontNameRules.classify(
                SourceKeys.nameOf(SourceKeys.named(new Object[] {res, R.font.luoshu_icons}, null))));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            assertNotNull(new android.graphics.fonts.Font.Builder(res, R.font.luoshu_body).build());
        }
        // Android 9 res/font key is the res/font path recorded from FontFamily.addFontFromAssetManager.
        assertEquals(FontDecision.REPLACE_SANS, FontNameRules.classify(SourceKeys.nameOf("res:res/font/luoshu_body.ttf")));
    }

    @Test
    public void assetAndTypefaceBuilderPathsLoadAndAreNamed() throws Exception {
        AssetManager am = test.getAssets();
        assertNotNull(Typeface.createFromAsset(am, "fonts/luoshu_body.ttf"));
        assertNotNull(new Typeface.Builder(am, "fonts/luoshu_body.ttf").build());
        assertEquals("asset:fonts/luoshu_body.ttf", SourceKeys.named(new Object[] {am, "fonts/luoshu_body.ttf"}, null));
        File f = copyToCache("fonts/luoshu_body.ttf", "luoshu_body.ttf");
        assertNotNull(Typeface.createFromFile(f));
        assertEquals("file:" + f.getPath(), SourceKeys.named(new Object[] {f}, null));
    }

    @Test
    public void descriptorSourcesAreNamedOnlyWhenTheyAreFontFiles() throws Exception {
        File f = copyToCache("fonts/luoshu_body.ttf", "luoshu_body_fd.ttf");
        try (ParcelFileDescriptor pfd = ParcelFileDescriptor.open(f, ParcelFileDescriptor.MODE_READ_ONLY)) {
            String path = SourceKeys.descriptorFontPath(pfd);
            assertNotNull(path);
            assertTrue(path, path.endsWith("/luoshu_body_fd.ttf"));
            String key = SourceKeys.fallback(new Object[] {pfd});
            assertEquals("fd:" + path, key);
            assertEquals(FontDecision.REPLACE_SANS, FontNameRules.classify(SourceKeys.nameOf(key)));
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                assertNotNull(new android.graphics.fonts.Font.Builder(pfd).build());
            }
        }
        try (FileInputStream in = new FileInputStream(f)) {
            String path = SourceKeys.descriptorFontPath(in.getFD());
            assertNotNull(path);
            assertTrue(path, path.endsWith("/luoshu_body_fd.ttf"));
        }
        // An asset descriptor points into the APK: never named after it.
        try (AssetFileDescriptor afd = test.getAssets().openFd("fonts/luoshu_body.ttf")) {
            assertNull(SourceKeys.descriptorFontPath(afd.getFileDescriptor()));
            assertNull(SourceKeys.descriptorFontPath(afd.getParcelFileDescriptor()));
        }
        // Downloadable fonts: the provider family name wins while a download is being built.
        SourceKeys.DOWNLOAD_FAMILY.set("Roboto");
        try {
            assertEquals("dl:Roboto", SourceKeys.fallback(new Object[] {ByteBuffer.allocate(4)}));
        } finally {
            SourceKeys.DOWNLOAD_FAMILY.remove();
        }
        assertNull(SourceKeys.fallback(new Object[] {ByteBuffer.allocate(4)}));
    }

    @Test
    public void realFontFilesAreDecidedAsExpected() throws Exception {
        assertEquals(FontDecision.REPLACE_SANS, SfntInspector.decide(asset("fonts/luoshu_body.ttf")));
        assertEquals(FontDecision.KEEP, SfntInspector.decide(asset("fonts/luoshu_icons.ttf")));
        assertEquals(FontDecision.KEEP, SfntInspector.decide(asset("fonts/luoshu_mono.ttf")));
        assertEquals(FontDecision.KEEP, SfntInspector.decide(asset("fonts/luoshu_mono.ttf"), false));
        assertEquals(FontDecision.REPLACE_MONO, SfntInspector.decide(asset("fonts/luoshu_mono.ttf"), true));
        assertEquals(FontDecision.REPLACE_SANS, SfntInspector.decide(asset("fonts/luoshu_body.ttf"), true));
    }

    @Test
    public void mixedFamilyIsKeptWhole() throws Exception {
        List<FontDecision> members = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            android.graphics.fonts.Font body = new android.graphics.fonts.Font.Builder(asset("fonts/luoshu_body.ttf")).setWeight(400).build();
            android.graphics.fonts.Font icons = new android.graphics.fonts.Font.Builder(asset("fonts/luoshu_icons.ttf")).setWeight(700).build();
            android.graphics.fonts.FontFamily fam = new android.graphics.fonts.FontFamily.Builder(body).addFont(icons).build();
            assertNotNull(new Typeface.CustomFallbackBuilder(fam).build());
            for (int i = 0; i < fam.getSize(); i++) members.add(SfntInspector.decide(fam.getFont(i).getBuffer()));
        } else {
            members.add(SfntInspector.decide(asset("fonts/luoshu_body.ttf")));
            members.add(SfntInspector.decide(asset("fonts/luoshu_icons.ttf")));
        }
        assertEquals(FontDecision.KEEP, FamilyVerdict.combine(members));
        assertEquals(FontDecision.REPLACE_SANS, FamilyVerdict.combine(members.subList(0, 1)));
    }

    @Test
    public void systemMonospacePassesTheFixedPitchProbe() {
        assertTrue(MonoProbe.systemMonospaceIsFixedPitch());
        assertNotNull(Typeface.create(Typeface.MONOSPACE, 700, false));
    }
}
