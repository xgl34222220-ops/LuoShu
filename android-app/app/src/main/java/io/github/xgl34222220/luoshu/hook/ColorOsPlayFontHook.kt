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
 * This class hooks only low-frequency Typeface factories. It never hooks TextView or Paint rendering
 * sinks, so it avoids the Compose main-thread stall introduced by the old Test8 implementation.
 */
class ColorOsPlayFontHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        if (lpparam.packageName != PLAY_PACKAGE || !isOplusFamily()) return

        runCatching { hookNamedFamilyFactory() }
            .onFailure { log("named family hook failed", it) }
        runCatching { hookDerivedTypefaceFactory() }
            .onFailure { log("derived typeface hook failed", it) }
        runCatching { hookWeightedTypefaceFactory() }
            .onFailure { log("weighted typeface hook failed", it) }

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
                        logReplacementOnce("Typeface.create(Typeface,style)", family, replacement.second)
                        param.result = replacement.first
                    }
                }
            },
        )
    }

    /** Compose commonly derives an exact 400/500 weight through the API 28 overload. */
    private fun hookWeightedTypefaceFactory() {
        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "create",
            Typeface::class.java,
            Int::class.javaPrimitiveType,
            Boolean::class.javaPrimitiveType,
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    if (HOOK_GUARD.get() == true) return
                    val original = param.args.getOrNull(0) as? Typeface ?: return
                    val family = familyName(original) ?: return
                    if (!isReplaceableFamily(family)) return
                    val weight = (param.args.getOrNull(1) as? Int ?: original.weight).coerceIn(1, 1000)
                    val italic = param.args.getOrNull(2) as? Boolean ?: original.isItalic
                    replacementForWeight(weight, italic)?.let { replacement ->
                        logReplacementOnce("Typeface.create(Typeface,weight)", family, replacement.second)
                        param.result = replacement.first
                    }
                }
            },
        )
    }

    private fun replacementForStyle(style: Int): Pair<Typeface, String>? = replacementForWeight(
        weight = if (style and Typeface.BOLD != 0) 700 else 400,
        italic = style and Typeface.ITALIC != 0,
    )

    private fun replacementForWeight(weight: Int, italic: Boolean): Pair<Typeface, String>? {
        val source = sourceForWeight(weight) ?: return null
        val base = loadTypeface(source) ?: return null
        val replacement = runCatching {
            HOOK_GUARD.set(true)
            Typeface.create(base, weight.coerceIn(1, 1000), italic)
        }.getOrDefault(base).also { HOOK_GUARD.remove() }
        return replacement to source
    }

    private fun sourceForWeight(weight: Int): String? {
        val nearest = AVAILABLE_WEIGHTS.minByOrNull { kotlin.math.abs(it - weight) } ?: 400
        val candidates = listOf(
            "/system/fonts/$nearest.ttf",
            when {
                weight >= 650 -> "/system/fonts/SourceSansPro-Bold.ttf"
                weight >= 500 -> "/system/fonts/SysFont-Medium.ttf"
                else -> "/system/fonts/SysFont-Regular.ttf"
            },
            when {
                weight >= 650 -> "/system/fonts/GoogleSans-Bold.ttf"
                weight >= 500 -> "/system/fonts/GoogleSans-Medium.ttf"
                else -> "/system/fonts/GoogleSansText-Regular.ttf"
            },
            "/system/fonts/SysSans-En-Regular.ttf",
            "/system/fonts/OPSans-En-Regular.ttf",
            "/system/fonts/Roboto-Regular.ttf",
            "/system/fonts/SourceSansPro-Regular.ttf",
        )
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
        if (Build.VERSION.SDK_INT >= 34) {
            val publicName = runCatching {
                XposedHelpers.callMethod(typeface, "getSystemFontFamilyName") as? String
            }.getOrNull()
            if (!publicName.isNullOrBlank()) return publicName
        }
        for (field in FAMILY_NAME_FIELDS) {
            val value = runCatching {
                XposedHelpers.getObjectField(typeface, field) as? String
            }.getOrNull()
            if (!value.isNullOrBlank()) return value
        }
        return null
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
        val AVAILABLE_WEIGHTS = listOf(100, 200, 300, 350, 400, 500, 600, 700, 800, 900)
        val FAMILY_NAME_FIELDS = listOf(
            "mSystemFontFamilyName",
            "mFontFamilyName",
            "mFamilyName",
        )

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
