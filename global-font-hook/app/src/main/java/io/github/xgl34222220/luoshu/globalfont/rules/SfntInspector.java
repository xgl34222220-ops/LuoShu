package io.github.xgl34222220.luoshu.globalfont.rules;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

/**
 * Minimal read-only sfnt (TTF/OTF/TTC first face) inspector used only when the name rules return
 * {@link FontDecision#UNKNOWN}. It reads the table directory plus the name, cmap, post and colour
 * table tags. The hook only calls it off the main thread and caches the result per font source, so
 * every font is inspected at most once per process (and the verdict is persisted per app).
 */
public final class SfntInspector {
    private SfntInspector() {}

    /** Result of an inspection; exposed for tests. */
    public static final class Report {
        public String family = "";
        public String fullName = "";
        public String postscriptName = "";
        public int basicLatinLetters;   // of 52 A-Z a-z
        public int asciiDigits;         // of 10
        public int privateUse;          // BMP PUA + supplementary PUA-A/B codepoints mapped
        public boolean fixedPitch;
        public boolean colour;          // COLR / CBDT / sbix / SVG
        public boolean parsed;

        public FontDecision decide() {
            return decide(false);
        }

        /**
         * With {@code monoSlot} a Latin text face that is fixed pitch (or named as code monospace)
         * becomes REPLACE_MONO; colour, icon, PUA and non-Latin faces stay KEEP either way.
         */
        public FontDecision decide(boolean monoSlot) {
            if (!parsed) return FontDecision.KEEP; // unreadable: never risk replacing
            FontDecision byName = FontNameRules.classifyAll(monoSlot, family, fullName, postscriptName);
            if (byName == FontDecision.KEEP) return FontDecision.KEEP;
            if (colour) return FontDecision.KEEP;
            if (fixedPitch && !monoSlot) return FontDecision.KEEP;
            if (basicLatinLetters < 40) return FontDecision.KEEP; // no Latin text cmap
            if (privateUse > basicLatinLetters) return FontDecision.KEEP; // ligature/PUA icon font
            if (fixedPitch || byName == FontDecision.REPLACE_MONO) return FontDecision.REPLACE_MONO;
            return byName == FontDecision.REPLACE_SERIF ? FontDecision.REPLACE_SERIF : FontDecision.REPLACE_SANS;
        }
    }

    public static FontDecision decide(ByteBuffer font) {
        return inspect(font).decide();
    }

    public static FontDecision decide(ByteBuffer font, boolean monoSlot) {
        return inspect(font).decide(monoSlot);
    }

    public static Report inspect(ByteBuffer source) {
        Report r = new Report();
        if (source == null) return r;
        ByteBuffer b = source.duplicate().order(ByteOrder.BIG_ENDIAN);
        b.position(0);
        try {
            int base = 0;
            int tag = b.getInt(0);
            if (tag == 0x74746366) { // 'ttcf'
                base = b.getInt(12);
            }
            int sfnt = b.getInt(base);
            if (sfnt != 0x00010000 && sfnt != 0x4F54544F && sfnt != 0x74727565) return r; // TrueType, 'OTTO', 'true'
            int numTables = b.getShort(base + 4) & 0xFFFF;
            int nameOff = -1, cmapOff = -1, postOff = -1;
            for (int i = 0; i < numTables; i++) {
                int rec = base + 12 + i * 16;
                int t = b.getInt(rec);
                int off = b.getInt(rec + 8);
                switch (t) {
                    case 0x6E616D65: nameOff = off; break;        // name
                    case 0x636D6170: cmapOff = off; break;        // cmap
                    case 0x706F7374: postOff = off; break;        // post
                    case 0x434F4C52: case 0x43424454: case 0x73626978: case 0x53564720:
                        r.colour = true; break;                   // COLR CBDT sbix 'SVG '
                    default: break;
                }
            }
            if (nameOff >= 0) readNames(b, nameOff, r);
            if (postOff >= 0) r.fixedPitch = b.getInt(postOff + 12) != 0;
            if (cmapOff < 0) return r;
            readCmap(b, cmapOff, r);
            r.parsed = true;
        } catch (RuntimeException e) {
            r.parsed = false;
        }
        return r;
    }

