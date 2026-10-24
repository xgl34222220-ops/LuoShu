package io.github.xgl34222220.luoshu.globalfont.rules;

/* Decides from measured glyph advances whether a face is fixed pitch. */
public final class MonoMetrics {
    private MonoMetrics() {}

    /* Allowed spread between widest and narrowest advance, as a fraction of the widest. */
    public static final float TOLERANCE = 0.02f;

    /* True when there are at least two finite, positive advances that agree within {@link #TOLERANCE}. */
    public static boolean sameAdvance(float... advances) {
        if (advances == null || advances.length < 2) return false;
        float lo = Float.POSITIVE_INFINITY;
        float hi = 0f;
        for (float a : advances) {
            if (Float.isNaN(a) || Float.isInfinite(a) || a <= 0f) return false;
            if (a < lo) lo = a;
            if (a > hi) hi = a;
        }
        return hi - lo <= hi * TOLERANCE;
    }
}
