package io.github.xgl34222220.luoshu.globalfont.rules;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import org.junit.Test;

public class SourceNamesTest {
    @Test
    public void googleFontsQueryNamesTheFamily() {
        assertEquals("Noto Sans", SourceNames.familyFromQuery("name=Noto Sans&weight=700&italic=0&besteffort=true"));
        assertEquals("Roboto", SourceNames.familyFromQuery("weight=400&name=Roboto"));
        assertEquals("Roboto", SourceNames.familyFromQuery("Roboto"));
        assertEquals("Roboto", SourceNames.familyFromQuery("  Roboto:wght@700 "));
        assertEquals("Material Symbols Outlined", SourceNames.familyFromQuery("name=Material Symbols Outlined"));
        assertNull(SourceNames.familyFromQuery("weight=400&italic=1"));
        assertNull(SourceNames.familyFromQuery(""));
        assertNull(SourceNames.familyFromQuery(null));
    }

    @Test
    public void downloadedNamesGoThroughTheSameRules() {
        assertEquals(FontDecision.REPLACE_SANS, FontNameRules.classify(SourceNames.familyFromQuery("name=Roboto&weight=400")));
        assertEquals(FontDecision.KEEP, FontNameRules.classify(SourceNames.familyFromQuery("name=Material Symbols Outlined")));
        assertEquals(FontDecision.REPLACE_SERIF, FontNameRules.classify(SourceNames.familyFromQuery("name=Noto Serif")));
    }

    @Test
    public void descriptorLinkOnlyNamesRealFontFiles() {
        assertEquals("/data/user/0/com.x/files/fonts/Inter-Bold.ttf",
                SourceNames.fontPathFromLink("/data/user/0/com.x/files/fonts/Inter-Bold.ttf"));
        assertEquals("/data/fonts/files/~~a/Roboto-Regular.OTF", SourceNames.fontPathFromLink("/data/fonts/files/~~a/Roboto-Regular.OTF"));
        // An asset descriptor points into the APK: must not be named "base".
        assertNull(SourceNames.fontPathFromLink("/data/app/~~x/com.x-1/base.apk"));
        assertNull(SourceNames.fontPathFromLink("/memfd:font (deleted)"));
        assertNull(SourceNames.fontPathFromLink("/data/user/0/com.x/cache/f.ttf (deleted)"));
        assertNull(SourceNames.fontPathFromLink("/dev/ashmem"));
        assertNull(SourceNames.fontPathFromLink("socket:[1234]"));
        assertNull(SourceNames.fontPathFromLink("anon_inode:[eventfd]"));
        assertNull(SourceNames.fontPathFromLink(null));
    }
}
