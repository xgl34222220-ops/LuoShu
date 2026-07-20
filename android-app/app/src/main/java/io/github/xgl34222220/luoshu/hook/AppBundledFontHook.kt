package io.github.xgl34222220.luoshu.hook

import android.content.Context
import android.content.res.AssetFileDescriptor
import android.content.res.AssetManager
import android.content.res.Resources
import android.graphics.Typeface
import android.os.ParcelFileDescriptor
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.io.File
import java.io.FileInputStream
import java.util.concurrent.ConcurrentHashMap

/**
 * Replaces fonts bundled inside a scoped application's APK with LuoShu's currently mounted font.
 *
 * A Magisk/system font overlay cannot affect assets/ProductSans-Regular.ttf or res/font entries,
 * because those bytes are loaded from the application's own APK. Vector/LSPosed runs this hook in
 * memory and leaves the target APK and its signature untouched.
 */
class AppBundledFontHook : IXposedHookLoadPackage {
    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        val packageName = lpparam.packageName ?: return
        if (packageName.startsWith("io.github.xgl34222220.luoshu")) return

        runCatching { hookRawAssetReads(packageName) }
            .onFailure { log(packageName, "AssetManager font hook failed", it) }
        runCatching { hookTypefaceFactories(packageName) }
            .onFailure { log(packageName, "Typeface factory hook failed", it) }
        runCatching { hookTypefaceBuilder(packageName) }
            .onFailure { log(packageName, "Typeface.Builder hook failed", it) }
        runCatching { hookModernFontBuilder(packageName) }
            .onFailure { log(packageName, "Font.Builder hook failed", it) }
        runCatching { hookResourcesFonts(packageName) }
            .onFailure { log(packageName, "Resources font hook failed", it) }
        runCatching { hookAndroidXResourcesCompat(packageName, lpparam.classLoader) }
            .onFailure { log(packageName, "ResourcesCompat hook skipped", it) }

