<div align="center">

# 洛书 LuoShu

**Android 无 Hook 全局字体复合与安全切换模块**

适用于 Magisk、KernelSU、SukiSU Ultra、APatch 与 Mountify

[![Release](https://img.shields.io/github/v/release/xgl34222220-ops/LuoShu?display_name=tag&sort=semver&label=正式版)](https://github.com/xgl34222220-ops/LuoShu/releases/latest)
[![Build](https://github.com/xgl34222220-ops/LuoShu/actions/workflows/build.yml/badge.svg)](https://github.com/xgl34222220-ops/LuoShu/actions/workflows/build.yml)
[![Android](https://img.shields.io/badge/重点适配-Android%2016-3ddc84?logo=android)](docs/TEST_MATRIX.md)
[![License](https://img.shields.io/badge/license-GPL--3.0--only-orange)](LICENSE)

[下载最新正式版](https://github.com/xgl34222220-ops/LuoShu/releases/latest) · [完整使用教程](docs/USER_GUIDE.md) · [兼容性记录](docs/TEST_MATRIX.md) · [问题反馈](https://github.com/xgl34222220-ops/LuoShu/issues)

</div>

洛书以用户选择的**中文字体作为完整基底**，把英文字体和数字字体中的目标字形与度量写入同一份复合字体，再按当前设备的原厂字体配置安全映射到系统文字字体槽。这样可以分别控制中文、英文和数字风格，同时避免缺字回退、字体抢占和直接修改系统分区。

模块包始终内置原生 Android 管理 App，也提供相同正式签名的独立 APK。项目不再使用 WebUI。

## 快速开始

1. 在 [Releases](https://github.com/xgl34222220-ops/LuoShu/releases/latest) 下载 `LuoShu-<版本>.zip`，并核对同名 SHA-256 文件。
2. 使用 Root 管理器刷入模块，完整重启手机。
3. 通过模块“操作”按钮安装内置 App，或安装 Release 中的独立 APK。
4. 在 App 中导入字体，分别选择中文、英文和数字字体。
5. 点击“生成并应用复合字体”，等待任务完成后再次完整重启。

第一次使用、字体目录说明、字重选择、恢复系统字体和故障排查见 [完整使用教程](docs/USER_GUIDE.md)。

## 核心能力

- **中文、英文、数字独立选择**：中文保持完整覆盖，英文与数字只替换各自负责的字符。
- **设备自适应原厂清单**：安装阶段读取当前设备的 `fonts.xml`、`font_fallback.xml` 与 OEM 字体配置，记录真实路径、分区、TTC 索引和字体度量。
- **多 ROM 安全映射**：重点适配 ColorOS 16、HyperOS 3，并为其他 Android ROM 保留通用扫描与回退路径。
- **真实字重与可变字体**：静态字体只显示实际存在的字重；可变字体读取真实设计轴范围。
- **快速当前字重组合**：静态多字重字体默认只生成用户当前选择的字重，避免无提示生成整套 100–900 输出。
- **完整格式支持**：支持常见 TrueType `glyf`、CFF、CFF2、TTF、OTF、TTC 和可变字体。
- **角色覆盖检查**：任务开始前分别校验中文基底、英文和数字所需的关键字符。
- **事务提交与安全回退**：新字体通过验证后才替换旧有效负载；任务失败、超时或内存不足不会先删除当前可用字体。
- **缓存与后台任务恢复**：相同组合使用 SHA-256 缓存，App 被关闭或系统回收后仍可重新接管任务状态。
- **安全导入**：可从字体模块 ZIP 中提取字体，但不会执行第三方脚本。

## 使用方式

### 直接应用单个字体

中文、英文和数字都选择同一字体、同一标准字重时，洛书会优先走快速应用路径。适合只想把系统字体整体替换为一套字体的用户。

### 生成组合字体

分别选择中文、英文和数字字体后，洛书会以中文字体为基底合成完整字体。适合中文使用一套字体、英文或数字使用另一套字体的场景。

### 字重与设计轴

- 静态字体只会提供真实存在的字重按钮；
- 静态多字重字体只组合当前选择的字重；
- 真正包含 `wght` 等设计轴的可变字体可继续使用完整轴控制；
- 不存在的字重不会通过文件名伪装成已支持。

## 字体目录

```text
/sdcard/LuoShu/
├── fonts/      # 用户文字字体（TTF / OTF / TTC）
├── import/     # 待导入的字体模块 ZIP
└── reports/    # 脱敏诊断报告
```

也可以直接在 App 中调用系统文件选择器导入字体，无需手动创建目录。

## 字体要求

- 中文基底需包含常用中文、英文字母、数字和常用标点；
- 英文字体需包含 `A–Z`、`a–z` 和常用标点；
- 数字字体需包含 `0–9` 和常用数字标点；
- 文件扩展名必须与真实字体格式一致；
- 图标字体、彩色字体、损坏文件和伪装扩展名会被拦截；
- 请勿上传或分发没有授权的商业字体。

洛书不会随仓库或发布包附带商业字体。用户自行提供字体及生成结果的使用和分发责任由字体权利人及使用者承担。

## 兼容性

重点回归环境：

- 一加 15：ColorOS 16 / Android 16；
- Redmi K80 至尊版：HyperOS 3 / Android 16；
- Magisk、KernelSU、SukiSU Ultra、APatch、Mountify。

未在 [测试矩阵](docs/TEST_MATRIX.md) 标记为通过的设备与 ROM 仍属于待验证范围。扫描引擎可以在不同 ROM 上共用，但生成的原厂字体清单、真实路径、XML 来源、字体度量与最终映射均按每台设备独立生成。

## 功能边界

洛书只管理**Android 系统文字字体**，不提供 Emoji、图标字体、符号字体或应用资源替换。

以下内容通常不受洛书控制：

- 应用自行打包的字体；
- 输入法键帽、QQ/微信等应用内置资源字体；
- 游戏、阅读器等使用的私有字体引擎；
- 网页通过 CSS 下载的网络字体；
- 图片、Canvas、SVG 路径化文字；
- 与洛书同时覆盖相同系统字体路径的其他模块。

## 安全设计

- 不直接修改 `/system`、`/product`、`/vendor` 等只读分区；
- 不覆盖设备原始字体 XML；
- 不在刷写、`post-fs-data` 或普通后台服务阶段生成大型复合字体；
- 不执行导入 ZIP 中的脚本；
- 输出字体在提交前重新打开并验证字符覆盖、格式和轮廓；
- 字体负载和配置状态共同参与事务恢复；
- 不通过重启 SystemUI 或字体服务热刷新宣称字体已经完整生效；
- 日志与诊断报告在分享前应检查隐私信息。

发现安全问题时请按 [SECURITY.md](SECURITY.md) 私下报告。

## 文档

- [完整使用教程](docs/USER_GUIDE.md)
- [兼容性与真机测试矩阵](docs/TEST_MATRIX.md)
- [设备字体模板引擎说明](docs/DEVICE_FONT_TEMPLATE_ENGINE.md)
- [发布流程](docs/RELEASING.md)
- [参与贡献](CONTRIBUTING.md)
- [版本变化](CHANGELOG.md)
- [第三方组件与致谢](THIRD_PARTY_NOTICES.md)

## 从源码构建

构建正式包需要 Linux、Python 3、Android SDK、Java 17 和网络连接：

```sh
sh ./scripts/prepare_composite_runtime.sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

生成文件位于 `dist/`。正式 Release 由固定签名工作流构建，模块内置 App 与独立 APK 必须字节一致。

## 反馈问题

提交 Issue 时请提供：设备型号、ROM 与 Android 版本、Root 管理器、挂载环境、字体格式与体积、复现步骤，以及已经检查隐私信息的诊断报告。请勿上传无授权字体文件。

## 许可证

洛书当前源码采用 **GNU General Public License v3.0 only**（SPDX：`GPL-3.0-only`），完整条款见 [LICENSE](LICENSE)。分发洛书或其修改版本时，需要按照 GPLv3 提供对应源代码、保留版权与许可证声明，并将基于洛书的整体修改版本继续置于 GPLv3 下。

历史标签和发行包继续适用其发布时附带的许可证；历史 MIT 文本保存在 [`licenses/LuoShu-MIT-HISTORICAL.txt`](licenses/LuoShu-MIT-HISTORICAL.txt)。第三方组件适用各自许可证，详情见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 `licenses/`。

作者：**惜故里丶**
