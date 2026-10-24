package io.github.xgl34222220.luoshu.globalfont.rules;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.io.IOException;
import java.nio.ByteBuffer;
import org.junit.Test;

/** "Monospace to system monospace" switch: off keeps every verdict as before, on maps only code mono faces. */
public class MonoSlotRulesTest {
    static final String[] CODE_MONO = {
            "SFMono-Regular.otf", "JetBrainsMono-Regular.ttf", "RobotoMono-Bold.ttf", "SourceCodePro-Regular.otf",
            "res/font/roboto_mono_medium.ttf", "robotomono_regular", "FiraCode-Retina.ttf", "Consolas.ttf",
            "CourierPrime-Regular.ttf", "Menlo-Regular.ttf", "CascadiaCode.ttf", "Inconsolata-Regular.ttf",
            "IBMPlexMono-Text.ttf", "NotoSansMono-Regular.ttf", "SpaceMono-Bold.ttf", "DejaVuSansMono.ttf",
            "Hack-Regular.ttf", "Roboto Mono"};

    static final String[] STILL_KEPT = {
            "Monoton-Regular.ttf", "Monofett.ttf", "JetBrainsSans-Regular.ttf", "MaterialIcons-Regular.ttf",
            "NotoEmoji-Mono.ttf", "mono_digits.ttf", "MonoIcons.ttf", "tnum_mono.ttf", "clock_mono.ttf",
            "NotoSansMonoArabic.ttf", "MathMono.otf"};

    @Test
    public void switchOffKeepsEveryMonoFaceExactlyAsBefore() {
        for (String n : CODE_MONO) assertEquals(n, FontDecision.KEEP, FontNameRules.classify(n, false));
        for (String n : CODE_MONO) assertEquals(n, FontDecision.KEEP, FontNameRules.classify(n));
        for (String n : STILL_KEPT) assertEquals(n, FontDecision.KEEP, FontNameRules.classify(n));
    }

    @Test
    public void switchOnMapsCodeMonospaceToMonoSlot() {
        for (String n : CODE_MONO) assertEquals(n, FontDecision.REPLACE_MONO, FontNameRules.classify(n, true));
    }

    @Test
    public void switchOnStillKeepsIconsDigitsDisplayAndScriptFaces() {
        for (String n : STILL_KEPT) assertEquals(n, FontDecision.KEEP, FontNameRules.classify(n, true));
    }

    @Test
    public void switchDoesNotChangeTextOrUnknownVerdicts() {
        for (String n : new String[] {"Inter-Bold.otf", "NotoSerif-Bold.ttf", "3f9c0a1e.woff2", "a.ttf", "Numans-Regular.ttf"}) {
            assertEquals(n, FontNameRules.classify(n, false), FontNameRules.classify(n, true));
        }
    }

    @Test
    public void classifyAllPrefersKeepThenMono() {
        assertEquals(FontDecision.REPLACE_MONO, FontNameRules.classifyAll(true, "x", "Roboto Mono", "Roboto Mono Regular"));
        assertEquals(FontDecision.REPLACE_MONO, FontNameRules.classifyAll(true, "Inter", "RobotoMono-Regular"));
        assertEquals(FontDecision.KEEP, FontNameRules.classifyAll(true, "Roboto Mono", "Material Icons"));
        assertEquals(FontDecision.KEEP, FontNameRules.classifyAll(false, "Inter", "RobotoMono-Regular"));
    }

    @Test
    public void codeMonospaceNameCheck() {
        assertTrue(FontNameRules.isCodeMonospace("JetBrains Mono"));
        assertTrue(FontNameRules.isCodeMonospace("Source Code Pro"));
        assertFalse(FontNameRules.isCodeMonospace("Monoton"));
        assertFalse(FontNameRules.isCodeMonospace("JetBrains Sans"));
        assertFalse(FontNameRules.isCodeMonospace(null));
    }

    @Test
    public void sfntFixedPitchFollowsSwitch() throws IOException {
        ByteBuffer fixed = ByteBuffer.wrap(SfntInspectorTest.font("x3", SfntInspectorTest.LATIN, true, false));
        assertEquals(FontDecision.KEEP, SfntInspector.decide(fixed));
        assertEquals(FontDecision.KEEP, SfntInspector.decide(fixed, false));
        assertEquals(FontDecision.REPLACE_MONO, SfntInspector.decide(fixed, true));
        ByteBuffer named = ByteBuffer.wrap(SfntInspectorTest.font("Roboto Mono", SfntInspectorTest.LATIN, false, false));
        assertEquals(FontDecision.KEEP, SfntInspector.decide(named, false));
        assertEquals(FontDecision.REPLACE_MONO, SfntInspector.decide(named, true));
        // Colour, PUA icon and non-Latin fixed-pitch faces stay kept with the switch on.
        assertEquals(FontDecision.KEEP, SfntInspector.decide(ByteBuffer.wrap(SfntInspectorTest.font("x5", SfntInspectorTest.LATIN, true, true)), true));
        assertEquals(FontDecision.KEEP, SfntInspector.decide(ByteBuffer.wrap(SfntInspectorTest.font("x6", new int[][] {{0x20, 0x7E}, {0xE000, 0xE8FF}}, true, false)), true));
        assertEquals(FontDecision.KEEP, SfntInspector.decide(ByteBuffer.wrap(SfntInspectorTest.font("x7", new int[][] {{0x30, 0x39}, {0x4E00, 0x9FFF}}, true, false)), true));
        // Proportional text faces are unaffected by the switch.
        ByteBuffer inter = ByteBuffer.wrap(SfntInspectorTest.font("Inter", SfntInspectorTest.LATIN, false, false));
        assertEquals(FontDecision.REPLACE_SANS, SfntInspector.decide(inter, true));
    }

    @Test
    public void monoVerdictRoundTripsThroughCacheAndParse() {
        assertTrue(FontDecision.REPLACE_MONO.replaces());
        assertEquals(FontDecision.REPLACE_MONO, FontDecision.parse("REPLACE_MONO"));
        DecisionCache c = new DecisionCache();
        c.put("res:roboto_mono~m", FontDecision.REPLACE_MONO);
        DecisionCache back = new DecisionCache();
        back.load(c.serialize());
        assertEquals(FontDecision.REPLACE_MONO, back.get("res:roboto_mono~m"));
        assertEquals(FontDecision.REPLACE_MONO, new DecisionCache().resolveByName("k~m", true, "RobotoMono-Regular.ttf"));
        assertEquals(FontDecision.KEEP, new DecisionCache().resolveByName("k", false, "RobotoMono-Regular.ttf"));
    }

    @Test
    public void monoMetricsNeedsEqualPositiveAdvances() {
        assertTrue(MonoMetrics.sameAdvance(28.9f, 28.9f, 29.0f, 28.9f));
        assertFalse(MonoMetrics.sameAdvance(10f, 30f, 20f));
        assertFalse(MonoMetrics.sameAdvance(0f, 0f));
        assertFalse(MonoMetrics.sameAdvance(12f));
        assertFalse(MonoMetrics.sameAdvance(Float.NaN, Float.NaN));
        assertFalse(MonoMetrics.sameAdvance((float[]) null));
    }
}
