# 更新日志

本文件记录洛书的重要功能变化。正式发布版本以 GitHub Releases 中的标签、构建产物和 SHA-256 为准。

## [Unreleased]

- 暂无。

## [v14.3.1] - 2026-07-19

- 修复正式签名发布工作流错误调用不存在的 `testReleaseUnitTest`，改为执行项目实际存在并由日常 CI 使用的 `testDebugUnitTest`。
- 保留 `lintRelease`、固定签名 `assembleRelease`、APK 证书校验、Full/Lite 成品校验与不可变 GitHub Release 门禁。
- 功能代码与 v14.3 保持一致；版本号提升至 14323，使用新的不可变 `v14.3.1` 标签发布。

## [v14.3] - 2026-07-19

- 发布 Material 3 Glass 与 Miuix 双皮肤原生 App，所有核心页面、设置和操作弹层均拥有独立实现。
- 新增 DataStore 外观持久化、MaterialKolor 种子色、Monet、柔和/鲜艳/中性色板、三态深色与 AMOLED 纯黑。
- 原生 App 新增持久字体索引，启动后优先读取本地数据，进入字体库不再等待 Root 全量扫描。
- 新增轻量字体目录指纹；目录未变化时跳过字体解析，仅在新增、修改、删除、导入或主动刷新时重建索引。
- 开机服务根据指纹后台预热模块字体 JSON；后台刷新失败不会清空已经显示的字体列表。
- 字体预览增加 Typeface LRU、同字体导出并发去重、Root 导出限流与更大的持久缓存。
- 支持 TTF、OTF、TTC/OTC 和字体模块 ZIP 安全导入；TTC/OTC 会拆分全部字体面并生成稳定身份。
- 支持真实可变字体全部 `fvar` 轴预览与最终实例化，支持静态多字重真实源文件切换。
- 支持中文、英文和数字三槽复合字体、独立设计轴与字形覆盖诊断。
- 支持系统全局粗细微调，并保留 ROM fallback、符号字体、彩色字体和 monospace。
- Full 模块内置固定签名 App，支持刷写阶段自动覆盖更新及首次开机补装；Lite 不内置 App。
- 字体切换和复合生成继续使用后台任务、锁、事务提交、进度恢复和失败回滚。

### v14.3 Alpha1.11

- 完成字体库本地索引、轻量指纹、开机预热和预览缓存性能重构。

### v14.3 Alpha1.10

- Full 模块内置 App 支持自动覆盖更新、版本一致跳过与首次开机补装。

### v14.3 Alpha1.9

- 运行入口收敛为正式 `LuoShuAppShell`，清理旧 UI；确认框、选择器、详情和导入浮层完成双皮肤。

### v14.3 Alpha1.8

- 字体库、字体组合和运行日志完成独立 Material / Miuix 页面实现。

### v14.3 Alpha1.7

- 建立 Material 3 Glass / Miuix 双皮肤架构和完整外观设置。

### v14.3 Alpha1.6

- Miuix 页面统一使用白泽视觉系统、大标题、超椭圆卡片和液态悬浮导航。

### v14.3 Alpha1.5

- 区分字体原始默认、Android Regular 400 与当前设计轴，并加入系统全局粗细微调和覆盖诊断。

### v14.3 Alpha1.4

- Android 原生预览接入真实可变字体多轴参数和静态多字重文件。

### v14.3 Alpha1.3

- 多字重优先读取字体内部 `OS/2.usWeightClass`，完善内部 Family、Italic、Variable 归类及 200/800 支持。
