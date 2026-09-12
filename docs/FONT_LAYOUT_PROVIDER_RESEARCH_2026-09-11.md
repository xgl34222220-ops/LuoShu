# HyperOS 布局与 Google 字体覆盖复查（PR 217 Test3）

## 结论与证据边界

前两轮的 hhea/OS2 对齐、复合英数基线修正没有覆盖 Android 的全部布局路径。
Test3 补上可由源码和实际字体文件复现的缺口；没有 K80 至尊版或一加 15 的连接设备，
不能把主机测试通过写成这些设备的界面问题已经全部解决。

用户反馈的状态栏、QQ 回复和年龄标签上偏与布局度量差异相符，但尚未取得对应
控件的运行时 FontMetrics、实际字体槽位及用户字体，因此不能认定所有页面只有同一个原因。

## Android 的两组纵向度量

Android 16 的 [Skia FreeType 后端](https://android.googlesource.com/platform/external/skia/+/refs/tags/android-16.0.0_r1/src/ports/SkFontHost_FreeType.cpp)
分别读取：

- ascent/descent/leading：OS/2 的 USE_TYPO_METRICS 决定是否采用 typo 度量，否则使用 FreeType 的行度量。
- top/bottom：读取 face bbox。SFNT 字体，包括通常的 TTF 和 OTF，bbox 由 head 表提供。

[FreeType SFNT 读取代码](https://github.com/freetype/freetype/blob/master/src/sfnt/sfobjs.c)
与 [Android 16 BoringLayout](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-16.0.0_r1/core/java/android/text/BoringLayout.java)
可对应验证：includePad 的高度使用 bottom-top，padding 还取决于 top-ascent。
[StaticLayout](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-16.0.0_r1/core/java/android/text/StaticLayout.java)
的首末行也区分这些值。因此，仅压缩 OS/2 Win 字段或重新计算复合字体的真实字形外框，
不能保证原厂控件的行框、留白和垂直居中保持一致。

公开实现提供了两个可核实的方案：

- [霞鹜的高级字体模板](https://github.com/lxgw/advanced-cjk-font-magisk-module-template/blob/main/system/etc/fonts.xml)
  使用 Roboto EmptyFont 提供度量，再通过 fallback 绘制用户字体。其 README 明确说明了度量壳用途。
- [MFFM 的 port_android_metrics](https://github.com/mistu01/mffmv11/blob/e50d6a80020cec3d987a2cfddddf997ac76d68d7/compile.py)
  同时设置 hhea、OS/2 和 head 的上下边界。其固定数值不能作为 K80 的实机标定值。

Test3 在 HyperOS 最终生成阶段采用本机、同分区、同槽位的原厂 head.yMin/yMax，按 UPEM 比例
写入隔离的待启动字体。上下边界也加入缓存键，避免 Clock 与正文仅因行度量相同就错误共享输出。
不逐槽重编 CJK 轮廓；glyf/CFF/gvar 保持原始内容，保留前两轮的性能改进。

这是特定 ROM 的 UI 度量兼容处理，不是重新计算真实字形包围盒。用户原始文件及通用复合结果
不被改写；最终槽位 head 可以小于某些极端字形的真实范围。此类字形在严格裁切控件中的表现仍需
实测。旧清单没有可信 head 时保留旧行度量和来源边界，不捏造原厂数值。

诊断文件 `.luoshu-metrics-report.json` 新增 sourceHead、outputHead、sourceUpem、
layoutBoundsSource 和 layoutBoundsDifferFromSource，可判断是否真正使用了原厂布局边界。

扫描器同时修正合法零下伸被拒绝的问题，并记录原厂 head。零下伸合法不等于用户 K80
原厂时钟一定是零下伸。升级安装会在自挂载前重扫；新增 metricsRevision 使旧清单可自动迁移，
没有可信原厂视图或扫描失败则保留原有清单，并继续保留待扫描状态。

## Google 英文、数字保持默认

中文回落到系统字体，并不意味着 Google 的西文来自同一个字体文件。
Google 应用可能通过字体 Provider 取得独立下载字体；Android 的
[Downloadable Fonts 文档](https://developer.android.com/develop/ui/views/text-and-emoji/downloadable-fonts)
说明了这种由 Provider 提供字体文件的机制。

洛书的旧代码有两个可复现问题：

1. 目标带 fvar、用户源不带 fvar 时主动拒绝生成。组合后的用户字体常为静态字体，因而可能一直被跳过。
   [Skia 的 variation API](https://api.skia.org/structSkFontArguments.html)
   明确允许忽略字体不存在的轴。Test3 保留合法静态输出，不伪造变量轴及轮廓表；变量源适配静态目标时
   固定所有轴，wght 采用目标请求值，其余轴采用源默认值。
2. 只按 Google Sans 文件名查找，漏过数字、哈希及无后缀缓存。Test3 在已知字体缓存目录内按
   文件头和 name 表的精确 family 白名单识别，排除 Google Sans Code、无关字体、损坏文件和暂不支持的 TTC。

服务保留有界开机发现窗口，首次命中后仍检查后续下载的字体；重复挂载按内容识别，避免反复挂载及
无意义重启 Play。诊断继续区分未发现、缺源、生成失败与命名空间挂载失败。

没有默认禁用 GMS 字体组件，也没有删除其字体数据。应用在 APK 内嵌的字体、WebView 网页字体，
以及启动窗口结束后才下载的缓存，仍不由此次 Provider 修复保证覆盖。已经缓存 Typeface 的应用
可能需要重新打开，实际效果还取决于 root 管理器的命名空间可见性。

## 验证与测试方法

回归测试覆盖同一源字体的不同分区/槽位边界、UPEM 比例、无 head 旧清单、零/浅下伸、缓存不串槽、
原厂扫描迁移，以及 Google 变量/静态组合和不透明缓存文件名。额外通过主机 FreeType 检查字体
实际加载后的布局边界和字形数据；这些检查不能替代 Android 真机运行。

Test3 模块应覆盖刷入并重启，然后在洛书重新生成/应用原来的字体或组合，按提示再次重启。
只刷模块而不重新应用，会继续使用之前已经生成的字体负载，无法验证本次槽位修复。
优先复查状态栏时钟、QQ 回复/年龄标签及 Google 应用同一页面的中文、英文和数字。

独立 APK 未修改，复用已验证的 PR 217 debug APK；测试包不会合并主分支或创建正式 Release。
