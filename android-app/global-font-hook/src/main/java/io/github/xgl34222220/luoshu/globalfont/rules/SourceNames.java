package io.github.xgl34222220.luoshu.globalfont.rules;

import java.util.Locale;

/** String helpers that give a name to fonts loaded from buffers, descriptors or font providers. */
public final class SourceNames {
    private SourceNames() {}

    private static final int MAX_NAME = 128;

    /**
     * Family name in a {@code android.provider.FontRequest} query. Accepts key/value queries
     * ({@code name=Noto Sans&weight=700}, key {@code name} or {@code family}) and a plain family
     * string; a {@code :axis} suffix is dropped. Null when there is no usable name.
     */
    public static String familyFromQuery(String query) {
        if (query == null || query.trim().isEmpty()) return null;
        if (!query.contains("=")) return tidy(query);
        for (String pair : query.split("&")) {
            int eq = pair.indexOf('=');
            if (eq < 1) continue;
            String k = pair.substring(0, eq).trim().toLowerCase(Locale.ROOT);
            if ("name".equals(k) || "family".equals(k)) return tidy(pair.substring(eq + 1));
        }
        return null;
    }

    private static String tidy(String raw) {
        String v = raw;
        int axis = v.indexOf(':');
        if (axis > 0) v = v.substring(0, axis);
        v = v.replace('\t', ' ').replace('\n', ' ').trim();
        return v.isEmpty() || v.length() > MAX_NAME ? null : v;
    }

    /**
     * The target of a {@code /proc/self/fd/N} link when it is an absolute path to a font file
     * (ttf/otf/ttc/otc/woff/woff2). Null for memfd, ashmem, /dev nodes, deleted files, APKs and
     * anything else, so those fonts are decided from their bytes instead.
     */
    public static String fontPathFromLink(String link) {
        if (link == null) return null;
        String path = link.trim();
        if (!path.startsWith("/") || path.startsWith("/dev/") || path.startsWith("/memfd:")
                || path.endsWith(" (deleted)")) {
            return null;
        }
        String lower = path.toLowerCase(Locale.ROOT);
        int dot = lower.lastIndexOf('.');
        if (dot < 0 || dot < lower.lastIndexOf('/')) return null;
        switch (lower.substring(dot + 1)) {
            case "ttf": case "otf": case "ttc": case "otc": case "woff": case "woff2":
                return path;
            default:
                return null;
        }
    }
}
