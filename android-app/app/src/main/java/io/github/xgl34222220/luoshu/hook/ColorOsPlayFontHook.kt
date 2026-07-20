package io.github.xgl34222220.luoshu.hook

import android.graphics.Paint
import android.graphics.Typeface
import android.os.Build
import android.widget.TextView
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.io.File
import java.util.concurrent.ConcurrentHashMap

/**
 * ColorOS / OPlus compatibility bridge for Google Play downloadable fonts.
 *
 * Some OPlus devices resolve Google Sans through Android's downloadable font database rather than
 * opening assets/ProductSans-Regular.ttf in the Play process. The generic asset hook cannot see
 * that route, so this class catches both hyphenated family aliases and final text assignments.
 */
class ColorOsPlayFontHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        if (lpparam.packageName != PLAY_PACKAGE || !isOplusFamily()) return

        runCatching { hookFamilyAlias() }
            .onFailure { log("family alias hook failed", it) }
        runCatching { hookFinalTypefaceSinks() }
            .onFailure { log("final typeface hook failed", it) }

        XposedBridge.log("LuoShu ColorOS PlayFontHook active: ${lpparam.packageName}")
    }

    private fun hookFamilyAlias() {
        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "create",
            String::class.java,
            Int::class.javaPrimitiveType,
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    if (HOOK_GUARD.get() == true) return
                    val family = param.args.getOrNull(0) as? String ?: return
                    if (!isReplaceableFamily(family)) return
                    val style = param.args.getOrNull(1) as? Int ?: Typeface.NORMAL
                    replacementForStyle(style)?.let { replacement ->
                        logReplacementOnce("Typeface.create(String)", family, replacement.second)
                        param.result = replacement.first
                    }
                }
            },
        )
    }

    /**
     * Downloadable fonts may already be constructed by the framework before Play receives them.
     * Catch TextView, Compose/TextPaint and custom text at their final Typeface assignment while
     * retaining icon, symbol, emoji, barcode and monospace families.
     */
    private fun hookFinalTypefaceSinks() {
        XposedBridge.hookAllMethods(
            TextView::class.java,
            "setTypeface",
            object : XC_MethodHook() {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    if (HOOK_GUARD.get() == true || param.args.isEmpty()) return
                    val original = param.args.getOrNull(0) as? Typeface
                    if (isExcludedTypeface(original)) return
                    val explicitStyle = param.args.getOrNull(1) as? Int
                    val style = explicitStyle ?: original?.style ?: Typeface.NORMAL
                    replacementForStyle(style)?.let { replacement ->
                        param.args[0] = replacement.first
                        logReplacementOnce(
                            "TextView.setTypeface",
                            familyName(original).orEmpty(),
                            replacement.second,
                        )
                    }
                }
            },
        )

        XposedBridge.hookAllMethods(
            Paint::class.java,
            "setTypeface",
            object : XC_MethodHook() {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    if (HOOK_GUARD.get() == true || param.args.isEmpty()) return
                    val original = param.args.getOrNull(0) as? Typeface
                    if (isExcludedTypeface(original)) return
                    val style = original?.style ?: Typeface.NORMAL
                    replacementForStyle(style)?.let { replacement ->
                        param.args[0] = replacement.first
                        logReplacementOnce(
                            "Paint.setTypeface",
                            familyName(original).orEmpty(),
                            replacement.second,
                        )
                    }
                }
            },
        )
    }

    private fun replacementForStyle(style: Int): Pair<Typeface, String>? {
        val source = sourceForStyle(style) ?: return null
        val base = loadTypeface(source) ?: return null
        val replacement = if (style == Typeface.NORMAL) {
            base
        } else {
            runCatching {
                HOOK_GUARD.set(true)
                Typeface.create(base, style)
            }.getOrDefault(base).also { HOOK_GUARD.remove() }
        }
        return replacement to source
    }

    private fun sourceForStyle(style: Int): String? {
        val bold = style and Typeface.BOLD != 0
        val candidates = if (bold) {
            listOf(
                "/system/fonts/SourceSansPro-Bold.ttf",
                "/system/fonts/SysFont-Bold.ttf",
                "/system/fonts/GoogleSans-Bold.ttf",
                "/system/fonts/Roboto-Bold.ttf",
                "/system/fonts/SysFont-Regular.ttf",
                "/system/fonts/Roboto-Regular.ttf",
            )
        } else {
            listOf(
                "/system/fonts/SysFont-Regular.ttf",
                "/system/fonts/SysSans-En-Regular.ttf",
                "/system/fonts/OPSans-En-Regular.ttf",
                "/system/fonts/GoogleSans-Regular.ttf",
                "/system/fonts/Roboto-Regular.ttf",
                "/system/fonts/SourceSansPro-Regular.ttf",
            )
        }
        return candidates.firstOrNull { File(it).canRead() }
    }

    private fun loadTypeface(source: String): Typeface? {
        TYPEFACE_CACHE[source]?.let { return it }
        return runCatching {
            HOOK_GUARD.set(true)
            Typeface.createFromFile(source)
        }.getOrNull().also { HOOK_GUARD.remove() }?.also { TYPEFACE_CACHE[source] = it }
    }

    private fun familyName(typeface: Typeface?): String? {
        typeface ?: return null
        return runCatching {
            XposedHelpers.getObjectField(typeface, "mSystemFontFamilyName") as? String
        }.getOrNull()
    }

    private fun isReplaceableFamily(value: String): Boolean {
        val normalized = normalize(value)
        if (EXCLUDED_NORMALIZED.any(normalized::contains)) return false
        return REPLACEABLE_NORMALIZED.any(normalized::contains)
    }

    private fun isExcludedTypeface(typeface: Typeface?): Boolean {
        val family = familyName(typeface) ?: return false
        val normalized = normalize(family)
        return EXCLUDED_NORMALIZED.any(normalized::contains)
    }

    private fun normalize(value: String): String = buildString(value.length) {
        value.lowercase().forEach { character ->
            if (character.isLetterOrDigit()) append(character)
        }
    }

    private fun isOplusFamily(): Boolean {
        val identity = "${Build.MANUFACTURER} ${Build.BRAND}".lowercase()
        return OPLUS_MARKERS.any(identity::contains)
    }

    private fun logReplacementOnce(route: String, family: String, source: String) {
        val key = "$route|$family|$source"
        if (LOGGED_REPLACEMENTS.putIfAbsent(key, true) == null) {
            XposedBridge.log(
                "LuoShu ColorOS PlayFontHook replaced [com.android.vending] via $route: " +
                    "${family.ifBlank { "default" }} -> $source",
            )
        }
    }

    private fun log(message: String, error: Throwable) {
        XposedBridge.log(
            "LuoShu ColorOS PlayFontHook $message: ${error.javaClass.simpleName}: ${error.message}",
        )
    }

    private companion object {
        const val PLAY_PACKAGE = "com.android.vending"

        val HOOK_GUARD = ThreadLocal<Boolean>()
        val TYPEFACE_CACHE = ConcurrentHashMap<String, Typeface>()
        val LOGGED_REPLACEMENTS = ConcurrentHashMap<String, Boolean>()

        val OPLUS_MARKERS = listOf("oppo", "oneplus", "realme", "oplus")
        val REPLACEABLE_NORMALIZED = listOf(
            "googlesans",
            "googlesanstext",
            "googlesansflex",
            "productsans",
            "roboto",
            "sourcesans",
            "sysfont",
            "syssans",
            "opsans",
        )
        val EXCLUDED_NORMALIZED = listOf(
            "emoji",
            "symbol",
            "icon",
            "materialicon",
            "materialsymbol",
            "dingbat",
            "barcode",
            "qrcode",
            "monospace",
            "code",
        )
    }
}
