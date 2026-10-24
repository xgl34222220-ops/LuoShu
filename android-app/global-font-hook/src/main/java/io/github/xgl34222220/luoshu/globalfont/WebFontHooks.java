package io.github.xgl34222220.luoshu.globalfont;

import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import io.github.xgl34222220.luoshu.globalfont.rules.WebFontRules;
import java.io.ByteArrayInputStream;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/*
 * Makes android.webkit.WebView pages fall back to the system font by answering body-text web-font
 * requests with an empty 404. Only {@code shouldInterceptRequest} is hooked (it already runs on
 * Chromium's IO threads, never on the UI thread) plus {@code WebView.setWebViewClient}, which is
 * called once per WebView to find the app's own client subclass. The decision reads the URL, the
 * Accept header and an app-provided MIME type only; response bodies are never read.
 */
final class WebFontHooks {
    private WebFontHooks() {}

    static final String REASON = "Not Found (LuoShu global font)";
    private static final Set<Class<?>> HOOKED = Collections.newSetFromMap(new ConcurrentHashMap<>());
    private static volatile boolean blockUnknown;

    static void install(boolean blockUnknownFonts) {
        blockUnknown = blockUnknownFonts;
        final XC_MethodHook intercept = new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                apply(param);
            }
        };
        // Default client (no client set, or subclasses that call super / only override the String form).
        Deopt.method(WebViewClient.class, "shouldInterceptRequest", WebView.class, WebResourceRequest.class);
        XposedHelpers.findAndHookMethod(WebViewClient.class, "shouldInterceptRequest",
                WebView.class, WebResourceRequest.class, intercept);
        Deopt.method(WebView.class, "setWebViewClient", WebViewClient.class);
        XposedHelpers.findAndHookMethod(WebView.class, "setWebViewClient", WebViewClient.class, new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                Object client = param.args[0];
                if (client == null) return;
                for (Class<?> c = client.getClass(); c != null && c != WebViewClient.class; c = c.getSuperclass()) {
                    Method m;
                    try {
                        m = c.getDeclaredMethod("shouldInterceptRequest", WebView.class, WebResourceRequest.class);
                    } catch (NoSuchMethodException e) {
                        continue;
                    }
                    if (HOOKED.add(c)) {
                        Deopt.member(m);
                        XposedBridge.hookMethod(m, intercept);
                        Log.v("webview client hooked: " + c.getName());
                    }
                    return; // most-derived override found
                }
            }
        });
    }

    private static void apply(XC_MethodHook.MethodHookParam param) {
        Object reqObj = param.args.length > 1 ? param.args[1] : null;
        if (!(reqObj instanceof WebResourceRequest)) return;
        WebResourceRequest req = (WebResourceRequest) reqObj;
        if (req.isForMainFrame()) return;
        Object res = param.getResult();
        String mime = null;
        if (res instanceof WebResourceResponse) {
            WebResourceResponse r = (WebResourceResponse) res;
            if (REASON.equals(r.getReasonPhrase())) return; // already ours (super() chain)
            mime = r.getMimeType();
            if (mime == null) return; // app answered with something we cannot classify; respect it
        }
        String url = String.valueOf(req.getUrl());
        Map<String, String> headers = req.getRequestHeaders();
        String accept = headers == null ? null : headers.get("Accept");
        if (accept == null && headers != null) accept = headers.get("accept");
        if (WebFontRules.verdict(url, accept, mime, blockUnknown) != WebFontRules.Verdict.BLOCK) return;
        Map<String, String> h = new HashMap<>(2);
        h.put("Access-Control-Allow-Origin", "*");
        h.put("Cache-Control", "no-store");
        param.setResult(new WebResourceResponse("text/plain", "utf-8", 404, REASON, h,
                new ByteArrayInputStream(new byte[0])));
        Log.v("web font blocked: " + url);
    }
}
