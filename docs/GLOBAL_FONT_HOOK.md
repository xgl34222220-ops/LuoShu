# 洛书全局字体（可选 LSPosed 伴随模块）

> 目录：`global-font-hook/`。独立 Gradle 工程，独立产出 APK（CI 产物 `LuoShu-GlobalFont-Companion`）。
> 洛书主模块保持**无 Hook**，主模块 ZIP 不包含本模块任何文件（`scripts/module_payload_manifest.txt` 未改动，CI 有检查）。

## 解决什么问题

洛书替换的是系统字体。很多 App 自己打包了正文字体（如 X 的 Chirp、Claude 的 Styrene/Tiempos、各类 `assets/fonts/*.ttf`、Compose `Font(R.font.x)`），网页也会下载自己的 Web 字体，所以这些地方的拉丁字母和数字仍是 App/网页自带字体。
本模块的效果类似 ColorOS flip font：在用户**在 LSPosed 中勾选**的 App 里，把 App 内置的正文字体和 WebView 网页正文字体换回系统默认字体（即洛书替换后的字体），并保持原来请求的字重和斜体。

## 原理与 Hook 点

| 场景 | Hook 点 | 动作 |
| --- | --- | --- |
| Android 10+ 所有 App 字体加载 | `android.graphics.fonts.Font.Builder` 全部构造器（只记录来源：asset 路径 / 文件路径 / 资源名 / 无名 buffer） | 记录 builder → 来源 |
| | `Font.Builder.build()` | 记录 Font → 来源 |
| | `Typeface.CustomFallbackBuilder(FontFamily)` 构造器 | 记录 builder → family |
| | `Typeface.CustomFallbackBuilder.build()` | 判定 family 第一个字体；正文字体返回 `Typeface.create(Typeface.DEFAULT/SERIF, 原字重, 原斜体)` |
| Android 9 | `Typeface.Builder` 构造器 + `build()`、`Typeface.createFromAsset`、`Typeface.createFromFile(String/File)` | 仅按名字判定 |
| WebView 网页字体 | `WebViewClient.shouldInterceptRequest(WebView, WebResourceRequest)`（基类）+ `WebView.setWebViewClient` 时对 App 自己的 client 子类的同名覆写方法挂一次 | 正文 Web 字体回 404 空响应，页面回落到系统字体 |

为什么 Android 10+ 只挂 `Font.Builder` + `CustomFallbackBuilder` 就够：AOSP 中
`Typeface.createFromAsset/createFromFile` → `Typeface.Builder.build()` → `Font.Builder` + `CustomFallbackBuilder`；
`Resources.getFont` → `ResourcesImpl.loadFont` → `Typeface.Builder(...).build()` 或 `Typeface.createFromResources`（同样走 `Font.Builder` + `CustomFallbackBuilder`）；
AndroidX `ResourcesCompat.getFont` / `TypefaceCompatApi29Impl`（含可下载字体）与 Compose `Font(resId)`（`Resources.getFont`）/ `Font(assetManager, path)` / `Font(file)`（`Typeface.Builder`）全部汇入这两个入口。
这样同一个字体只在加载时判定一次，不重复挂上层 API。

### 判定规则（与主模块扫描保持一致）

`rules/FontNameRules.java`：

* **保留**（不替换）：名字含 icon / symbol / material / awesome / glyph / dingbat / weather / fontello / emptyfont（同 `common/font_import.sh import_is_icon_name`）、emoji / twemoji / noto-color（同 `import_is_color_font_name`）、`common/font_inventory.py GENERIC_DENY_FILE_TOKENS` 全部词（emoji icon symbol math music mono monospace clock dingbat barcode qrcode materialicons notocoloremoji 及阿拉伯/希伯来/泰文/天城文等脚本专用字体），另加 iconfont、fontawesome/`fa-*`、Material Symbols、remixicon、codicon、KaTeX/MathJax/STIX/latex、digit/number/`num`、LCD/七段、等宽与代码字体（mono、SF Mono、JetBrains、Source Code 等）。单测 `coversModuleScannerTokens` 直接读取上述两个仓库文件，主模块名单新增词而这里漏掉时测试失败。
* **衬线**：名字含 serif（且不含 sans）或常见衬线正文族（Tiempos、Copernicus、Georgia、Noto Serif…）→ 换成系统 `Typeface.SERIF` 对应字重，保持设计意图。
* **无法判断**：内容哈希名（`3f9c0a1e.woff2`）、R8 缩短名（`a.ttf`、`res/font/b0.ttf`）、无名 buffer → 交给 `SfntInspector` 读字体表：name 表族名再走一遍名单；有 COLR/CBDT/sbix/SVG（彩色/表情）、`post.isFixedPitch`（等宽）、cmap 拉丁字母不足 40/52（无拉丁 cmap，如纯数字/纯图标/纯 CJK）、私用区码位多于拉丁字母（连字图标字体如 Material Icons）→ 保留；否则替换。读不出来的字体一律保留。

