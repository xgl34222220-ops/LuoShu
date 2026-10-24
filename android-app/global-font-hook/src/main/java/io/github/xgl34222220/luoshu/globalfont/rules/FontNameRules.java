package io.github.xgl34222220.luoshu.globalfont.rules;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/*
 * Pure-JVM font classification by file name / family name only.
 *
 * <p>This is the fast path: it does no IO, allocates a few short strings and never touches the
 * font bytes. Anything it cannot decide is reported as {@link FontDecision#UNKNOWN} so the caller
 * can schedule a one-off sfnt inspection off the main thread.</p>
 *
 * <p>The preserve tokens are a superset of the LuoShu module's own scanners so the companion never
 * replaces a face the module itself treats as non-body text:</p>
 * <ul>
 *   <li>{@code common/font_import.sh import_is_icon_name}: icon symbol material awesome glyph
 *       dingbat weather fontello emptyfont</li>
 *   <li>{@code common/font_import.sh import_is_color_font_name}: emoji emojione twemoji noto-color</li>
 *   <li>{@code common/font_inventory.py GENERIC_DENY_FILE_TOKENS}: emoji icon symbol math music
 *       mono monospace clock dingbat barcode qrcode materialicons notocoloremoji and the
 *       script-specific fallbacks</li>
 * </ul>
 * {@code FontNameRulesTest#coversModuleScannerTokens} reads those repository files and fails when a
 * token there is missing here.
 */
public final class FontNameRules {
    private FontNameRules() {}

    /* Substring tokens: a lower-cased name containing any of these is never replaced. */
    public static final List<String> PRESERVE_SUBSTRINGS = Collections.unmodifiableList(java.util.Arrays.asList(
            // icon fonts (LuoShu import_is_icon_name + common web/app icon sets)
            "icon", "symbol", "material", "awesome", "glyph", "dingbat", "weather", "fontello",
            "emptyfont", "icomoon", "iconfont", "fontawesome", "remixicon", "ionicon", "octicon",
            "codicon", "dashicon", "entypo", "linearicon", "themify", "lucide", "tabler", "phosphor",
            "feather", "boxicon", "glyphicon", "segoe-mdl", "segoemdl", "segmdl", "fluentsystem",
            "simple-line", "simpleline", "streamline", "uicons", "bootstrap-icons", "materialdesign",
            // colour / emoji fonts (import_is_color_font_name)
            "emoji", "emojione", "twemoji", "noto-color", "notocolor", "joypixels", "blobmoji",
            // math / formula
            "math", "latex", "katex", "mathjax", "mjx", "stix", "asana", "cambria-math",
            // clocks, digits and numeric display faces
            "clock", "digit", "number", "numeral", "numeric", "lcd", "7seg", "sevenseg", "segment",
            "dseg", "odometer", "countdown",
            // monospace / code: replacing breaks alignment
            "mono", "monospace", "consol", "courier", "menlo", "firacode", "sourcecode",
            "jetbrains", "cascadia", "inconsolata", "hack-", "ibmplexmono", "sfmono",
            // misc non-text (font_inventory GENERIC_DENY_FILE_TOKENS)
            "music", "barcode", "qrcode", "materialicons", "notocoloremoji", "braille",
            // script-specific fallbacks (font_inventory GENERIC_DENY_FILE_TOKENS)
            "adlam", "arabic", "hebrew", "thai", "devanagari", "bengali", "tamil", "telugu",
            "malayalam", "gujarati", "gurmukhi", "kannada", "khmer", "lao", "tibetan", "myanmar",
            "sinhala", "ethiopic", "georgian", "armenian", "japanese", "korean", "hangul",
            "hiragana", "katakana", "odia", "oriya", "cjkjp", "cjkkr"));

    /* Whole-word tokens: too short to match as substrings ("num" would hit "Numans"). */
    public static final Set<String> PRESERVE_WORDS = Collections.unmodifiableSet(new LinkedHashSet<>(
            java.util.Arrays.asList("num", "nums", "fa", "fab", "fas", "far", "fal", "mdi", "ico",
                    "icons", "sym", "seg", "led", "code", "tnum")));

