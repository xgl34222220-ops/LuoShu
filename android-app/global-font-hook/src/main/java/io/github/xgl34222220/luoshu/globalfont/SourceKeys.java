package io.github.xgl34222220.luoshu.globalfont;

import android.content.res.AssetManager;
import android.content.res.Resources;
import android.os.Build;
import android.os.ParcelFileDescriptor;
import android.system.Os;
import io.github.xgl34222220.luoshu.globalfont.rules.SourceNames;
import java.io.File;
import java.io.FileDescriptor;
import java.util.Map;

/*
 * Turns font-loading arguments into a cache key {@code scheme:name}. Only framework classes are
 * used here so instrumented tests can call it without Xposed.
 *
 * <p>Schemes: {@code file:} path, {@code asset:} asset path, {@code res:} resource entry name (or
 * res/font path on Android 9), {@code dl:} downloadable-font family, {@code fd:} font file behind a
 * descriptor.</p>
 */
final class SourceKeys {
    private SourceKeys() {}

    /* Downloadable-font family currently being turned into a Typeface on this thread. */
    static final ThreadLocal<String> DOWNLOAD_FAMILY = new ThreadLocal<>();

    private static final String MONO_SUFFIX = "~m";

    /* Key for constructor arguments that carry a name; null for buffers and descriptors. */
    static String named(Object[] args, Map<Object, String> fontKeys) {
        Object first = args != null && args.length > 0 ? args[0] : null;
        Object second = args != null && args.length > 1 ? args[1] : null;
        if (first instanceof File) return "file:" + ((File) first).getPath();
        if (first instanceof String) return "file:" + first;
        if (first instanceof AssetManager) return second instanceof String ? "asset:" + second : null;
        if (first instanceof Resources) {
            if (!(second instanceof Integer)) return null;
            try {
                return "res:" + ((Resources) first).getResourceEntryName((Integer) second);
            } catch (Resources.NotFoundException e) {
                return null;
            }
        }
        // Font(Font) copy constructor, Android 10+ only; the class must not be referenced on 9.
        if (fontKeys != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
                && first instanceof android.graphics.fonts.Font) {
            return fontKeys.get(first);
        }
        return null;
    }

    /*
     * Second-chance key for unnamed sources: the downloadable family set for this thread, else the
     * font file a descriptor points to. Null when neither applies.
     */
    static String fallback(Object[] args) {
        String family = DOWNLOAD_FAMILY.get();
        if (family != null) return "dl:" + family;
        String path = args != null && args.length > 0 ? descriptorFontPath(args[0]) : null;
        return path == null ? null : "fd:" + path;
    }

    /* The name inside a key: no scheme prefix and no mono-switch suffix. */
    static String nameOf(String key) {
        String k = key.endsWith(MONO_SUFFIX) ? key.substring(0, key.length() - MONO_SUFFIX.length()) : key;
        int colon = k.indexOf(':');
        return colon >= 0 && colon <= 6 ? k.substring(colon + 1) : k;
    }

    /* Separate cache slot for verdicts made with the mono switch on. */
    static String withMono(String key, boolean monoSlot) {
        return monoSlot ? key + MONO_SUFFIX : key;
    }

    /* Font file path behind a {@link ParcelFileDescriptor} or {@link FileDescriptor}, else null. */
    static String descriptorFontPath(Object source) {
        try {
            if (source instanceof ParcelFileDescriptor) {
                return fdLinkFont(((ParcelFileDescriptor) source).getFd());
            }
            if (source instanceof FileDescriptor) {
                // ParcelFileDescriptor.dup is public API; it gives us an int fd to resolve.
                ParcelFileDescriptor copy = ParcelFileDescriptor.dup((FileDescriptor) source);
                try {
                    return fdLinkFont(copy.getFd());
                } finally {
                    copy.close();
                }
            }
        } catch (Exception | LinkageError e) {
            // invalid or closed descriptor: stays unnamed
        }
        return null;
    }

    private static String fdLinkFont(int fd) throws Exception {
        return fd < 0 ? null : SourceNames.fontPathFromLink(Os.readlink("/proc/self/fd/" + fd));
    }
}
