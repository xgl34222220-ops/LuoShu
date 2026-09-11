# PR 217 Test4：状态栏改善后的剩余问题

## 已收到的实机反馈

Test3 后，用户确认 K80 至尊版状态栏时钟正常；酷安标题与热度、QQ 回复输入及年龄标签仍存在位置问题。
一加 15 的万能遥控在温度数字下方仍裁切说明文字。K80 时钟其余界面已替换，但秒表大数字保持默认。
这些是用户提供的效果反馈，不等于已经测得对应控件实际使用的 Typeface 或 FontMetrics。

## 本轮修改

### ColorOS 实际运行路径遗漏

普通切换和组合实际使用 `legacy_v14_4` 引擎。它的 `_font_anchor` 直接复制源字体；
主目录虽然有 normalizer，兼容引擎没有调用它。此前最终校准阶段只为 HyperOS 执行，
所以改动主目录 normalizer 不会修正一加这条真实路径。

新增 ColorOS 最终处理阶段，普通切换和组合在提交前都调用。仅处理已经生成的字体槽位，
逐槽使用本机原厂清单中的行度量和上下边界；保留每个文件实际选定的字重，不扩大覆盖范围。
全部输出先生成，再替换暂存文件。缺少原厂数据、过期清单或 TTC 多字体集合会保留来源并记录原因。
HyperOS 不会再执行 ColorOS 的处理。

### HyperOS 的 CJK 字符覆盖与回退

公开 HyperOS 3 rodin 样本中，默认 sans-serif 指向 `Roboto-Regular.ttf`。该文件包含完整 ASCII、
不包含汉字，并不是空字体。其原始文件及 XML 可复核：

- [Roboto 文件](https://github.com/Klozz/xiaomi_rodin_dump/blob/missi-user-16-BP2A.250605.031.A3-OS3.0.300.0.WOJMIXM-release-keys/system/system/fonts/Roboto-Regular.ttf)
- [font_fallback.xml](https://github.com/Klozz/xiaomi_rodin_dump/blob/missi-user-16-BP2A.250605.031.A3-OS3.0.300.0.WOJMIXM-release-keys/system/system/etc/font_fallback.xml)

[Android 16 Minikin](https://android.googlesource.com/platform/frameworks/minikin/+/refs/tags/android-16.0.0_r1/libs/minikin/FontCollection.cpp)
优先选择已经包含当前字符的首个字体家族。把完整 CJK 字体放进原厂西文槽，会让汉字直接命中
主字体，改变原来的 CJK 回退路径。按主字体测量和按实际文字测量也有区别，参见
[Paint.getFontMetrics](https://developer.android.com/reference/android/graphics/Paint#getFontMetrics(android.graphics.Paint.FontMetrics))。

本轮记录可信原厂字符覆盖，在仍有相应 CJK 字体可用的条件下，恢复原厂西文槽与中文回退的分工。
只调整字符映射；保留 Test3 已有效的行度量、上下边界和字形数据。旧清单缺少字符覆盖信息时保持原行为，
等待可信原厂重扫。时钟、等宽和符号槽不参与这一处理。
回退证明使用首选 Unicode cmap，避免其他 cmap 有字、实际渲染却取不到的情况；
没有证明回退字体具有相同异体字时，保留原有 UVS 记录及对应普通字符映射。

这修正的是可证实的字体选择路径差异。公开 rodin 固件不是用户的 K80 固件，不能据此认定
QQ、酷安的所有剩余偏移已经找到唯一原因。QQ 的具体 Span 绘制仍需实机数据。

### 秒表的独立字体来源

只读分析公开小米时钟 13.56.0（包名 `com.android.deskclock`，版本号 130205600）后发现：
`StopwatchChronometer.onFinishInflate()` 为大数字设置 `fonts/MitypeMono-DemiBold.otf`，
`TypefaceFactory.get()` 再通过 `Typeface.createFromAsset()` 从应用 assets 读取。

[原始 APK，固定提交](https://github.com/RandomPush/android_earth_dump/blob/1ae98d2fc740d94b2a61864245ea440e6672cd89/system/system/data-app/MIUIDeskClockCnUninstall/MIUIDeskClockCnUninstall.apk)
的 SHA-256 为 `f71a9ff814a3a341b8b617146c89457dfd7a00290e4685e6dfa46046ebfd6d60`。
[Android API](https://developer.android.com/reference/android/graphics/Typeface#createFromAsset(android.content.res.AssetManager,%20java.lang.String))
说明了这条独立的 AssetManager 加载路径。

系统目录中的 MiClock/Mitype 覆盖无法替换 APK 里的该资源。本轮不修改、重签或覆盖系统时钟 APK，
不把秒表标成已修复。上述样本较旧，需要核对用户当前版本是否仍采用相同调用。

### 可直接导出的字体诊断

App 原有“生成脱敏诊断报告”按钮增加字体诊断段。报告区分可信原厂清单、当前启动负载和采集进程可见字体，
采集有限的中文、英文和数字字形边界，并列出相关应用的字体资源候选。
不导出完整字体、聊天内容、账号信息或设备标识；数据缺失及超时会明确记录。

报告只能提供候选路径和字体数值，不声称已经观察到第三方应用实际选中的 Typeface。
用户复现后可直接发送 `/sdcard/LuoShu/reports/LuoShu-diagnostic-summary.txt`，便于区分
映射未命中、回退差异和源字形相对基线的差异。

## 测试与设备确认

主机回归覆盖 ColorOS 普通/组合入口、跨分区度量与字重、原始字形表保留、HyperOS 中文回退及诊断数据真实性。
完整 App-only 源码门禁通过。ColorOS 13 项、HyperOS 原有批处理 13 项、新增路由 15 项、
原厂度量契约 11 项、字体诊断 10 项及 FreeType 布局 5 项通过。
Android APK 需要通过 CI 的 lint、单元测试和编译，再与对应模块一起提供。

设备测试需覆盖刷入模块、更新配套测试 App 并重启，然后重新应用当前字体/组合，按提示重启。
保持“默认卸载模块”关闭。重点复查一加万能遥控说明文字、K80 酷安和 QQ；状态栏作为已通过的回归项。
秒表字体来源仍需当前 APK/诊断确认，暂不承诺替换效果。
