package io.github.xgl34222220.luoshu.hook

import android.content.Context
import android.content.res.AssetManager
import android.content.res.Resources
import android.graphics.Typeface
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage
import java.io.File
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

        runCatching { hookTypefaceFactories() }
            .onFailure { log(packageName, "Typeface factory hook failed", it) }
        runCatching { hookTypefaceBuilder() }
            .onFailure { log(packageName, "Typeface.Builder hook failed", it) }
        runCatching { hookResourcesFonts() }
            .onFailure { log(packageName, "Resources font hook failed", it) }
        runCatching { hookAndroidXResourcesCompat(lpparam.classLoader) }
            .onFailure { log(packageName, "ResourcesCompat hook skipped", it) }

        XposedBridge.log("LuoShu AppFontHook active: $packageName")
    }

    private fun hookTypefaceFactories() {
        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "createFromAsset",
            AssetManager::class.java,
            String::class.java,
            replaceResultFromRequest { param -> param.args.getOrNull(1) as? String },
        )

        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "createFromFile",
            String::class.java,
            replaceResultFromRequest { param -> param.args.getOrNull(0) as? String },
        )

        XposedHelpers.findAndHookMethod(
            Typeface::class.java,
            "createFromFile",
            File::class.java,
            replaceResultFromRequest { param -> (param.args.getOrNull(0) as? File)?.path },
        )
    }

    private fun hookTypefaceBuilder() {
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
                    replacementTypeface(request, original)?.let { param.result = it }
                }
            },
        )
    }

    private fun hookResourcesFonts() {
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
                    replacementTypeface(request, original)?.let { param.result = it }
                }
            },
        )
    }

    private fun hookAndroidXResourcesCompat(classLoader: ClassLoader) {
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
                    replacementTypeface(request, original)?.let { param.result = it }
                }
            },
        )
    }

    private fun replaceResultFromRequest(
        requestProvider: (XC_MethodHook.MethodHookParam) -> String?,
    ): XC_MethodHook = object : XC_MethodHook() {
        override fun afterHookedMethod(param: MethodHookParam) {
            val request = requestProvider(param) ?: return
            val original = param.result as? Typeface
            replacementTypeface(request, original)?.let { param.result = it }
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
        if (!shouldReplace(request)) return null
        val source = sourceForRequest(request) ?: return null
        val base = TYPEFACE_CACHE[source] ?: runCatching {
            Typeface.createFromFile(source)
        }.getOrNull()?.also { TYPEFACE_CACHE[source] = it } ?: return null

        val style = original?.style ?: Typeface.NORMAL
        return if (style == Typeface.NORMAL) base else Typeface.create(base, style)
    }

    private fun sourceForRequest(request: String): String? {
        val lower = request.lowercase()
        val weight = when {
            "black" in lower || "heavy" in lower || "-90" in lower || "900" in lower -> 900
            "extrabold" in lower || "extra_bold" in lower || "-80" in lower || "800" in lower -> 800
            "bold" in lower || "demibold" in lower || "-70" in lower || "700" in lower -> 700
            "semibold" in lower || "semi_bold" in lower || "-60" in lower || "600" in lower -> 600
            "medium" in lower || "-50" in lower || "500" in lower -> 500
            "light" in lower || "-30" in lower || "300" in lower -> 300
            "thin" in lower || "-10" in lower || "100" in lower -> 100
            else -> 400
        }
        val candidates = listOf(
            "/system/fonts/$weight.ttf",
            "/system/fonts/Roboto-Regular.ttf",
            "/system/fonts/MiSansVF.ttf",
        )
        return candidates.firstOrNull { File(it).canRead() }
    }

    private fun shouldReplace(request: String): Boolean {
        val lower = request.lowercase()
        if (EXCLUDED_MARKERS.any(lower::contains)) return false
        return INCLUDED_MARKERS.any(lower::contains)
    }

    private fun log(packageName: String, message: String, error: Throwable) {
        XposedBridge.log("LuoShu AppFontHook [$packageName] $message: ${error.javaClass.simpleName}: ${error.message}")
    }

    private companion object {
        const val BUILDER_REQUEST_KEY = "luoshu_font_request"

        val TYPEFACE_CACHE = ConcurrentHashMap<String, Typeface>()

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
