package io.github.xgl34222220.luoshu.hook

import android.graphics.Typeface
import android.os.Build
import android.util.TypedValue
import android.widget.EditText
import android.widget.TextView
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.abs

/**
 * QQ/TIM compatibility layer.
 *
 * HyperOS QQ mixes OEM aliases and custom TextViews, which can leave one screen using several
 * Typeface objects. This hook is intentionally limited to the main QQ/TIM UI process and only
 * touches TextView/factory assignment; it never hooks Paint or Canvas hot paths.
 *
 * Compact tags are handled separately on every ROM. They are adjusted only when the selected
 * font's measured vertical metrics are actually taller than the available one-line content box.
 */
class QqFontCompatibilityHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        val packageName = lpparam.packageName ?: return
        val processName = lpparam.processName ?: packageName
        if (!isQqUiProcess(packageName, processName)) return

        // Avoid hidden SystemProperties APIs inside third-party processes. Xiaomi/Redmi/POCO public
        // Build identity is sufficient for deciding whether the HyperOS-only unification layer runs.
        val hyperOs = isHyperOsFamily(
            manufacturer = Build.MANUFACTURER,
            brand = Build.BRAND,
            miOsVersionName = null,
            miuiVersionCode = null,
        )

        if (hyperOs) {
            runCatching { hookTextViewTypeface(packageName) }
                .onFailure { log(packageName, "TextView unification hook failed", it) }
            runCatching { hookNamedFamilyFactory(packageName) }
                .onFailure { log(packageName, "Typeface family hook failed", it) }
        }
        runCatching { hookCompactLabels(packageName) }
            .onFailure { log(packageName, "compact-label metrics hook failed", it) }

        XposedBridge.log(
            "LuoShu QqFontCompatibilityHook active: package=$packageName process=$processName " +
                "hyperOs=$hyperOs",
        )
    }

    private fun hookTextViewTypeface(packageName: String) {
        XposedBridge.hookAllMethods(
            TextView::class.java,
            "setTypeface",
            object : XC_MethodHook() {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    if (TYPEFACE_GUARD.get() == true || param.args.isEmpty()) return
                    val view = param.thisObject as? TextView ?: return
                    val original = param.args.getOrNull(0) as? Typeface
                    val family = typefaceFamilyName(original)
                    if (shouldPreserveQqTypeface(view.text, family)) return
                    if (!isReplaceableQqFamily(family)) return

                    val explicitStyle = param.args.getOrNull(1) as? Int
                    val weight = original?.weight ?: if (
                        (explicitStyle ?: Typeface.NORMAL) and Typeface.BOLD != 0
                    ) {
                        700
                    } else {
                        400
                    }
                    val italic = when {
                        explicitStyle != null -> explicitStyle and Typeface.ITALIC != 0
                        else -> original?.isItalic == true
                    }
                    val replacement = replacementTypeface(weight, italic) ?: return
                    param.args[0] = replacement
                    logReplacementOnce(packageName, "TextView", family, weight)
                }
            },
        )
    }

    private fun hookNamedFamilyFactory(packageName: String) {
        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "create",
            String::class.java,
            Int::class.javaPrimitiveType,
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    if (TYPEFACE_GUARD.get() == true) return
                    val family = param.args.getOrNull(0) as? String ?: return
                    if (!isReplaceableQqFamily(family)) return
                    val style = param.args.getOrNull(1) as? Int ?: Typeface.NORMAL
                    val weight = if (style and Typeface.BOLD != 0) 700 else 400
                    val replacement = replacementTypeface(weight, style and Typeface.ITALIC != 0) ?: return
                    param.result = replacement
                    logReplacementOnce(packageName, "Typeface.create", family, weight)
                }
            },
        )
    }

    private fun hookCompactLabels(packageName: String) {
        XposedBridge.hookAllMethods(
            TextView::class.java,
            "onLayout",
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    if (LABEL_GUARD.get() == true) return
                    val view = param.thisObject as? TextView ?: return
                    if (view is EditText || view.height <= 0 || view.text.isNullOrEmpty()) {
                        restoreRecycledLabelIfNeeded(view)
                        return
                    }

                    val currentSizePx = view.textSize
                    var state = XposedHelpers.getAdditionalInstanceField(
                        view,
                        LABEL_SIZE_STATE_KEY,
                    ) as? LabelSizeState

                    // If QQ itself changed the recycled view's size after our adjustment, discard the
                    // stale state instead of restoring a size that belonged to an older chip.
                    if (
                        state != null &&
                        abs(currentSizePx - state.appliedPx) > LABEL_SIZE_EPSILON_PX &&
                        abs(currentSizePx - state.originalPx) > LABEL_SIZE_EPSILON_PX
                    ) {
                        XposedHelpers.removeAdditionalInstanceField(view, LABEL_SIZE_STATE_KEY)
                        state = null
                    }

                    val originalSizePx = state?.originalPx ?: currentSizePx
                    val metrics = view.resources.displayMetrics
                    val density = metrics.density.takeIf { it.isFinite() && it > 0f } ?: return
                    val scaledDensity = metrics.scaledDensity.takeIf { it.isFinite() && it > 0f } ?: return
                    val textSizeSp = originalSizePx / scaledDensity
                    val heightDp = view.height / density
                    val candidate = isCompactQqLabelCandidate(
                        textSizeSp = textSizeSp,
                        heightDp = heightDp,
                        lineCount = view.lineCount,
                        textLength = view.text.length,
                        editable = false,
                    )
                    if (!candidate) {
                        restoreRecycledLabelIfNeeded(view, state)
                        return
                    }

                    val available = view.height - view.compoundPaddingTop - view.compoundPaddingBottom
                    val fontMetrics = view.paint.fontMetricsInt
                    val currentFontHeight = if (view.includeFontPadding) {
                        fontMetrics.bottom - fontMetrics.top
                    } else {
                        fontMetrics.descent - fontMetrics.ascent
                    }
                    val originalFontHeight = originalQqLabelFontHeightPx(
                        currentFontHeightPx = currentFontHeight,
                        currentTextSizePx = currentSizePx,
                        originalTextSizePx = originalSizePx,
                    )
                    val targetPx = fittedQqLabelTextSizePx(
                        currentTextSizePx = originalSizePx,
                        availableHeightPx = available,
                        fontHeightPx = originalFontHeight,
                    )

                    if (targetPx == null) {
                        restoreRecycledLabelIfNeeded(view, state)
                        return
                    }
                    if (abs(currentSizePx - targetPx) <= LABEL_SIZE_EPSILON_PX) return

                    LABEL_GUARD.set(true)
                    try {
                        view.setTextSize(TypedValue.COMPLEX_UNIT_PX, targetPx)
                        XposedHelpers.setAdditionalInstanceField(
                            view,
                            LABEL_SIZE_STATE_KEY,
                            LabelSizeState(originalPx = originalSizePx, appliedPx = targetPx),
                        )
                        view.requestLayout()
                    } finally {
                        LABEL_GUARD.remove()
                    }
                    logLabelAdjustmentOnce(packageName, view, "fit-metrics")
                }
            },
        )
    }

    private fun restoreRecycledLabelIfNeeded(
        view: TextView,
        knownState: LabelSizeState? = null,
    ) {
        val state = knownState ?: XposedHelpers.getAdditionalInstanceField(
            view,
            LABEL_SIZE_STATE_KEY,
        ) as? LabelSizeState ?: return

        XposedHelpers.removeAdditionalInstanceField(view, LABEL_SIZE_STATE_KEY)
        if (abs(view.textSize - state.appliedPx) > LABEL_SIZE_EPSILON_PX) return

        LABEL_GUARD.set(true)
        try {
            view.setTextSize(TypedValue.COMPLEX_UNIT_PX, state.originalPx)
            view.requestLayout()
        } finally {
            LABEL_GUARD.remove()
        }
    }

    private fun replacementTypeface(weight: Int, italic: Boolean): Typeface? {
        val normalizedWeight = weight.coerceIn(1, 1000)
        val styleKey = "$normalizedWeight|$italic"
        STYLED_TYPEFACE_CACHE[styleKey]?.let { return it }

        val source = sourceForWeight(normalizedWeight) ?: return null
        val base = TYPEFACE_CACHE[source] ?: runCatching {
            TYPEFACE_GUARD.set(true)
            Typeface.createFromFile(source)
        }.getOrNull().also { TYPEFACE_GUARD.remove() }?.also { TYPEFACE_CACHE[source] = it } ?: return null

        val styled = runCatching {
            TYPEFACE_GUARD.set(true)
            // LuoShu minSdk is API 28, so the exact-weight overload is always available.
            Typeface.create(base, normalizedWeight, italic)
        }.getOrDefault(base).also { TYPEFACE_GUARD.remove() }
        STYLED_TYPEFACE_CACHE.putIfAbsent(styleKey, styled)
        return STYLED_TYPEFACE_CACHE[styleKey] ?: styled
    }

    private fun sourceForWeight(weight: Int): String? {
        val nearest = AVAILABLE_WEIGHTS.minByOrNull { kotlin.math.abs(it - weight) } ?: 400
        val candidates = listOf(
            "/system/fonts/$nearest.ttf",
            "/system/fonts/400.ttf",
            "/system/fonts/MiSansVF.ttf",
            "/system/fonts/Roboto-Regular.ttf",
        )
        return candidates.firstOrNull { File(it).canRead() }
    }

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

    private fun logReplacementOnce(packageName: String, route: String, family: String?, weight: Int) {
        val key = "$packageName|$route|${family.orEmpty()}|$weight"
        if (LOGGED_REPLACEMENTS.add(key)) {
            XposedBridge.log(
                "LuoShu QQ font replaced [$packageName] via $route: " +
                    "family=${family ?: "unknown"} weight=$weight",
            )
        }
    }

    private fun logLabelAdjustmentOnce(packageName: String, view: TextView, route: String) {
        val sample = view.text.take(12).toString()
        val key = "$packageName|$route|$sample|${view.textSize.toInt()}|${view.height}"
        if (LOGGED_LABELS.add(key)) {
            XposedBridge.log(
                "LuoShu QQ compact label adjusted [$packageName] via $route: text=$sample",
            )
        }
    }

    private fun log(packageName: String, message: String, error: Throwable) {
        XposedBridge.log(
            "LuoShu QqFontCompatibilityHook [$packageName] $message: " +
                "${error.javaClass.simpleName}: ${error.message}",
        )
    }

    private data class LabelSizeState(
        val originalPx: Float,
        val appliedPx: Float,
    )

    private companion object {
        const val LABEL_SIZE_STATE_KEY = "luoshu_qq_label_size_state"
        const val LABEL_SIZE_EPSILON_PX = 0.5f

        val TYPEFACE_GUARD = ThreadLocal<Boolean>()
        val LABEL_GUARD = ThreadLocal<Boolean>()
        val TYPEFACE_CACHE = ConcurrentHashMap<String, Typeface>()
        val STYLED_TYPEFACE_CACHE = ConcurrentHashMap<String, Typeface>()
        val LOGGED_REPLACEMENTS = ConcurrentHashMap.newKeySet<String>()
        val LOGGED_LABELS = ConcurrentHashMap.newKeySet<String>()
        val AVAILABLE_WEIGHTS = listOf(100, 200, 300, 350, 400, 500, 600, 700, 800, 900)
        val FAMILY_NAME_FIELDS = listOf(
            "mSystemFontFamilyName",
            "mFontFamilyName",
            "mFamilyName",
        )
    }
}
