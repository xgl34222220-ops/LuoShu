# 洛书 v14.3.3

洛书 v14.3.3 是 v14.3 正式版发布流程的签名验证修订，完整字体功能与双皮肤界面保持不变。

## 修复内容

- 固定签名 Release APK 已通过 `apksigner verify`，签名者证书有效。
- 当前 App 最低版本为 Android 9 / API 28，正式 APK 使用系统支持的 APK Signature Scheme v3。
- 修复发布工作流错误地只接受 v2 签名的问题。
- 发布门禁现在要求：
  - `apksigner` 验证命令成功；
  - v2、v3、v3.1 或 v3.2 中至少一个受支持方案为 `true`；
  - 签名者数量大于零；
  - 输出中存在证书 SHA-256 摘要。
- 兼容新版 `apksigner` 使用 `V3.0 Signer` 的输出格式，不再硬匹配旧版 `Signer #1` 文本。
- `v14.3`、`v14.3.1` 与 `v14.3.2` 标签保持不可变，本次使用新的 `v14.3.3 / 14325` 发布。

## 完整功能

- Material 3 Glass 与 Miuix 两套独立 Compose 界面。
- DataStore 外观持久化、MaterialKolor、Monet、三态深色和 AMOLED 纯黑。
- App 私有字体索引优先加载，轻量目录指纹仅在字体变化时重建。
- Typeface LRU、预览导出并发合并、Root 限流与开机后台预热。
- TTF、OTF、TTC/OTC 和字体模块 ZIP 安全导入。
- 真实可变字体全部 `fvar` 轴、静态多字重和中文/英文/数字复合。
- 字形覆盖诊断、系统全局粗细微调、事务提交与失败恢复。
- Full 模块内置固定签名 App并支持自动安装或更新；Lite 不内置 App。

## 安装

1. 推荐刷入 `LuoShu-v14.3.3-Full.zip`。
2. 完整重启设备。
3. Full 包会自动安装或覆盖更新正式 App；失败时可通过模块“操作”按钮重试。
4. 只需要模块字体能力、不需要 App 时使用 Lite 包。

从 Alpha Debug App 迁移到固定签名正式 App时，系统可能暂时保留两个不同包名的 App。确认正式 App正常后，可手动卸载名称带 Debug 的测试版本。

正式 Release 包含 Full、Lite、固定签名 APK，以及每个产物对应的 SHA-256 文件。
