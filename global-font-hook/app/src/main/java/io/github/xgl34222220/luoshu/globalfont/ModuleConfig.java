package io.github.xgl34222220.luoshu.globalfont;

/** Preference keys shared by the companion UI and the hook side. */
public final class ModuleConfig {
    private ModuleConfig() {}

    public static final String MODULE_PACKAGE = "io.github.xgl34222220.luoshu.globalfont";
    public static final String PREFS = "global_font";
    public static final String KEY_ENABLED = "enabled";
    public static final String KEY_APP_FONTS = "app_fonts";
    public static final String KEY_WEB_FONTS = "web_fonts";
    public static final String KEY_WEB_BLOCK_UNKNOWN = "web_block_unknown";
    public static final String KEY_VERBOSE = "verbose_log";
    /** Map programming monospace faces onto the system monospace face. */
    public static final String KEY_MONO_SLOT = "mono_to_system_mono";

    public static final boolean DEFAULT_ENABLED = true;
    public static final boolean DEFAULT_APP_FONTS = true;
    public static final boolean DEFAULT_WEB_FONTS = true;
    public static final boolean DEFAULT_WEB_BLOCK_UNKNOWN = false;
    public static final boolean DEFAULT_VERBOSE = false;
    /** Off by default: some apps align text using their own monospace metrics. */
    public static final boolean DEFAULT_MONO_SLOT = false;

    /**
     * Process-wide marker, set with {@code System.setProperty} once the app-font hooks are installed
     * in a process. A native companion can read it to leave the Java font path to this module.
     */
    public static final String PROCESS_MARKER = "luoshu.gfh.active";

    public static final String TAG = "LuoShuGlobalFont";
}