### 先 deoptimize 再 Hook

ART 可能把 `Font.Builder.build()` 这类短方法内联进调用方，或保留 AOT 编译副本，导致 Hook 装上了却被绕过（漏拦）。参考 MFGA-Xposed 的做法，每个 Hook 安装前先对目标方法调用一次 deoptimize：

- 范围：仅限已 Hook 的方法——`Font.Builder` 全部构造与 `build()`、`Typeface.CustomFallbackBuilder(FontFamily)` 与 `build()`、Android 9 的 `Typeface.Builder` 构造与 `build()`、`createFromAsset`、`createFromFile(String/File)`，以及 `WebViewClient.shouldInterceptRequest`、`WebView.setWebViewClient` 和 App 自己的 `shouldInterceptRequest` 覆写。
- 实现：`Deopt` 通过反射调用 LSPosed 旧 API 的 `XposedBridge.deoptimizeMethod(Member)`；框架没有该方法或调用失败时静默跳过，Hook 照常安装，不会崩溃。
- 开销：每个方法只在模块加载时调用一次，不在绘制/加载热路径上。

## 为什么不会卡（硬性性能约束）

1. **只挂加载入口**：绝不挂 `onDraw`、`measure`、`TextView.setTypeface`、`Paint`、`Canvas`、`StaticLayout` 等热路径。字体加载在一个 App 生命周期里通常只有几次到几十次。
2. **每个字体只判定一次**：判定结果按来源（`asset:路径`/`file:路径`/`res:资源名`/无名字体的表目录 CRC，加上字体字节数）缓存在 `ConcurrentHashMap`；替换后的 Typeface 按 `(来源, 字重, 斜体)` 缓存，同一 `(衬线/无衬线, 字重, 斜体)` 只创建一个系统 Typeface 单例反复复用。
3. **主线程零文件 IO、零 cmap 解析**：先用文件名判定（纯字符串，约 1 µs）。只有名字无法判断时才需要读字体表：若当前在主线程，**本次保持原字体**，把检查丢到后台低优先级守护线程，结果写入缓存并持久化到该 App 自己的 `cache/luoshu_global_font.tsv`（后台写），下次加载/下次启动直接命中；不在主线程时才就地检查（且只做一次）。持久化文件也只在后台线程读取。
4. **WebView 只看 URL**：`shouldInterceptRequest` 本身运行在 Chromium 的 IO 线程；判定只看 URL 后缀、请求 Accept 头和 App 已给出的 MIME，**不读任何响应体**，不发起任何网络请求；非字体请求在后缀比较后立即返回。
5. **未勾选的 App 零开销**：LSPosed 只把模块注入作用域内的进程；作用域外的 App 不加载本模块任何代码。作用域内每个进程只装一次 Hook，且只在 `isFirstApplication` 时安装。配置用 XSharedPreferences 读一次（一个很小的 XML）。

### 可量化开销（`DecisionCacheBenchmarkTest`，JVM，ns/op）

CI 每次运行都会把实测值写进 `app/build/reports/global-font-benchmark.txt`、Job Summary 和产物。开发机（aarch64，JDK 17）一次实测：

| 操作 | 耗时 |
| --- | --- |
| 文件名判定 `FontNameRules.classify` | ≈ 1.1 µs |
| 判定缓存命中 | ≈ 0.04 µs |
| `(来源, 字重, 斜体)` → Typeface 缓存命中 | ≈ 0.2 µs |
| WebView URL 判定（含非字体请求） | ≈ 0.7 µs |
| sfnt 深度检查（每个字体最多一次，不在主线程） | ≈ 2 µs（合成小字体；真实字体只读表目录/name/cmap 分段，仍在微秒到亚毫秒级） |

作为对比，一次 `Typeface.createFromAsset` 本身要 mmap 并解析整个字体文件（毫秒级），Hook 增加的开销低于其千分之一；渲染每一帧不经过任何 Hook。

## WebView 网页字体

