# 洛书 v14.3.1

洛书 v14.3.1 是 v14.3 正式版的发布流程修订版，功能代码与 v14.3 保持一致。

## 修复内容

- 修复正式签名发布工作流错误调用不存在的 `testReleaseUnitTest`。
- 正式发布改为运行项目实际存在、并已由日常验证工作流持续使用的 `testDebugUnitTest`。
- 继续强制执行 `lintRelease`、固定签名 `assembleRelease`、APK 证书校验、Full/Lite 包结构和 SHA-256 校验。
- 已存在的 `v14.3` 标签保持不可变，本次使用新的 `v14.3.1` 标签和版本号 14323。

## v14.3 完整功能

- Material 3 Glass 与 Miuix 两套独立 Compose 界面。
- DataStore 外观持久化、MaterialKolor、Monet、三态深色与 AMOLED 纯黑。
- App 私有字体索引优先加载，轻量目录指纹只在字体发生变化时重建。
- Typeface LRU、预览导出并发合并、Root 限流和开机后台预热。
- TTF、OTF、TTC/OTC 和字体模块 ZIP 安全导入。
- 真实可变字体全部 `fvar` 轴、静态多字重和中文/英文/数字复合。
- 字形覆盖诊断、系统全局粗细微调以及事务提交和失败恢复。
- Full 模块内置固定签名 App并支持自动安装或更新；Lite 不内置 App。

## 安装说明

1. 推荐刷入 `LuoShu-v14.3.1-Full.zip`。
2. 完整重启设备。
3. Full 包会自动安装或更新正式 App；自动安装失败时可使用模块“操作”按钮重试。
4. 只使用模块功能、不需要 App 时可刷入 Lite 包。

从 Alpha Debug App 迁移到固定签名正式 App时，系统中可能暂时同时保留 Debug 与正式 App。确认正式 App正常后可手动卸载名称带 Debug 的测试版本。

正式发布包含 Full、Lite、固定签名 APK 以及每个文件对应的 SHA-256。
