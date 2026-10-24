package io.github.xgl34222220.luoshu.globalfont.rules;

import static org.junit.Assert.assertEquals;

import java.util.Arrays;
import java.util.Collections;
import org.junit.Test;

public class FamilyVerdictTest {
    @Test
    public void anyKeptMemberKeepsTheWholeFamily() {
        assertEquals(FontDecision.KEEP, FamilyVerdict.combine(Arrays.asList(FontDecision.REPLACE_SANS, FontDecision.KEEP)));
        assertEquals(FontDecision.KEEP, FamilyVerdict.combine(Arrays.asList(FontDecision.KEEP, FontDecision.REPLACE_SANS)));
        // Undecided (deferred sfnt check) also keeps: never replace half a family.
        assertEquals(FontDecision.KEEP, FamilyVerdict.combine(Arrays.asList(FontDecision.REPLACE_SANS, FontDecision.UNKNOWN)));
        assertEquals(FontDecision.KEEP, FamilyVerdict.combine(Arrays.asList(FontDecision.REPLACE_SANS, null)));
    }

    @Test
    public void allTextMembersFollowTheFirst() {
        assertEquals(FontDecision.REPLACE_SANS, FamilyVerdict.combine(Collections.singletonList(FontDecision.REPLACE_SANS)));
        assertEquals(FontDecision.REPLACE_SERIF, FamilyVerdict.combine(Arrays.asList(FontDecision.REPLACE_SERIF, FontDecision.REPLACE_SANS)));
        assertEquals(FontDecision.REPLACE_MONO, FamilyVerdict.combine(Arrays.asList(FontDecision.REPLACE_MONO, FontDecision.REPLACE_MONO)));
    }

    @Test
    public void emptyFamilyIsLeftAlone() {
        assertEquals(FontDecision.UNKNOWN, FamilyVerdict.combine(Collections.emptyList()));
        assertEquals(FontDecision.UNKNOWN, FamilyVerdict.combine(null));
    }
}
