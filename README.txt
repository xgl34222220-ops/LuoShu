洛书（LuoShu）

Android 无 Hook 全局字体复合与安全切换模块。
适用于 Magisk、KernelSU、SukiSU Ultra 与 APatch。

项目主页：
https://github.com/xgl34222220-ops/LuoShu

最新正式版：
https://github.com/xgl34222220-ops/LuoShu/releases/latest

完整使用教程：
https://github.com/xgl34222220-ops/LuoShu/blob/main/docs/USER_GUIDE.md

v2.3.0 挂载架构：
- 洛书真实字体负载保存在模块私有目录 .luoshu-payload
- 标准 system、product、vendor 等模块目录只保留空壳
- 洛书自行完成 systemless 挂载
- 不需要安装、选择、配置或推荐任何元模块
- 不修改 Mountify、Hybrid Mount、Magic Mount 等外部模块配置
- 保留系统原厂 Emoji、图标、衬线、斜体与 fallback

核心机制：
- 中文字体作为完整基底
- 英文字体仅替换对应拉丁字形
- 数字字体仅替换对应数字字形
- 安装阶段扫描当前设备真实字体目录与配置
- 应用字体时优先按照本机清单覆盖真实 UI 字体槽位
- 静态多字重字体默认只组合当前选择的字重
- 可变字体读取真实设计轴范围
- 字体负载与配置状态事务提交，失败保留旧有效配置
- 唯一模块包始终内置正式 App，也提供相同签名的独立 APK
- 模块不声明或打包 WebUI

快速使用：
1. 从 Latest Release 下载模块 ZIP 并核对 SHA-256
2. 通过 Root 管理器刷入并完整重启
3. 使用模块“操作”按钮安装内置 App，或安装独立 APK
4. 导入字体并分别选择中文、英文和数字字体
5. 点击“生成并应用复合字体”
6. 任务完成后再次完整重启

用户目录：
- /sdcard/LuoShu/fonts/   用户文字字体
- /sdcard/LuoShu/import/  待导入字体模块 ZIP
- /sdcard/LuoShu/reports/ 脱敏诊断报告

功能边界：
洛书只管理 Android 系统文字字体，不提供 Emoji、图标字体、符号字体或应用资源替换。应用自带字体、输入法键帽、图片文字、网页下载字体和私有字体引擎通常不经过系统字体映射。

安全说明：
- 不执行导入 ZIP 中的脚本
- 不直接修改只读系统分区
- 不覆盖原厂字体 XML
- 输出字体验证通过后才提交
- 失败、超时或内存不足不会先删除当前有效字体
- 卸载时只清理洛书记录的挂载与私有负载

许可证：
洛书当前源码采用 GPL-3.0-only。分发修改版本时必须遵守 GPLv3 的对应源代码、同许可证和声明保留要求。第三方组件适用各自许可证，详见 licenses/ 与 THIRD_PARTY_NOTICES.md。

作者：惜故里丶
