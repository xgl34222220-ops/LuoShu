package io.github.xgl34222220.luoshu.globalfont;

import android.content.res.AssetManager;
import android.content.res.Resources;
import android.os.ParcelFileDescriptor;
import android.system.Os;
import io.github.xgl34222220.luoshu.globalfont.rules.SourceNames;
import java.io.File;
import java.io.FileDescriptor;
import java.util.Map;

/**
 * Names where a font is loaded from. Framework types only (no Xposed classes), so the instrumented
 * tests can feed it real {@code Resources}, assets and descriptors on every API level.
 *
 * <p>Key schemes: {@code file:}, {@code asset:}, {@code res:} (resource entry name, or the
 * res/font path on Android 9), {@code dl:} (downloadable-font family from the provider request),
 * {@code fd:} (descriptor whose /proc/self/fd link is a real font file).</p>
 */
final class FontSources {
    private FontSources() {}

    /** Family of the downloadable-font request being built on this thread, if any. */
    static final ThreadLocal<String> DOWNLOAD_NAME = new ThreadLocal<>();

    /** Key that names where a Font.Builder / Typeface.Builder reads from. Null when unnamed. */
    static String sourceKey(Object[] args, Map<Object, String> fontKeys) {
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
        // android.graphics.fonts.Font only exists on Android 10+; never touch the class on Android 9.
        if (fontKeys != null && android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q
                && a instanceof android.graphics.fonts.Font) {
            return fontKeys.get(a);
        }
        return null; // ByteBuffer / ParcelFileDescriptor / FileDescriptor
    }

    /** Name part of a key: drops the scheme ("asset:", "res:", "dl:", "fd:") and the mono-switch suffix. */
    static String stripScheme(String key) {
        String k = key.endsWith("~m") ? key.substring(0, key.length() - 2) : key;
        int colon = k.indexOf(':');
        return colon >= 0 && colon < 7 ? k.substring(colon + 1) : k;
    }

    /**
     * Name for a source {@link #sourceKey} could not name: the downloadable-font family being built
     * on this thread first, then a descriptor that points at a real font file. Null otherwise.
     */
    static String unnamedKey(Object[] args) {
        String dl = DOWNLOAD_NAME.get();
        if (dl != null) return "dl:" + dl;
        if (args == null || args.length == 0) return null;
        String path = descriptorFontPath(args[0]);
        return path != null ? "fd:" + path : null;
    }

    /** /proc/self/fd link of a PFD or FileDescriptor when it is a font file, else null. */
    static String descriptorFontPath(Object source) {
        try {
            if (source instanceof ParcelFileDescriptor) {
                return linkPath(((ParcelFileDescriptor) source).getFd());
            }
            if (source instanceof FileDescriptor) {
                // Public API only (no hidden "descriptor" field): dup, read the link, close the dup.
                try (ParcelFileDescriptor dup = ParcelFileDescriptor.dup((FileDescriptor) source)) {
                    return linkPath(dup.getFd());
                }
            }
        } catch (Throwable t) {
            // closed / invalid descriptor: unnamed, the sfnt check decides
        }
        return null;
    }

    private static String linkPath(int fd) throws Exception {
        if (fd < 0) return null;
        return SourceNames.fontPathFromLink(Os.readlink("/proc/self/fd/" + fd));
    }
}
