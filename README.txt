洛书（LuoShu）

Android 全局文字字体复合与安全切换模块。

核心机制：
- 中文字体作为完整基底
- 英文字体仅替换对应拉丁字形
- 数字字体仅替换对应数字字形
- 所有系统文字槽使用同一份完整复合字体
- 不依赖缺字回退，不覆盖 fonts.xml / font_fallback.xml
- 原生 Android App 提交任务并显示真实阶段、百分比与缓存状态
- 字体负载与配置状态事务提交，失败自动保留旧配置
- 刷写和开机阶段不生成大字体
- 唯一发布模块包始终内置原生洛书 App，也提供独立 APK 下载
- Lite/App-less 变体已取消
- 模块包不再声明或打包 WebUI

目录：
- /sdcard/LuoShu/fonts/   用户文字字体
- /sdcard/LuoShu/import/  待导入字体模块 ZIP
- /sdcard/LuoShu/reports/ 诊断报告

范围：
洛书只管理系统文字字体，不提供 Emoji、图标字体、符号字体或应用资源替换。导入时仍会识别并拦截这些字体，防止误当作文字字体。

支持：
Magisk、KernelSU、SukiSU Ultra、APatch、Mountify。

许可证：
洛书当前源码采用 GPL-3.0-only。分发修改版本时必须遵守 GPLv3 的对应源代码、同许可证和声明保留要求。CPython、FontTools 等第三方组件适用各自许可证，详见 licenses/ 与 THIRD_PARTY_NOTICES.md。历史版本继续适用其发布时附带的许可证；用户自行提供的字体不受洛书许可证授权。

- 应用内置字体边界：输入法键帽、应用自带字体、图片文字和部分 WebView 不经过系统字体映射，无 Hook 模块无法强制替换。
