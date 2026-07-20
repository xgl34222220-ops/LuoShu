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
 * OPlus / ColorOS compatibility bridge for Google Play's downloadable Google Sans families.
 *
 * On some ColorOS 16 devices Play resolves Google Sans through Android's downloadable font
 * database instead of opening assets/ProductSans-Regular.ttf. The generic asset hook therefore
 * never sees the request. This hook handles the hyphenated family aliases and the final text
 * sinks inside com.android.vending without modifying /data/fonts or disabling GMS FontProvider.
 */
class ColorOsPlayFontHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        if (lpparam.packageName != PLAY_PACKAGE || !isOplusFamily()) return

        runCatching { hookFamilyFactories() }
            .onFailure { log("family factory hook failed", it) }
        runCatching { hookFinalTypefaceSinks() }
            .onFailure { log("final typeface hook failed", it) }

        XposedBridge.log("LuoShu ColorOS PlayFontHook active: ${lpparam.packageName}")
    }

    private fun hookFamilyFactories() {
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
                    replacementForStyle(style)?.let {
                        logReplacementOnce("Typeface.create(String)", family, it.second)
                        param.result = it.first
                    }
                }
            },
        )

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
                    replacementForStyle(style)?.let {
                        logReplacementOnce("Typeface.create(Typeface)", family, it.second)
                        param.result = it.first
                    }
                }
            },
        )

        // API 28+: Typeface.create(Typeface, weight, italic). Compose and newer Play builds may
        // use this overload after resolving a downloadable Google Sans family.
        runCatching {
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
                        val weight = param.args.getOrNull(1) as? Int ?: 400
                        val italic = param.args.getOrNull(2) as? Boolean ?: false
                        replacementForWeight(weight, italic)?.let {
                            logReplacementOnce("Typeface.create(weight)", family, it.second)
                            param.result = it.first
                        }
                    }
                },
            )
        }
    }

    /**
     * ColorOS Play can receive a fully constructed downloadable Typeface from the framework, so
     * no asset/file constructor runs in the app. Catch the last assignment while excluding icon,
     * emoji, symbol and code families.
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
                    replacementForStyle(style)?.let {
                        param.args[0] = it.first
                        logReplacementOnce("TextView.setTypeface", familyName(original).orEmpty(), it.second)
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
                    replacementForStyle(style)?.let {
                        param.args[0] = it.first
                        logReplacementOnce("Paint.setTypeface", familyName(original).orEmpty(), it.second)
                    }
                }
            },
        )
    }

    private fun replacementForStyle(style: Int): Pair<Typeface, String>? {
        val weight = if (style and Typeface.BOLD != 0) 700 else 400
        val italic = style and Typeface.ITALIC != 0
        return replacementForWeight(weight, italic)
    }

    private fun replacementForWeight(weight: Int, italic: Boolean): Pair<Typeface, String>? {
        val source = sourceForWeight(weight) ?: return null
        val base = loadTypeface(source) ?: return null
        val replacement = runCatching {
            HOOK_GUARD.set(true)
            if (Build.VERSION.SDK_INT >= 28) {
                Typeface.create(base, weight.coerceIn(1, 1000), italic)
            } else {
                val style = (if (weight >= 600) Typeface.BOLD else Typeface.NORMAL) or
                    (if (italic) Typeface.ITALIC else Typeface.NORMAL)
                Typeface.create(base, style)
            }
        }.getOrDefault(base).also { HOOK_GUARD.remove() }
        return replacement to source
    }

    private fun sourceForWeight(weight: Int): String? {
        val candidates = when {
            weight >= 650 -> listOf(
                "/system/fonts/SourceSansPro-Bold.ttf",
                "/system/fonts/SysFont-Bold.ttf",
                "/system/fonts/GoogleSans-Bold.ttf",
                "/system/fonts/Roboto-Bold.ttf",
                "/system/fonts/SysFont-Regular.ttf",
                "/system/fonts/Roboto-Regular.ttf",
            )
            weight >= 500 -> listOf(
                "/system/fonts/SourceSansPro-SemiBold.ttf",
                "/system/fonts/SysFont-Medium.ttf",
                "/system/fonts/GoogleSans-Medium.ttf",
                "/system/fonts/Roboto-Medium.ttf",
                "/system/fonts/SysFont-Regular.ttf",
                "/system/fonts/Roboto-Regular.ttf",
            )
            else -> listOf(
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

    private fun normalize(value: String): String = value.lowercase().filter(Char::isLetterOrDigit)

    private fun isOplusFamily(): Boolean {
        val identity = "${Build.MANUFACTURER} ${Build.BRAND}".lowercase()
        if (OPLUS_MARKERS.any(identity::contains)) return true
        val version = runCatching {
            XposedHelpers.callStaticMethod(
                XposedHelpers.findClass("android.os.SystemProperties", null),
                "get",
                "ro.build.version.oplusrom",
                "",
            ) as? String
        }.getOrNull()
        return !version.isNullOrBlank()
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
