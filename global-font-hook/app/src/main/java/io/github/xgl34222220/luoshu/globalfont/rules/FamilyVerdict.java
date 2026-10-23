package io.github.xgl34222220.luoshu.globalfont.rules;

import java.util.List;

/**
 * Verdict for a font family built from several fonts (XML font-family, FontFamily.Builder with
 * extra fonts). A family is swapped only when all of its fonts are body text; one icon, emoji or
 * undecided member keeps the whole family. The first font picks the replacement style.
 */
public final class FamilyVerdict {
    private FamilyVerdict() {}

    /** UNKNOWN for an empty or missing list, KEEP when any member is not replaceable. */
    public static FontDecision combine(List<FontDecision> members) {
        if (members == null || members.isEmpty()) return FontDecision.UNKNOWN;
        boolean allText = true;
        for (FontDecision d : members) allText &= d != null && d.replaces();
        return allText ? members.get(0) : FontDecision.KEEP;
    }
}