* 判定为正文字体（如 `abs.twimg.com/.../chirp-regular-web.woff2`、`fonts.gstatic.com/s/roboto/...`）→ 返回 `404` 空响应，CSS 回落到 `font-family` 后续项，最终是系统 sans-serif（洛书字体）。
* 放行：图标/数学/表情字体（目录或文件名命中名单，如 `fonts.gstatic.com/s/materialsymbolsoutlined/`、`fontawesome/webfonts/fa-solid-900.woff2`、`katex/fonts/`、`iconfont`），以及**名字无法判断的哈希名字体**（防止图标变方块）。设置里的“激进模式”可选择连无法判断的字体一起拦截（仍不拦截命中图标名单的）。
* `data:` 内联字体不经过 `shouldInterceptRequest`，无法拦截。

## X（Twitter）内置浏览器结论

* X Android 的“使用内置浏览器（Use in-app browser）”开关位于：设置和隐私 → 无障碍、显示和语言 → 显示和声音（来源：<https://technastic.com/disable-in-app-browsers-android>）。
* Android 上第三方 App 的“内置浏览器”有两种实现：WebView（在 App 进程内）或 Chrome Custom Tabs（由默认浏览器，通常是 Chrome，在**浏览器进程**里渲染，见 <https://developer.android.com/develop/ui/views/layout/webapps>）。公开资料没有说明 X 用的是哪一种，这里也没有拿到 X 的 APK 做静态确认，所以按两种情况处理，并给出真机上一步就能分辨的方法：
  * **若是 Custom Tabs**：页面在 `com.android.chrome` 进程中由 Blink 渲染，网页字体请求走 Chrome 的原生网络栈（C++），**没有 Java 层的逐请求回调**可以 Hook；把 Chrome 加入作用域也只能改到 Chrome 的 Java UI，改不到网页字体。要在 Chrome 内拦截只能做原生 Hook（Blink `FontResource`/网络栈），体积和维护成本过高且随 Chrome 版本失效，本模块**不做**。替代方案：在 X 设置里关闭“使用内置浏览器”，再用一个基于系统 WebView 的浏览器（如 Via 等，加入本模块作用域）打开链接；或使用支持“禁用网页字体/自定义字体”的浏览器（如 Firefox 的 `browser.display.use_document_fonts=0`）。
  * **若是 WebView**：只要在 LSPosed 勾选 X，本模块的 WebView 拦截直接生效。
* 验证方法：勾选 X 并打开调试日志，打开一个外链文章；LSPosed 日志里若出现 `web font blocked:` 说明是 WebView 并已生效；若完全没有 `webview client hooked`/`web font blocked` 且多任务界面显示的是 Chrome 样式，即为 Custom Tabs。

## 作用域推荐

微信 `com.tencent.mm`、QQ `com.tencent.mobileqq`、小红书 `com.xingin.xhs`、X `com.twitter.android`、Claude `com.anthropic.claude`，以及 Google 系（Gmail、YouTube、Gemini `com.google.android.apps.bard`、Google App、地图、相册、翻译）。这份列表通过 `xposedscope` 声明，LSPosed 会显示为推荐项；是否勾选由用户决定。修改作用域或开关后需重启目标 App。

## 已知限制

* **自绘引擎**：Flutter（Skia/Impeller 自带字体管理）、Unity/Unreal/Cocos 等游戏引擎、React Native 的部分自定义字体管理器、以及直接用 NDK `AFont`/FreeType 的 App 不走 Android 的 Java 字体加载入口，无法替换。
* **微信/QQ**：大部分原生界面可以生效；内置网页使用腾讯 X5/XWeb 内核（不是 `android.webkit.WebView`），网页字体拦截对其无效；小程序/部分页面为自绘或 X5 渲染。
* **Chrome Custom Tabs**：见上文 X 结论，在浏览器进程渲染，本模块不处理。
* **首次加载**：名字无法判断（哈希/混淆名）的字体若在主线程加载，第一次保持原样，后台判定完成后从下一次加载（通常是下次启动）开始替换。
* **Android 9**：只按名字判定，名字无法判断的字体保持原样。
* **网页**：哈希名 Web 字体默认放行（宁可不换也不让图标变方块），可在设置中开启激进模式；`data:` 内联字体无法拦截。
* **签名**：PR 构建的 APK 用 CI 临时 debug key 签名，不同次构建之间不能覆盖安装，需要先卸载旧包。

## 开关

伴随 App（桌面图标“洛书全局字体”，也可从 LSPosed 模块设置进入）：总开关、App 内置字体、WebView 网页字体、激进模式（默认关）、调试日志（默认关）。真正生效的前提是：在 LSPosed 启用本模块并勾选目标 App。洛书主 App 未做改动。
