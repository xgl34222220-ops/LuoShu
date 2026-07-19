# 洛书 v14.3.2

洛书 v14.3.2 是 v14.3 正式版的发布修订版本，完整字体功能与双皮肤界面保持不变。

## 修复内容

- 修复主题层通过 `LocalContext.current.getColor()` 读取 Android 系统 Monet 色值的问题。
- 改为使用 Compose 的 `LocalResources.current` 查询系统强调色，使配置变化能够触发正确更新，避免主题可能继续使用旧色值。
- 正式发布门禁已分别验证 `lintRelease`、`testDebugUnitTest` 与 `assembleRelease` 全部通过。
- 保留固定签名、APK v2 证书校验、Full 内嵌 APK、Lite 不含 APK及全部 SHA-256 校验。
- `v14.3` 与 `v14.3.1` 标签保持不可变，本次使用新的 `v14.3.2 / 14324` 发布。

## 完整功能

- Material 3 Glass 与 Miuix 两套独立 Compose 界面。
- DataStore 外观持久化、MaterialKolor、Monet、三态深色和 AMOLED 纯黑。
- App 私有字体索引优先加载，轻量目录指纹仅在字体变化时重建。
- Typeface LRU、预览导出并发合并、Root 限流与开机后台预热。
- TTF、OTF、TTC/OTC 和字体模块 ZIP 安全导入。
- 真实可变字体全部 `fvar` 轴、静态多字重和中文/英文/数字复合。
- 字形覆盖诊断、系统全局粗细微调、事务提交和失败恢复。
- Full 模块内置固定签名 App并支持自动安装或更新；Lite 不内置 App。

## 安装

1. 推荐刷入 `LuoShu-v14.3.2-Full.zip`。
2. 完整重启设备。
3. Full 包会自动安装或覆盖更新正式 App；失败时可通过模块“操作”按钮重试。
4. 只需要模块字体能力、不需要 App 时使用 Lite 包。

从 Alpha Debug App 迁移到固定签名正式 App时，系统可能暂时保留两个不同包名的 App。确认正式 App正常后，可手动卸载名称带 Debug 的测试版本。

正式 Release 包含 Full、Lite、固定签名 APK，以及每个产物对应的 SHA-256 文件。
