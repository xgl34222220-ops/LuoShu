# 洛书 v2.4.0 正式版

v2.4.0 集中修复“同一系统内部分界面仍使用默认字体”和“字体已经生效却被误判失败”两类问题，同时保持 v2.3.8/v2.3.9 正式版 App UI 不变。

## 主要更新

- 修复已成功挂载的字体因文件路径、inode 或视图差异而被错误判定为失败，并避免误触发恢复默认字体。
- 重做 Android 系统、OEM、中文与英文 fallback 字体槽位覆盖，补齐 `variant=elegant/compact`、`zh-Hans`、`zh-Hant` 等入口。
- 生成字体保留目标 ROM 的 Family、PostScript 与 name table 身份，降低系统组件和第三方应用按内部名称加载时回退原厂字体的概率。
- 继续保留 Emoji、图标、数学、音乐及源字体不支持脚本的系统 fallback，避免方框乱码。
- 补齐 Play 商店与 GMS 直接读取下载版 Google Sans 的独立字体链路。
- 扫描 GMS、Play 和 Android 字体更新缓存中的实际 Google Sans 文件，按目标字重生成身份兼容副本。
- 在 zygote、Google Play 服务和 Play 商店各自的挂载命名空间中执行只读 bind，覆盖 HyperOS 与 ColorOS 的多用户目录差异。
- 不删除、不改写 Google 或 Android 字体提供器的原始缓存文件。

## 安装说明

直接在 Magisk、KernelSU 或 APatch 管理器中覆盖刷入并完整重启。升级后请在洛书中重新应用一次当前字体，再完整重启一次，以重新生成 v2.4.0 字体负载。

<!-- v2.4.0 explicit stable release trigger -->
