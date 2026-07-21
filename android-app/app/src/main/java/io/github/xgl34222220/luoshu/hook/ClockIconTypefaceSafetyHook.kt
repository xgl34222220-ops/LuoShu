package io.github.xgl34222220.luoshu.hook

import android.content.res.Resources
import android.graphics.Paint
import android.graphics.Typeface
import android.widget.TextView
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.util.ArrayDeque

/**
 * Safety layer for the clock-only final Typeface sinks.
 *
 * AppBundledFontHook intentionally runs a broad final assignment hook for HyperOS Clock because
 * some timer/alarm digits bypass normal font factories. This layer captures the caller's original
 * Typeface before that broad hook and restores it afterwards for icon fonts and, more importantly,
 * for every alarm playback/alert execution path.
 *
 * Clock child processes are treated as functional runtime processes rather than UI processes. Their
 * Typeface arguments are always restored so font customization cannot affect ringtone lifetime,
 * alarm receivers, full-screen alerts or notification services.
 */
class ClockIconTypefaceSafetyHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        val packageName = lpparam.packageName ?: return
        if (packageName !in CLOCK_PACKAGES) return
        val processName = lpparam.processName ?: packageName
        val restoreAll = !shouldInstallClockUiFontHooks(packageName, processName)

        runCatching { hookTextViewTypeface(packageName, processName, restoreAll) }
            .onFailure { log(packageName, processName, "TextView safety hook failed", it) }
        runCatching { hookPaintTypeface(packageName, processName, restoreAll) }
            .onFailure { log(packageName, processName, "Paint safety hook failed", it) }

        XposedBridge.log(
            "LuoShu ClockIconTypefaceSafetyHook active: package=$packageName " +
                "process=$processName restoreAll=$restoreAll",
        )
    }

    private fun hookTextViewTypeface(packageName: String, processName: String, restoreAll: Boolean) {
        val stack = ThreadLocal<ArrayDeque<CapturedTypeface>>()
        XposedBridge.hookAllMethods(
            TextView::class.java,
            "setTypeface",
            captureOriginalTypeface(stack),
        )
        XposedBridge.hookAllMethods(
            TextView::class.java,
            "setTypeface",
            object : XC_MethodHook(PRIORITY_AFTER_FONT_HOOK) {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    if (param.args.isEmpty()) return
                    val original = stack.get()?.peekLast()?.value
                    val view = param.thisObject as? TextView ?: return
                    val family = typefaceFamilyName(original)
                    val callers = if (restoreAll) emptyList() else currentCallerClassNames()
                    val criticalAlarmCall = !restoreAll && isClockAlarmCriticalCall(callers)
                    if (
                        !restoreAll &&
                        !criticalAlarmCall &&
                        !shouldPreserveClockTextTypeface(view.text, family)
                    ) {
                        return
                    }
                    param.args[0] = original
                    logPreservedOnce(
                        packageName = packageName,
                        processName = processName,
                        route = "TextView",
                        familyName = family,
                        text = view.text,
                        textSizeSp = null,
                        reason = when {
                            restoreAll -> "non-ui-process"
                            criticalAlarmCall -> "alarm-runtime"
                            else -> "icon-family"
                        },
                    )
                }
            },
        )
    }

    private fun hookPaintTypeface(packageName: String, processName: String, restoreAll: Boolean) {
        val stack = ThreadLocal<ArrayDeque<CapturedTypeface>>()
        XposedBridge.hookAllMethods(
            Paint::class.java,
            "setTypeface",
            captureOriginalTypeface(stack),
        )
        XposedBridge.hookAllMethods(
            Paint::class.java,
            "setTypeface",
            object : XC_MethodHook(PRIORITY_AFTER_FONT_HOOK) {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    if (param.args.isEmpty()) return
                    val original = stack.get()?.peekLast()?.value
                    val paint = param.thisObject as? Paint ?: return
                    val family = typefaceFamilyName(original)
                    val textSizeSp = paintTextSizeSp(paint)
                    val callers = if (restoreAll) emptyList() else currentCallerClassNames()
                    val criticalAlarmCall = !restoreAll && isClockAlarmCriticalCall(callers)
                    if (
                        !restoreAll &&
                        !criticalAlarmCall &&
                        !shouldPreserveClockPaintTypeface(
                            familyName = family,
                            systemDefault = isSystemDefaultTypeface(original),
                            textSizeSp = textSizeSp,
                            callerClassNames = callers,
                        )
                    ) {
                        return
                    }
                    param.args[0] = original
                    logPreservedOnce(
                        packageName = packageName,
                        processName = processName,
                        route = "Paint",
                        familyName = family,
                        text = null,
                        textSizeSp = textSizeSp,
                        reason = when {
                            restoreAll -> "non-ui-process"
                            criticalAlarmCall -> "alarm-runtime"
                            else -> "icon-family",
                        },
                    )
                }
            },
        )
    }

    private fun captureOriginalTypeface(
        stack: ThreadLocal<ArrayDeque<CapturedTypeface>>,
    ): XC_MethodHook = object : XC_MethodHook(PRIORITY_BEFORE_FONT_HOOK) {
        override fun beforeHookedMethod(param: MethodHookParam) {
            val entries = stack.get() ?: ArrayDeque<CapturedTypeface>().also(stack::set)
            entries.addLast(CapturedTypeface(param.args.getOrNull(0) as? Typeface))
        }

        override fun afterHookedMethod(param: MethodHookParam) {
            val entries = stack.get() ?: return
            if (entries.isNotEmpty()) entries.removeLast()
            if (entries.isEmpty()) stack.remove()
        }
    }

    private fun currentCallerClassNames(): List<String> = Thread.currentThread().stackTrace
        .asSequence()
        .drop(2)
        .take(MAX_CALLER_FRAMES)
        .map { it.className }
        .toList()

    private fun typefaceFamilyName(typeface: Typeface?): String? {
        typeface ?: return null
        for (field in FAMILY_NAME_FIELDS) {
            val value = runCatching {
                XposedHelpers.getObjectField(typeface, field) as? String
            }.getOrNull()
            if (!value.isNullOrBlank()) return value
        }
        return null
    }

    private fun paintTextSizeSp(paint: Paint): Float? {
        val scaledDensity = Resources.getSystem().displayMetrics.scaledDensity
        if (!scaledDensity.isFinite() || scaledDensity <= 0f) return null
        val value = paint.textSize / scaledDensity
        return value.takeIf { it.isFinite() && it >= 0f }
    }

    private fun isSystemDefaultTypeface(typeface: Typeface?): Boolean =
        typeface == null ||
            typeface === Typeface.DEFAULT ||
            typeface === Typeface.DEFAULT_BOLD ||
            typeface === Typeface.SANS_SERIF ||
            typeface === Typeface.SERIF

    private fun logPreservedOnce(
        packageName: String,
        processName: String,
        route: String,
        familyName: String?,
        text: CharSequence?,
        textSizeSp: Float?,
        reason: String,
    ) {
        val sample = text?.take(8)?.toString().orEmpty()
        val roundedSize = textSizeSp?.toInt()?.toString().orEmpty()
        val key = "$processName|$route|$reason|${familyName.orEmpty()}|$sample|$roundedSize"
        if (LOGGED_PRESERVATIONS.add(key)) {
            XposedBridge.log(
                "LuoShu Clock safety preserved [$packageName/$processName] " +
                    "$route reason=$reason family=${familyName ?: "unknown"} " +
                    "sizeSp=${textSizeSp ?: -1f}",
            )
        }
    }

    private fun log(packageName: String, processName: String, message: String, error: Throwable) {
        XposedBridge.log(
            "LuoShu ClockIconTypefaceSafetyHook [$packageName/$processName] $message: " +
                "${error.javaClass.simpleName}: ${error.message}",
        )
    }

    private data class CapturedTypeface(val value: Typeface?)

    private companion object {
        const val PRIORITY_BEFORE_FONT_HOOK = 10_000
        const val PRIORITY_AFTER_FONT_HOOK = -10_000
        const val MAX_CALLER_FRAMES = 28

        val FAMILY_NAME_FIELDS = listOf(
            "mSystemFontFamilyName",
            "mFontFamilyName",
            "mFamilyName",
        )
        val LOGGED_PRESERVATIONS = java.util.concurrent.ConcurrentHashMap.newKeySet<String>()
    }
}
