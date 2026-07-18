package io.github.xgl34222220.luoshu

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
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

private const val APP_ASSET_URL = "https://appassets.androidplatform.net/assets/index.html"

@SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
@Composable
internal fun HybridWebView(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val activity = context as Activity
    val webView = remember {
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
            .build()

        WebView(context).apply {
            setBackgroundColor(Color.TRANSPARENT)
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
                    view?.evaluateJavascript(
                        "document.documentElement.dataset.luoshuHost='hybrid-app';document.body?.classList.add('luoshu-hybrid-host');",
                        null,
                    )
                }
            }
            WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
            loadUrl(APP_ASSET_URL)
        }
    }

    AndroidView(factory = { webView }, modifier = modifier)

    DisposableEffect(webView) {
        onDispose {
            webView.stopLoading()
            webView.removeJavascriptInterface("ksu")
            webView.destroy()
        }
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
    fun fullScreen(enabled: Boolean) {
        activity.runOnUiThread {
            WindowCompat.setDecorFitsSystemWindows(activity.window, !enabled)
        }
    }

    @JavascriptInterface
    fun enableEdgeToEdge(enabled: Boolean) {
        activity.runOnUiThread {
            WindowCompat.setDecorFitsSystemWindows(activity.window, !enabled)
        }
    }

    @JavascriptInterface
    fun toast(message: String) {
        activity.runOnUiThread {
            Toast.makeText(activity, message, Toast.LENGTH_SHORT).show()
        }
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

    @JavascriptInterface
    fun listPackages(type: String): String = "[]"

    @JavascriptInterface
    fun getPackagesInfo(packages: String): String = "[]"

    @JavascriptInterface
    fun exit() {
        activity.runOnUiThread { activity.finish() }
    }
}
