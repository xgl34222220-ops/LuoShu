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
    /** Map code monospace faces to the system monospace slot instead of keeping them. */
    public static final String KEY_MONO_SLOT = "mono_to_system_mono";

    public static final boolean DEFAULT_ENABLED = true;
    public static final boolean DEFAULT_APP_FONTS = true;
    public static final boolean DEFAULT_WEB_FONTS = true;
    public static final boolean DEFAULT_WEB_BLOCK_UNKNOWN = false;
    public static final boolean DEFAULT_VERBOSE = false;
    /** Off: some apps rely on their own monospace metrics for alignment. */
    public static final boolean DEFAULT_MONO_SLOT = false;

    public static final String TAG = "LuoShuGlobalFont";
}
