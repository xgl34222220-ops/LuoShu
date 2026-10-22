package io.github.xgl34222220.luoshu.globalfont.rules;

/** What to do with one app-bundled font. */
public enum FontDecision {
    /** Body text, sans: swap for {@code Typeface.create(Typeface.DEFAULT, weight, italic)}. */
    REPLACE_SANS,
    /** Body text, serif: swap for {@code Typeface.create(Typeface.SERIF, weight, italic)}. */
    REPLACE_SERIF,
    /** Icon / symbol / emoji / math / clock / digit / mono / script face: leave untouched. */
    KEEP,
    /**
     * Code monospace face: swap for {@code Typeface.create(Typeface.MONOSPACE, weight, italic)}.
     * Only produced when the user turned on the "monospace to system monospace" switch (off by
     * default); with the switch off the same face is {@link #KEEP} exactly as before.
     */
    REPLACE_MONO,
    /** Name says nothing (hashed, obfuscated, raw buffer): needs one sfnt inspection. */
    UNKNOWN;

    public boolean replaces() {
        return this == REPLACE_SANS || this == REPLACE_SERIF || this == REPLACE_MONO;
    }

    public static FontDecision parse(String s) {
        if (s == null) return UNKNOWN;
        try {
            return valueOf(s.trim());
        } catch (IllegalArgumentException e) {
            return UNKNOWN;
        }
    }
}
