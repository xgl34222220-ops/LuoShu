# 洛书（LuoShu）

面向 Android 16 的全局字体切换模块，支持替换系统与应用中的中文、英文和数字字体，并针对 ColorOS、HyperOS、Google Play/GMS 动态字体及微信 XWeb 页面做了适配。

这个项目最初只是自用。新系统的字体链路越来越分散：系统界面已经换了字体，Google Play 仍可能使用 Google Sans，微信公众号/XWeb 页面也可能继续显示默认字体。为了把这些入口统一起来，我做了洛书，并在实际设备上不断补齐兼容处理。

## 功能

- 从 `/sdcard/Fonts/` 识别和切换 TTF/OTF 字体
- 覆盖系统中文、英文和数字字体别名
- 适配 ColorOS 16、HyperOS 3 与 Android 16
- 桥接 Google Play/GMS 动态字体目录
- 桥接微信 XWeb/公众号字体渲染
- 提供 MIUIX 风格 WebUI、字体预览、收藏和恢复默认
- 保留系统 Emoji、代码字体、可变字体等必要回退

正式构建包内含 ARM64 原生字体扫描加速程序 `luoshud`；扫描失败时会自动回退到 Shell 实现，不参与字体挂载核心流程。

## 已测试设备

- 一加 15（PLK110），ColorOS 16
- Redmi K80 至尊版（25060RK16C），HyperOS 3

其他 Android 设备可自行测试。不同 ROM、应用版本和字体文件的字形覆盖范围可能影响最终效果。

## 安装与使用

1. 将 TTF/OTF 字体放入 `/sdcard/Fonts/`。
2. 通过 KernelSU、Magisk 或兼容管理器刷入模块。
3. 完整重启手机。
4. 打开模块 WebUI 选择字体；切换后按提示重启系统界面或手机。

建议使用同时包含中文、拉丁字母和数字的完整字体。字体自身缺字时，Android 会回退到系统字体；应用明确打包并强制使用的私有字体也不一定能由系统模块覆盖。

## 构建

```sh
./scripts/build.sh
```

生成文件位于 `dist/`。GitHub Actions 也会自动检查脚本并生成可刷入 ZIP。

## 反馈

提交 Issue 时请附上设备型号、ROM/Android 版本、Root 管理器、复现步骤和脱敏日志。请勿上传账号、完整设备备份或个人字体文件。

## 开源协议

[MIT License](LICENSE)
