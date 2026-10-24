package io.github.xgl34222220.luoshu.globalfont.rules;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import io.github.xgl34222220.luoshu.globalfont.rules.WebFontRules.Verdict;
import org.junit.Test;

public class WebFontRulesTest {
    private static Verdict v(String url) {
        return WebFontRules.verdict(url, null, null, false);
    }

    @Test
    public void detectsFontRequestsByExtensionAcceptAndMime() {
        assertTrue(WebFontRules.isFontRequest("https://a.com/x/Inter.woff2?v=3#h", null, null));
        assertTrue(WebFontRules.isFontRequest("https://a.com/font", "font/woff2", null));
        assertTrue(WebFontRules.isFontRequest("https://a.com/font", null, "application/font-woff"));
        assertFalse(WebFontRules.isFontRequest("https://a.com/app.js", "*/*", null));
        assertFalse(WebFontRules.isFontRequest("https://a.com/woff2.css", "text/css", null));
        assertEquals(Verdict.NOT_FONT, v("https://abs.twimg.com/responsive-web/client-web/main.js"));
    }

    @Test
    public void bodyFontsAreBlocked() {
        assertEquals(Verdict.BLOCK, v("https://abs.twimg.com/fonts/v2/chirp-regular-web.woff2"));
        assertEquals(Verdict.BLOCK, v("https://cdn.example.com/assets/fonts/Inter-Bold.woff2"));
        assertEquals(Verdict.BLOCK, v("https://fonts.gstatic.com/s/roboto/v30/KFOmCnqEu92Fr1Mu4mxK.woff2"));
        assertEquals(Verdict.BLOCK, v("https://fonts.gstatic.com/s/notoserif/v21/ga6Iaw1J5X9T9RW6j9bNfFc.woff2"));
    }

    @Test
    public void iconMathAndUnknownFontsAreAllowed() {
        assertEquals(Verdict.ALLOW, v("https://fonts.gstatic.com/s/materialsymbolsoutlined/v190/kJF1BvYX7BgnkSrUwT8OhrdQw4oELdPIeeII9v6oDMzByHX9rA6RzaxHMPdY43zj-jCxv3fzvRNU22ZXGJpEpjC_1v-p_4MrImHCIJIZrDCvHOej.woff2"));
        assertEquals(Verdict.ALLOW, v("https://use.fontawesome.com/releases/v6/webfonts/fa-solid-900.woff2"));
        assertEquals(Verdict.ALLOW, v("https://cdn.jsdelivr.net/npm/katex/dist/fonts/KaTeX_Main-Regular.woff2"));
        assertEquals(Verdict.ALLOW, v("https://at.alicdn.com/t/font_12345_abcd.woff2?t=1"));
        assertEquals(Verdict.ALLOW, v("https://site.com/static/iconfont/iconfont.ttf"));
        assertEquals(Verdict.ALLOW, v("https://site.com/_next/static/media/a34f9d1faa5f3315-s.p.woff2"));
        assertEquals(Verdict.ALLOW, WebFontRules.verdict("data:font/woff2;base64,AAAA", null, "font/woff2", true));
    }

    @Test
    public void aggressiveModeBlocksUnknownButNeverIcons() {
        assertEquals(Verdict.BLOCK, WebFontRules.verdict("https://site.com/_next/static/media/a34f9d1faa5f3315-s.p.woff2", null, null, true));
        assertEquals(Verdict.ALLOW, WebFontRules.verdict("https://site.com/icons/3f9c0a1e7b.woff2", null, null, true));
    }
}
