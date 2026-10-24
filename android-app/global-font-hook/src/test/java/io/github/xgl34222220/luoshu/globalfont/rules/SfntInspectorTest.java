package io.github.xgl34222220.luoshu.globalfont.rules;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import org.junit.Test;

/* Builds tiny synthetic sfnt files in memory so the test needs no binary fixtures. */
public class SfntInspectorTest {
    static byte[] font(String family, int[][] ranges, boolean fixedPitch, boolean colour) throws IOException {
        byte[] name = nameTable(family);
        byte[] cmap = cmapFormat12(ranges);
        byte[] post = new byte[32];
        if (fixedPitch) post[15] = 1;
        String[] tags = colour ? new String[] {"COLR", "cmap", "name", "post"} : new String[] {"cmap", "name", "post"};
        byte[][] tables = colour ? new byte[][] {new byte[4], cmap, name, post} : new byte[][] {cmap, name, post};
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bos);
        out.writeInt(0x00010000);
        out.writeShort(tables.length);
        out.writeShort(0); out.writeShort(0); out.writeShort(0);
        int offset = 12 + 16 * tables.length;
        for (int i = 0; i < tables.length; i++) {
            out.write(tags[i].getBytes(StandardCharsets.US_ASCII));
            out.writeInt(0);
            out.writeInt(offset);
            out.writeInt(tables[i].length);
            offset += tables[i].length;
        }
        for (byte[] t : tables) out.write(t);
        return bos.toByteArray();
    }

    static byte[] nameTable(String family) throws IOException {
        byte[] s = family.getBytes(StandardCharsets.UTF_16BE);
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bos);
        out.writeShort(0); out.writeShort(1); out.writeShort(6 + 12);
        out.writeShort(3); out.writeShort(1); out.writeShort(0x409); out.writeShort(1);
        out.writeShort(s.length); out.writeShort(0);
        out.write(s);
        return bos.toByteArray();
    }

    static byte[] cmapFormat12(int[][] ranges) throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bos);
        out.writeShort(0); out.writeShort(1);
        out.writeShort(3); out.writeShort(10); out.writeInt(12);
        out.writeShort(12); out.writeShort(0);
        out.writeInt(16 + ranges.length * 12); out.writeInt(0); out.writeInt(ranges.length);
        int glyph = 1;
        for (int[] r : ranges) {
            out.writeInt(r[0]); out.writeInt(r[1]); out.writeInt(glyph);
            glyph += r[1] - r[0] + 1;
        }
        return bos.toByteArray();
    }

    static final int[][] LATIN = {{0x20, 0x7E}};

    @Test
    public void latinTextFaceIsReplaced() throws IOException {
        SfntInspector.Report r = SfntInspector.inspect(ByteBuffer.wrap(font("Inter", LATIN, false, false)));
        assertTrue(r.parsed);
        assertEquals("Inter", r.family);
        assertEquals(52, r.basicLatinLetters);
        assertEquals(10, r.asciiDigits);
        assertEquals(FontDecision.REPLACE_SANS, r.decide());
    }

    @Test
    public void iconEmojiMonoAndNonLatinFacesAreKept() throws IOException {
        // Ligature icon font: Latin letters present for ligatures, thousands of PUA glyphs.
        assertEquals(FontDecision.KEEP, SfntInspector.decide(ByteBuffer.wrap(font("x1", new int[][] {{0x20, 0x7E}, {0xE000, 0xE8FF}}, false, false))));
        // Named icon font
        assertEquals(FontDecision.KEEP, SfntInspector.decide(ByteBuffer.wrap(font("Material Icons", LATIN, false, false))));
        // Colour (emoji) table
        assertEquals(FontDecision.KEEP, SfntInspector.decide(ByteBuffer.wrap(font("x2", LATIN, false, true))));
        // Fixed pitch
        assertEquals(FontDecision.KEEP, SfntInspector.decide(ByteBuffer.wrap(font("x3", LATIN, true, false))));
        // Digits-only / CJK-only cmap
        assertEquals(FontDecision.KEEP, SfntInspector.decide(ByteBuffer.wrap(font("x4", new int[][] {{0x30, 0x39}, {0x4E00, 0x9FFF}}, false, false))));
        // Garbage never replaces
        assertEquals(FontDecision.KEEP, SfntInspector.decide(ByteBuffer.wrap(new byte[] {1, 2, 3})));
    }

    @Test
    public void serifFamilyMapsToSerif() throws IOException {
        assertEquals(FontDecision.REPLACE_SERIF, SfntInspector.decide(ByteBuffer.wrap(font("Noto Serif", LATIN, false, false))));
    }
}
