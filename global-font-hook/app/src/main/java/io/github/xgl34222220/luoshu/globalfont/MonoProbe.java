package io.github.xgl34222220.luoshu.globalfont;

import android.graphics.Paint;
import android.graphics.Typeface;
import io.github.xgl34222220.luoshu.globalfont.rules.MonoMetrics;

/**
 * Measures {@code Typeface.MONOSPACE} once per process. The mono switch only maps code fonts onto
 * it when narrow and wide glyphs really have the same advance.
 */
final class MonoProbe {
    private MonoProbe() {}

    /** Narrow, wide, digit and punctuation glyphs. */
    private static final char[] PROBE = {'i', 'W', '0', 'm', '.'};
    private static volatile Boolean fixedPitch;

    static boolean systemMonospaceIsFixedPitch() {
        Boolean known = fixedPitch;
        if (known == null) {
            known = measure();
            fixedPitch = known;
        }
        return known;
    }

    private static boolean measure() {
        try {
            Paint paint = new Paint();
            paint.setTypeface(Typeface.MONOSPACE);
            paint.setTextSize(40f);
            float[] widths = new float[PROBE.length];
            for (int i = 0; i < PROBE.length; i++) widths[i] = paint.measureText(PROBE, i, 1);
            return MonoMetrics.sameAdvance(widths);
        } catch (RuntimeException | LinkageError e) {
            return false;
        }
    }
}