    private static void readNames(ByteBuffer b, int off, Report r) {
        int count = b.getShort(off + 2) & 0xFFFF;
        int strings = off + (b.getShort(off + 4) & 0xFFFF);
        for (int i = 0; i < count; i++) {
            int rec = off + 6 + i * 12;
            int platform = b.getShort(rec) & 0xFFFF;
            int nameId = b.getShort(rec + 6) & 0xFFFF;
            if (nameId != 1 && nameId != 4 && nameId != 6 && nameId != 16) continue;
            int len = b.getShort(rec + 8) & 0xFFFF;
            int at = strings + (b.getShort(rec + 10) & 0xFFFF);
            if (len == 0 || len > 512) continue;
            byte[] raw = new byte[len];
            for (int k = 0; k < len; k++) raw[k] = b.get(at + k);
            String value = (platform == 0 || platform == 3)
                    ? new String(raw, StandardCharsets.UTF_16BE)
                    : new String(raw, StandardCharsets.ISO_8859_1);
            if ((nameId == 1 || nameId == 16) && (r.family.isEmpty() || nameId == 16)) r.family = value;
            else if (nameId == 4 && r.fullName.isEmpty()) r.fullName = value;
            else if (nameId == 6 && r.postscriptName.isEmpty()) r.postscriptName = value;
        }
    }

    private static void readCmap(ByteBuffer b, int off, Report r) {
        int n = b.getShort(off + 2) & 0xFFFF;
        int best = -1, bestFormat = -1;
        for (int i = 0; i < n; i++) {
            int rec = off + 4 + i * 8;
            int platform = b.getShort(rec) & 0xFFFF;
            int encoding = b.getShort(rec + 2) & 0xFFFF;
            int sub = off + b.getInt(rec + 4);
            int format = b.getShort(sub) & 0xFFFF;
            boolean unicode = platform == 0 || (platform == 3 && (encoding == 1 || encoding == 10));
            if (!unicode) continue;
            if (format == 12 && bestFormat != 12) { best = sub; bestFormat = 12; }
            else if (format == 4 && bestFormat == -1) { best = sub; bestFormat = 4; }
        }
        if (best < 0) return;
        if (bestFormat == 4) readFormat4(b, best, r);
        else readFormat12(b, best, r);
    }

    private static void count(int start, int end, Report r) {
        r.basicLatinLetters += overlap(start, end, 'A', 'Z') + overlap(start, end, 'a', 'z');
        r.asciiDigits += overlap(start, end, '0', '9');
        r.privateUse += overlap(start, end, 0xE000, 0xF8FF)
                + overlap(start, end, 0xF0000, 0xFFFFD) + overlap(start, end, 0x100000, 0x10FFFD);
    }

    private static int overlap(int s, int e, int lo, int hi) {
        int a = Math.max(s, lo), z = Math.min(e, hi);
        return z >= a ? z - a + 1 : 0;
    }

    private static void readFormat4(ByteBuffer b, int sub, Report r) {
        int segX2 = b.getShort(sub + 6) & 0xFFFF;
        int ends = sub + 14;
        int starts = ends + segX2 + 2;
        int deltas = starts + segX2;
        int ranges = deltas + segX2;
        for (int i = 0; i < segX2 / 2; i++) {
            int end = b.getShort(ends + i * 2) & 0xFFFF;
            int start = b.getShort(starts + i * 2) & 0xFFFF;
            if (start == 0xFFFF) continue;
            int rangeOffset = b.getShort(ranges + i * 2) & 0xFFFF;
            if (rangeOffset == 0) {
                // idDelta mapping: every codepoint maps (glyph 0 only if delta wraps to 0)
                count(start, end, r);
            } else {
                // glyphIdArray mapping: count only codepoints that are interesting and non-zero
                for (int cp = start; cp <= end; cp++) {
                    boolean interesting = (cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z')
                            || (cp >= '0' && cp <= '9') || (cp >= 0xE000 && cp <= 0xF8FF);
                    if (!interesting) continue;
                    int at = ranges + i * 2 + rangeOffset + (cp - start) * 2;
                    if (at + 1 >= b.limit()) break;
                    if ((b.getShort(at) & 0xFFFF) != 0) count(cp, cp, r);
                }
            }
        }
    }

    private static void readFormat12(ByteBuffer b, int sub, Report r) {
        long groups = b.getInt(sub + 12) & 0xFFFFFFFFL;
        if (groups > 200_000) groups = 200_000;
        for (int i = 0; i < groups; i++) {
            int g = sub + 16 + i * 12;
            count(b.getInt(g), b.getInt(g + 4), r);
        }
    }
}
