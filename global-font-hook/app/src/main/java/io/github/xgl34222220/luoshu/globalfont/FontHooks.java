package io.github.xgl34222220.luoshu.globalfont;

import android.content.res.AssetManager;
import android.content.res.Resources;
import android.graphics.Typeface;
import android.graphics.fonts.Font;
import android.graphics.fonts.FontFamily;
import android.os.Build;
import android.os.Looper;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import io.github.xgl34222220.luoshu.globalfont.rules.DecisionCache;
import io.github.xgl34222220.luoshu.globalfont.rules.FontDecision;
import io.github.xgl34222220.luoshu.globalfont.rules.FontNameRules;
import io.github.xgl34222220.luoshu.globalfont.rules.SfntInspector;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Collections;
import java.util.Map;
import java.util.Set;
import java.util.WeakHashMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.zip.CRC32;

/**
 * Redirects app-bundled body-text fonts to the system default family (which LuoShu replaced).
 *
 * <p>Only font <b>loading</b> entry points are hooked. On Android 10+ every app font path
 * (Typeface.createFromAsset / createFromFile / Typeface.Builder / Resources.getFont /
 * ResourcesCompat.getFont / Compose Font(resId|asset|file) / downloadable fonts via TypefaceCompat)
 * funnels into {@code Font.Builder} + {@code Typeface.CustomFallbackBuilder.build()}, so those are the
 * only hooks. Each font is decided once; draw/measure/setTypeface/Paint/Canvas are never touched.</p>
 */
final class FontHooks {
    private FontHooks() {}

    static final DecisionCache CACHE = new DecisionCache();
    /** (source, weight, italic) -> replacement typeface. */
    private static final ConcurrentHashMap<String, Typeface> STYLED = new ConcurrentHashMap<>();
    /** (kind, weight, italic) -> one shared system typeface instance. */
    private static final ConcurrentHashMap<String, Typeface> FACES = new ConcurrentHashMap<>();
    private static final Map<Object, String> BUILDER_KEYS = Collections.synchronizedMap(new WeakHashMap<>());
    private static final Map<Object, String> FONT_KEYS = Collections.synchronizedMap(new WeakHashMap<>());
    private static final Map<Object, Object> FALLBACK_FAMILIES = Collections.synchronizedMap(new WeakHashMap<>());
    private static final Set<String> PENDING = ConcurrentHashMap.newKeySet();
    private static final AtomicBoolean SAVE_SCHEDULED = new AtomicBoolean();
    private static volatile ScheduledExecutorService worker;
    private static volatile File store;

    static void install(XC_LoadPackage.LoadPackageParam lp) {
        if (lp.appInfo != null && lp.appInfo.dataDir != null) {
            store = new File(lp.appInfo.dataDir, "cache/luoshu_global_font.tsv");
            worker().execute(FontHooks::loadStore); // file IO off the main thread
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            installQ();
        } else {
            installP();
        }
    }

    // ---------------------------------------------------------------- Android 10+

