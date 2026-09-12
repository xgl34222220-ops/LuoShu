# PR 217 Test7：修正动态字体入口与运行期 Google 字体维护

> 4.2.0 后续：用户确认 Test7 的 K80 酷安、QQ 标签偏移仍存在，应用空字体主题后仅略有改善。
> 因此下文 Test7 的主机验证不代表该问题已在实机解决。4.2.0 的新增修正和剩余范围见文末。

用户反馈 Test6 后 K80 酷安、QQ 年龄标签仍偏移，Google 应用在使用中又恢复默认字体。
本轮继续修改实际运行路径，不把用户已有的诊断文件当作 Test6 安装后的新记录。

## K80：Test6 仅根据 init 复制推断 Overlay 来源不完整

同一份 [dali 官方 OS3.0.305.0.WONCNXM 固件](https://bigota.d.miui.com/OS3.0.305.0.WONCNXM/dali-ota_full-OS3.0.305.0.WONCNXM-user-16.0-3298197d54.zip)
的 `miui-framework.jar` 还包含后续处理：

- `SymlinkUtils.doProcessSymlink()` 在框架运行后更新
  `/data/system/fonts/theme_webview/Roboto-Regular.ttf`。主题启用时指向主题字体；
  MIUI 字体启用时指向 `MultiLangHelper.getMiproFileList()[0]`；其余情况才指向系统 Roboto。
- 简体中文 MiSans 分支指向 `/system/fonts/MiSansVF.ttf`。同时该方法切换
  `hyper_fonts.xml` / `miui_fonts.xml` 及相应 fallback XML，并重启 WebView 进程。
- ROM 的 `/system/fonts/MiSansVF_Overlay.ttf` 本身是通往上述动态入口的符号链接。

因此 Test6 把此入口固定为 Roboto 度量、并从中剔除中文，不能代表原厂框架启动后的行为。
本轮保留已验证的这一个原厂动态链接，继续通过实际 MiSans / MiSansLatin / Roboto 槽位替换字体；
最终暂存和启动补齐都不再把这个链接盖成普通字体文件。其他 ROM 中同名的普通字体仍按原有逐槽规则处理。
旧库存通过专用覆盖修订刷新，不从可变 `/data` 字体内容采集所谓原厂度量。

这纠正的是已确认的模块路由错误，不表示已经在用户的 K80 上观测到 QQ 或酷安的每个实际 Typeface。
已正常的独立时钟槽位和 ColorOS 的逐槽规则继续保留。

同一固件的 `framework.jar` 进一步确认了这种入口差异为何可能成为布局问题：
`Paint.getFontMetrics()` / `getFontMetricsInt()` 直接调用 native 度量；
`Canvas.drawText()` 经 `Paint.getNativeInstance()` 调用小米的 `checkMiuiFont()`，后者可以在绘制前
替换 native Typeface。`measureText()` 也有检查，而 `getTypeface()` 可能返回与 native 字体不同的
`mShowTypeface`。因此先取度量、再首次绘制的控件可能使用不同字体完成这两个步骤。
这证明框架存在该调用顺序差异，不等于已证明截图中的每个控件都触发；修复应消除入口不一致，
不能凭截图给全套字形添加统一位移。

上述原厂 JAR 均通过 ZIP CRC 校验：`framework.jar` 为 49,051,559 字节，SHA-256
`98f86a81d4a605e54be8ef55978bdec55e7058e357f1bd48e2ea47312636540c`；
`miui-framework.jar` 为 6,996,294 字节，SHA-256
`68558eacc85f0002375be17ba8cd0f032e527b26dc6c31924349e7e826f88247`。

## Google：原维护在开机约两分钟后停止

[Android Downloadable Fonts 文档](https://developer.android.com/develop/ui/views/text-and-emoji/downloadable-fonts)
说明字体按需经 provider 获取、缓存并通过异步回调交给应用；它不是只在开机时加载一次的系统字体。
本轮也检查了 [KillGMSFont 的实际实现](https://github.com/MrCarb0n/killgmsfont/blob/master/customize.sh)
和 [MFFM](https://github.com/mistu01/mffmv11)。它们处理字体服务和缓存，不能仅凭替换系统字体文件覆盖下载字体。

洛书原服务执行 24 次、间隔 5 秒后退出，后来的新字重、缓存文件替换和 GMS 进程重建均不会再处理。
本轮保留字体 provider，增加运行期变化检测和挂载修复。空闲时只检查文件元数据与目标进程视图，
变化时才调用字体处理；后台维护不再反复强制停止 Play。模块停用、删除或恢复默认字体后结束维护。
已看到自身替换字体时重用缓存，避免重复生成替换文件。

默认每 30 秒检测一次，稳定但挂载失败时每 5 分钟重试。每次保存处理前的状态，避免处理过程中
才出现的字体被处理后的状态快照掩盖。自身挂载可能触发一次额外幂等检查，稳定后不反复处理字体。

文件挂载修复不能改写应用已经加载到内存的 Typeface。新文件下载与应用首次读取之间仍可能发生竞争；
本轮没有冒称所有 Google 应用的私有字体、网页字体或 APK 内置字体都已覆盖，也不通过清空整个 GMS 数据来掩盖问题。

## 验证与交付

针对性回归已通过：原厂契约 22 项、CJK/动态入口 18 项、Google 生命周期 9 项、provider 字体处理 12 项、
切换/provider 6 项，以及 PID 扫描检查。动态入口测试覆盖 Test6 旧库存迁移、启动清理、普通 Overlay 文件兼容，
并通过真实 FreeType 验证原厂链接跟随不同字体时的度量。Google 测试覆盖处理期间新增字体的竞争、
缓存文件原子替换、进程视图重建、稳定时不重复处理、clone 重用和维护期间不强停 Play。

沿用 Test4 的已验证配套 APK，保持测试签名一致。完整构建与交付包哈希记录于 PR。
从 Test6 覆盖刷入并重启即可执行本轮启动迁移，后续重新应用字体也会遵守新的动态入口规则。
没有连接 K80 / 一加实机，容器也不允许创建真实 mount namespace；相关真实挂载检查明确跳过。
本地回归验证运行分支和字体文件行为，不能替代实机页面与持续使用验证。

## 4.2.0：变量组合字体与空主题反馈

继续检查同一 K80 原厂框架可确认，`TypefaceUtils.getCurrentMgr()` 在主题字体启用时选择
`ThemeFontManager`，否则可能选择 `MiProFontManager`。`checkFont()` 对已经匹配主题字体的
Typeface 提前返回；MiPro 分支则可能经过 `VFUtils.getVarFont()` 按文字大小和字重选择实例。
这说明应用空字体主题确实能改变字体选择流程。用户报告的“稍有改善”与此相容，但我们没有读取
该空主题本体或用户 App 的运行中 Typeface，不能据此断言剩余偏移只有一个原因。

本轮发现并复现了合成器的独立问题：向可变中文基底导入固定的英文、数字轮廓时，只清除了
原 glyph 的 `gvar`，却保留其 `HVAR` / `VVAR` 度量变化映射。
[OpenType HVAR 规范](https://learn.microsoft.com/en-us/typography/opentype/spec/hvar)
明确，HVAR 能独立于轮廓向字宽和边距增加字重相关增量；仅删除轮廓变化不能停止这部分变化。

合成后的静态字母在复现字体中 `hmtx=620`，选取 weight 400 时宽度为 620，weight 900 时却变成
920，额外 300 来自被替换的中文基底旧字母。4.2.0 仅取消成功导入 glyph 的 HVAR/VVAR 映射，
保留共享增量数据和未替换中文的动态字重。主引擎与实际使用的兼容引擎同步修正，并更新固定组合、
自动多字重的缓存代次，升级不再迁移这些旧合成缓存。重新应用组合时会生成修正后的字体。

回归覆盖隐式 advance 映射、多个 glyph 共享增量、水平及垂直度量映射、保存后重读，以及主/兼容
两条生成路径。真实主机 FreeType 在 weight 400/900 下确认：修复后的英文与数字都保持 620，
中文仍从 620 变为 920。该结果证明字宽/边距残留问题被修复，不能将它直接等同于 QQ 年龄标签的
垂直偏移已解决。

另外修复 HyperOS 批处理成功后遗留 `hyperos-metrics-*` 中间目录的问题。最终字体已经拥有自己的
硬链接或副本，中间文件无需随缓存和升级复制；现在成功和异常结束均清理，重复补齐不会继续累积。

K80 酷安及 QQ 标签的剩余垂直偏移仍列为已知兼容问题。未移动全套字形、未关闭 MIUI 系统优化或
布局引擎，也未替换用户已应用的主题。4.2.0 的主机回归不能代替这部分实机验证。
