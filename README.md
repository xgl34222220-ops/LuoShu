<div align="center">

# 洛书 LuoShu

**Android 无 Hook 全局字体复合与安全切换模块**

适用于 Magisk、KernelSU、SukiSU Ultra 与 APatch

[![Release](https://img.shields.io/github/v/release/xgl34222220-ops/LuoShu?display_name=tag&sort=semver&label=正式版)](https://github.com/xgl34222220-ops/LuoShu/releases/latest)
[![Build](https://github.com/xgl34222220-ops/LuoShu/actions/workflows/build.yml/badge.svg)](https://github.com/xgl34222220-ops/LuoShu/actions/workflows/build.yml)
[![ROM](https://img.shields.io/badge/ROM-设备原厂清单自适应-3ddc84?logo=android)](docs/USER_GUIDE.md#10-设备自适应原厂字体清单)
[![License](https://img.shields.io/badge/license-GPL--3.0--only-orange)](LICENSE)

[下载最新正式版](https://github.com/xgl34222220-ops/LuoShu/releases/latest) · [完整使用教程](docs/USER_GUIDE.md) · [真机验证状态](docs/TEST_MATRIX.md) · [问题反馈](https://github.com/xgl34222220-ops/LuoShu/issues)

</div>

洛书以用户选择的**中文字体作为完整基底**，把英文字体和数字字体中的目标字形与度量写入同一份复合字体，再按照当前设备的原厂字体配置映射到系统文字字体槽。中文、英文和数字可以分别选择，同时避免缺字回退、字体抢占和直接修改系统分区。

从 **v2.3.0** 开始，洛书使用完全独立的私有自挂载架构。真实字体负载保存在模块私有目录，由洛书自己完成挂载；不需要安装、选择或配置任何元模块。即使设备中同时存在其他挂载类模块，它们也不会负责洛书的字体负载。

模块包始终内置原生 Android 管理 App，也提供相同正式签名的独立 APK。项目不使用 WebUI。

## 快速开始

1. 在 [Releases](https://github.com/xgl34222220-ops/LuoShu/releases/latest) 下载 `LuoShu-<版本>.zip`，并核对同名 SHA-256 文件。
2. 使用当前 Root 管理器刷入模块，完整重启手机。
3. 通过模块“操作”按钮安装内置 App，或安装 Release 中的独立 APK。
4. 在 App 中导入字体，分别选择中文、英文和数字字体。
5. 点击“生成并应用复合字体”，任务完成后再次完整重启。

不需要额外安装挂载模块，也不需要把洛书加入任何白名单。

## 核心能力

- **中文、英文、数字独立选择**：中文保持完整覆盖，英文与数字只替换各自负责的字符。
- **设备自适应原厂清单**：安装阶段读取当前设备真实字体目录和字体配置，记录路径、分区、TTC 索引与字体度量。
- **私有自挂载**：真实负载位于 `.luoshu-payload/`，标准模块分区目录保持为空，洛书自行完成 systemless 挂载。
- **不依赖元模块**：不检测、不修改、不同步 Mountify、Hybrid Mount、Magic Mount 或其他元模块配置。
- **保留系统资源**：原厂 Emoji、图标、衬线、斜体、fallback 和未被洛书管理的字体槽保持原样。
- **真实字重与可变字体**：静态字体只显示实际存在的字重；可变字体读取真实设计轴范围。
- **格式支持**：支持 TrueType `glyf`、CFF、CFF2、TTF、OTF、TTC 和可变字体。
- **角色覆盖检查**：任务开始前分别校验中文基底、英文和数字所需的关键字符。
- **事务提交与安全回退**：新字体通过验证后才替换旧有效负载；失败、超时或内存不足不会先删除当前可用字体。
- **缓存与后台恢复**：相同组合使用 SHA-256 缓存，App 被关闭或系统回收后仍可重新接管任务状态。
- **安全导入**：可从字体模块 ZIP 中提取字体，但不会执行第三方脚本。

## 挂载架构

洛书安装后会把真实分区负载迁移到：

```text
/data/adb/modules/LuoShu/.luoshu-payload/
├── system/
├── system_ext/
├── product/
├── my_product/
└── vendor/
```

标准的 `system/`、`product/`、`vendor/` 等模块目录只保留空壳，避免 Root 管理器或其他挂载组件重复接管。KernelSU、SukiSU Ultra 和 APatch 在 `post-mount` 阶段由洛书挂载；Magisk 在 `post-fs-data` 阶段由洛书挂载。挂载失败保持 fail-open，不阻断系统启动；App 和模块状态在字体事务已确认且自挂载状态正常后显示所选字体已生效，开机不再重复扫描或哈希完整字体树，深度加载验证仅用于手动诊断。

## 使用方式

### 直接应用单个字体

中文、英文和数字都选择同一字体、同一标准字重时，洛书优先走快速应用路径。

### 生成组合字体

分别选择中文、英文和数字字体后，洛书以中文字体为基底生成完整复合字体。

### 字重与设计轴

- 静态字体只提供真实存在的字重；
- 静态多字重字体只组合当前选择的字重；
- 包含 `wght`、`wdth`、`opsz`、`slnt` 等轴的可变字体可使用完整轴控制；
- 不存在的字重不会通过文件名伪装成已支持。

## 用户字体目录

```text
/sdcard/LuoShu/
├── fonts/      # 用户文字字体（TTF / OTF / TTC）
├── import/     # 待导入的字体模块 ZIP
└── reports/    # 脱敏诊断报告
```

也可以直接在 App 中调用系统文件选择器导入字体。

## 字体要求

- 中文基底需包含常用中文、英文字母、数字和常用标点；
- 英文字体需包含 `A–Z`、`a–z` 和常用标点；
- 数字字体需包含 `0–9` 和常用数字标点；
- 文件扩展名必须与真实字体格式一致；
- 图标字体、彩色字体、损坏文件和伪装扩展名会被拦截；
- 请勿上传或分发没有授权的商业字体。

洛书不会随仓库或发布包附带商业字体。

## ROM 与机型兼容机制

洛书不依赖预先写死手机型号。只要设备把系统 UI 文字字体暴露在可读取的字体配置或受支持字体分区中，安装扫描器就可以建立设备清单。

当前主要映射分区：

```text
/system/fonts
/system_ext/fonts
/product/fonts
/my_product/fonts
/vendor/fonts
```

`/odm`、`/oem`、`/my_region`、`/hw_product` 等目录也会参与诊断和 ROM 特征识别。ColorOS、HyperOS 等名称只表示已有真机验证和额外故障回退适配，不是 ROM 白名单。

## 功能边界

洛书只管理 **Android 系统文字字体**，不提供 Emoji、图标字体、符号字体或应用资源替换。以下内容通常不受洛书控制：

- 应用自行打包的字体；
- 输入法键帽、QQ/微信等应用内置资源字体；
- 游戏、阅读器等私有字体引擎；
- 网页通过 CSS 下载的网络字体；
- 图片、Canvas、SVG 路径化文字；
- 与洛书同时覆盖相同系统字体路径的其他字体模块。

## 安全设计

- 不直接修改 `/system`、`/product`、`/vendor` 等只读分区；
- 不覆盖设备原始字体 XML；
- 不执行导入 ZIP 中的脚本；
- 输出字体在提交前重新打开并验证字符覆盖、格式和轮廓；
- 字体负载和配置状态共同参与事务恢复；
- 不通过只重启 SystemUI 宣称字体已经完整生效；
- 卸载时只解除洛书记录的挂载并清理洛书私有负载。

## 文档

- [完整使用教程](docs/USER_GUIDE.md)
- [真机验证状态与发布测试矩阵](docs/TEST_MATRIX.md)
- [设备字体模板引擎说明](docs/DEVICE_FONT_TEMPLATE_ENGINE.md)
- [发布流程](docs/RELEASING.md)
- [版本变化](CHANGELOG.md)

## 从源码构建

```sh
sh ./scripts/prepare_composite_runtime.sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

正式 Release 由固定签名工作流构建，模块内置 App 与独立 APK 必须字节一致。

## 反馈问题

提交 Issue 时请提供：设备型号、ROM 与 Android 版本、Root 管理器、字体格式与体积、复现步骤，以及已经检查隐私信息的诊断报告。请勿上传无授权字体文件。

## 许可证

洛书当前源码采用 **GNU General Public License v3.0 only**（SPDX：`GPL-3.0-only`），完整条款见 [LICENSE](LICENSE)。分发洛书或其修改版本时，需要按照 GPLv3 提供对应源代码、保留版权与许可证声明，并将基于洛书的整体修改版本继续置于 GPLv3 下。

历史标签和发行包继续适用其发布时附带的许可证；历史 MIT 文本保存在 [`licenses/LuoShu-MIT-HISTORICAL.txt`](licenses/LuoShu-MIT-HISTORICAL.txt)。第三方组件适用各自许可证，详情见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 `licenses/`。

作者：**惜故里丶**
