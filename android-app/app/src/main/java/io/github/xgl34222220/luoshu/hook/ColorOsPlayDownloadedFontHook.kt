package io.github.xgl34222220.luoshu.hook

import android.os.Build
import android.os.ParcelFileDescriptor
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.io.File
import java.util.concurrent.ConcurrentHashMap

/**
 * Replaces ColorOS/OPlus downloadable Google Sans fonts at the low-frequency Font.Builder layer.
 *
 * Google Play's search field can receive GoogleSansText from /data/fonts/files through a
 * ParcelFileDescriptor. That path bypasses Typeface.create(...) but still builds a Font before it is
 * added to a FontFamily. This hook replaces only clearly identified Google Sans/Product Sans files
 * and never touches Paint/TextView/Compose rendering hot paths.
 */
class ColorOsPlayDownloadedFontHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        if (lpparam.packageName != PLAY_PACKAGE || !isOplusFamily()) return

        val builderClass = XposedHelpers.findClassIfExists(
            "android.graphics.fonts.Font\$Builder",
            null,
        ) ?: return

        runCatching { hookBuilderConstructors(builderClass) }
            .onFailure { log("Font.Builder constructor hook failed", it) }
        runCatching { hookBuilderBuild(builderClass) }
            .onFailure { log("Font.Builder build hook failed", it) }

        XposedBridge.log("LuoShu ColorOS Play downloaded-font hook active: ${lpparam.packageName}")
    }

    private fun hookBuilderConstructors(builderClass: Class<*>) {
        XposedBridge.hookAllConstructors(
            builderClass,
            object : XC_MethodHook() {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    if (HOOK_GUARD.get() == true) return
                    PENDING_REQUEST.set(requestFromArgs(param.args))
                }

                override fun afterHookedMethod(param: MethodHookParam) {
                    val request = PENDING_REQUEST.get()
                    PENDING_REQUEST.remove()
                    if (request.isNullOrBlank() || !isDownloadedGoogleFont(request)) return
                    XposedHelpers.setAdditionalInstanceField(
                        param.thisObject,
                        REQUEST_KEY,
                        request,
                    )
                }
            },
        )
    }

    private fun hookBuilderBuild(builderClass: Class<*>) {
        XposedBridge.hookAllMethods(
            builderClass,
            "build",
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    if (HOOK_GUARD.get() == true) return
                    val originalFont = param.result ?: return
                    val remembered = XposedHelpers.getAdditionalInstanceField(
                        param.thisObject,
                        REQUEST_KEY,
                    ) as? String
                    val request = remembered ?: fontFilePath(originalFont) ?: return
                    if (!isDownloadedGoogleFont(request)) return

                    val style = runCatching {
                        XposedHelpers.callMethod(originalFont, "getStyle")
                    }.getOrNull()
                    val weight = runCatching {
                        XposedHelpers.callMethod(style, "getWeight") as? Int
                    }.getOrNull() ?: weightFromName(request)
                    val slant = runCatching {
                        XposedHelpers.callMethod(style, "getSlant") as? Int
                    }.getOrNull() ?: 0
                    val source = sourceForWeight(weight) ?: return

                    val replacement = runCatching {
                        HOOK_GUARD.set(true)
                        val replacementBuilder = XposedHelpers.newInstance(builderClass, File(source))
                        XposedHelpers.callMethod(replacementBuilder, "setWeight", weight.coerceIn(1, 1000))
                        XposedHelpers.callMethod(replacementBuilder, "setSlant", slant)
                        XposedHelpers.callMethod(replacementBuilder, "build")
                    }.getOrNull().also {
                        HOOK_GUARD.remove()
                    } ?: return

                    logReplacementOnce(request, source)
                    param.result = replacement
                }
            },
        )
    }

    private fun requestFromArgs(args: Array<Any?>): String? {
        args.firstOrNull { it is File }?.let { return (it as File).path }
        args.firstOrNull { it is ParcelFileDescriptor }?.let {
            return parcelFilePath(it as ParcelFileDescriptor)
        }
        args.firstOrNull { it?.javaClass?.name == "android.graphics.fonts.Font" }?.let {
            return fontFilePath(it)
        }
        return args.firstOrNull { it is String } as? String
    }

    private fun parcelFilePath(descriptor: ParcelFileDescriptor): String? {
        val procPath = "/proc/self/fd/${descriptor.fd}"
        return runCatching {
            android.system.Os.readlink(procPath)
        }.getOrNull()?.takeIf { it.isNotBlank() }
            ?: runCatching { File(procPath).canonicalPath }.getOrNull()
    }

    private fun fontFilePath(font: Any): String? {
        return runCatching {
            (XposedHelpers.callMethod(font, "getFile") as? File)?.path
        }.getOrNull()
    }

    private fun isDownloadedGoogleFont(request: String): Boolean {
        val lower = request.lowercase()
        val normalized = buildString(lower.length) {
            lower.forEach { character -> if (character.isLetterOrDigit()) append(character) }
        }
        val googleFamily = GOOGLE_MARKERS.any(normalized::contains)
        val dataFontPath = "/data/fonts/" in lower || "/data/system/fonts/" in lower
        return googleFamily && dataFontPath && EXCLUDED_MARKERS.none(normalized::contains)
    }

    private fun weightFromName(request: String): Int {
        val lower = request.lowercase()
        return when {
            "black" in lower || "900" in lower -> 900
            "extrabold" in lower || "800" in lower -> 800
            "bold" in lower || "700" in lower -> 700
            "semibold" in lower || "demibold" in lower || "600" in lower -> 600
            "medium" in lower || "500" in lower -> 500
            "light" in lower || "300" in lower -> 300
            "extralight" in lower || "200" in lower -> 200
            "thin" in lower || "100" in lower -> 100
            else -> 400
        }
    }

    private fun sourceForWeight(weight: Int): String? {
        val nearest = AVAILABLE_WEIGHTS.minByOrNull { kotlin.math.abs(it - weight) } ?: 400
        val candidates = listOf(
            "/system/fonts/$nearest.ttf",
            when {
                weight >= 650 -> "/system/fonts/GoogleSans-Bold.ttf"
                weight >= 500 -> "/system/fonts/GoogleSans-Medium.ttf"
                else -> "/system/fonts/GoogleSansText-Regular.ttf"
            },
            "/system/fonts/GoogleSans-Regular.ttf",
            "/system/fonts/SysFont-Regular.ttf",
            "/system/fonts/Roboto-Regular.ttf",
        )
        return candidates.firstOrNull { File(it).canRead() }
    }

    private fun isOplusFamily(): Boolean {
        val identity = "${Build.MANUFACTURER} ${Build.BRAND}".lowercase()
        return OPLUS_MARKERS.any(identity::contains)
    }

    private fun logReplacementOnce(request: String, source: String) {
        val key = "$request|$source"
        if (LOGGED_REPLACEMENTS.putIfAbsent(key, true) == null) {
            XposedBridge.log(
                "LuoShu ColorOS Play downloaded font replaced: $request -> $source",
            )
        }
    }

    private fun log(message: String, error: Throwable) {
        XposedBridge.log(
            "LuoShu ColorOS Play downloaded-font hook $message: " +
                "${error.javaClass.simpleName}: ${error.message}",
        )
    }

    private companion object {
        const val PLAY_PACKAGE = "com.android.vending"
        const val REQUEST_KEY = "luoshu_coloros_downloaded_font_request"

        val HOOK_GUARD = ThreadLocal<Boolean>()
        val PENDING_REQUEST = ThreadLocal<String?>()
        val LOGGED_REPLACEMENTS = ConcurrentHashMap<String, Boolean>()
        val AVAILABLE_WEIGHTS = listOf(100, 200, 300, 350, 400, 500, 600, 700, 800, 900)
        val OPLUS_MARKERS = listOf("oppo", "oneplus", "realme", "oplus")
        val GOOGLE_MARKERS = listOf(
            "googlesans",
            "googlesanstext",
            "googlesansflex",
            "productsans",
        )
        val EXCLUDED_MARKERS = listOf(
            "emoji",
            "symbol",
            "icon",
            "materialicon",
            "materialsymbol",
            "monospace",
            "code",
        )
    }
}
