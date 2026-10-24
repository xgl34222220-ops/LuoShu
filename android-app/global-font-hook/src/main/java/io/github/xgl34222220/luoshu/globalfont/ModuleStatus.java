package io.github.xgl34222220.luoshu.globalfont;

import android.content.Context;
import android.content.pm.PackageManager;

/*
 * What the LuoShu App shows about the built-in LSPosed module. Read in the App's own process only;
 * nothing here references the Xposed API, so the App runs the same with or without LSPosed.
 */
public final class ModuleStatus {
    private ModuleStatus() {}

    /*
     * Replaced with {@code return true} by {@link HookEntry} when LSPosed loads the module into the
     * App's own process (the App is in the module scope). Kept and never inlined (consumer-rules.pro).
     */
    public static boolean isModuleActive() {
        return Boolean.getBoolean("luoshu.gfh.module.self");
    }

    /*
     * True when LSPosed has activated this module: the self hook above fired, or LSPosed's
     * xposedsharedprefs support lets the App create world-readable module preferences (it only
     * does that for enabled modules, whether or not the App itself is in the scope).
     */
    public static boolean isActivated(Context context) {
        return isModuleActive() || SettingsActivity.worldReadablePrefs(context) != null;
    }

    /* The former standalone companion APK is still installed (it can be uninstalled now). */
    public static boolean legacyCompanionInstalled(Context context) {
        try {
            context.getPackageManager().getPackageInfo(ModuleConfig.LEGACY_COMPANION_PACKAGE, 0);
            return true;
        } catch (PackageManager.NameNotFoundException | RuntimeException e) {
            return false;
        }
    }
}