    /* Well-known serif text families; mapped to the system serif instead of sans. */
    public static final String[] SERIF_FAMILIES = {
            "tiempos", "copernicus", "georgia", "lora", "merriweather", "playfair", "garamond",
            "baskerville", "times", "caslon", "charter", "bodoni", "didot", "crimson", "literata",
            "newsreader", "minion", "palatino", "cambria", "sabon", "songti", "mingti", "fangsong"};

    /*
     * Preserve tokens whose only meaning is "fixed-pitch / programming face". They are skipped when
     * the mono switch is on and the name is a code monospace family; every other token still keeps.
     */
    private static final Set<String> CODE_ONLY_TOKENS = Collections.unmodifiableSet(new LinkedHashSet<>(
            java.util.Arrays.asList("mono", "monospace", "consol", "courier", "menlo", "firacode",
                    "sourcecode", "jetbrains", "cascadia", "inconsolata", "hack-", "ibmplexmono", "sfmono",
                    "code")));

    /* Programming families recognised without a "mono" word (separators removed before matching). */
    private static final String[] CODE_FAMILIES = {
            "consolas", "courier", "menlo", "firacode", "sourcecode", "jetbrainsmono", "cascadia",
            "inconsolata", "ibmplexmono", "sfmono", "dejavusansmono"};

    private static boolean containsAny(String lower, String[] tokens) {
        for (String t : tokens) if (lower.contains(t)) return true;
        return false;
    }

    private static final String[] FONT_EXTENSIONS = {
            ".woff2", ".woff", ".ttf", ".otf", ".ttc", ".otc", ".eot", ".fnt", ".xml"};

    /* Classify one name: a path, an asset name, a resource entry name, or a family name. */
    public static FontDecision classify(String rawName) {
        return classify(rawName, false);
    }

    /*
     * Classify with the "monospace to system monospace" switch. Off: identical to
     * {@link #classify(String)}. On: a programming monospace name with no other preserve reason is
     * {@link FontDecision#REPLACE_MONO}; all other verdicts are unchanged.
     */
    public static FontDecision classify(String rawName, boolean monoSlot) {
        if (rawName == null) return FontDecision.UNKNOWN;
        String base = baseName(rawName);
        if (base.isEmpty()) return FontDecision.UNKNOWN;
        String lower = base.toLowerCase(Locale.ROOT);
        List<String> words = words(base);
        boolean code = monoSlot && codeMonospace(words);
        if (hasPreserveToken(lower, words, code)) return FontDecision.KEEP;
        if (code) return FontDecision.REPLACE_MONO;
        if (looksObfuscated(lower)) return FontDecision.UNKNOWN;
        if (lower.contains("serif") ? !lower.contains("sans") : containsAny(lower, SERIF_FAMILIES)) {
            return FontDecision.REPLACE_SERIF;
        }
        return FontDecision.REPLACE_SANS;
    }

    private static boolean hasPreserveToken(String lower, List<String> words, boolean skipCodeTokens) {
        for (int i = 0, n = PRESERVE_SUBSTRINGS.size(); i < n; i++) {
            String t = PRESERVE_SUBSTRINGS.get(i);
            if (lower.contains(t) && !(skipCodeTokens && CODE_ONLY_TOKENS.contains(t))) return true;
        }
        for (int i = 0, n = words.size(); i < n; i++) {
            String w = words.get(i);
            if (PRESERVE_WORDS.contains(w) && !(skipCodeTokens && CODE_ONLY_TOKENS.contains(w))) return true;
        }
        return false;
    }

    /*
     * Combine several names that describe the same face (file name + family name). Any KEEP wins,
     * then any concrete replacement, otherwise UNKNOWN.
     */
    public static FontDecision classifyAll(String... names) {
        return classifyAll(false, names);
    }

