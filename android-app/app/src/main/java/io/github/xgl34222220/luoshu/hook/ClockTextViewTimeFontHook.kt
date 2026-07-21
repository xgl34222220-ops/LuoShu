package io.github.xgl34222220.luoshu.hook

import android.content.Context
import android.content.ContextWrapper
import android.graphics.Paint
import android.graphics.Typeface
import android.widget.TextView
import androidx.annotation.Keep
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.io.File
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap

/**
 * Covers HyperOS Clock time values rendered by ordinary TextView/Layout paths.
 *
 * The existing ClockUiDrawFontHook remains responsible for custom Canvas views such as the timer
 * wheel. This hook only enters TextViews containing digits (or a known clock-family separator), fits
 * the replacement to the original measured width, and restores the Paint immediately after onDraw.
 */
@Keep
class ClockTextViewTimeFontHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        val packageName = lpparam.packageName ?: return
        if (packageName !in CLOCK_PACKAGES) return
        val processName = lpparam.processName ?: packageName
        if (!shouldInstallClockUiFontHooks(packageName, processName)) return

        runCatching { installTextViewDrawHook(packageName, processName) }
            .onFailure { error ->
                XposedBridge.log(
                    "LuoShu ClockTextViewTimeFontHook [$packageName] failed: " +
                        "${error.javaClass.simpleName}: ${error.message}",
                )
            }
    }

    private fun installTextViewDrawHook(packageName: String, processName: String) {
        val captures = ThreadLocal<ArrayDeque<CapturedTextPaint>>()
        XposedBridge.hookAllMethods(
            TextView::class.java,
            "onDraw",
            object : XC_MethodHook(PRIORITY_TEXT_VIEW) {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    val stack = captures.get() ?: ArrayDeque<CapturedTextPaint>().also(captures::set)
                    val view = param.thisObject as? TextView
                    if (view == null || !isSafeTextView(packageName, processName, view)) {
                        stack.addLast(CapturedTextPaint.EMPTY)
                        return
                    }

                    val text = view.text
                    val paint = view.paint
                    val originalTypeface = paint.typeface
                    val familyName = typefaceFamilyName(originalTypeface)
                    if (!shouldReplaceClockTextViewText(text, familyName)) {
                        stack.addLast(CapturedTextPaint.EMPTY)
                        return
                    }

                    val originalScaleX = paint.textScaleX
                    val originalWidth = measure(paint, text)
                    val replacement = replacementTypeface(originalTypeface)
                    if (replacement == null || replacement === originalTypeface) {
                        stack.addLast(CapturedTextPaint.EMPTY)
                        return
                    }

                    paint.typeface = replacement
                    val replacementWidth = measure(paint, text)
                    paint.textScaleX = fittedClockTextScaleX(
                        originalScaleX = originalScaleX,
                        originalWidthPx = originalWidth,
                        replacementWidthPx = replacementWidth,
                    )
                    stack.addLast(
                        CapturedTextPaint(
                            paint = paint,
                            originalTypeface = originalTypeface,
                            originalScaleX = originalScaleX,
                        ),
                    )
                    logOnce(
                        packageName = packageName,
                        text = text,
                        familyName = familyName,
                        originalWidth = originalWidth,
                        replacementWidth = replacementWidth,
                        scaleX = paint.textScaleX,
                    )
                }

                override fun afterHookedMethod(param: MethodHookParam) {
                    val stack = captures.get() ?: return
                    val capture = if (stack.isEmpty()) null else stack.removeLast()
                    capture?.paint?.let { paint ->
                        paint.typeface = capture.originalTypeface
                        paint.textScaleX = capture.originalScaleX
                    }
                    if (stack.isEmpty()) captures.remove()
                }
            },
        )
    }

    private fun isSafeTextView(
        packageName: String,
        processName: String,
        view: TextView,
    ): Boolean {
        val classNames = buildList {
            add(view.javaClass.name)
            addAll(contextClassNames(view.context))
        }
        return shouldEnterClockTextDrawScope(
            packageName = packageName,
            processName = processName,
            classNames = classNames,
            attached = runCatching { view.isAttachedToWindow }.getOrDefault(false),
            shown = runCatching { view.isShown }.getOrDefault(false),
        )
    }

    private fun contextClassNames(context: Context?): List<String> {
        val names = ArrayList<String>(6)
        var current = context
        var depth = 0
        while (current != null && depth < MAX_CONTEXT_DEPTH) {
            names.add(current.javaClass.name)
            current = (current as? ContextWrapper)?.baseContext
            depth += 1
        }
        return names
    }

    private fun measure(paint: Paint, text: CharSequence?): Float {
        if (text.isNullOrEmpty()) return 0f
        return runCatching { paint.measureText(text.toString()) }.getOrDefault(0f)
    }

    private fun replacementTypeface(original: Typeface?): Typeface? {
        val weight = original?.weight ?: 400
        val italic = original?.isItalic == true
        val source = sourceForWeight(weight) ?: return null
        val key = "$source|$weight|$italic"
        TYPEFACE_CACHE[key]?.let { return it }

        val base = BASE_CACHE[source] ?: runCatching {
            Typeface.createFromFile(source)
        }.getOrNull()?.also { BASE_CACHE[source] = it } ?: return null
        val styled = runCatching {
            Typeface.create(base, weight.coerceIn(1, 1000), italic)
        }.getOrDefault(base)
        TYPEFACE_CACHE.putIfAbsent(key, styled)
        return TYPEFACE_CACHE[key] ?: styled
    }

    private fun sourceForWeight(weight: Int): String? {
        val nearest = AVAILABLE_WEIGHTS.minByOrNull { candidate ->
            kotlin.math.abs(candidate - weight)
        } ?: 400
        return listOf(
            "/system/fonts/$nearest.ttf",
            "/system/fonts/400.ttf",
            "/system/fonts/MiSansVF.ttf",
            "/system/fonts/Roboto-Regular.ttf",
        ).firstOrNull { path -> File(path).canRead() }
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

    private fun logOnce(
        packageName: String,
        text: CharSequence?,
        familyName: String?,
        originalWidth: Float,
        replacementWidth: Float,
        scaleX: Float,
    ) {
        val sample = text?.take(12)?.toString().orEmpty()
        val key = "$packageName|$sample|${familyName.orEmpty()}"
        if (LOGGED.add(key)) {
            XposedBridge.log(
                "LuoShu Clock TextView time replaced [$packageName]: " +
                    "text=$sample family=${familyName ?: "unknown"} " +
                    "originalWidth=$originalWidth replacementWidth=$replacementWidth scaleX=$scaleX",
            )
        }
    }

    private data class CapturedTextPaint(
        val paint: Paint?,
        val originalTypeface: Typeface?,
        val originalScaleX: Float,
    ) {
        companion object {
            val EMPTY = CapturedTextPaint(null, null, 1f)
        }
    }

    private companion object {
        const val PRIORITY_TEXT_VIEW = 7_500
        const val MAX_CONTEXT_DEPTH = 8
        val AVAILABLE_WEIGHTS = listOf(100, 200, 300, 350, 400, 500, 600, 700, 800, 900)
        val FAMILY_NAME_FIELDS = listOf(
            "mSystemFontFamilyName",
            "mFontFamilyName",
            "mFamilyName",
        )
        val BASE_CACHE = ConcurrentHashMap<String, Typeface>()
        val TYPEFACE_CACHE = ConcurrentHashMap<String, Typeface>()
        val LOGGED = ConcurrentHashMap.newKeySet<String>()
    }
}
