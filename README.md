# 洛书（LuoShu）

面向现代 Android 的全局字体管理模块，支持文字字体与 Emoji 独立切换，并针对 Android 16、ColorOS 16、HyperOS 3、Google/GMS 动态字体和微信 XWeb 做兼容处理。

## 主要功能

- 扫描 `/sdcard/LuoShu/fonts/` 中的 TTF、OTF、TTC 文字字体
- 从 `/sdcard/LuoShu/emoji/` 独立管理 Emoji 字体
- 从 `/sdcard/LuoShu/import/` 安全导入其他字体模块 ZIP，只提取字体，不执行其中脚本
- 检查真实文件头，拦截仅修改扩展名的 WOFF、WOFF2、ZIP 或损坏文件
- WebUI 字符覆盖分析：中文、英文、数字、标点、符号、Emoji 与私用区
- 解析可变字体 `fvar` 轴，支持连续粗细预览
- 识别静态多字重家族并提供档位选择
- 一次开机只允许准备一次文字字体和一次 Emoji，避免连续热切换造成系统卡死
- 保留 ROM 自带 `fonts.xml`、fallback、符号字体和其他语言字体
- 适配 Google Play、GMS、Google 搜索、Gemini 相关进程的动态 Google Sans
- 适配微信 XWeb/公众号字体命名空间
- 支持 Magisk、KernelSU、SukiSU Ultra、APatch 常见模块环境

正式构建包保留 ARM64 原生扫描器 `system/bin/luoshud`，仅用于诊断回退；WebUI 默认使用安全 Shell 扫描。

## v14 切换与稳定性

v14 将字体切换状态改为轻量任务文件查询。切换期间不再反复扫描和重建字体预览文件，降低 WebUI 偶发退出和卡顿的概率。

切换任务会记录在本地。WebUI 中途退出、被系统回收或重新打开时，会自动继续确认切换结果，不需要重复点击。

模块脚本统一通过 `sh` 调用，开机还会静默校正权限，因此不再提供“修复脚本权限”按钮。用户无需理解或手动处理可执行位。

自救入口只保留真正有用的功能：

- 重建字体索引
- 清除 WebUI 缓存
- 生成诊断报告
- 重新检测状态

v14 不再建立或展示“上一个稳定配置”。字体不合适时，完整重启后直接选择其他字体或恢复系统默认字体即可。

## 已测试设备

- 一加 15（ColorOS 16）
- Redmi K80 至尊版（HyperOS 3）

其他设备和 ROM 可自行测试。字体本身的字形覆盖、私用区字符和应用内置字体会影响最终效果。

## 安装与使用

1. 把文字字体放入 `/sdcard/LuoShu/fonts/`。
2. 可选：把 Emoji 字体放入 `/sdcard/LuoShu/emoji/`。
3. 在 Magisk、KernelSU、SukiSU Ultra、APatch 或兼容管理器中刷入模块。
4. 完整重启手机。
5. 在模块 WebUI 中选择字体，准备完成后再次完整重启。

同一次开机内不要连续切换文字字体。洛书会主动阻止第二次准备，这是稳定保护，不是故障。

## Root 与元模块

- 未安装元模块时，直接使用 Root 管理器原生模块挂载。
- 需要元模块时仅推荐 **Mountify**。
- 不建议同时启用其他字体模块覆盖相同字体路径。

## 字体粗细调节

- **可变字体**：读取 `fvar` 的 `wght` 轴，提供连续滑块和实时预览。
- **静态多字重家族**：识别 Thin、Light、Regular、Medium、SemiBold、Bold、Black 等独立文件，并提供离散档位选择。

应用粗细时会写入 Android 全局 `font_weight_adjustment` 并请求字体服务刷新。已运行应用可能需要重新打开；ROM 不支持对应接口时自动降级为仅预览。

## 构建与检查

```sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

检查内容包括 Shell/JavaScript 语法、WebUI 资源版本、轻量切换任务、空字体库与多字体状态、缓存清理、扫描计时、Mountify 挂载同步和正式 ZIP 结构。

构建产物位于 `dist/`。推送 `v14` 到 `main` 后，GitHub Actions 会自动构建并创建正式 Release。

## 反馈

提交 Issue 时请附上设备型号、ROM、Android 版本、Root 管理器、复现步骤，以及 `/sdcard/LuoShu/reports/` 中的脱敏报告。请勿上传无授权字体文件。

## 开源协议

[MIT License](LICENSE)
