<div align="center">

# 洛书 · LuoShu

**Android 无 Hook 全局字体替换与复合引擎**

适用于 **Magisk · KernelSU · SukiSU Ultra · APatch**

[![Release](https://img.shields.io/github/v/release/xgl34222220-ops/LuoShu?display_name=release&label=重构版)](https://github.com/xgl34222220-ops/LuoShu/releases/latest)
[![Build](https://github.com/xgl34222220-ops/LuoShu/actions/workflows/build.yml/badge.svg)](https://github.com/xgl34222220-ops/LuoShu/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-GPL--3.0--only-orange)](LICENSE)

[下载最新正式版](https://github.com/xgl34222220-ops/LuoShu/releases/latest) · [使用教程](docs/USER_GUIDE.md) · [真机验证状态](docs/TEST_MATRIX.md) · [问题反馈](https://github.com/xgl34222220-ops/LuoShu/issues)

</div>

## 项目简介

**洛书**是一套面向 Root Android 设备的无 Hook 字体替换方案。

它不是简单把一个字体文件复制到几十个系统路径，而是先读取当前设备真实字体配置，再根据中文、英文、数字的角色分别生成和映射字体负载，尽量兼顾覆盖范围、字体度量、系统稳定性和存储占用。

当前公开版本从 **「重构版 1.0.0」** 重新开始，仓库 Release 与版本标签均以重构系列为起点。

## 主要能力

- **中文 / 英文 / 数字独立选择**：可以分别指定三类字体，也可以直接使用同一字体。
- **复合字体生成**：以中文字体为完整基底，将英文和数字目标字形合入同一字体，减少缺字回退和字体抢占。
- **设备自适应字体清单**：扫描当前 ROM 的实际字体目录、配置、字体槽、字重、TTC face 与字体度量，不依赖固定机型列表。
- **HyperOS / ColorOS 适配**：针对 OEM 字体路由、状态栏/系统 UI、英文数字槽和回退链提供额外处理。
- **Google 字体兼容**：设置中提供中文的「Google 字体兼容」页面，可检测、开启和恢复 GMS FontsProvider 组件状态，用于处理部分 Google 应用英数重新使用下载字体的问题。
- **无 Hook**：不依赖 LSPosed / Zygisk Hook，不向目标 App 注入代码。
- **私有 systemless 挂载**：字体负载保存在洛书自己的私有目录，由洛书完成挂载，不要求额外安装 Mountify 等元模块。
- **事务与回滚**：新字体完整生成并验证成功后才提交；生成失败、超时或内存不足时保留上一套可用负载。
- **字体缓存复用**：相同字体组合和设备契约可以复用已验证结果，减少重复生成。
- **原生 Android App**：模块内置正式签名 App，同时提供独立 APK，不使用 WebUI。

## 快速开始

1. 从 [Releases](https://github.com/xgl34222220-ops/LuoShu/releases/latest) 下载最新 `LuoShu-v*.zip`。
2. **关闭 Root 管理器中的「默认卸载模块」功能。**
3. 使用 Magisk / KernelSU / SukiSU Ultra / APatch 刷入模块。
4. 完整重启手机。
5. 安装模块内置 App，或安装 Release 中的独立 APK。
6. 在 App 中导入字体，选择中文、英文和数字字体。
7. 应用字体，等待任务完成后按提示完整重启。

> 不需要安装额外挂载模块，也不需要手工修改 `fonts.xml`。

## Google 字体兼容

部分 Google 应用会通过 Google Play 服务的 `FontsProvider` 获取下载字体，因此可能出现：

- 中文已经替换；
- 英文和数字一开始正常；
- 使用一段时间或重新打开 Google 商店后，英数又恢复成 Google 默认字体。

洛书内置：

**设置 → Google 字体兼容**

页面提供：

- **重新检测**：只读取当前状态，不修改系统；
- **开启 Google 字体兼容**：停用当前 Android 用户的 GMS FontsProvider；
- **恢复原设置**：按照洛书保存的原状态恢复组件。

该功能默认关闭，不会在安装、开机或升级时自动开启。

### 使用建议

1. 先正常应用字体并重启；
2. 如果 Google 商店等应用的英文数字仍反复恢复默认，再开启兼容；
3. 显示「已开启」后完整重启；
4. 检查 Google 商店、Chrome 等应用，以及放到后台再打开后的字体状态。

### 注意

Google 字体兼容会影响当前用户所有依赖 GMS 下载字体的应用，并不只作用于 Google 商店。它不会停用整个 Google Play 服务，也不会删除账户、App 数据或字体缓存。

**停用或卸载洛书前，请先进入该页面点击「恢复原设置」，然后完整重启。**

## 字体工作方式

### 直接字体

当中文、英文、数字选择同一个字体时，洛书优先使用快速路径，根据本机清单准备字体负载。

### 复合字体

当三类字体来源不同时：

```text
中文字体 ─┐
          ├─> 复合字体 ─> 本机字体槽 ─> systemless 挂载
英文字体 ─┤
数字字体 ─┘
```

中文字体负责完整正文基底，英文和数字只替换各自目标字符，尽量避免为了换英数破坏中文 fallback。

## 字体与格式支持

支持常见：

- TTF
- OTF
- TTC
- TrueType `glyf`
- CFF / CFF2
- Variable Font
- 多字重字体

可变字体会读取实际 `wght`、`wdth`、`opsz`、`slnt` 等设计轴；不存在的字重不会仅靠文件名伪装为可用。

## 用户目录

```text
/sdcard/LuoShu/
├── fonts/      # 用户字体
├── import/     # 待导入字体模块 ZIP
└── reports/    # 脱敏诊断报告
```

也可以直接使用 App 的系统文件选择器导入字体。

## 安全设计

洛书的基本原则是：**可以失败，但不能为了换字体先破坏当前可用系统。**

因此：

- 不直接写入 `/system`、`/product`、`/vendor` 等只读分区；
- 不覆盖整份原厂 `fonts.xml` / `font_fallback.xml`；
- 不执行导入字体 ZIP 中的第三方脚本；
- 图标、Emoji、符号、无关语言和高风险字体槽默认不参与普通替换；
- 新负载生成后会先进行格式、覆盖和契约检查；
- 切换失败时保留上一套有效字体；
- 卸载只处理洛书自己的挂载和记录。

## 功能边界

洛书主要管理 **Android 系统字体链路**。以下内容可能完全不经过系统字体，因此不保证被替换：

- App 自带字体文件；
- 游戏、阅读器等私有字体引擎；
- 输入法键帽等资源字体；
- 网页 CSS / WebFont；
- Canvas、SVG 路径或图片文字；
- 与洛书同时覆盖同一字体路径的其他模块。

Google 字体兼容也不能替换 App 自己打包的字体或网页指定字体。

## ROM 兼容

洛书不使用「机型白名单」作为主要覆盖依据，而是读取设备当前可见的字体分区和配置。

常见目标包括：

```text
/system/fonts
/system_ext/fonts
/product/fonts
/my_product/fonts
/vendor/fonts
/odm/fonts
/oem/fonts
/mi_ext/fonts
/hw_product/fonts
```

不同 ROM 实际目录可能不同。HyperOS、ColorOS 等专项逻辑是对其特殊字体路由的增强，不代表其他 ROM 一律不支持。

真机验证情况请查看：[docs/TEST_MATRIX.md](docs/TEST_MATRIX.md)。

## 版本规则

重构系列从 **1.0.0** 开始：

```text
1.0.0 → 1.1.1 → 2.0.0 → 2.2.2 → 3.0.0 → 3.3.3 → ...
```

当前第一个公开正式版本：**重构版 1.0.0**。

## 从源码构建

```sh
sh ./scripts/prepare_composite_runtime.sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

正式 Release 使用固定证书构建；模块内置 App 与独立 APK 必须保持一致。

## 问题反馈

提交 Issue 时建议提供：

- 手机型号；
- ROM 与 Android 版本；
- Magisk / KernelSU / SukiSU Ultra / APatch 版本；
- 使用的字体格式、字重和大致体积；
- 具体未覆盖的 App / 页面；
- 可复现步骤；
- 已检查隐私信息的洛书诊断报告。

请不要上传没有授权的商业字体文件。

## 文档

- [完整使用教程](docs/USER_GUIDE.md)
- [Google 字体兼容中文说明](docs/GOOGLE_FONT_COMPATIBILITY_ZH.md)
- [真机验证矩阵](docs/TEST_MATRIX.md)
- [设备字体模板引擎](docs/DEVICE_FONT_TEMPLATE_ENGINE.md)
- [发布流程](docs/RELEASING.md)
- [第三方许可证](THIRD_PARTY_NOTICES.md)

## 许可证

洛书源码采用 **GNU General Public License v3.0 only**（`GPL-3.0-only`）。

分发修改版本时，请遵守 GPLv3 关于源码提供、许可证保留和衍生作品许可的要求。第三方组件按各自许可证分发，详见 `THIRD_PARTY_NOTICES.md` 与 `licenses/`。

---

<div align="center">

**作者：惜故里丶**

如果洛书对你有帮助，欢迎 Star、反馈真机结果或提交改进建议。

</div>