    /* As {@link #classifyAll(String...)}; precedence KEEP, REPLACE_MONO, REPLACE_SERIF, REPLACE_SANS. */
    public static FontDecision classifyAll(boolean monoSlot, String... names) {
        int bestRank = 0;
        FontDecision best = FontDecision.UNKNOWN;
        for (String name : names) {
            FontDecision d = classify(name, monoSlot);
            if (d == FontDecision.KEEP) return d;
            int rank = d == FontDecision.REPLACE_MONO ? 3 : d == FontDecision.REPLACE_SERIF ? 2
                    : d == FontDecision.REPLACE_SANS ? 1 : 0;
            if (rank > bestRank) {
                bestRank = rank;
                best = d;
            }
        }
        return best;
    }

    /* True for programming monospace family names ("Roboto Mono", "Consolas"), false for "Monoton". */
    public static boolean isCodeMonospace(String rawName) {
        if (rawName == null) return false;
        String base = baseName(rawName);
        return !base.isEmpty() && codeMonospace(words(base));
    }

    private static boolean codeMonospace(List<String> words) {
        StringBuilder joined = new StringBuilder();
        for (String w : words) {
            if (w.endsWith("mono") || w.equals("monospace") || w.equals("monospaced") || w.equals("hack")) return true;
            joined.append(w);
        }
        return containsAny(joined.toString(), CODE_FAMILIES);
    }

    /* Strip directories, query strings and font extensions. */
    public static String baseName(String raw) {
        String s = raw;
        int q = s.indexOf('?');
        if (q >= 0) s = s.substring(0, q);
        int h = s.indexOf('#');
        if (h >= 0) s = s.substring(0, h);
        int slash = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'));
        if (slash >= 0) s = s.substring(slash + 1);
        String lower = s.toLowerCase(Locale.ROOT);
        for (String ext : FONT_EXTENSIONS) {
            if (lower.endsWith(ext)) {
                s = s.substring(0, s.length() - ext.length());
                break;
            }
        }
        return s.trim();
    }

    /*
     * Content-hashed or R8-shortened names ("a.ttf", "3f9c0a1e", "font_b1") carry no meaning, so they
     * must not be replaced on name alone.
     */
    static boolean looksObfuscated(String lowerBase) {
        String s = lowerBase;
        if (s.startsWith("font_") || s.startsWith("font-")) s = s.substring(5);
        if (s.length() <= 3) return true;
        int letters = 0, hex = 0, digits = 0, len = 0;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '-' || c == '_' || c == '.') continue;
            len++;
            if (c >= '0' && c <= '9') { digits++; hex++; }
            else if (c >= 'a' && c <= 'f') { hex++; letters++; }
            else if (c >= 'a' && c <= 'z') letters++;
        }
        if (len == 0) return true;
        if (hex == len && len >= 6 && digits > 0) return true; // content hash
        // long alnum soup with many digits, e.g. "ab12cd34ef56gh78"
        return len >= 12 && digits * 3 >= len && letters > 0;
    }

    /* Split "RobotoSlab-BoldItalic_v2" into lower-case words: roboto, slab, bold, italic, v, 2. */
    static List<String> words(String base) {
        ArrayList<String> out = new ArrayList<>(6);
        StringBuilder cur = new StringBuilder();
        char prev = 0;
        for (int i = 0; i < base.length(); i++) {
            char c = base.charAt(i);
            boolean alnum = Character.isLetterOrDigit(c);
            boolean boundary = !alnum
                    || (Character.isUpperCase(c) && Character.isLowerCase(prev))
                    || (Character.isDigit(c) != Character.isDigit(prev) && cur.length() > 0);
            if (boundary && cur.length() > 0) {
                out.add(cur.toString().toLowerCase(Locale.ROOT));
                cur.setLength(0);
            }
            if (alnum) cur.append(c);
            prev = c;
        }
        if (cur.length() > 0) out.add(cur.toString().toLowerCase(Locale.ROOT));
        return out;
    }
}
