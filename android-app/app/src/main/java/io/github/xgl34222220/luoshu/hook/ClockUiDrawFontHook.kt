package io.github.xgl34222220.luoshu.hook

import android.content.Context
import android.content.ContextWrapper
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.view.View
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.io.File
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap

/**
 * Clock font replacement restricted to visible, non-alarm UI drawing.
 *
 * No Typeface factory, Font.Builder, resource loader or global persistent Paint mutation is used
 * here. The selected LuoShu Typeface is applied only for one safe Canvas text call, horizontally
 * fitted to the width HyperOS measured with its original Clock face, then fully restored. Alarm
 * alert/full-screen/snooze views and every child process are excluded.
 */
class ClockUiDrawFontHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        val packageName = lpparam.packageName ?: return
        if (packageName !in CLOCK_PACKAGES) return
        val processName = lpparam.processName ?: packageName
        if (!shouldInstallClockUiFontHooks(packageName, processName)) return

        runCatching { hookViewDrawScope(packageName, processName) }
            .onFailure { log(packageName, "view draw scope failed", it) }
        runCatching { hookCanvasText(packageName, "drawText") }
            .onFailure { log(packageName, "Canvas.drawText hook failed", it) }
        runCatching { hookCanvasText(packageName, "drawTextRun") }
            .onFailure { log(packageName, "Canvas.drawTextRun hook failed", it) }

        XposedBridge.log(
            "LuoShu ClockUiDrawFontHook active: package=$packageName process=$processName",
        )
    }

    private fun hookViewDrawScope(packageName: String, processName: String) {
        XposedBridge.hookAllMethods(
            View::class.java,
            "draw",
            object : XC_MethodHook(PRIORITY_SCOPE) {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    val view = param.thisObject as? View
                    val stack = DRAW_SCOPE.get() ?: ArrayDeque<Boolean>().also(DRAW_SCOPE::set)
                    val classNames = if (view == null) {
                        emptyList()
                    } else {
                        buildList {
                            add(view.javaClass.name)
                            addAll(contextClassNames(view.context))
                        }
                    }
                    val safe = view != null && shouldEnterClockTextDrawScope(
                        packageName = packageName,
                        processName = processName,
                        classNames = classNames,
                        attached = runCatching { view.isAttachedToWindow }.getOrDefault(false),
                        shown = runCatching { view.isShown }.getOrDefault(false),
                    )
                    stack.addLast(safe)
                }

                override fun afterHookedMethod(param: MethodHookParam) {
                    val stack = DRAW_SCOPE.get() ?: return
                    if (stack.isNotEmpty()) stack.removeLast()
                    if (stack.isEmpty()) DRAW_SCOPE.remove()
                }
            },
        )
    }

    private fun hookCanvasText(packageName: String, methodName: String) {
        val captures = ThreadLocal<ArrayDeque<CapturedPaint>>()
        XposedBridge.hookAllMethods(
            Canvas::class.java,
            methodName,
            object : XC_MethodHook(PRIORITY_TEXT) {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    val stack = captures.get() ?: ArrayDeque<CapturedPaint>().also(captures::set)
                    if (!insideSafeDrawScope()) {
                        stack.addLast(CapturedPaint.EMPTY)
                        return
                    }
                    val paint = param.args.lastOrNull { it is Paint } as? Paint
                    val text = extractDrawText(param.args)
                    if (paint == null || !shouldReplaceClockDrawText(text, typefaceFamilyName(paint.typeface))) {
                        stack.addLast(CapturedPaint.EMPTY)
                        return
                    }

                    val originalTypeface = paint.typeface
                    val originalScaleX = paint.textScaleX
                    val originalWidth = measuredTextWidth(paint, text)
                    val family = typefaceFamilyName(originalTypeface)
                    val replacement = replacementTypeface(originalTypeface)
                    if (replacement == null || replacement === originalTypeface) {
                        stack.addLast(CapturedPaint.EMPTY)
                        return
                    }

                    paint.typeface = replacement
                    val replacementWidth = measuredTextWidth(paint, text)
                    paint.textScaleX = fittedClockTextScaleX(
                        originalScaleX = originalScaleX,
                        originalWidthPx = originalWidth,
                        replacementWidthPx = replacementWidth,
                    )
                    stack.addLast(
                        CapturedPaint(
                            paint = paint,
                            originalTypeface = originalTypeface,
                            originalTextScaleX = originalScaleX,
                        ),
                    )
                    logReplacementOnce(
                        packageName = packageName,
                        route = "Canvas.$methodName",
                        text = text,
                        familyName = family,
                        originalWidth = originalWidth,
                        replacementWidth = replacementWidth,
                        fittedScaleX = paint.textScaleX,
                    )
                }

                override fun afterHookedMethod(param: MethodHookParam) {
                    restoreCapture(captures)
                }
            },
        )
    }

    private fun restoreCapture(captures: ThreadLocal<ArrayDeque<CapturedPaint>>) {
        val stack = captures.get() ?: return
        val capture = if (stack.isEmpty()) null else stack.removeLast()
        capture?.paint?.let { paint ->
            paint.typeface = capture.originalTypeface
            paint.textScaleX = capture.originalTextScaleX
        }
        if (stack.isEmpty()) captures.remove()
    }

    private fun insideSafeDrawScope(): Boolean = DRAW_SCOPE.get()?.peekLast() == true

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

    private fun extractDrawText(args: Array<Any?>): CharSequence? {
        args.firstOrNull { it is CharSequence }?.let { value ->
            val text = value as CharSequence
            val numbers = args.filterIsInstance<Int>()
            if (numbers.size >= 2) {
                val start = numbers[0].coerceIn(0, text.length)
                val end = numbers[1].coerceIn(start, text.length)
                return text.subSequence(start, end)
            }
            return text
        }
        val chars = args.firstOrNull { it is CharArray } as? CharArray ?: return null
        val numbers = args.filterIsInstance<Int>()
        val start = numbers.getOrNull(0)?.coerceIn(0, chars.size) ?: 0
        val count = numbers.getOrNull(1)?.coerceIn(0, chars.size - start) ?: (chars.size - start)
        return String(chars, start, count)
    }

    private fun measuredTextWidth(paint: Paint, text: CharSequence?): Float {
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
        val nearest = AVAILABLE_WEIGHTS.minByOrNull { kotlin.math.abs(it - weight) } ?: 400
        return listOf(
            "/system/fonts/$nearest.ttf",
            "/system/fonts/400.ttf",
            "/system/fonts/MiSansVF.ttf",
            "/system/fonts/Roboto-Regular.ttf",
        ).firstOrNull { File(it).canRead() }
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

    private fun logReplacementOnce(
        packageName: String,
        route: String,
        text: CharSequence?,
        familyName: String?,
        originalWidth: Float,
        replacementWidth: Float,
        fittedScaleX: Float,
    ) {
        val sample = text?.take(12)?.toString().orEmpty()
        val key = "$packageName|$route|$sample|${familyName.orEmpty()}"
        if (LOGGED_REPLACEMENTS.add(key)) {
            XposedBridge.log(
                "LuoShu Clock UI draw replaced [$packageName] via $route: " +
                    "text=$sample family=${familyName ?: "unknown"} " +
                    "originalWidth=$originalWidth replacementWidth=$replacementWidth " +
                    "scaleX=$fittedScaleX",
            )
        }
    }

    private fun log(packageName: String, message: String, error: Throwable) {
        XposedBridge.log(
            "LuoShu ClockUiDrawFontHook [$packageName] $message: " +
                "${error.javaClass.simpleName}: ${error.message}",
        )
    }

    private data class CapturedPaint(
        val paint: Paint?,
        val originalTypeface: Typeface?,
        val originalTextScaleX: Float,
    ) {
        companion object {
            val EMPTY = CapturedPaint(null, null, 1f)
        }
    }

    private companion object {
        const val PRIORITY_SCOPE = 10_000
        const val PRIORITY_TEXT = 5_000
        const val MAX_CONTEXT_DEPTH = 8

        val DRAW_SCOPE = ThreadLocal<ArrayDeque<Boolean>>()
        val BASE_CACHE = ConcurrentHashMap<String, Typeface>()
        val TYPEFACE_CACHE = ConcurrentHashMap<String, Typeface>()
        val LOGGED_REPLACEMENTS = ConcurrentHashMap.newKeySet<String>()
        val AVAILABLE_WEIGHTS = listOf(100, 200, 300, 350, 400, 500, 600, 700, 800, 900)
        val FAMILY_NAME_FIELDS = listOf(
            "mSystemFontFamilyName",
            "mFontFamilyName",
            "mFamilyName",
        )
    }
}
