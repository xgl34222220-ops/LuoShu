# 洛书 v2.3.12

## 修复重点

- 修复 Play 商店搜索框、输入框及部分 GMS 页面绕过系统 `fonts.xml`，继续直接使用下载版 Google Sans 的问题。
- 恢复 HyperOS 旧版本能够覆盖的 Play 输入框字体入口。
- 补充 ColorOS 下 `/data/data`、`/data/user/*`、`/data/user_de/*` 以及 `/data/fonts/files` 的 Google 字体扫描。
- 为每个目标字重生成保留原 Google Sans Family/PostScript 身份的字体副本。
- 在 zygote、Google Play 服务和 Play 商店各自的挂载命名空间中执行只读 bind。
- 不删除、不修改 GMS 或 Android 字体提供器的原始缓存文件。
- 继续包含 v2.3.10 的验证误报修复和 v2.3.11 的系统/OEM/fallback 槽位修复。

## 测试说明

覆盖刷入并完整重启后，重新应用一次当前字体。重点检查 Play 商店搜索框、应用详情页输入区域，以及系统设置和普通第三方应用是否保持同一字体。
