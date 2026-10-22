package io.github.xgl34222220.luoshu.globalfont;

import android.content.res.AssetManager;
import android.content.res.Resources;
import android.graphics.Typeface;
import android.graphics.fonts.Font;
import android.graphics.fonts.FontFamily;
import android.os.Build;
import android.os.Looper;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import io.github.xgl34222220.luoshu.globalfont.rules.DecisionCache;
import io.github.xgl34222220.luoshu.globalfont.rules.FamilyVerdict;
import io.github.xgl34222220.luoshu.globalfont.rules.FontDecision;
import io.github.xgl34222220.luoshu.globalfont.rules.FontNameRules;
import io.github.xgl34222220.luoshu.globalfont.rules.SfntInspector;
import io.github.xgl34222220.luoshu.globalfont.rules.SourceNames;
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
 * only hooks. On Android 9 the public Typeface entry points are hooked, plus the hidden
 * {@code FontFamily.addFontFromAssetManager/addFontFromBuffer} and
 * {@code Typeface.createFromFamiliesWithDefault} used by res/font, AndroidX and FontsContract.
 * Downloadable fonts get their provider family name (FontsContract / FontsContractCompat), and
 * descriptor sources fall back to their /proc/self/fd font file name. A family is replaced only
 * when every member is body text. Each font is decided once; draw/measure/setTypeface/Paint/Canvas
 * are never touched.</p>
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
    /** Android 9: source key of the Typeface.Builder whose build() is running on this thread. */
    private static final ThreadLocal<String> P_BUILDER_KEY = new ThreadLocal<>();
    /** Android 9 hidden {@code android.graphics.FontFamily} -> fonts added to it (res/font, AndroidX, downloads). */
    private static final Map<Object, List<FontMember>> P_FAMILIES = Collections.synchronizedMap(new WeakHashMap<>());
    /** Downloadable-font {@code FontInfo} (framework or AndroidX) -> requested family name. */
    private static final Map<Object, String> DOWNLOAD_INFOS = Collections.synchronizedMap(new WeakHashMap<>());
    private static final Set<String> PENDING = ConcurrentHashMap.newKeySet();
    private static final AtomicBoolean SAVE_SCHEDULED = new AtomicBoolean();
    private static volatile ScheduledExecutorService worker;
    private static volatile File store;
    /** "Monospace to system monospace" switch (default off). Fixed for the process lifetime. */
    static volatile boolean monoSlot;

    static void install(XC_LoadPackage.LoadPackageParam lp, boolean monoToSystemMono) {
        monoSlot = monoToSystemMono;
        if (lp.appInfo != null && lp.appInfo.dataDir != null) {
            store = new File(lp.appInfo.dataDir, "cache/luoshu_global_font.tsv");
            worker().execute(FontHooks::loadStore); // file IO off the main thread
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            installQ();
        } else {
            installP();
        }
        installDownloadableNaming(lp.classLoader);
    }

    /**
     * Cache key for one source. With the mono switch on, verdicts are kept under their own key so a
     * face cached as KEEP while the switch was off is re-decided (and vice versa).
     */
    static String cacheKey(String key) {
        return monoSlot ? key + "~m" : key;
    }

    /** One font of a family: its source key (or null) plus its bytes when the framework exposes them. */
    static final class FontMember {
        final String name;
        final ByteBuffer buffer;

        FontMember(String name, ByteBuffer buffer) {
            this.name = name;
            this.buffer = buffer;
        }
    }

    /** Decision + cache key for one member; KEEP when nothing can be said yet. */
    private static final class Verdict {
        final String key;
        final FontDecision decision;

        Verdict(String key, FontDecision decision) {
            this.key = key;
            this.decision = decision;
        }
    }

    private static Verdict verdictFor(FontMember m) {
        String key;
        if (m.buffer != null) {
            key = cacheKey((m.name != null ? m.name : "buf:" + headerHash(m.buffer)) + "#" + m.buffer.capacity());
        } else if (m.name != null) {
            key = cacheKey(m.name);
        } else {
            return new Verdict(null, FontDecision.KEEP);
        }
        return new Verdict(key, decide(key, m.name, m.buffer));
    }

    /**
     * Whole-family verdict: any member kept (icon, emoji, undecided) keeps the family, otherwise the
     * first member decides. Returns null when the family should be left alone.
     */
    private static Typeface familyReplacement(List<FontMember> members, Typeface original) {
        if (members == null || members.isEmpty() || original == null) return null;
        ArrayList<FontDecision> decisions = new ArrayList<>(members.size());
        Verdict first = null;
        for (FontMember m : members) {
            // Every member is decided (cheap, cached) so their verdicts are warm for the next load.
            Verdict v = verdictFor(m);
            if (first == null) first = v;
            decisions.add(v.decision);
        }
        FontDecision d = FamilyVerdict.combine(decisions);
        if (!d.replaces() || first == null || first.key == null) return null;
        if (d == FontDecision.REPLACE_MONO && !MonoProbe.systemMonospaceIsFixedPitch()) {
            Log.v("system monospace is not fixed pitch, kept " + first.key);
            return null;
        }
        return styled(first.key, d, original.getWeight(), original.isItalic());
    }

    // ---------------------------------------------------------------- shared helpers

    /** Deoptimize every declared method of that name, matching {@code XposedBridge.hookAllMethods}. */
    private static void deoptAll(Class<?> type, String name) {
        try {
            for (Method m : type.getDeclaredMethods()) {
                if (m.getName().equals(name)) Deopt.member(m);
            }
        } catch (Throwable ignored) {
            // hooked exactly as before
        }
    }

    /** Deopt + hookAllMethods in its own try: a missing method only costs a log line. */
    private static void hookAll(Class<?> type, String name, XC_MethodHook hook) {
        if (type == null) return;
        try {
            deoptAll(type, name);
            int n = XposedBridge.hookAllMethods(type, name, hook).size();
            Log.v("hooked " + type.getName() + "#" + name + " x" + n);
        } catch (Throwable t) {
            Log.v("hook skipped " + type.getName() + "#" + name + ": " + t);
        }
    }

    // ---------------------------------------------------------------- Android 10+

    private static void installQ() {
        Deopt.constructors(Font.Builder.class);
        XposedBridge.hookAllConstructors(Font.Builder.class, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                String key = sourceKey(param.args);
                if (key == null) key = FontSources.unnamedKey(param.args); // download family / fd link
                if (key != null) BUILDER_KEYS.put(param.thisObject, key);
            }
        });
        Deopt.method(Font.Builder.class, "build");
        XposedHelpers.findAndHookMethod(Font.Builder.class, "build", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                Object font = param.getResult();
                String key = BUILDER_KEYS.remove(param.thisObject);
                if (font != null && key != null) FONT_KEYS.put(font, key);
            }
        });
        Deopt.constructor(Typeface.CustomFallbackBuilder.class, FontFamily.class);
        XposedHelpers.findAndHookConstructor(Typeface.CustomFallbackBuilder.class, FontFamily.class, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                FALLBACK_FAMILIES.put(param.thisObject, param.args[0]);
            }
        });
        Deopt.method(Typeface.CustomFallbackBuilder.class, "build");
        XposedHelpers.findAndHookMethod(Typeface.CustomFallbackBuilder.class, "build", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                Object family = FALLBACK_FAMILIES.remove(param.thisObject);
                Typeface result = (Typeface) param.getResult();
                if (family == null || result == null) return;
                try {
                    FontFamily fam = (FontFamily) family;
                    int size = fam.getSize();
                    if (size == 0) return;
                    ArrayList<FontMember> members = new ArrayList<>(size);
                    for (int i = 0; i < size; i++) {
                        Font font = fam.getFont(i);
                        members.add(new FontMember(FONT_KEYS.get(font), font.getBuffer()));
                    }
                    Typeface replacement = familyReplacement(members, result);
                    if (replacement != null) param.setResult(replacement);
                } catch (Throwable t) {
                    Log.v("fallback build skipped: " + t);
                }
            }
        });
    }

    /** Key that names where a Font.Builder reads from. Null when the source has no name. */
    static String sourceKey(Object[] args) {
        return FontSources.sourceKey(args, FONT_KEYS);
    }

    /** Name rules first; the sfnt check runs once, never on the main thread. */
    static FontDecision decide(String key, String name, ByteBuffer buffer) {
        FontDecision d = CACHE.get(key);
        if (d != null) return d;
        final boolean mono = monoSlot;
        d = name != null ? FontNameRules.classify(stripScheme(name), mono) : FontDecision.UNKNOWN;
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
                    FontDecision late = SfntInspector.decide(copy, mono);
                    CACHE.put(key, late);
                    PENDING.remove(key);
                    Log.v(late + " (sfnt, deferred) " + key);
                    scheduleSave();
                });
            }
            return FontDecision.KEEP;
        }
        d = SfntInspector.decide(buffer, mono);
        CACHE.put(key, d);
        Log.v(d + " (sfnt) " + key);
        scheduleSave();
        return d;
    }

    static Typeface styled(String key, FontDecision d, int weight, boolean italic) {
        String sk = DecisionCache.styleKey(key, weight, italic);
        Typeface cached = STYLED.get(sk);
        if (cached != null) return cached;
        String family = d == FontDecision.REPLACE_SERIF ? "serif" : d == FontDecision.REPLACE_MONO ? "mono" : "sans";
        String kind = family + '|' + weight + (italic ? "|i" : "|n");
        Typeface face = FACES.get(kind);
        if (face == null) {
            Typeface base = d == FontDecision.REPLACE_SERIF ? Typeface.SERIF
                    : d == FontDecision.REPLACE_MONO ? Typeface.MONOSPACE : Typeface.DEFAULT;
            int w = Math.max(1, Math.min(1000, weight));
            face = Typeface.create(base, w, italic);
            Typeface raced = FACES.putIfAbsent(kind, face);
            if (raced != null) face = raced;
        }
        STYLED.put(sk, face);
        return face;
    }

    static String stripScheme(String key) {
        return FontSources.stripScheme(key);
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
        Deopt.constructors(Typeface.Builder.class);
        XposedBridge.hookAllConstructors(Typeface.Builder.class, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                String key = sourceKey(param.args);
                if (key == null) key = FontSources.unnamedKey(param.args);
                if (key != null) BUILDER_KEYS.put(param.thisObject, key);
            }
        });
        Deopt.method(Typeface.Builder.class, "build");
        XposedHelpers.findAndHookMethod(Typeface.Builder.class, "build", new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                // Lets FontFamily.addFontFromBuffer inside build() name its buffer after this builder.
                P_BUILDER_KEY.set(BUILDER_KEYS.get(param.thisObject));
            }

            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                P_BUILDER_KEY.remove();
                replaceByName(param, BUILDER_KEYS.remove(param.thisObject));
            }
        });
        Deopt.method(Typeface.class, "createFromAsset", AssetManager.class, String.class);
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
        Deopt.method(Typeface.class, "createFromFile", String.class);
        Deopt.method(Typeface.class, "createFromFile", File.class);
        XposedHelpers.findAndHookMethod(Typeface.class, "createFromFile", String.class, fromFile);
        XposedHelpers.findAndHookMethod(Typeface.class, "createFromFile", File.class, fromFile);
        installPFontFamily();
    }

    /**
     * Android 8–9 res/font and AndroidX paths: {@code ResourcesImpl.loadFont} ->
     * {@code Typeface.createFromResources}, AndroidX {@code TypefaceCompatApi26Impl/28Impl}
     * ({@code ResourcesCompat.getFont}, Compose {@code Font(R.font.x)}) and
     * {@code FontsContract.buildTypeface} all register fonts with the hidden
     * {@code android.graphics.FontFamily} and finish with
     * {@code Typeface.createFromFamiliesWithDefault}. None of them go through Typeface.Builder's
     * public constructors, so they are hooked here. Each hook is independent and optional.
     */
    private static void installPFontFamily() {
        Class<?> fontFamily = XposedHelpers.findClassIfExists("android.graphics.FontFamily", null);
        if (fontFamily == null) {
            Log.v("android.graphics.FontFamily missing, res/font hooks skipped");
            return;
        }
        hookAll(fontFamily, "addFontFromAssetManager", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                if (!Boolean.TRUE.equals(param.getResult())) return;
                Object[] a = param.args;
                if (a.length < 2 || !(a[1] instanceof String)) return;
                boolean isAsset = a.length > 3 && Boolean.TRUE.equals(a[3]);
                addPFontMember(param.thisObject, new FontMember((isAsset ? "asset:" : "res:") + a[1], null));
            }
        });
        hookAll(fontFamily, "addFontFromBuffer", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                if (!Boolean.TRUE.equals(param.getResult())) return;
                Object a0 = param.args.length > 0 ? param.args[0] : null;
                if (!(a0 instanceof ByteBuffer)) return;
                String dl = FontSources.DOWNLOAD_NAME.get();
                addPFontMember(param.thisObject, new FontMember(dl != null ? "dl:" + dl : null, (ByteBuffer) a0));
            }
        });
        hookAll(Typeface.class, "createFromFamiliesWithDefault", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                try {
                    Object a0 = param.args.length > 0 ? param.args[0] : null;
                    Object result = param.getResult();
                    if (!(a0 instanceof Object[]) || !(result instanceof Typeface)) return;
                    Object[] families = (Object[]) a0;
                    if (families.length == 0 || families[0] == null) return;
                    List<FontMember> members = P_FAMILIES.get(families[0]);
                    if (members == null) return; // not a family this process registered (system fonts)
                    Typeface replacement;
                    synchronized (members) {
                        replacement = familyReplacement(new ArrayList<>(members), (Typeface) result);
                    }
                    if (replacement != null) param.setResult(replacement);
                } catch (Throwable t) {
                    Log.v("createFromFamiliesWithDefault skipped: " + t);
                }
            }
        });
    }

    private static void addPFontMember(Object family, FontMember m) {
        List<FontMember> list;
        synchronized (P_FAMILIES) {
            list = P_FAMILIES.get(family);
            if (list == null) {
                list = Collections.synchronizedList(new ArrayList<>(2));
                P_FAMILIES.put(family, list);
            }
        }
        list.add(m);
    }

    /** Android 9 has no Font object to inspect: name rules only, unknown names are kept. */
    private static void replaceByName(XC_MethodHook.MethodHookParam param, String key) {
        Typeface result = (Typeface) param.getResult();
        if (key == null || result == null || result == Typeface.DEFAULT) return;
        String ck = cacheKey(key);
        FontDecision d = CACHE.resolveByName(ck, monoSlot, stripScheme(key));
        if (!d.replaces()) return;
        if (d == FontDecision.REPLACE_MONO && !MonoProbe.systemMonospaceIsFixedPitch()) return;
        param.setResult(styled(ck, d, result.getWeight(), result.isItalic()));
    }

    // ---------------------------------------------------------------- downloadable font names

    /**
     * Gives downloadable fonts a name so the name rules can decide them on first load. The
     * provider request query ({@code name=Roboto&weight=700}) is remembered per returned
     * {@code FontInfo}; while that FontInfo array is being turned into a Typeface, the family name
     * is published on the building thread ({@link FontSources#DOWNLOAD_NAME}) and picked up by the
     * Font.Builder constructor hook (Android 10+) or FontFamily.addFontFromBuffer (Android 9).
     * Framework {@code FontsContract} plus AndroidX {@code FontsContractCompat} / {@code FontProvider}
     * / {@code TypefaceCompat} when present and not renamed by R8.
     */
    private static void installDownloadableNaming(ClassLoader appLoader) {
        XC_MethodHook fetch = new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                recordFetch(param.args, param.getResult());
            }
        };
        XC_MethodHook build = new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                String name = downloadNameOf(param.args);
                if (name == null) return;
                param.setObjectExtra("luoshu.prevDownloadName", FontSources.DOWNLOAD_NAME.get());
                param.setObjectExtra("luoshu.downloadName", name);
                FontSources.DOWNLOAD_NAME.set(name);
            }

            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                if (param.getObjectExtra("luoshu.downloadName") == null) return;
                Object prev = param.getObjectExtra("luoshu.prevDownloadName");
                if (prev instanceof String) FontSources.DOWNLOAD_NAME.set((String) prev);
                else FontSources.DOWNLOAD_NAME.remove();
            }
        };
        Class<?> fc = XposedHelpers.findClassIfExists("android.provider.FontsContract", null);
        hookAll(fc, "fetchFonts", fetch);
        hookAll(fc, "buildTypeface", build);
        if (appLoader == null) return;
        Class<?> compat = XposedHelpers.findClassIfExists("androidx.core.provider.FontsContractCompat", appLoader);
        hookAll(compat, "fetchFonts", fetch);
        hookAll(compat, "buildTypeface", build);
        Class<?> provider = XposedHelpers.findClassIfExists("androidx.core.provider.FontProvider", appLoader);
        hookAll(provider, "getFontFamilyResult", fetch);
        Class<?> typefaceCompat = XposedHelpers.findClassIfExists("androidx.core.graphics.TypefaceCompat", appLoader);
        hookAll(typefaceCompat, "createFromFontInfo", build);
    }

    /** fetchFonts(…, FontRequest) -> FontFamilyResult: remember request family for each FontInfo. */
    private static void recordFetch(Object[] args, Object result) {
        if (result == null || args == null) return;
        try {
            String name = null;
            for (Object a : args) {
                if (a == null) continue;
                String cls = a.getClass().getName();
                if (cls.endsWith("FontRequest")) {
                    Object q = XposedHelpers.callMethod(a, "getQuery");
                    name = SourceNames.familyFromQuery(q instanceof String ? (String) q : null);
                    break;
                }
            }
            if (name == null) return;
            Object fonts = XposedHelpers.callMethod(result, "getFonts");
            if (!(fonts instanceof Object[])) return;
            for (Object info : (Object[]) fonts) {
                if (info != null) DOWNLOAD_INFOS.put(info, name);
            }
        } catch (Throwable t) {
            Log.v("download name skipped: " + t);
        }
    }

    /** First requested family among FontInfo arrays in the arguments, or null. */
    private static String downloadNameOf(Object[] args) {
        if (args == null || DOWNLOAD_INFOS.isEmpty()) return null;
        for (Object a : args) {
            if (!(a instanceof Object[])) continue;
            for (Object info : (Object[]) a) {
                String n = info != null ? DOWNLOAD_INFOS.get(info) : null;
                if (n != null) return n;
            }
        }
        return null;
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
