洛书 · LuoShu

Android 全局字体替换与复合引擎。
适用于 Magisk、KernelSU、SukiSU Ultra 与 APatch。

当前公开系列从「重构版 1.0.0」开始。
后续正式版本：1.1.1 → 2.0.0 → 2.2.2 → 3.0.0 → 3.3.3……

项目主页：
https://github.com/xgl34222220-ops/LuoShu

最新正式版：
https://github.com/xgl34222220-ops/LuoShu/releases/latest

完整使用教程：
https://github.com/xgl34222220-ops/LuoShu/blob/main/docs/USER_GUIDE.md

核心功能：
- 中文、英文、数字字体可以分别选择
- 中文作为完整基底，英数按目标字符生成复合字体
- 自动扫描本机字体目录、字体配置、字重、TTC face 与字体度量
- 针对 HyperOS、ColorOS 等 OEM 字体路由提供额外适配
- 私有 systemless 挂载，不要求额外安装 Mountify 等元模块
- 相同组合复用已验证缓存，减少重复生成
- 新字体验证成功后才提交，失败保留上一套可用负载
- 原生 Android App，模块内置 App 与独立 APK 使用同一正式签名

快速使用：
1. 从 Latest Release 下载模块 ZIP
2. Root 管理器中的“默认卸载模块”必须关闭
3. 刷入模块并完整重启
4. 安装内置 App 或 Release 中的独立 APK
5. 导入字体，选择中文、英文、数字字体
6. 应用字体并按提示再次完整重启

Google 字体兼容：
设置 → Google 字体兼容

当 Google 商店等应用的中文已经替换，但英文数字反复恢复默认时，可进入该页面：
- “重新检测”只读取状态
- “开启 Google 字体兼容”停用当前 Android 用户的 GMS FontsProvider
- “恢复原设置”按洛书记录恢复原状态

该功能默认关闭，不停用整个 Google Play 服务，不删除账户、App 数据或字体缓存。
它会影响当前用户所有依赖 GMS 下载字体的应用，不只影响 Google 商店。
停用或卸载洛书前，请先恢复原设置并完整重启。

用户目录：
- /sdcard/LuoShu/fonts/    用户字体
- /sdcard/LuoShu/import/   待导入字体模块 ZIP
- /sdcard/LuoShu/reports/  脱敏诊断报告

支持常见 TTF、OTF、TTC、TrueType glyf、CFF/CFF2、多字重和可变字体。
可变字体读取实际设计轴，不存在的字重不会仅靠文件名伪装为可用。

安全原则：
- 不直接写只读系统分区
- 不覆盖整份原厂 fonts.xml / font_fallback.xml
- 不执行导入 ZIP 中的第三方脚本
- 图标、Emoji、符号和高风险槽默认不参与普通替换
- 新负载验证后才提交
- 失败、超时或内存不足保留当前有效字体
- 卸载只处理洛书自己的挂载与记录

功能边界：
洛书主要管理 Android 系统字体链路。App 自带字体、网页 CSS/WebFont、游戏或阅读器私有字体引擎、输入法资源字体、Canvas/SVG/图片文字等可能不经过系统字体，因此不保证替换。

真机验证状态：
https://github.com/xgl34222220-ops/LuoShu/blob/main/docs/TEST_MATRIX.md

许可证：
GPL-3.0-only。第三方组件许可证见 THIRD_PARTY_NOTICES.md 与 licenses/。

作者：惜故里丶
