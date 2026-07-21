package io.github.xgl34222220.luoshu.hook

import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.callbacks.XC_LoadPackage

/**
 * Scope gate for the generic APK-bundled-font replacement entry.
 *
 * Clock must never initialize AppBundledFontHook: even callbacks that immediately return still
 * register global Typeface/Font/Resources methods in the alarm process. Clock uses the isolated
 * ClockUiDrawFontHook instead. QQ/TIM remain delegated so AppBundledFontHook can apply its existing
 * dedicated early-return policy without changing behavior for Play and other scoped applications.
 */
class ScopedAppBundledFontHook : IXposedHookLoadPackage {
    private val delegate = AppBundledFontHook()

    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        val packageName = lpparam.packageName ?: return
        if (packageName in CLOCK_PACKAGES) {
            XposedBridge.log("LuoShu generic App font hook not initialized for Clock: $packageName")
            return
        }
        delegate.handleLoadPackage(lpparam)
    }
}
