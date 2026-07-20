package io.github.xgl34222220.luoshu.hook

import android.graphics.Typeface
import android.os.Build
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.io.File
import java.util.concurrent.ConcurrentHashMap

/**
 * Safe ColorOS / OPlus compatibility bridge for Google Play downloadable fonts.
 *
 * Test8 hooked Paint.setTypeface(), which is a very hot Compose rendering path and can stall Play's
 * main thread. This implementation only intercepts Typeface factory calls whose family is explicitly
 * identified as Google Sans / Product Sans / Roboto. It never hooks TextView or Paint rendering sinks.
 */
class ColorOsPlayFontHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        if (lpparam.packageName != PLAY_PACKAGE || !isOplusFamily()) return

        runCatching { hookNamedFamilyFactory() }
            .onFailure { log("named family hook failed", it) }
        runCatching { hookDerivedTypefaceFactory() }
            .onFailure { log("derived typeface hook failed", it) }

        XposedBridge.log("LuoShu ColorOS PlayFontHook active (factory-only): ${lpparam.packageName}")
    }

    private fun hookNamedFamilyFactory() {
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
     * A downloaded Google Sans Typeface may already exist before Play derives a bold/italic face.
     * This factory call is infrequent compared with Paint.setTypeface(), so it covers that route
     * without adding work to every Compose text draw.
     */
    private fun hookDerivedTypefaceFactory() {
        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "create",
            Typeface::class.java,
            Int::class.javaPrimitiveType,
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    if (HOOK_GUARD.get() == true) return
                    val original = param.args.getOrNull(0) as? Typeface ?: return
                    val family = familyName(original) ?: return
                    if (!isReplaceableFamily(family)) return
                    val style = param.args.getOrNull(1) as? Int ?: original.style
                    replacementForStyle(style)?.let { replacement ->
                        logReplacementOnce("Typeface.create(Typeface)", family, replacement.second)
                        param.result = replacement.first
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

    private fun familyName(typeface: Typeface): String? {
        return runCatching {
            XposedHelpers.getObjectField(typeface, "mSystemFontFamilyName") as? String
        }.getOrNull()
    }

    private fun isReplaceableFamily(value: String): Boolean {
        val normalized = normalize(value)
        if (EXCLUDED_NORMALIZED.any(normalized::contains)) return false
        return REPLACEABLE_NORMALIZED.any(normalized::contains)
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
                    "$family -> $source",
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
