# 洛书 v2.3.0

v2.3.0 将洛书从“适配不同元模块”改为**完全独立的私有自挂载架构**。这是一次挂载层重构，重点解决 Mountify、Hybrid Mount、Magic Mount 等外部挂载组件与洛书重复接管时可能出现的二屏卡死、探针误判和字体事务回滚问题。

## 主要变化

- 真实字体负载迁移到 `.luoshu-payload/<partition>` 私有目录。
- 标准 `system`、`system_ext`、`product`、`my_product`、`vendor` 模块目录只保留空壳。
- 洛书不再检测、配置、同步或依赖任何元模块。
- 不需要把洛书加入 Mountify、Hybrid Mount、Magic Mount 或其他组件白名单。
- KernelSU / SukiSU Ultra 在 `post-mount` 阶段由洛书自行挂载。
- Magisk / APatch 在 `post-fs-data` 阶段由洛书自行挂载。
- 自挂载只覆盖洛书实际使用的字体与配置目录，保留 ROM 原厂 Emoji、图标、衬线、斜体与 fallback。
- 重复执行不会叠加第二层挂载；挂载失败保持 fail-open，不阻断系统启动。
- 卸载时逆序解除洛书记录的挂载，并清理私有负载和自挂载状态。

## 刷入说明

1. 下载 `LuoShu-v2.3.0.zip` 和同名 SHA-256 文件。
2. 直接通过 Magisk、KernelSU、SukiSU Ultra 或 APatch 刷入。
3. 不需要安装或配置任何元模块。
4. 完整重启设备。
5. 进入洛书 App 应用字体；任务完成后再次完整重启。

覆盖旧版安装时会迁移当前字体配置。若旧负载架构需要重建，刷入日志会明确提示首次开机后台重建，并在完成后通知再次重启。

## 验证范围

本版本已经通过：

- Shell 与 Python 语法检查；
- 私有负载迁移和标准目录空壳验证；
- 自挂载字体覆盖、ROM Emoji 保留和重复执行回归；
- 覆盖安装、升级状态迁移和卸载清理；
- 设备字体可信度、字体事务、缓存与任务恢复测试；
- Android App Lint、单元测试与正式签名构建；
- 模块 ZIP 完整性、SHA-256 和内置 App 一致性检查。

## 版本信息

- 模块版本：`v2.3.0`
- 模块 versionCode：`20300`
- App versionName：`2.3.0`
- App versionCode：`2030001`

正式发布包含模块 ZIP、模块 SHA-256、独立 APK 和 APK SHA-256。请只从本仓库 GitHub Releases 下载正式文件。
