package io.github.xgl34222220.luoshu.globalfont;

import android.os.Build;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XSharedPreferences;
import de.robv.android.xposed.XC_MethodReplacement;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/*
 * LSPosed entry. LSPosed only injects this class into apps the user ticked in the module scope, so
 * apps outside the scope pay nothing at all. Inside a scoped app the hooks are installed once per
 * process and only on font-loading entry points (never on draw / measure / setTypeface / Paint).
 *
 * <p>The module ships inside the LuoShu App. When LSPosed also loads it into the App's own process,
 * only {@link ModuleStatus#isModuleActive()} is replaced (one hook, no preferences, no font hooks),
 * so the App starts exactly as without LSPosed.
 */
public final class HookEntry implements IXposedHookLoadPackage {
    private static volatile boolean installed;

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lp) {
        if (!lp.isFirstApplication) return;
        if (ModuleConfig.isLuoShuApp(lp.packageName)) {
            markSelfActive(lp);
            return;
        }
        if (installed) return;
        if ("android".equals(lp.packageName) || ModuleConfig.LEGACY_COMPANION_PACKAGE.equals(lp.packageName)) return;
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) return;
        installed = true;
        // The former standalone companion APK sets the same marker once its font hooks are in. If it is
        // still enabled and already replaced fonts in this process, do not hook the same entries twice.
        if (ModuleConfig.alreadyReplaced()) {
            XposedBridge.log(ModuleConfig.TAG + ": " + ModuleConfig.PROCESS_MARKER
                    + " already set in " + lp.packageName + " (old companion module active), skipping");
            return;
        }

        boolean enabled = ModuleConfig.DEFAULT_ENABLED;
        boolean appFonts = ModuleConfig.DEFAULT_APP_FONTS;
        boolean webFonts = ModuleConfig.DEFAULT_WEB_FONTS;
        boolean blockUnknown = ModuleConfig.DEFAULT_WEB_BLOCK_UNKNOWN;
        boolean verbose = ModuleConfig.DEFAULT_VERBOSE;
        boolean monoSlot = ModuleConfig.DEFAULT_MONO_SLOT;
        try {
            // One small read per process; new-style XSharedPreferences (xposedminversion 93).
            XSharedPreferences prefs = new XSharedPreferences(ModuleConfig.MODULE_PACKAGE, ModuleConfig.PREFS);
            enabled = prefs.getBoolean(ModuleConfig.KEY_ENABLED, enabled);
            appFonts = prefs.getBoolean(ModuleConfig.KEY_APP_FONTS, appFonts);
            webFonts = prefs.getBoolean(ModuleConfig.KEY_WEB_FONTS, webFonts);
            blockUnknown = prefs.getBoolean(ModuleConfig.KEY_WEB_BLOCK_UNKNOWN, blockUnknown);
            verbose = prefs.getBoolean(ModuleConfig.KEY_VERBOSE, verbose);
            monoSlot = prefs.getBoolean(ModuleConfig.KEY_MONO_SLOT, monoSlot);
        } catch (Throwable t) {
            XposedBridge.log(ModuleConfig.TAG + ": prefs unavailable, using defaults: " + t);
        }
        if (!enabled) return;

        Log.verbose = verbose;
        if (appFonts) {
            try {
                FontHooks.install(lp, monoSlot);
                System.setProperty(ModuleConfig.PROCESS_MARKER, "1");
            } catch (Throwable t) {
                XposedBridge.log(ModuleConfig.TAG + ": font hooks failed in " + lp.packageName + ": " + t);
            }
        }
        if (webFonts) {
            try {
                WebFontHooks.install(blockUnknown);
            } catch (Throwable t) {
                XposedBridge.log(ModuleConfig.TAG + ": webview hooks failed in " + lp.packageName + ": " + t);
            }
        }
        Log.v("installed in " + lp.packageName + " appFonts=" + appFonts + " webFonts=" + webFonts + " monoSlot=" + monoSlot);
    }

    /* The App's own process: report "active" to the App and nothing else. */
    private static void markSelfActive(XC_LoadPackage.LoadPackageParam lp) {
        try {
            XposedHelpers.findAndHookMethod(ModuleStatus.class.getName(), lp.classLoader, "isModuleActive",
                    XC_MethodReplacement.returnConstant(Boolean.TRUE));
        } catch (Throwable t) {
            XposedBridge.log(ModuleConfig.TAG + ": self status hook failed: " + t);
        }
    }
}
