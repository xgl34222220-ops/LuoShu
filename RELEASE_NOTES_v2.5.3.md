# 洛书 v2.5.3

本次正式版集中修正 v2.5.2 录屏复查发现的 UI 一致性问题，不改变字体引擎、provider bridge、事务回滚或字体组合算法。

## UI 一致性
- 新增统一图标视觉规格：Header 48dp 点击区 / 22dp glyph、Bottom Dock 20dp、Section 18dp、Tool 20dp、Status 22dp、Trailing 18dp。
- Bottom Dock 取消 selected 21dp / unselected 19dp 的尺寸动画，选中态只改变颜色和指示器，不再让图标忽大忽小。
- 首页、字体库、字体组合、任务中心的 Header Action 统一尺寸与 Loading 外接尺寸。
- 设置分类、字体库管理入口、组合工具、诊断/任务状态图标统一视觉槽，并对不同 vector 做轻量 optical scale 补偿。
- 修正实际路由页面：HomeScreenCompact、FontLibraryScreenCompact、FontStudioScreenMiuix、LogsScreenCompact；不再只调整备用 Screen。
- Home / Library / Studio / Logs 统一由 App Shell 预留悬浮底栏安全空间，减少内容被底栏压住。

## 验证
- scripts/check.sh
- Android lintDebug
- Android testDebugUnitTest
- Android assembleDebug
- 正式发布链会再次执行完整源码/模块检查、Release Lint、单元测试、正式签名 APK 与发布就绪门禁。

## 真机状态
ColorOS 16、HyperOS 3、Magisk、APatch 真机矩阵仍保持 pending；本次稳定版由维护者明确授权放行，不伪造真机 PASS。
