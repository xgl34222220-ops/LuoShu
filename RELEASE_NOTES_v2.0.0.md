# 洛书 v2.0.0

洛书 v2.0.0 是一次完整架构重构：从应用运行时 Hook 改为开机前完成的 Android 系统字体配置与字体文件覆盖。

## 核心变化

- **完全移除运行时字体 Hook**：不再拦截 Xposed、TextView、Canvas、Typeface 或应用字体工厂，避免逐帧处理、掉帧、数字裁切及对时钟响铃链路的干扰。
- **系统级无 Hook 全局字体**：读取设备原始 `fonts.xml`、`font_fallback.xml` 和 OEM customization XML，保留原 family、alias、locale 与 fallback 顺序，只重写明确安全的 UI 字体家族。
- **多 ROM 支持**：统一覆盖 HyperOS、ColorOS 和通用 AOSP 的真实字体文件槽与配置入口。
- **真实九档字重**：生成 100–900 静态字重，并规范字体 Family、Full Name、PostScript Name 与 `OS/2.usWeightClass`。
- **安全保护**：Emoji、Symbol、Material 图标、monospace、serif、数学字体、二维码字体和专用时钟字体默认保持原样。
- **事务与开机回退**：XML 和字体引用全部验证后才原子启用；开机发现损坏、缺失或分区别名异常时自动撤销 XML，继续使用文件槽兼容映射。
- **高刷新率**：App 在前台、获得焦点和显示模式变化时持续申请当前分辨率支持的最高刷新率，后台、失焦和画中画时自动释放。
- **模块减重**：移除字体引擎不使用的 SSL、SQLite、网络、调试和 CPython 测试运行时，保留 FontTools、变量轴、复合字体、真实字重与完整离线能力。模块体积由约 15.7 MB 降至约 11.2 MB。

## 保留能力

- TTF、OTF、TTC/OTC 与字体模块 ZIP 导入；
- 中文、英文、数字三槽复合字体；
- 可变字体 `fvar` 轴实例化；
- 静态多字重字体族；
- 字体预览、后台任务、断点恢复和任务中心；
- Material 3 Glass 与 Miuix 双界面。

## 兼容边界

无 Hook 引擎覆盖所有正常使用 Android system font map 的系统界面和应用。应用若把字体直接打包在 APK 的 `assets` 或 `res/font` 中并自行加载，该私有字体不会被系统字体映射强制替换。v2.0.0 不再用高频 Hook 追补这类应用，以优先保证系统稳定性、流畅度和闹钟等关键功能。

## 安装与升级

- 可直接覆盖刷入旧版洛书；
- 完整重启后进入洛书 App 重新应用一次字体；
- 从旧 Hook 测试版升级时，无需保留 Vector/LSPosed 作用域；
- 恢复系统默认字体会同时清理生成的字体 XML、字重文件和分区别名。

## 验证

正式提交通过：

- Font engine smoke tests；
- No-Hook font engine tests；
- Embedded runtime size tests；
- App display performance tests；
- App-only 源码门禁、Android Lint、单元测试与 Release APK 构建；
- 模块 ZIP 完整性、内置 APK 一致性和 SHA-256 校验；
- 固定签名 APK 证书验证。
