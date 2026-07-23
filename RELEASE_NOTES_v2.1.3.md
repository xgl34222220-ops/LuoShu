<!-- prerelease -->
# LuoShu v2.1.3

## 修复

- 修复 Android 12+、ColorOS 及其他启用可更新字体服务的系统中，Play 商店搜索框、Gmail 等 Google 应用继续使用 `/data/fonts/files` 内置 Google Sans、绕过洛书字体的问题。
- 洛书会在启动早期识别动态字体配置，只隔离 `google-sans`、`google-sans-text`、`google-sans-flex`、`product-sans` 及其 Medium/Bold 命名字体族，再将这些名字按 400/500/700 字重指向当前洛书字体。
- 不覆盖或删除 `/data/fonts/files` 中由系统签名及 fs-verity 管理的字体文件；动态 Emoji、图标字体和其他下载字体保持原样。
- 切换字体后无需运行任何外置脚本，完整重启即自动应用；切回系统默认字体或卸载洛书时自动解除配置覆盖。
- 自动恢复旧实验版本可能留下的 `.luoshu-bak` 动态字体缓存副本。

## 重点验证

- ColorOS Android 16 / API 36，运行时 `google-sans*` 原本来自 `/data/fonts/files` 的设备。
- 重启后检查 Play 商店搜索框的英文和数字是否跟随当前洛书字体。
- 检查动态 NotoColorEmoji 与其他非 Google Sans 字体仍由系统正常加载。
- 检查切回默认字体并重启后，动态字体配置完整恢复。

> 本版修复依据 ColorOS 真机字体配置和 `dumpsys font` 链路完成；发布前已完成脚本语法、XML 过滤、命名字体注入和安全恢复测试，最终视觉效果仍以不同 ROM 真机验证为准。
