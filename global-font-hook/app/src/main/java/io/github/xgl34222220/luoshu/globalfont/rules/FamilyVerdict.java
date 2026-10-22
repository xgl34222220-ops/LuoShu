package io.github.xgl34222220.luoshu.globalfont.rules;

import java.util.List;

/**
 * One verdict for a whole font family (several fonts registered together, e.g. a res/font XML
 * family or a {@code FontFamily.Builder} with text + icon faces).
 *
 * <p>Rule: if <b>any</b> member must be kept (icon, emoji, symbol, still undecided) the whole family
 * is kept, so a family that mixes text and icon faces never loses its icons. Otherwise the first
 * member decides (it is the face the family was built around).</p>
 */
public final class FamilyVerdict {
    private FamilyVerdict() {}

    /** Empty input means "nothing known about this family": UNKNOWN (callers leave it alone). */
    public static FontDecision combine(List<FontDecision> members) {
        if (members == null || members.isEmpty()) return FontDecision.UNKNOWN;
        for (int i = 0, n = members.size(); i < n; i++) {
            FontDecision d = members.get(i);
            if (d == null || !d.replaces()) return FontDecision.KEEP;
        }
        return members.get(0);
    }
}