    private static void installQ() {
        XposedBridge.hookAllConstructors(Font.Builder.class, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                String key = sourceKey(param.args);
                if (key != null) BUILDER_KEYS.put(param.thisObject, key);
            }
        });
        XposedHelpers.findAndHookMethod(Font.Builder.class, "build", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                Object font = param.getResult();
                String key = BUILDER_KEYS.remove(param.thisObject);
                if (font != null && key != null) FONT_KEYS.put(font, key);
            }
        });
        XposedHelpers.findAndHookConstructor(Typeface.CustomFallbackBuilder.class, FontFamily.class, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                FALLBACK_FAMILIES.put(param.thisObject, param.args[0]);
            }
        });
        XposedHelpers.findAndHookMethod(Typeface.CustomFallbackBuilder.class, "build", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                Object family = FALLBACK_FAMILIES.remove(param.thisObject);
                Typeface result = (Typeface) param.getResult();
                if (family == null || result == null) return;
                try {
                    FontFamily fam = (FontFamily) family;
                    if (fam.getSize() == 0) return;
                    Font font = fam.getFont(0);
                    Typeface replacement = replacementFor(FONT_KEYS.get(font), font, result);
                    if (replacement != null) param.setResult(replacement);
                } catch (Throwable t) {
                    Log.v("fallback build skipped: " + t);
                }
            }
        });
    }

    /** Key that names where a Font.Builder reads from. Null when the source has no name. */
    static String sourceKey(Object[] args) {
        if (args == null || args.length == 0 || args[0] == null) return null;
        Object a = args[0];
        if (a instanceof File) return "file:" + ((File) a).getPath();
        if (a instanceof String) return "file:" + a;
        if (a instanceof AssetManager && args.length > 1 && args[1] instanceof String) return "asset:" + args[1];
        if (a instanceof Resources && args.length > 1 && args[1] instanceof Integer) {
            try {
                return "res:" + ((Resources) a).getResourceEntryName((Integer) args[1]);
            } catch (Throwable t) {
                return null;
            }
        }
        if (a instanceof Font) return FONT_KEYS.get(a);
        return null; // ByteBuffer / ParcelFileDescriptor / FileDescriptor
    }

    private static Typeface replacementFor(String name, Font font, Typeface original) {
        ByteBuffer buffer = font.getBuffer();
        String key = (name != null ? name : "buf:" + headerHash(buffer)) + "#" + buffer.capacity();
        FontDecision d = decide(key, name, buffer);
        if (!d.replaces()) return null;
        int weight = original.getWeight();
        boolean italic = original.isItalic();
        return styled(key, d, weight, italic);
    }

    /** Name rules first; the sfnt check runs once, never on the main thread. */
    static FontDecision decide(String key, String name, ByteBuffer buffer) {
        FontDecision d = CACHE.get(key);
        if (d != null) return d;
        d = name != null ? FontNameRules.classify(stripScheme(name)) : FontDecision.UNKNOWN;
        if (d != FontDecision.UNKNOWN) {
            CACHE.put(key, d);
            Log.v(d + " (name) " + key);
            return d;
        }
        if (buffer == null) return FontDecision.KEEP;
        if (Looper.getMainLooper().isCurrentThread()) {
            // Keep the original this time; inspect in the background so the next load is decided.
            final ByteBuffer copy = buffer.duplicate();
            if (PENDING.add(key)) {
                worker().execute(() -> {
                    FontDecision late = SfntInspector.decide(copy);
                    CACHE.put(key, late);
                    PENDING.remove(key);
                    Log.v(late + " (sfnt, deferred) " + key);
                    scheduleSave();
                });
            }
            return FontDecision.KEEP;
        }
        d = SfntInspector.decide(buffer);
        CACHE.put(key, d);
        Log.v(d + " (sfnt) " + key);
        scheduleSave();
        return d;
    }

    static Typeface styled(String key, FontDecision d, int weight, boolean italic) {
        String sk = DecisionCache.styleKey(key, weight, italic);
        Typeface cached = STYLED.get(sk);
        if (cached != null) return cached;
        String kind = (d == FontDecision.REPLACE_SERIF ? "serif" : "sans") + '|' + weight + (italic ? "|i" : "|n");
        Typeface face = FACES.get(kind);
        if (face == null) {
            Typeface base = d == FontDecision.REPLACE_SERIF ? Typeface.SERIF : Typeface.DEFAULT;
            int w = Math.max(1, Math.min(1000, weight));
            face = Typeface.create(base, w, italic);
            Typeface raced = FACES.putIfAbsent(kind, face);
            if (raced != null) face = raced;
        }
        STYLED.put(sk, face);
        return face;
    }

    private static String stripScheme(String key) {
        int colon = key.indexOf(':');
        return colon >= 0 && colon < 7 ? key.substring(colon + 1) : key;
    }

    /** Identity for an unnamed font: CRC of its table directory (includes per-table checksums). */
    static String headerHash(ByteBuffer b) {
        try {
            int len = Math.min(b.capacity(), 12 + 16 * 32);
            byte[] head = new byte[len];
            ByteBuffer dup = b.duplicate();
            dup.position(0);
            dup.get(head, 0, len);
            CRC32 crc = new CRC32();
            crc.update(head, 0, len);
            return Long.toHexString(crc.getValue());
        } catch (Throwable t) {
            return "x";
        }
    }

    // ---------------------------------------------------------------- Android 9

    private static void installP() {
        XposedBridge.hookAllConstructors(Typeface.Builder.class, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                String key = sourceKey(param.args);
                if (key != null) BUILDER_KEYS.put(param.thisObject, key);
            }
        });
        XposedHelpers.findAndHookMethod(Typeface.Builder.class, "build", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                replaceByName(param, BUILDER_KEYS.remove(param.thisObject));
            }
        });
        XposedHelpers.findAndHookMethod(Typeface.class, "createFromAsset", AssetManager.class, String.class, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                replaceByName(param, "asset:" + param.args[1]);
            }
        });
        XC_MethodHook fromFile = new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                Object a = param.args[0];
                if (a != null) replaceByName(param, "file:" + (a instanceof File ? ((File) a).getPath() : a));
            }
        };
        XposedHelpers.findAndHookMethod(Typeface.class, "createFromFile", String.class, fromFile);
        XposedHelpers.findAndHookMethod(Typeface.class, "createFromFile", File.class, fromFile);
    }

    /** Android 9 has no Font object to inspect: name rules only, unknown names are kept. */
    private static void replaceByName(XC_MethodHook.MethodHookParam param, String key) {
        Typeface result = (Typeface) param.getResult();
        if (key == null || result == null || result == Typeface.DEFAULT) return;
        FontDecision d = CACHE.resolveByName(key, stripScheme(key));
        if (!d.replaces()) return;
        param.setResult(styled(key, d, result.getWeight(), result.isItalic()));
    }

    // ---------------------------------------------------------------- persistence

    private static ScheduledExecutorService worker() {
        ScheduledExecutorService w = worker;
        if (w == null) {
            synchronized (FontHooks.class) {
                w = worker;
                if (w == null) {
                    ScheduledThreadPoolExecutor ex = new ScheduledThreadPoolExecutor(1, r -> {
                        Thread t = new Thread(r, "LuoShuFontInspect");
                        t.setDaemon(true);
                        t.setPriority(Thread.MIN_PRIORITY);
                        return t;
                    });
                    ex.setKeepAliveTime(10, TimeUnit.SECONDS);
                    ex.allowCoreThreadTimeOut(true);
                    worker = w = ex;
                }
            }
        }
        return w;
    }

    private static void loadStore() {
        File f = store;
        if (f == null || !f.isFile()) return;
        try {
            CACHE.load(new String(Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8));
        } catch (Throwable t) {
            Log.v("decision store unreadable: " + t);
        }
    }

    private static void scheduleSave() {
        if (store == null || !SAVE_SCHEDULED.compareAndSet(false, true)) return;
        worker().schedule(() -> {
            SAVE_SCHEDULED.set(false);
            if (!CACHE.takeDirty()) return;
            File f = store;
            try {
                File dir = f.getParentFile();
                if (dir != null && !dir.isDirectory() && !dir.mkdirs()) return;
                File tmp = new File(f.getPath() + ".tmp");
                try (FileOutputStream out = new FileOutputStream(tmp)) {
                    out.write(CACHE.serialize().getBytes(StandardCharsets.UTF_8));
                }
                if (!tmp.renameTo(f)) Log.v("decision store rename failed");
            } catch (Throwable t) {
                Log.v("decision store write failed: " + t);
            }
        }, 3, TimeUnit.SECONDS);
    }
}
