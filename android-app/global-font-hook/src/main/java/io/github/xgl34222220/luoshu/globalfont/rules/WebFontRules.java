package io.github.xgl34222220.luoshu.globalfont.rules;

import java.util.Locale;

/*
 * WebView web-font interception policy. Looks only at the request URL, the request Accept header
 * and (when the app itself already produced a response) its MIME type. It never reads a body.
 */
public final class WebFontRules {
    private WebFontRules() {}

    public enum Verdict {
        /* Not a font request: leave it alone. */
        NOT_FONT,
        /* Font request for an icon / symbol / math / unknown face: let it load. */
        ALLOW,
        /* Body-text web font: answer 404 so the page falls back to the system (LuoShu) font. */
        BLOCK
    }

    private static final String[] FONT_EXTENSIONS = {".woff2", ".woff", ".ttf", ".otf", ".eot", ".ttc"};

    public static boolean isFontRequest(String url, String accept, String responseMime) {
        if (responseMime != null) {
            String m = responseMime.toLowerCase(Locale.ROOT);
            if (m.startsWith("font/") || m.startsWith("application/font") || m.startsWith("application/x-font")
                    || m.equals("application/vnd.ms-fontobject")) return true;
        }
        if (accept != null) {
            String a = accept.toLowerCase(Locale.ROOT);
            if (a.startsWith("font/") || a.startsWith("application/font")) return true;
        }
        if (url == null) return false;
        String path = pathOf(url).toLowerCase(Locale.ROOT);
        for (String ext : FONT_EXTENSIONS) if (path.endsWith(ext)) return true;
        return false;
    }

    public static Verdict verdict(String url, String accept, String responseMime, boolean blockUnknown) {
        if (!isFontRequest(url, accept, responseMime)) return Verdict.NOT_FONT;
        if (url == null || url.regionMatches(true, 0, "data:", 0, 5)) return Verdict.ALLOW;
        String path = pathOf(url);
        String[] segments = path.split("/");
        // Any directory that names an icon/math/emoji set protects every file under it
        // (fonts.gstatic.com/s/materialsymbolsoutlined/..., /fontawesome/webfonts/..., /katex/fonts/...).
        for (int i = 0; i < segments.length - 1; i++) {
            if (!segments[i].isEmpty() && FontNameRules.classify(segments[i]) == FontDecision.KEEP) return Verdict.ALLOW;
        }
        String file = segments.length == 0 ? "" : segments[segments.length - 1];
        FontDecision d = FontNameRules.classify(file);
        if (d == FontDecision.UNKNOWN) {
            // Google Fonts static CDN: /s/<family>/v<N>/<hash>.woff2 names the family two levels up.
            String host = hostOf(url);
            if (host.endsWith("fonts.gstatic.com") && segments.length >= 4 && "s".equals(segments[1])) {
                d = FontNameRules.classify(segments[2]);
            }
        }
        switch (d) {
            case KEEP: return Verdict.ALLOW;
            case REPLACE_SANS:
            case REPLACE_SERIF: return Verdict.BLOCK;
            default: return blockUnknown ? Verdict.BLOCK : Verdict.ALLOW;
        }
    }

    static String pathOf(String url) {
        String s = url;
        int scheme = s.indexOf("://");
        if (scheme >= 0) {
            int slash = s.indexOf('/', scheme + 3);
            s = slash >= 0 ? s.substring(slash) : "/";
        }
        int q = s.indexOf('?');
        if (q >= 0) s = s.substring(0, q);
        int h = s.indexOf('#');
        if (h >= 0) s = s.substring(0, h);
        return s;
    }

    static String hostOf(String url) {
        int scheme = url.indexOf("://");
        if (scheme < 0) return "";
        int start = scheme + 3;
        int end = start;
        while (end < url.length() && "/?#:".indexOf(url.charAt(end)) < 0) end++;
        return url.substring(start, end).toLowerCase(Locale.ROOT);
    }
}