        XposedBridge.log("LuoShu AppFontHook active: $packageName")
    }

    /**
     * HyperOS Clock may read a font asset into a ByteBuffer before constructing Font.Builder.
     * Replacing the stream here covers that route while still excluding icon/emoji assets.
     */
    private fun hookRawAssetReads(packageName: String) {
        XposedBridge.hookAllMethods(
            AssetManager::class.java,
            "open",
            object : XC_MethodHook() {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    val request = param.args.firstOrNull { it is String } as? String ?: return
                    val source = sourceForRequest(request) ?: return
                    val stream = runCatching { FileInputStream(source) }.getOrNull() ?: return
                    logReplacementOnce(packageName, "AssetManager.open", request, source)
                    param.result = stream
                }
            },
        )

        XposedBridge.hookAllMethods(
            AssetManager::class.java,
            "openFd",
            object : XC_MethodHook() {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    val request = param.args.firstOrNull { it is String } as? String ?: return
                    val source = sourceForRequest(request) ?: return
                    val file = File(source)
                    val descriptor = runCatching {
                        val pfd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
                        AssetFileDescriptor(pfd, 0L, file.length())
                    }.getOrNull() ?: return
                    logReplacementOnce(packageName, "AssetManager.openFd", request, source)
                    param.result = descriptor
                }
            },
        )
    }

    private fun hookTypefaceFactories(packageName: String) {
        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "createFromAsset",
            AssetManager::class.java,
            String::class.java,
            replaceResultFromRequest(packageName, "Typeface.createFromAsset") { param ->
                param.args.getOrNull(1) as? String
            },
        )

        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "createFromFile",
            String::class.java,
            replaceResultFromRequest(packageName, "Typeface.createFromFile") { param ->
                param.args.getOrNull(0) as? String
            },
        )

        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "createFromFile",
            File::class.java,
            replaceResultFromRequest(packageName, "Typeface.createFromFile") { param ->
                (param.args.getOrNull(0) as? File)?.path
            },
        )
    }

    private fun hookTypefaceBuilder(packageName: String) {
        val builderClass = Typeface.Builder::class.java

        XposedHelpers.findAndHookConstructor(
            builderClass,
            AssetManager::class.java,
            String::class.java,
            rememberBuilderRequest { param -> param.args.getOrNull(1) as? String },
        )
        XposedHelpers.findAndHookConstructor(
            builderClass,
            Resources::class.java,
            Int::class.javaPrimitiveType,
            rememberBuilderRequest { param ->
                val resources = param.args.getOrNull(0) as? Resources ?: return@rememberBuilderRequest null
                val id = param.args.getOrNull(1) as? Int ?: return@rememberBuilderRequest null
                resourceRequest(resources, id)
            },
        )
        XposedHelpers.findAndHookConstructor(
            builderClass,
            String::class.java,
            rememberBuilderRequest { param -> param.args.getOrNull(0) as? String },
        )
        XposedHelpers.findAndHookConstructor(
            builderClass,
            File::class.java,
            rememberBuilderRequest { param -> (param.args.getOrNull(0) as? File)?.path },
        )

        XposedHelpers.findAndHookMethod(
            builderClass,
            "build",
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    val request = XposedHelpers.getAdditionalInstanceField(
                        param.thisObject,
                        BUILDER_REQUEST_KEY,
                    ) as? String ?: return
                    val original = param.result as? Typeface
                    replacementTypeface(request, original)?.let {
                        logReplacementOnce(packageName, "Typeface.Builder", request, sourceForRequest(request).orEmpty())
                        param.result = it
                    }
                }
            },
        )
    }

    /**
     * Android 10+ exposes android.graphics.fonts.Font.Builder. HyperOS Clock builds MiSansRCF and
     * Mitype families through this API, then wraps them in FontFamily/CustomFallbackBuilder.
     */
    private fun hookModernFontBuilder(packageName: String) {
        val builderClass = XposedHelpers.findClassIfExists(
            "android.graphics.fonts.Font\$Builder",
            null,
        ) ?: return

        XposedBridge.hookAllConstructors(
            builderClass,
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    if (MODERN_FONT_GUARD.get() == true) return
                    val request = when {
                        param.args.size >= 2 && param.args[0] is AssetManager && param.args[1] is String -> {
                            param.args[1] as String
                        }
                        param.args.size >= 2 && param.args[0] is Resources && param.args[1] is Int -> {
                            resourceRequest(param.args[0] as Resources, param.args[1] as Int)
                        }
                        param.args.firstOrNull() is File -> (param.args.first() as File).path
                        else -> null
                    } ?: return
                    if (!shouldReplace(request)) return
                    XposedHelpers.setAdditionalInstanceField(param.thisObject, MODERN_BUILDER_REQUEST_KEY, request)
                }
            },
        )

        XposedBridge.hookAllMethods(
            builderClass,
            "build",
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    if (MODERN_FONT_GUARD.get() == true) return
                    val request = XposedHelpers.getAdditionalInstanceField(
                        param.thisObject,
                        MODERN_BUILDER_REQUEST_KEY,
                    ) as? String ?: return
                    val originalFont = param.result ?: return

                    val style = runCatching { XposedHelpers.callMethod(originalFont, "getStyle") }.getOrNull()
                    val originalWeight = runCatching {
                        XposedHelpers.callMethod(style, "getWeight") as? Int
                    }.getOrNull() ?: 400
                    val slant = runCatching {
                        XposedHelpers.callMethod(style, "getSlant") as? Int
                    }.getOrNull() ?: 0
                    val weight = weightFromRequest(request) ?: originalWeight
                    val source = sourceForWeight(request, weight) ?: return

                    val replacement = runCatching {
                        MODERN_FONT_GUARD.set(true)
                        val replacementBuilder = XposedHelpers.newInstance(builderClass, File(source))
                        XposedHelpers.callMethod(replacementBuilder, "setWeight", weight)
                        XposedHelpers.callMethod(replacementBuilder, "setSlant", slant)
                        XposedHelpers.callMethod(replacementBuilder, "build")
                    }.getOrNull().also {
                        MODERN_FONT_GUARD.remove()
                    } ?: return

                    logReplacementOnce(packageName, "Font.Builder", request, source)
                    param.result = replacement
                }
            },
        )
    }

    private fun hookResourcesFonts(packageName: String) {
        XposedHelpers.findAndHookMethod(
            Resources::class.java,
            "getFont",
            Int::class.javaPrimitiveType,
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    val resources = param.thisObject as? Resources ?: return
                    val id = param.args.getOrNull(0) as? Int ?: return
                    val request = resourceRequest(resources, id) ?: return
                    val original = param.result as? Typeface
                    replacementTypeface(request, original)?.let {
                        logReplacementOnce(packageName, "Resources.getFont", request, sourceForRequest(request).orEmpty())
                        param.result = it
                    }
                }
            },
        )
    }

    private fun hookAndroidXResourcesCompat(packageName: String, classLoader: ClassLoader) {
        val clazz = XposedHelpers.findClassIfExists(
            "androidx.core.content.res.ResourcesCompat",
            classLoader,
        ) ?: return

        XposedHelpers.findAndHookMethod(
            clazz,
            "getFont",
            Context::class.java,
            Int::class.javaPrimitiveType,
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    val context = param.args.getOrNull(0) as? Context ?: return
                    val id = param.args.getOrNull(1) as? Int ?: return
                    val request = resourceRequest(context.resources, id) ?: return
                    val original = param.result as? Typeface
                    replacementTypeface(request, original)?.let {
                        logReplacementOnce(packageName, "ResourcesCompat.getFont", request, sourceForRequest(request).orEmpty())
                        param.result = it
                    }
                }
            },
        )
    }

    private fun replaceResultFromRequest(
        packageName: String,
        route: String,
        requestProvider: (XC_MethodHook.MethodHookParam) -> String?,
    ): XC_MethodHook = object : XC_MethodHook() {
        override fun afterHookedMethod(param: MethodHookParam) {
            val request = requestProvider(param) ?: return
            val original = param.result as? Typeface
            replacementTypeface(request, original)?.let {
                logReplacementOnce(packageName, route, request, sourceForRequest(request).orEmpty())
                param.result = it
            }
        }
    }

    private fun rememberBuilderRequest(
        requestProvider: (XC_MethodHook.MethodHookParam) -> String?,
    ): XC_MethodHook = object : XC_MethodHook() {
        override fun afterHookedMethod(param: MethodHookParam) {
            val request = requestProvider(param) ?: return
            if (!shouldReplace(request)) return
            XposedHelpers.setAdditionalInstanceField(param.thisObject, BUILDER_REQUEST_KEY, request)
        }
    }

    private fun resourceRequest(resources: Resources, id: Int): String? {
        return runCatching {
            val type = resources.getResourceTypeName(id)
            if (type != "font") return null
            resources.getResourceEntryName(id)
        }.getOrNull()
    }

    private fun replacementTypeface(request: String, original: Typeface?): Typeface? {
        val source = sourceForRequest(request) ?: return null
        val base = TYPEFACE_CACHE[source] ?: runCatching {
            Typeface.createFromFile(source)
        }.getOrNull()?.also { TYPEFACE_CACHE[source] = it } ?: return null

        val style = original?.style ?: Typeface.NORMAL
        return if (style == Typeface.NORMAL) base else Typeface.create(base, style)
    }

    private fun sourceForRequest(request: String): String? {
        val weight = weightFromRequest(request) ?: 400
        return sourceForWeight(request, weight)
    }

    private fun sourceForWeight(request: String, weight: Int): String? {
        if (!shouldReplace(request)) return null
        val lower = request.lowercase()
        val normalizedWeight = nearestWeight(weight)
        val variableRequest = "vf" in lower || "variable" in lower || "flex" in lower || "rcf" in lower
        val candidates = buildList {
            if (variableRequest) {
                add("/system/fonts/MiSansVF.ttf")
                add("/system/fonts/RobotoFlex-Regular.ttf")
            }
            add("/system/fonts/$normalizedWeight.ttf")
            add("/system/fonts/400.ttf")
            add("/system/fonts/Roboto-Regular.ttf")
            add("/system/fonts/MiSansVF.ttf")
        }
        return candidates.firstOrNull { File(it).canRead() }
    }

    private fun nearestWeight(weight: Int): Int {
        return AVAILABLE_WEIGHTS.minByOrNull { kotlin.math.abs(it - weight) } ?: 400
    }

    private fun weightFromRequest(request: String): Int? {
        val lower = request.lowercase()
        return when {
            "black" in lower || "heavy" in lower || "-90" in lower || "900" in lower -> 900
            "extrabold" in lower || "extra_bold" in lower || "-80" in lower || "800" in lower -> 800
            "demibold" in lower || "semi-bold" in lower || "semibold" in lower ||
                "semi_bold" in lower || "-60" in lower || "600" in lower -> 600
            "bold" in lower || "-70" in lower || "700" in lower -> 700
            "medium" in lower || "-50" in lower || "500" in lower -> 500
            "regular" in lower || "-40" in lower || "400" in lower -> 400
            "light" in lower || "-30" in lower || "300" in lower -> 300
            "extralight" in lower || "extra_light" in lower || "-20" in lower || "200" in lower -> 200
            "thin" in lower || "-10" in lower || "100" in lower -> 100
            else -> null
        }
    }

    private fun shouldReplace(request: String): Boolean {
        val lower = request.lowercase()
        if (EXCLUDED_MARKERS.any(lower::contains)) return false
        return INCLUDED_MARKERS.any(lower::contains)
    }

    private fun logReplacementOnce(packageName: String, route: String, request: String, source: String) {
        val key = "$packageName|$route|$request|$source"
        if (LOGGED_REPLACEMENTS.putIfAbsent(key, true) == null) {
            XposedBridge.log("LuoShu AppFontHook replaced [$packageName] via $route: $request -> $source")
        }
    }

    private fun log(packageName: String, message: String, error: Throwable) {
        XposedBridge.log("LuoShu AppFontHook [$packageName] $message: ${error.javaClass.simpleName}: ${error.message}")
    }

    private companion object {
        const val BUILDER_REQUEST_KEY = "luoshu_font_request"
        const val MODERN_BUILDER_REQUEST_KEY = "luoshu_modern_font_request"

        val TYPEFACE_CACHE = ConcurrentHashMap<String, Typeface>()
        val LOGGED_REPLACEMENTS = ConcurrentHashMap<String, Boolean>()
        val MODERN_FONT_GUARD = ThreadLocal<Boolean>()
        val AVAILABLE_WEIGHTS = listOf(100, 200, 300, 350, 400, 500, 600, 700, 800, 900)

        val INCLUDED_MARKERS = listOf(
            "productsans",
            "product_sans",
            "googlesans",
            "google_sans",
            "misansrcf",
            "misans",
            "mitype2019",
            "mitypemono",
            "roboto",
            "sourcesans",
            "source_sans",
        )

        val EXCLUDED_MARKERS = listOf(
            "emoji",
            "symbol",
            "misymbol",
            "icon",
            "materialicons",
            "material_symbols",
            "dingbat",
            "barcode",
            "qrcode",
        )
    }
}
