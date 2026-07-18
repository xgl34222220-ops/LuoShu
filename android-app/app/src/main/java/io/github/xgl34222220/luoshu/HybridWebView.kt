package io.github.xgl34222220.luoshu

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.util.Base64
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.webkit.WebViewAssetLoader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.FilterInputStream
import java.io.InputStream

private const val APP_ASSET_URL = "https://appassets.androidplatform.net/assets/index.html"
private const val ROOT_FONT_PREFIX = "https://appassets.androidplatform.net/root-font/"

@SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
@Composable
internal fun HybridWebView(reloadKey: Int = 0, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val activity = context as Activity
    var ready by remember(reloadKey) { mutableStateOf(false) }

    val webView = remember(reloadKey) {
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
            .addPathHandler("/root-font/", RootFontPathHandler())
            .build()

        WebView(context).apply {
            setBackgroundColor(Color.WHITE)
            setLayerType(View.LAYER_TYPE_HARDWARE, null)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.databaseEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.setSupportZoom(false)
            settings.builtInZoomControls = false
            settings.displayZoomControls = false
            settings.mediaPlaybackRequiresUserGesture = true

            addJavascriptInterface(LuoShuJavascriptBridge(activity, this), "ksu")
            webChromeClient = WebChromeClient()
            webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest): WebResourceResponse? {
                    return assetLoader.shouldInterceptRequest(request.url)
                }

                override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest): Boolean {
                    val url = request.url
                    if (url.host == "appassets.androidplatform.net") return false
                    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, url)) }
                    return true
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    val hostScript = """
                        (function installHybridHost(){
                          const cssId='luoshuHybridAppCss';
                          if(!document.getElementById(cssId)){
                            const style=document.createElement('style');
                            style.id=cssId;
                            style.textContent=`
                              html,body{background:#f7f8fb!important;overflow:auto!important}
                              body>*:not(#fontWorkbenchModal):not(.toast){display:none!important}
                              #fontWorkbenchModal{display:block!important;position:static!important;inset:auto!important;background:transparent!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;opacity:1!important;visibility:visible!important;padding:0!important;min-height:100vh!important}
                              #fontWorkbenchModal .workbench-sheet{position:static!important;width:100%!important;max-width:none!important;height:auto!important;min-height:100vh!important;max-height:none!important;margin:0!important;border:0!important;border-radius:0!important;box-shadow:none!important;transform:none!important;background:#f7f8fb!important;overflow:visible!important}
                              #fontWorkbenchModal .workbench-hero{display:none!important}
                              #fontWorkbenchModal .workbench-close,.workbench-version{display:none!important}
                              #fontWorkbenchModal .workbench-tabs{position:sticky!important;top:0!important;z-index:10!important;background:rgba(247,248,251,.96)!important;backdrop-filter:blur(16px)!important;-webkit-backdrop-filter:blur(16px)!important}
                              #fontWorkbenchModal .workbench-body{min-height:calc(100vh - 90px)!important;overflow:visible!important}
                              .modal.show{animation:none!important}
                            `;
                            document.head.appendChild(style);
                          }

                          const convertUrl=(value)=>{
                            if(!value) return value;
                            try{return window.ksu.fontUrl(String(value));}catch(_){return value;}
                          };
                          const convertFont=(font)=>{
                            if(!font||font.__hybridMapped) return font;
                            const copy={...font,__hybridMapped:true,sourceFile:font.file};
                            copy.file=convertUrl(font.file);
                            if(font.variants&&typeof font.variants==='object'){
                              copy.variants=Object.fromEntries(Object.entries(font.variants).map(([key,value])=>[key,convertUrl(value)]));
                            }
                            return copy;
                          };
                          if(window.App&&!window.App.__hybridFontBridge){
                            const originalApply=window.App.applyFontData.bind(window.App);
                            window.App.applyFontData=(data,persist=true)=>{
                              const mapped={...data,fonts:Array.isArray(data?.fonts)?data.fonts.map(convertFont):[]};
                              return originalApply(mapped,persist);
                            };
                            window.App.fonts=(window.App.fonts||[]).map(convertFont);
                            window.App.__hybridFontBridge=true;
                          }

                          document.querySelectorAll('.modal.show').forEach(node=>{
                            if(node.id!=='fontWorkbenchModal') node.classList.remove('show');
                          });
                          if(typeof window.openWorkbench==='function'){
                            Promise.resolve(window.openWorkbench()).finally(()=>{
                              document.getElementById('fontWorkbenchModal')?.classList.add('show');
                              document.body.classList.add('workbench-open');
                              window.__luoshuHybridReady=true;
                            });
                          }else{
                            setTimeout(installHybridHost,80);
                          }
                        })();
                    """.trimIndent()
                    view?.evaluateJavascript(hostScript) { }
                    view?.postDelayed({
                        view.evaluateJavascript("Boolean(window.__luoshuHybridReady)") { value ->
                            if (value == "true") ready = true else view.evaluateJavascript(hostScript, null)
                        }
                    }, 420)
                    view?.postDelayed({ ready = true }, 1_500)
                }
            }
            WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
            loadUrl(APP_ASSET_URL)
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        AndroidView(factory = { webView }, modifier = Modifier.fillMaxSize())
        if (!ready) CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
    }

    DisposableEffect(webView) {
        onDispose {
            webView.stopLoading()
            webView.removeJavascriptInterface("ksu")
            webView.destroy()
        }
    }
}

