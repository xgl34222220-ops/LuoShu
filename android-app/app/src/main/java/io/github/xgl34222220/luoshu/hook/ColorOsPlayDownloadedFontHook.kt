package io.github.xgl34222220.luoshu.hook

import android.os.Build
import android.os.ParcelFileDescriptor
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.io.File
import java.nio.ByteBuffer
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap

/**
 * Replaces ColorOS/OPlus downloadable Google Sans fonts at the low-frequency Font.Builder layer.
 *
 * Android's downloaded-font store usually uses opaque UUID filenames. The previous implementation
 * searched those paths for "GoogleSansText", so the Play search field was skipped even though the
 * file itself was Google Sans. This version reads the font's SFNT name table and also handles the
 * direct-ByteBuffer constructor used after the system maps a downloaded font into memory.
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
                    val stack = CONSTRUCTOR_REQUESTS.get()
                        ?: ArrayDeque<CapturedRequest>().also(CONSTRUCTOR_REQUESTS::set)
                    stack.addLast(CapturedRequest(requestFromArgs(param.args)))
                }

                override fun afterHookedMethod(param: MethodHookParam) {
                    val stack = CONSTRUCTOR_REQUESTS.get() ?: return
                    val request = if (stack.isEmpty()) null else stack.removeLast().value
                    if (stack.isEmpty()) CONSTRUCTOR_REQUESTS.remove()
                    if (request == null || !isDownloadedGoogleFont(request)) return
                    XposedHelpers.setAdditionalInstanceField(param.thisObject, REQUEST_KEY, request)
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
                    ) as? FontRequest
                    val request = remembered ?: requestFromFont(originalFont) ?: return
                    if (!isDownloadedGoogleFont(request)) {
                        logOpaqueDataFontOnce(request)
                        return
                    }

                    val style = runCatching {
                        XposedHelpers.callMethod(originalFont, "getStyle")
                    }.getOrNull()
                    val weight = runCatching {
                        XposedHelpers.callMethod(style, "getWeight") as? Int
                    }.getOrNull() ?: weightFromName(request.description)
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

                    logReplacementOnce(request.description, source)
                    param.result = replacement
                }
            },
        )
    }

    private fun requestFromArgs(args: Array<out Any?>): FontRequest? {
        args.firstOrNull { it is File }?.let { return requestFromFile(it as File) }
        args.firstOrNull { it is ParcelFileDescriptor }?.let {
            val path = parcelFilePath(it as ParcelFileDescriptor)
            return path?.let(::requestFromPath)
        }
        args.firstOrNull { it is ByteBuffer }?.let {
            return FontRequest(
                path = null,
                identity = SfntFontIdentity.fromBuffer(it as ByteBuffer),
                sourceKind = "buffer",
            )
        }
        args.firstOrNull { it?.javaClass?.name == "android.graphics.fonts.Font" }?.let {
            return requestFromFont(it)
        }
        return (args.firstOrNull { it is String } as? String)?.let(::requestFromPath)
    }

    private fun requestFromFont(font: Any): FontRequest? {
        val file = runCatching {
            XposedHelpers.callMethod(font, "getFile") as? File
        }.getOrNull()
        if (file != null) return requestFromFile(file)
        val buffer = runCatching {
            XposedHelpers.callMethod(font, "getBuffer") as? ByteBuffer
        }.getOrNull()
        return FontRequest(
            path = null,
            identity = SfntFontIdentity.fromBuffer(buffer),
            sourceKind = "font-buffer",
        ).takeIf { !it.identity.isNullOrBlank() }
    }

    private fun requestFromPath(path: String): FontRequest = requestFromFile(File(path))

    private fun requestFromFile(file: File): FontRequest = FontRequest(
        path = file.path,
        identity = SfntFontIdentity.fromFile(file),
        sourceKind = "file",
    )

    private fun parcelFilePath(descriptor: ParcelFileDescriptor): String? {
        val procPath = "/proc/self/fd/${descriptor.fd}"
        return runCatching {
            android.system.Os.readlink(procPath)
        }.getOrNull()?.takeIf { it.isNotBlank() }
            ?: runCatching { File(procPath).canonicalPath }.getOrNull()
    }

    private fun isDownloadedGoogleFont(request: FontRequest): Boolean {
        val normalized = normalize(request.description)
        val googleFamily = GOOGLE_MARKERS.any(normalized::contains)
        val dataFontPath = request.path?.lowercase()?.let {
            "/data/fonts/" in it || "/data/system/fonts/" in it
        } == true
        val mappedBuffer = request.path == null && !request.identity.isNullOrBlank()
        return googleFamily && (dataFontPath || mappedBuffer) && EXCLUDED_MARKERS.none(normalized::contains)
    }

    private fun logOpaqueDataFontOnce(request: FontRequest) {
        val path = request.path?.lowercase() ?: return
        if ("/data/fonts/" !in path && "/data/system/fonts/" !in path) return
        val key = request.description
        if (LOGGED_UNRECOGNIZED.putIfAbsent(key, true) == null) {
            XposedBridge.log(
                "LuoShu ColorOS Play downloaded font inspected but not replaced: ${request.description}",
            )
        }
    }

    private fun normalize(value: String): String = buildString(value.length) {
        value.lowercase().forEach { character -> if (character.isLetterOrDigit()) append(character) }
    }

    private fun weightFromName(request: String): Int {
        val lower = request.lowercase()
        return when {
            "black" in lower || "900" in lower -> 900
            "extrabold" in lower || "800" in lower -> 800
            "semibold" in lower || "demibold" in lower || "600" in lower -> 600
            "bold" in lower || "700" in lower -> 700
            "medium" in lower || "500" in lower -> 500
            "extralight" in lower || "200" in lower -> 200
            "light" in lower || "300" in lower -> 300
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

    private data class CapturedRequest(val value: FontRequest?)

    private data class FontRequest(
        val path: String?,
        val identity: String?,
        val sourceKind: String,
    ) {
        val description: String
            get() = buildString {
                append(sourceKind)
                path?.let { append(':').append(it) }
                identity?.let { append('|').append(it) }
            }
    }

    private companion object {
        const val PLAY_PACKAGE = "com.android.vending"
        const val REQUEST_KEY = "luoshu_coloros_downloaded_font_request_v2"

        val HOOK_GUARD = ThreadLocal<Boolean>()
        val CONSTRUCTOR_REQUESTS = ThreadLocal<ArrayDeque<CapturedRequest>>()
        val LOGGED_REPLACEMENTS = ConcurrentHashMap<String, Boolean>()
        val LOGGED_UNRECOGNIZED = ConcurrentHashMap<String, Boolean>()
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
