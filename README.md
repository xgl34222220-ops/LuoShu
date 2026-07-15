# 洛书（LuoShu）

面向现代 Android 的通用全局字体管理模块，支持文字字体与 Emoji 独立切换，并针对 Android 16、ColorOS 16、HyperOS 3、Google/GMS 动态字体和微信 XWeb 做兼容处理。

项目最初用于自用。随着 Android 字体来源分散到系统字体、ROM 私有字体、GMS 动态字体和应用独立 WebView，仅替换单个字体文件已经无法获得一致效果，因此逐步整理为可维护的开源模块。

## 主要功能

- 从 `/sdcard/LuoShu/fonts/` 扫描 TTF、OTF、TTC 文字字体
- 从 `/sdcard/LuoShu/emoji/` 独立管理 Emoji 字体
- 检查真实文件头，拦截仅修改扩展名的 WOFF、WOFF2、ZIP 或损坏文件
- WebUI 字符抽样覆盖分析：中文、英文、数字、标点、符号、日文、韩文、Emoji 与私用区
- 解析可变字体 `fvar` 表，显示 `wght`、`wdth` 等轴的最小值、默认值和最大值
- 安全重启工作流：一次开机只允许准备一次文字字体和一次 Emoji，避免连续热切换造成系统卡死
- 保留 ROM 自带 `fonts.xml`、fallback、符号字体和其他语言字体
- 适配 Google Play、GMS、Google 搜索、Gemini 相关进程的动态 Google Sans 挂载命名空间
- 适配微信 XWeb/公众号字体命名空间
- 支持 Magisk、KernelSU、SukiSU、APatch 常见模块环境

正式构建包保留 ARM64 原生扫描器 `system/bin/luoshud`，用于旧目录诊断与故障回退；WebUI 默认仍使用安全 Shell 扫描，它不参与字体挂载核心流程。

## 已测试设备

- 一加 15（ColorOS 16）
- Redmi K80 至尊版（HyperOS 3）

其他设备和 ROM 可自行测试。字体自身的字形覆盖、私用区字符和应用内置字体会影响最终效果。

## 安装与使用

1. 把文字字体放入 `/sdcard/LuoShu/fonts/`。
2. 可选：把 Emoji 字体放入 `/sdcard/LuoShu/emoji/`。
3. 在 Magisk、KernelSU 或兼容管理器中刷入模块。
4. 完整重启手机。
5. 在模块 WebUI 中选择字体，准备完成后按提示再次完整重启。

切换字体后不要连续热切换。洛书会在同一次开机内阻止第二次文字/Emoji 准备，这是稳定性保护，不是故障。

## Hybrid Mount

- 推荐将洛书设置为 **Magic**。
- 不要设置为 **Ignore**，否则模块文件不会参与挂载。
- 洛书自己管理字体目标，避免与其他字体模块、字体元模块重复覆盖同一路径。

## 构建

```sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

产物位于 `dist/`。更新 `module.prop` 版本并推送到 `main` 后，GitHub Actions 会自动构建并创建对应 Release。

## 反馈

提交 Issue 时请附上：

- 设备型号、ROM 与 Android 版本
- Root 管理器和版本
- 使用的字体格式（不要上传无授权字体文件）
- 复现步骤
- `/sdcard/LuoShu/reports/` 中的脱敏检测报告

## 开源协议

[MIT License](LICENSE)