private class RootFontPathHandler : WebViewAssetLoader.PathHandler {
    override fun handle(path: String): WebResourceResponse? {
        val decoded = runCatching {
            val bytes = Base64.decode(path, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            bytes.toString(Charsets.UTF_8)
        }.getOrNull() ?: return null

        val allowed = decoded.startsWith("/data/adb/modules/LuoShu/") ||
            decoded.startsWith("/sdcard/LuoShu/") ||
            decoded.startsWith("/storage/emulated/0/LuoShu/")
        if (!allowed || decoded.contains("\u0000")) return null

        val process = runCatching {
            ProcessBuilder("su", "-c", "cat ${RootShell.quote(decoded)}")
                .redirectErrorStream(true)
                .start()
        }.getOrNull() ?: return null

        val stream = ProcessInputStream(process.inputStream, process)
        return WebResourceResponse(mimeFor(decoded), null, stream).apply {
            responseHeaders = mapOf(
                "Cache-Control" to "private, max-age=120",
                "Access-Control-Allow-Origin" to "https://appassets.androidplatform.net",
            )
        }
    }

    private fun mimeFor(path: String): String = when (path.substringAfterLast('.', "").lowercase()) {
        "otf" -> "font/otf"
        "ttc" -> "font/collection"
        "woff" -> "font/woff"
        "woff2" -> "font/woff2"
        else -> "font/ttf"
    }
}

private class ProcessInputStream(input: InputStream, private val process: Process) : FilterInputStream(input) {
    override fun close() {
        runCatching { super.close() }
        runCatching { process.errorStream.close() }
        runCatching { process.outputStream.close() }
        runCatching { process.destroy() }
    }
}

private class LuoShuJavascriptBridge(
    private val activity: Activity,
    private val webView: WebView,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val callbackPattern = Regex("^[A-Za-z_$][A-Za-z0-9_$]*$")

    @JavascriptInterface
    fun exec(command: String, optionsJson: String, callbackName: String) {
        if (!callbackPattern.matches(callbackName)) return
        scope.launch {
            val result = RootShell.exec(command)
            val script = """
                (function(){
                  var callback=window[${JSONObject.quote(callbackName)}];
                  if(typeof callback==='function') callback(${result.code},${JSONObject.quote(result.stdout)},${JSONObject.quote(result.stderr)});
                })();
            """.trimIndent()
            webView.evaluateJavascript(script, null)
        }
    }

    @JavascriptInterface
    fun spawn(command: String, argsJson: String, optionsJson: String, callbackName: String) {
        if (!callbackPattern.matches(callbackName)) return
        val args = runCatching {
            val array = JSONArray(argsJson)
            List(array.length()) { index -> array.optString(index) }
        }.getOrDefault(emptyList())
        val shellCommand = buildString {
            append(command)
            args.forEach { append(' ').append(RootShell.quote(it)) }
        }
        scope.launch {
            val result = RootShell.exec(shellCommand)
            val script = """
                (function(){
                  var child=window[${JSONObject.quote(callbackName)}];
                  if(!child) return;
                  if(${JSONObject.quote(result.stdout)} && child.stdout) child.stdout.emit('data',${JSONObject.quote(result.stdout)});
                  if(${JSONObject.quote(result.stderr)} && child.stderr) child.stderr.emit('data',${JSONObject.quote(result.stderr)});
                  child.emit('exit',${result.code});
                })();
            """.trimIndent()
            webView.evaluateJavascript(script, null)
        }
    }

    @JavascriptInterface
    fun fontUrl(path: String): String {
        if (path.startsWith(ROOT_FONT_PREFIX)) return path
        if (path.startsWith("http://") || path.startsWith("https://")) return path
        val encoded = Base64.encodeToString(path.toByteArray(Charsets.UTF_8), Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        return ROOT_FONT_PREFIX + encoded
    }

    @JavascriptInterface
    fun fullScreen(enabled: Boolean) {
        activity.runOnUiThread { WindowCompat.setDecorFitsSystemWindows(activity.window, !enabled) }
    }

    @JavascriptInterface
    fun enableEdgeToEdge(enabled: Boolean) {
        activity.runOnUiThread { WindowCompat.setDecorFitsSystemWindows(activity.window, !enabled) }
    }

    @JavascriptInterface
    fun toast(message: String) {
        activity.runOnUiThread { Toast.makeText(activity, message, Toast.LENGTH_SHORT).show() }
    }

    @JavascriptInterface
    fun moduleInfo(): String = JSONObject()
        .put("id", "LuoShu")
        .put("name", "洛书")
        .put("version", "v14.2 Alpha3")
        .put("versionCode", 14203)
        .put("moduleDir", "/data/adb/modules/LuoShu")
        .put("host", "hybrid-app")
        .toString()

    @JavascriptInterface fun listPackages(type: String): String = "[]"
    @JavascriptInterface fun getPackagesInfo(packages: String): String = "[]"
    @JavascriptInterface fun exit() { activity.runOnUiThread { activity.finish() } }
}
