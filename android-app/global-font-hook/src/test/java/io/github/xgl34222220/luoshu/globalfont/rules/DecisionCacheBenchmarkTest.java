package io.github.xgl34222220.luoshu.globalfont.rules;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import org.junit.Test;

/*
 * Quantifies the per-load overhead the hook adds. The thresholds are deliberately loose (CI
 * machines vary); the measured numbers are printed and written to
 * build/reports/global-font-benchmark.txt so the PR can quote them.
 */
public class DecisionCacheBenchmarkTest {
    private static final String[] NAMES = {
            "fonts/Roboto-Regular.ttf", "MaterialIcons-Regular.ttf", "res/font/inter_semibold.ttf",
            "fa-solid-900.woff2", "a.ttf", "NotoSerif-Bold.ttf", "KaTeX_Main-Regular.woff2", "chirp-regular-web.woff2"};
    private static final String[] URLS = {
            "https://abs.twimg.com/fonts/v2/chirp-regular-web.woff2",
            "https://fonts.gstatic.com/s/materialsymbolsoutlined/v190/kJF1BvYX7Bgnk.woff2",
            "https://abs.twimg.com/responsive-web/client-web/main.8b2f1e2a.js",
            "https://pbs.twimg.com/media/GXyz123.jpg?format=jpg&name=small"};

    private static double nsPerOp(Runnable r, int iterations) {
        for (int i = 0; i < iterations / 4; i++) r.run(); // warm-up
        long t0 = System.nanoTime();
        for (int i = 0; i < iterations; i++) r.run();
        return (System.nanoTime() - t0) / (double) iterations;
    }

    @Test
    public void overheadIsMicroseconds() throws IOException {
        final int n = 200_000;
        final int[] idx = {0};
        double classify = nsPerOp(() -> FontNameRules.classify(NAMES[idx[0]++ & 7]), n);

        DecisionCache cache = new DecisionCache();
        for (String name : NAMES) cache.resolveByName(name, name);
        double hit = nsPerOp(() -> cache.get(NAMES[idx[0]++ & 7]), n);
        double styleHit;
        {
            java.util.concurrent.ConcurrentHashMap<String, Object> faces = new java.util.concurrent.ConcurrentHashMap<>();
            for (String name : NAMES) faces.put(DecisionCache.styleKey(name, 400, false), new Object());
            styleHit = nsPerOp(() -> faces.get(DecisionCache.styleKey(NAMES[idx[0]++ & 7], 400, false)), n);
        }
        double web = nsPerOp(() -> WebFontRules.verdict(URLS[idx[0]++ & 3], null, null, false), n);

        byte[] font = SfntInspectorTest.font("Inter", new int[][] {{0x20, 0x7E}, {0xA0, 0x24F}, {0x4E00, 0x9FFF}}, false, false);
        ByteBuffer buf = ByteBuffer.wrap(font);
        double inspect = nsPerOp(() -> SfntInspector.decide(buf), 20_000);

        String report = String.format(java.util.Locale.ROOT,
                "name classify: %.0f ns/op%ndecision cache hit: %.0f ns/op%n(source,weight,italic) typeface cache hit: %.0f ns/op%n"
                        + "webview url verdict: %.0f ns/op%nsfnt deep inspection (once per font, off main thread): %.0f ns/op%n",
                classify, hit, styleHit, web, inspect);
        System.out.print(report);
        File dir = new File("build/reports");
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        try (FileOutputStream out = new FileOutputStream(new File(dir, "global-font-benchmark.txt"))) {
            out.write(report.getBytes(StandardCharsets.UTF_8));
        }
        assertTrue("classify " + classify, classify < 20_000);
        assertTrue("cache hit " + hit, hit < 5_000);
        assertTrue("style hit " + styleHit, styleHit < 5_000);
        assertTrue("web verdict " + web, web < 20_000);
        assertTrue("inspection " + inspect, inspect < 500_000);
    }

    @Test
    public void cacheRoundTripsAcrossLaunches() {
        DecisionCache a = new DecisionCache();
        a.put("asset:fonts/a.ttf#1234", FontDecision.REPLACE_SANS);
        a.put("res:b0#99", FontDecision.KEEP);
        a.put("pfd:x", FontDecision.UNKNOWN);
        assertTrue(a.takeDirty());
        DecisionCache b = new DecisionCache();
        b.load(a.serialize());
        assertEquals(2, b.size());
        assertEquals(FontDecision.REPLACE_SANS, b.get("asset:fonts/a.ttf#1234"));
        assertEquals(FontDecision.KEEP, b.get("res:b0#99"));
    }
}
