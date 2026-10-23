package io.github.xgl34222220.luoshu.globalfont;

import android.content.res.AssetManager;
import android.graphics.Typeface;
import android.graphics.fonts.Font;
import android.graphics.fonts.FontFamily;
import android.os.Build;
import android.os.Looper;
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
 * only hooks. Android 9 additionally needs the hidden {@code android.graphics.FontFamily} add calls
 * and {@code Typeface.createFromFamiliesWithDefault}, which res/font, AndroidX and FontsContract use.
 * Fonts from a provider are named after the requested family, descriptor fonts after the file they
 * point to. A family with several fonts is swapped only when every font in it is body text. Each font
 * is decided once; draw/measure/setTypeface/Paint/Canvas are never touched.</p>
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
    /** Android 9: hidden FontFamily instance -> fonts this process added to it. */
    private static final Map<Object, List<Member>> P_MEMBERS = Collections.synchronizedMap(new WeakHashMap<>());
    /** Provider FontInfo (framework or AndroidX) -> family named in its FontRequest. */
    private static final Map<Object, String> PROVIDER_FAMILIES = Collections.synchronizedMap(new WeakHashMap<>());
    private static final Set<String> PENDING = ConcurrentHashMap.newKeySet();
    private static final AtomicBoolean SAVE_SCHEDULED = new AtomicBoolean();
    private static volatile ScheduledExecutorService worker;
    private static volatile File store;
    /** "Monospace to system monospace" switch, read once per process (default off). */
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
        installProviderNaming(lp.classLoader);
    }

    /** A font of a family: where it came from (may be null) and its bytes (null on Android 9 assets). */
    static final class Member {
        final String name;
        final ByteBuffer bytes;

        Member(String name, ByteBuffer bytes) {
            this.name = name;
            this.bytes = bytes;
        }

        /** Cache key: buffers are keyed by name (or header CRC) plus size, names by themselves. */
        String key() {
            if (bytes != null) {
                String id = name != null ? name : "buf:" + headerHash(bytes);
                return SourceKeys.withMono(id + "#" + bytes.capacity(), monoSlot);
            }
            return name != null ? SourceKeys.withMono(name, monoSlot) : null;
        }
    }

    /**
     * Replacement for a whole family, or null to leave it. Every member is decided (so the cache is
     * warm next time); the first member's key and the combined verdict pick the system face.
     */
    private static Typeface replaceFamily(List<Member> members, Typeface built) {
        if (built == null || members == null || members.isEmpty()) return null;
        List<FontDecision> verdicts = new ArrayList<>(members.size());
        String leadKey = null;
        for (int i = 0; i < members.size(); i++) {
            Member m = members.get(i);
            String key = m.key();
            if (i == 0) leadKey = key;
            verdicts.add(key == null ? FontDecision.KEEP : decide(key, m.name, m.bytes));
        }
        FontDecision d = FamilyVerdict.combine(verdicts);
        if (leadKey == null || !d.replaces() || !monoUsable(d, leadKey)) return null;
        return styled(leadKey, d, built.getWeight(), built.isItalic());
    }

    /** REPLACE_MONO is only applied when the system monospace face measures as fixed pitch. */
    private static boolean monoUsable(FontDecision d, String key) {
        if (d != FontDecision.REPLACE_MONO || MonoProbe.systemMonospaceIsFixedPitch()) return true;
        Log.v("system monospace not fixed pitch, kept " + key);
        return false;
    }

    /** hookAllMethods after deoptimizing every overload; a missing class or method is only logged. */
    private static void hookEvery(Class<?> type, String method, XC_MethodHook hook) {
        if (type == null) return;
        try {
            for (java.lang.reflect.Method m : type.getDeclaredMethods()) {
                if (m.getName().equals(method)) Deopt.member(m);
            }
            Log.v("hooked " + type.getName() + "#" + method + " x" + XposedBridge.hookAllMethods(type, method, hook).size());
        } catch (Throwable t) {
            Log.v("hook skipped " + type.getName() + "#" + method + ": " + t);
        }
    }

    // ---------------------------------------------------------------- Android 10+

    private static void installQ() {
        Deopt.constructors(Font.Builder.class);
        XposedBridge.hookAllConstructors(Font.Builder.class, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                String key = sourceKey(param.args);
                if (key == null) key = SourceKeys.fallback(param.args);
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
                    List<Member> members = new ArrayList<>(fam.getSize());
                    for (int i = 0; i < fam.getSize(); i++) {
                        Font font = fam.getFont(i);
                        members.add(new Member(FONT_KEYS.get(font), font.getBuffer()));
                    }
                    Typeface replacement = replaceFamily(members, result);
                    if (replacement != null) param.setResult(replacement);
                } catch (Throwable t) {
                    Log.v("fallback build skipped: " + t);
                }
            }
        });
    }

    /** Key that names where a Font.Builder reads from. Null when the source has no name. */
    static String sourceKey(Object[] args) {
        return SourceKeys.named(args, FONT_KEYS);
    }

    /** Name rules first; the sfnt check runs once, never on the main thread. */
    static FontDecision decide(String key, String name, ByteBuffer buffer) {
        FontDecision d = CACHE.get(key);
        if (d != null) return d;
        final boolean mono = monoSlot;
        d = name != null ? FontNameRules.classify(SourceKeys.nameOf(name), mono) : FontDecision.UNKNOWN;
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
        Typeface base;
        String slot;
        if (d == FontDecision.REPLACE_MONO) {
            base = Typeface.MONOSPACE;
            slot = "mono";
        } else if (d == FontDecision.REPLACE_SERIF) {
            base = Typeface.SERIF;
            slot = "serif";
        } else {
            base = Typeface.DEFAULT;
            slot = "sans";
        }
        String kind = slot + '|' + weight + (italic ? "|i" : "|n");
        Typeface face = FACES.get(kind);
        if (face == null) {
            int w = Math.max(1, Math.min(1000, weight));
            face = Typeface.create(base, w, italic);
            Typeface raced = FACES.putIfAbsent(kind, face);
            if (raced != null) face = raced;
        }
        STYLED.put(sk, face);
        return face;
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
                if (key == null) key = SourceKeys.fallback(param.args);
                if (key != null) BUILDER_KEYS.put(param.thisObject, key);
            }
        });
        Deopt.method(Typeface.Builder.class, "build");
        XposedHelpers.findAndHookMethod(Typeface.Builder.class, "build", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
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
        installHiddenFontFamily();
    }

    /**
     * Android 9 (and 8) res/font, AndroidX TypefaceCompatApi26/28Impl and FontsContract build
     * typefaces by adding fonts to the hidden {@code android.graphics.FontFamily} and calling
     * {@code Typeface.createFromFamiliesWithDefault(FontFamily[], ...)}, bypassing the public
     * builders. AOSP signatures: {@code addFontFromAssetManager(AssetManager, String path, int cookie,
     * boolean isAsset, ...)} and {@code addFontFromBuffer(ByteBuffer, ...)}, both returning boolean.
     */
    private static void installHiddenFontFamily() {
        Class<?> hidden = XposedHelpers.findClassIfExists("android.graphics.FontFamily", null);
        if (hidden == null) {
            Log.v("android.graphics.FontFamily not found, res/font path not hooked");
            return;
        }
        hookEvery(hidden, "addFontFromAssetManager", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                Object[] a = param.args;
                if (!Boolean.TRUE.equals(param.getResult()) || a.length < 2 || !(a[1] instanceof String)) return;
                boolean asset = a.length >= 4 && Boolean.TRUE.equals(a[3]);
                remember(param.thisObject, new Member((asset ? "asset:" : "res:") + a[1], null));
            }
        });
        hookEvery(hidden, "addFontFromBuffer", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                Object a0 = param.args.length > 0 ? param.args[0] : null;
                if (!Boolean.TRUE.equals(param.getResult()) || !(a0 instanceof ByteBuffer)) return;
                String family = SourceKeys.DOWNLOAD_FAMILY.get();
                remember(param.thisObject, new Member(family == null ? null : "dl:" + family, (ByteBuffer) a0));
            }
        });
        hookEvery(Typeface.class, "createFromFamiliesWithDefault", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                try {
                    Object arr = param.args.length > 0 ? param.args[0] : null;
                    Object built = param.getResult();
                    if (!(arr instanceof Object[]) || !(built instanceof Typeface)) return;
                    Object[] families = (Object[]) arr;
                    List<Member> members = families.length > 0 && families[0] != null ? P_MEMBERS.get(families[0]) : null;
                    if (members == null) return; // not built from fonts this process added
                    List<Member> snapshot;
                    synchronized (members) {
                        snapshot = new ArrayList<>(members);
                    }
                    Typeface replacement = replaceFamily(snapshot, (Typeface) built);
                    if (replacement != null) param.setResult(replacement);
                } catch (Throwable t) {
                    Log.v("createFromFamiliesWithDefault skipped: " + t);
                }
            }
        });
    }

    private static void remember(Object family, Member m) {
        List<Member> list;
        synchronized (P_MEMBERS) {
            list = P_MEMBERS.get(family);
            if (list == null) P_MEMBERS.put(family, list = Collections.synchronizedList(new ArrayList<>()));
        }
        list.add(m);
    }

    /** Android 9 has no Font object to inspect: name rules only, unknown names are kept. */
    private static void replaceByName(XC_MethodHook.MethodHookParam param, String key) {
        Typeface result = (Typeface) param.getResult();
        if (key == null || result == null || result == Typeface.DEFAULT) return;
        String ck = SourceKeys.withMono(key, monoSlot);
        FontDecision d = CACHE.resolveByName(ck, monoSlot, SourceKeys.nameOf(key));
        if (!d.replaces() || !monoUsable(d, ck)) return;
        param.setResult(styled(ck, d, result.getWeight(), result.isItalic()));
    }

    // ---------------------------------------------------------------- provider (downloadable) fonts

    /**
     * Names provider fonts after the family in their FontRequest so name rules can decide them.
     * {@code fetchFonts}/{@code getFontFamilyResult} return a result whose {@code getFonts()} lists
     * FontInfo objects; each is mapped to the request family. While {@code buildTypeface} /
     * {@code createFromFontInfo} turns those FontInfo into a Typeface, the family is exposed on the
     * thread through {@link SourceKeys#DOWNLOAD_FAMILY}. AndroidX classes are used only when the app
     * ships them under their public names.
     */
    private static void installProviderNaming(ClassLoader appLoader) {
        XC_MethodHook onFetch = new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                mapFontInfos(param.args, param.getResult());
            }
        };
        XC_MethodHook onBuild = new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                String family = familyOfInfos(param.args);
                if (family == null) return;
                param.setObjectExtra("luoshu.outerFamily", SourceKeys.DOWNLOAD_FAMILY.get());
                param.setObjectExtra("luoshu.scoped", Boolean.TRUE);
                SourceKeys.DOWNLOAD_FAMILY.set(family);
            }

            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                if (param.getObjectExtra("luoshu.scoped") == null) return;
                Object outer = param.getObjectExtra("luoshu.outerFamily");
                if (outer instanceof String) SourceKeys.DOWNLOAD_FAMILY.set((String) outer);
                else SourceKeys.DOWNLOAD_FAMILY.remove();
            }
        };
        Class<?> framework = XposedHelpers.findClassIfExists("android.provider.FontsContract", null);
        hookEvery(framework, "fetchFonts", onFetch);
        hookEvery(framework, "buildTypeface", onBuild);
        if (appLoader == null) return;
        Class<?> compat = XposedHelpers.findClassIfExists("androidx.core.provider.FontsContractCompat", appLoader);
        hookEvery(compat, "fetchFonts", onFetch);
        hookEvery(compat, "buildTypeface", onBuild);
        hookEvery(XposedHelpers.findClassIfExists("androidx.core.provider.FontProvider", appLoader), "getFontFamilyResult", onFetch);
        hookEvery(XposedHelpers.findClassIfExists("androidx.core.graphics.TypefaceCompat", appLoader), "createFromFontInfo", onBuild);
    }

    private static void mapFontInfos(Object[] args, Object result) {
        if (args == null || result == null) return;
        try {
            String family = null;
            for (Object a : args) {
                if (a != null && a.getClass().getSimpleName().equals("FontRequest")) {
                    Object query = XposedHelpers.callMethod(a, "getQuery");
                    family = SourceNames.familyFromQuery(query instanceof String ? (String) query : null);
                    break;
                }
            }
            if (family == null) return;
            Object infos = XposedHelpers.callMethod(result, "getFonts");
            if (!(infos instanceof Object[])) return;
            for (Object info : (Object[]) infos) {
                if (info != null) PROVIDER_FAMILIES.put(info, family);
            }
        } catch (Throwable t) {
            Log.v("provider font naming skipped: " + t);
        }
    }

    private static String familyOfInfos(Object[] args) {
        if (args == null || PROVIDER_FAMILIES.isEmpty()) return null;
        for (Object a : args) {
            if (!(a instanceof Object[])) continue;
            for (Object info : (Object[]) a) {
                String family = info == null ? null : PROVIDER_FAMILIES.get(info);
                if (family != null) return family;
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
