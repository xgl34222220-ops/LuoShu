# 洛书 v14.3 Alpha1.10

## Full 模块自动安装或更新 App

本版本不增加字体功能，重点解决每次刷入 Full 模块后还需要单独安装 APK 的问题。

## 安装流程

- Full 模块继续内置 `bundled/LuoShu-App.apk`。
- 构建时新增 `bundled/app.prop`，记录内置 APK 的真实包名、版本号、版本名称与 SHA-256。
- 刷入 Full 模块时会先校验 APK 完整性，再检查当前已安装 App 的版本。
- 已安装版本与模块内置版本一致时直接跳过，不重复安装。
- 版本不一致或尚未安装时，优先在刷写阶段执行覆盖更新。
- 覆盖安装使用 `pm install -r -d --user 0`，保留 App 数据、字体缓存和 Material / Miuix 外观设置。

## 首次开机补装

- 某些 Root 管理器或刷写环境无法调用 Android 包管理器时，会写入待安装标记。
- 系统首次完整启动后，`service.sh` 会自动补装一次。
- 首次开机安装成功后清除标记，不再重复执行。
- 若签名冲突或安装失败，会停止自动重试，避免每次开机重复失败；用户可通过模块“操作”按钮手动重试。
- 安装详情记录在模块目录的 `logs/app-install.log`。

## 统一安装器

- 新增 `common/app_installer.sh`，由 `customize.sh`、`service.sh` 与 `action.sh` 共用。
- 支持当前版本跳过、旧版本覆盖更新、无 `pm` 延迟安装、签名失败记录与 APK SHA-256 校验。
- 新增 Shell 回归测试覆盖以上路径。

## Lite 包

- Lite 模块继续不内置 App，也不会尝试安装 App。
- 需要自动更新 App 时应使用 Full 模块。

## 保持不变

- Material 3 Glass / Miuix 双皮肤架构与外观设置。
- 真实可变字体全部 `fvar` 轴预览和最终提交。
- 静态多字重真实源文件切换。
- 同字体标准 Regular 400 直接应用。
- 系统全局粗细微调。
- 中文、英文、数字与标点覆盖诊断。
- TTF、OTF、TTC 和字体模块 ZIP 安全导入。

本版本继续作为 Draft PR 真机测试版本，不合并、不发布。
