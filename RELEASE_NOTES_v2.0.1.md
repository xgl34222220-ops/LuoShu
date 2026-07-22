# 洛书 v2.0.1

本版本修复 v2.0.0 真机回归中最严重的字体切换与全局一致性问题。

- 字体负载失败只隔离生成文件，不再写入 Root 管理器的 `disable`；旧版本自建标记可在用户主动重试时恢复。
- 恢复系统默认字体不再被 `disable`、`skip_mount` 或其他模块忽略标记阻断。
- Magic Mount RC/RS 会保留原配置，并自动补齐洛书负载实际使用的 `product`、`system_ext`、`my_product` 等分区。
- HyperOS 除 MiSans 与数字字重槽外，也按真实分区覆盖直立的 GoogleSans、GoogleSansText 与 Roboto UI 槽。
- 直接字体、可变字体实例、静态多字重、复合字体和 Mono 派生字体统一使用固定 em 比例的 hhea/OS/2 度量。
- 中文、英文、数字继续通过全局覆盖门禁；复合字体按中文基底校准英文和数字字形高度及基线。
- Material 与 MIUIx 字体库继续使用共享中英数字预览源，不再出现“天地玄黄 · Hello”旧分支。
- 版本提升至 `v2.0.1 / 20001`，正式 App `versionCode` 为 `2000101`，避免旧 App 被误认为最新版。

Emoji、图标、衬线、斜体及专用时钟字体保持 ROM 原样。应用若将字体直接打包在 APK 内并自行加载，仍不受 Android 系统字体映射控制。
