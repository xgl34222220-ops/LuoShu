package io.github.xgl34222220.luoshu.globalfont.rules;

import java.util.Locale;

/**
 * Names for font sources that do not carry one themselves (ByteBuffer / FileDescriptor /
 * ParcelFileDescriptor). Pure string logic so it can be unit tested on the JVM.
 */
public final class SourceNames {
    private SourceNames() {}

    private static final String[] FONT_FILE_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"};

    /**
     * Family requested from a downloadable-font provider, from a {@code FontRequest} query.
     * Handles the Google Fonts form {@code name=Noto Sans&weight=700&italic=0&besteffort=true} and
     * the bare legacy form {@code Roboto}. Returns null when no family can be read.
     */
    public static String familyFromQuery(String query) {
        if (query == null) return null;
        String q = query.trim();
        if (q.isEmpty()) return null;
        if (q.indexOf('=') < 0) return clean(q);
        for (String part : q.split("&")) {
            int eq = part.indexOf('=');
            if (eq <= 0) continue;
            String key = part.substring(0, eq).trim().toLowerCase(Locale.ROOT);
            if (key.equals("name") || key.equals("family")) return clean(part.substring(eq + 1));
        }
        return null;
    }

    private static String clean(String s) {
        String v = s.trim();
        int colon = v.indexOf(':'); // "Roboto:wght@700" style
        if (colon > 0) v = v.substring(0, colon).trim();
        if (v.isEmpty() || v.length() > 128) return null;
        return v.replace('\t', ' ').replace('\n', ' ');
    }

    /**
     * Fallback name for a descriptor source: the {@code /proc/self/fd/N} link target, but only when
     * it is a real font file. Anything else (an APK holding an asset, memfd, ashmem, pipes, sockets,
     * deleted files) returns null so the font goes to the sfnt check instead of being named "base".
     */
    public static String fontPathFromLink(String link) {
        if (link == null) return null;
        String s = link.trim();
        if (s.isEmpty() || s.charAt(0) != '/' || s.endsWith(" (deleted)")) return null;
        if (s.startsWith("/memfd:") || s.startsWith("/dev/")) return null;
        String lower = s.toLowerCase(Locale.ROOT);
        for (String ext : FONT_FILE_EXTENSIONS) {
            if (lower.endsWith(ext)) return s;
        }
        return null;
    }
}
