package io.github.xgl34222220.luoshu.globalfont.rules;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.Test;

public class FontNameRulesTest {
    private static void keep(String name) {
        assertEquals(name, FontDecision.KEEP, FontNameRules.classify(name));
    }

    private static void sans(String name) {
        assertEquals(name, FontDecision.REPLACE_SANS, FontNameRules.classify(name));
    }

    @Test
    public void iconSymbolEmojiMathClockDigitFacesAreKept() {
        for (String n : new String[] {
                "fonts/MaterialIcons-Regular.ttf", "MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].ttf",
                "fa-solid-900.woff2", "fa_brands.ttf", "fontawesome-webfont.ttf", "iconfont.ttf",
                "res/font/app_icons.ttf", "icomoon.woff", "NotoColorEmoji.ttf", "Twemoji.Mozilla.ttf",
                "KaTeX_Main-Regular.woff2", "latinmodern-math.otf", "STIXTwoMath.otf",
                "AndroidClock.ttf", "MiClock-Light.ttf", "DigitalNumbers.ttf", "dseg7-classic.ttf",
                "num_bold.ttf", "SFMono-Regular.otf", "JetBrainsMono-Regular.ttf", "RobotoMono-Bold.ttf",
                "SourceCodePro-Regular.otf", "glyphs.ttf", "weathericons.ttf", "NotoSansArabic.ttf",
                "Symbols-Nerd.ttf", "remixicon.woff2", "codicon.ttf"}) {
            keep(n);
        }
    }

    @Test
    public void bodyTextFacesAreReplaced() {
        for (String n : new String[] {
                "fonts/Roboto-Regular.ttf", "Inter-Bold.otf", "chirp-regular-web.woff2", "Styrene-B-Medium.otf",
                "res/font/sf_pro_text_semibold.ttf", "PingFangSC-Regular.ttf", "HarmonyOS_Sans_SC.ttf",
                "GoogleSans-Medium.ttf", "Montserrat-Italic.ttf", "OpenSans.ttf", "Lato-Black.ttf",
                "Numans-Regular.ttf"}) {
            sans(n);
        }
    }

    @Test
    public void serifFacesMapToSystemSerif() {
        assertEquals(FontDecision.REPLACE_SERIF, FontNameRules.classify("NotoSerif-Bold.ttf"));
        assertEquals(FontDecision.REPLACE_SERIF, FontNameRules.classify("TiemposText-Regular.otf"));
        assertEquals(FontDecision.REPLACE_SERIF, FontNameRules.classify("Copernicus-Book.otf"));
        assertEquals(FontDecision.REPLACE_SANS, FontNameRules.classify("NotoSans-SansSerif.ttf"));
    }

    @Test
    public void hashedOrObfuscatedNamesAreUnknown() {
        for (String n : new String[] {"a.ttf", "res/font/b0.ttf", "3f9c0a1e7b.woff2", "font_c.ttf",
                "/_next/static/media/a34f9d1faa5f3315-s.p.woff2", "", null}) {
            assertEquals(String.valueOf(n), FontDecision.UNKNOWN, FontNameRules.classify(n));
        }
    }

    @Test
    public void familyNameCanRescueAnUnknownFile() {
        assertEquals(FontDecision.REPLACE_SANS, FontNameRules.classifyAll("a.ttf", "Inter"));
        assertEquals(FontDecision.KEEP, FontNameRules.classifyAll("a.ttf", "Material Icons"));
        assertEquals(FontDecision.UNKNOWN, FontNameRules.classifyAll("a.ttf", "b1"));
    }

    /** Every token the LuoShu module scanners treat as non-body must be preserved here too. */
    @Test
    public void coversModuleScannerTokens() throws Exception {
        File root = new File(System.getProperty("user.dir"));
        File importSh = null;
        for (File d = root; d != null; d = d.getParentFile()) {
            File f = new File(d, "common/font_import.sh");
            if (f.isFile()) { importSh = f; break; }
        }
        if (importSh == null) return; // running outside the repository checkout
        List<String> tokens = new ArrayList<>();
        String sh = new String(Files.readAllBytes(importSh.toPath()), StandardCharsets.UTF_8);
        Matcher fn = Pattern.compile("import_is_(?:icon|color_font)_name\\(\\)[\\s\\S]*?case \"\\$_lower\" in ([^)]*)\\)").matcher(sh);
        while (fn.find()) {
            for (String part : fn.group(1).split("\\|")) tokens.add(part.replace("*", "").trim());
        }
        File inv = new File(importSh.getParentFile(), "font_inventory.py");
        String py = new String(Files.readAllBytes(inv.toPath()), StandardCharsets.UTF_8);
        Matcher deny = Pattern.compile("GENERIC_DENY_FILE_TOKENS = \\(([\\s\\S]*?)\\n\\)").matcher(py);
        assertTrue("GENERIC_DENY_FILE_TOKENS not found", deny.find());
        Matcher q = Pattern.compile("\"([a-z0-9-]+)\"").matcher(deny.group(1));
        while (q.find()) tokens.add(q.group(1));
        assertTrue(tokens.size() > 20);
        for (String t : tokens) {
            String token = t.toLowerCase(Locale.ROOT);
            if (token.equals("serif")) continue; // app serif body text maps to the system serif instead
            assertEquals("module token not preserved: " + token, FontDecision.KEEP,
                    FontNameRules.classify("x" + token + "x.ttf"));
        }
    }
}
