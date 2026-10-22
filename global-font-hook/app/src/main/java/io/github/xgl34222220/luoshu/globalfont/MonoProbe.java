package io.github.xgl34222220.luoshu.globalfont;

import android.graphics.Paint;
import android.graphics.Typeface;
import io.github.xgl34222220.luoshu.globalfont.rules.MonoMetrics;

/**
 * Checks that the system monospace face (LuoShu's mono slot) really is fixed pitch, by measuring a
 * few glyphs of very different natural widths. Used by the settings screen to grey out the
 * "monospace to system monospace" switch and, once per process, by the hook before it maps a code
 * font onto {@code Typeface.MONOSPACE}.
 */
final class MonoProbe {
    private MonoProbe() {}

    static final String SAMPLE = "iW0m.";
    private static volatile Boolean cached;

    static boolean systemMonospaceIsFixedPitch() {
        Boolean c = cached;
        if (c != null) return c;
        boolean ok;
        try {
            Paint p = new Paint();
            p.setTypeface(Typeface.MONOSPACE);
            p.setTextSize(48f);
            float[] adv = new float[SAMPLE.length()];
            for (int i = 0; i < adv.length; i++) adv[i] = p.measureText(SAMPLE, i, i + 1);
            ok = MonoMetrics.sameAdvance(adv);
        } catch (Throwable t) {
            ok = false;
        }
        cached = ok;
        return ok;
    }
}
