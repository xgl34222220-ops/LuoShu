package io.github.xgl34222220.luoshu.globalfont.rules;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Per-process verdict cache keyed by font source ("asset:fonts/x.ttf", "res:inter_bold",
 * "file:/data/.../x.ttf#123456"). Lookups are a single ConcurrentHashMap read, so a font that was
 * decided once costs nothing on later loads. The map can be serialised to a tiny properties-like
 * text file so the next launch of the same app starts warm.
 */
public final class DecisionCache {
    private final ConcurrentHashMap<String, FontDecision> map = new ConcurrentHashMap<>();
    private volatile boolean dirty;

    public FontDecision get(String key) {
        return key == null ? null : map.get(key);
    }

    public void put(String key, FontDecision decision) {
        if (key == null || decision == null) return;
        if (map.put(key, decision) != decision) dirty = true;
    }

    public int size() {
        return map.size();
    }

    public boolean takeDirty() {
        boolean d = dirty;
        dirty = false;
        return d;
    }

    /** Resolve by name first; fall back to the cached deep-inspection verdict. */
    public FontDecision resolveByName(String key, String... names) {
        return resolveByName(key, false, names);
    }

    /** {@link #resolveByName(String, String...)} honouring the mono switch (callers key it separately). */
    public FontDecision resolveByName(String key, boolean monoSlot, String... names) {
        FontDecision cached = get(key);
        if (cached != null) return cached;
        FontDecision d = FontNameRules.classifyAll(monoSlot, names);
        if (d != FontDecision.UNKNOWN) put(key, d);
        return d;
    }

    public String serialize() {
        StringBuilder sb = new StringBuilder("# LuoShu global font decisions v1\n");
        for (Map.Entry<String, FontDecision> e : map.entrySet()) {
            if (e.getValue() == FontDecision.UNKNOWN) continue;
            sb.append(e.getKey().replace('\n', ' ').replace('\t', ' ')).append('\t').append(e.getValue().name()).append('\n');
        }
        return sb.toString();
    }

    public void load(String text) {
        if (text == null) return;
        for (String line : text.split("\n")) {
            if (line.isEmpty() || line.charAt(0) == '#') continue;
            int tab = line.lastIndexOf('\t');
            if (tab <= 0) continue;
            FontDecision d = FontDecision.parse(line.substring(tab + 1));
            if (d != FontDecision.UNKNOWN) map.putIfAbsent(line.substring(0, tab), d);
        }
    }

    /** Key for the (source, weight, italic) -> replacement Typeface cache. */
    public static String styleKey(String source, int weight, boolean italic) {
        return source + '|' + weight + (italic ? "|i" : "|n");
    }
}
