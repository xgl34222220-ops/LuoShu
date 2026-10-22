package io.github.xgl34222220.luoshu.globalfont.rules;

/**
 * Whether measured advances describe a fixed-pitch face. The companion measures the system
 * {@code Typeface.MONOSPACE} (LuoShu's mono slot) with a few very different glyphs; if they are not
 * all the same width the slot is not really monospace and "monospace to system monospace" stays off.
 */
public final class MonoMetrics {
    private MonoMetrics() {}

    /** Relative tolerance for rounding in hinted advances. */
    public static final float TOLERANCE = 0.02f;

    public static boolean sameAdvance(float... advances) {
        if (advances == null || advances.length < 2) return false;
        float min = Float.MAX_VALUE, max = 0f;
        for (float a : advances) {
            if (!(a > 0f) || Float.isInfinite(a)) return false;
            min = Math.min(min, a);
            max = Math.max(max, a);
        }
        return (max - min) <= max * TOLERANCE;
    }
}
