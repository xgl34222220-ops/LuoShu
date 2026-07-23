<!-- prerelease -->
# LuoShu v2.1.3

## 修复

- 修复 Android 12+、ColorOS 及其他启用可更新字体服务的系统中，Play 商店搜索框、Gmail 等应用继续使用 `/data/fonts/files` 内置 Google Sans、绕过洛书字体的问题。
- 修复逻辑已直接集成洛书模块，不需要用户运行任何外置脚本。
- 洛书会在 `post-fs-data` 阶段、FontManagerService 建立共享字体表之前处理真实动态字体配置。
- 保留 `/data/fonts/files` 中的系统签名字体、fs-verity、动态 Emoji、其他字体和全部 `updatedFontDir`，只隔离 `google-sans*` 与 `product-sans*` 命名字体族。
- 将 Google Sans Regular、Text、Flex、Display、Medium、Bold 等名称按 400/500/700 字重指向当前洛书字体。
- 切回系统默认字体或卸载洛书时自动解除配置桥，重启后恢复系统原始字体表。

## 验证依据

- ColorOS 16.1 / Android 16 真机诊断确认，系统分区的 `GoogleSans*.ttf` 已经是洛书字体，但运行时 `google-sans*` 仍指向 `/data/fonts/files`。
- AOSP FontManagerService 会在启动时读取 `/data/fonts/config/config.xml`，并将后加载的同名 family 覆盖系统 family；因此后置复制字体文件和强停 Play 商店不会重建字体表。
- 已完成 Shell 语法、PersistentSystemFontConfig 结构过滤、`updatedFontDir` 保留、Emoji family 保留和系统命名字体注入测试。

> 安装或切换字体后需要完整重启。验收标准是重启后的 `dumpsys font` 中 `google-sans*` 不再指向 `/data/fonts/files`。
