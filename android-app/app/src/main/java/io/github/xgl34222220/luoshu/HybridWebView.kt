package io.github.xgl34222220.luoshu

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color as ComposeColor
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

private const val APP_ASSET_URL = "https://appassets.androidplatform.net/assets/index.html?host=hybrid-app"

private val HYBRID_BOOT_SCRIPT = """
(function bootLuoShuHybrid(){
  document.documentElement.dataset.luoshuHost = 'hybrid-app';
  document.body.classList.add('luoshu-hybrid-host');
  document.body.classList.remove('modal-open','mix-picker-open');
  document.querySelectorAll('.modal.show').forEach(function(item){
    if(item.id !== 'fontWorkbenchModal') item.classList.remove('show');
  });

  var style = document.getElementById('luoshuHybridHostStyle');
  if(!style){
    style = document.createElement('style');
    style.id = 'luoshuHybridHostStyle';
    style.textContent = `
      html,body{width:100%!important;height:100%!important;min-height:100%!important;margin:0!important;overflow:hidden!important;background:var(--bg,#f6f7fb)!important}
      body.luoshu-hybrid-host{padding:0!important;touch-action:auto!important}
      body.luoshu-hybrid-host>:not(.modal):not(.toast):not(script):not(style){display:none!important}
      body.luoshu-hybrid-host #fontWorkbenchModal{position:fixed!important;z-index:2000!important;inset:0!important;display:flex!important;align-items:stretch!important;padding:0!important;opacity:1!important;visibility:visible!important;pointer-events:auto!important;background:var(--bg,#f6f7fb)!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important}
      body.luoshu-hybrid-host #fontWorkbenchModal .workbench-sheet{width:100%!important;height:100%!important;max-width:none!important;max-height:none!important;margin:0!important;border:0!important;border-radius:0!important;background:var(--bg,#f6f7fb)!important;box-shadow:none!important;transform:none!important;animation:none!important}
      body.luoshu-hybrid-host .workbench-hero{padding:16px 54px 13px 16px!important;background:var(--card)!important;border-bottom:1px solid var(--line)!important}
      body.luoshu-hybrid-host .workbench-close{display:none!important}
      body.luoshu-hybrid-host .workbench-tabs{flex:0 0 auto;background:var(--card)!important;border-bottom:1px solid var(--line)!important}
      body.luoshu-hybrid-host .workbench-body{padding:12px 10px max(18px,env(safe-area-inset-bottom,0px))!important;background:var(--bg,#f6f7fb)!important}
      body.luoshu-hybrid-host .workbench-section{box-shadow:none!important}
      body.luoshu-hybrid-host .modal:not(#fontWorkbenchModal).show{z-index:6000!important;display:flex!important}
      body.luoshu-hybrid-host .mix-picker-modal.show{z-index:6500!important}
      body.luoshu-hybrid-host .v14-switch-progress{bottom:18px!important;z-index:7000!important}
      @media(max-width:620px){body.luoshu-hybrid-host .workbench-sheet{height:100%!important;border-radius:0!important}}
    `;
    document.head.appendChild(style);
  }

  function openWorkbench(){
    if(window.LuoShuWorkbench && typeof window.LuoShuWorkbench.open === 'function'){
      window.LuoShuWorkbench.open();
      document.body.classList.add('luoshu-hybrid-ready');
      return true;
    }
    return false;
  }

  if(!openWorkbench()){
    var attempts = 0;
    var timer = setInterval(function(){
      attempts += 1;
      if(openWorkbench() || attempts > 160) clearInterval(timer);
    },50);
  }
})();
""".trimIndent()

@SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
@Composable
internal fun HybridWebView(
    modifier: Modifier = Modifier,
    reloadKey: Int = 0,
) {
    val context = LocalContext.current
    val activity = context as Activity
    var ready by remember(reloadKey) { mutableStateOf(false) }

    val webView = remember(reloadKey) {
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
            .build()

        WebView(context).apply {
            setBackgroundColor(Color.rgb(246, 247, 251))
            setLayerType(View.LAYER_TYPE_HARDWARE, null)
            overScrollMode = View.OVER_SCROLL_NEVER
            isVerticalScrollBarEnabled = false
            isHorizontalScrollBarEnabled = false
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
                    view?.evaluateJavascript(HYBRID_BOOT_SCRIPT) {
                        postDelayed({ ready = true }, 180L)
                    }
                }
            }
            WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
            loadUrl(APP_ASSET_URL)
        }
    }

    Box(modifier = modifier.background(MaterialTheme.colorScheme.background)) {
        AndroidView(factory = { webView }, modifier = Modifier.fillMaxSize())
        if (!ready) {
            Box(
                modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator()
            }
        }
    }

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
        .put("host", "hybrid-app-alpha2")
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
