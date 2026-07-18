# 洛书（LuoShu）

> 面向现代 Android 的全局字体复合与安全切换模块。

[![Release](https://img.shields.io/github/v/release/xgl34222220-ops/LuoShu?display_name=tag&sort=semver)](https://github.com/xgl34222220-ops/LuoShu/releases)
[![Build](https://github.com/xgl34222220-ops/LuoShu/actions/workflows/build.yml/badge.svg)](https://github.com/xgl34222220-ops/LuoShu/actions/workflows/build.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

洛书以用户选择的中文字体作为完整基底，将英文字体和数字字体中的对应字形与度量写入同一份复合字体，再映射到系统文字字体槽。这样既保留完整中文覆盖，也避免英文或数字源字体自带中文时抢占中文显示。

## 设计目标

- **中文完整**：中文字符始终来自所选中文基底。
- **英文独立**：拉丁字母及相关字符来自所选英文字体。
- **数字独立**：数字字符来自所选数字字体。
- **不依赖缺字回退**：系统文字槽使用同一份完整复合字体。
- **不覆盖字体 XML**：不修改 `fonts.xml` 或 `font_fallback.xml`。
- **安全提交**：生成、验证、暂存和替换采用事务流程；失败时保留旧有效字体。
- **低风险启动**：刷写和开机阶段不扫描或生成大字体。
- **可恢复任务**：App 关闭或被系统回收后，可重新接管后台任务。

## 功能

- 扫描 `/sdcard/LuoShu/fonts/` 中的 TTF、OTF、TTC 字体。
- 中文、英文和数字字体分别选择并生成完整复合字体。
- 支持常见 TrueType `glyf`、CFF、CFF2、TTC 和可变字体。
- 可变字体读取真实 `wght` 范围，静态字体只使用真实存在的字重档位。
- 组合任务入队前分别检查中文基底、英文和数字角色的关键字形覆盖。
- 校验真实文件头、字符覆盖、轮廓和最终生成结果。
- 相同组合使用 SHA-256 缓存，默认最多保留三份。
- 从 `/sdcard/LuoShu/import/` 安全导入字体模块 ZIP，不执行第三方脚本。
- 自动过滤图标字体、彩色字体、损坏文件和伪装扩展名。
- 支持 Magisk、KernelSU、SukiSU Ultra、APatch 与 Mountify。
- 提供原生 Android 管理 App、WebUI、诊断报告和字体覆盖分析。

## 功能边界

洛书只管理**系统文字字体**，不提供 Emoji、图标字体、符号字体或应用资源替换功能。

以下内容通常不受洛书控制：

- 应用自行打包的字体；
- 游戏、阅读器等使用的私有字体引擎；
- 网页通过 CSS 下载的网络字体；
- 图片、Canvas、SVG 路径化文字；
- 与洛书同时覆盖相同系统字体路径的其他模块。

## 兼容性

重点适配 Android 16、ColorOS 16、HyperOS 3，以及 Magisk、KernelSU、SukiSU Ultra、APatch 和 Mountify。

当前候选版本重点回归设备：

- 一加 15（ColorOS 16）；
- Redmi K80 至尊版（HyperOS 3 / Android 16）。

未在 `docs/TEST_MATRIX.md` 标记为通过的组合仍属于待验证范围。

## 安装

1. 从 Releases 下载模块 ZIP，并核对随附 SHA-256。
2. Full 包内置 App；Lite 包不内置 App，字体功能相同。
3. 通过 Root 管理器刷入模块。刷写阶段只部署文件，不安装 App、不扫描字体、不生成复合字体。
4. 完整重启手机。
5. Full 包用户在 Root 管理器中点击洛书模块的“操作”按钮，安装或更新内置 App；也可以直接安装 Release 中的独立 APK。
6. 将字体放入 `/sdcard/LuoShu/fonts/`。
7. 打开洛书 App 或 WebUI，分别选择中文、英文和数字字体。
8. 点击“生成并应用复合字体”，等待进度达到 100%。
9. 再次完整重启后生效。

覆盖升级后首次启动保持系统默认字体，需要重新应用一次字体或字体组合。同一次开机内只允许提交一次文字字体变更，避免字体缓存和挂载状态不一致。

## 字体要求

- 中文基底需包含常用中文、英文字母、数字和常用标点；
- 英文字体需包含 `A–Z`、`a–z` 和常用标点；
- 数字字体需包含 `0–9` 和常用数字标点；
- 文件扩展名必须与真实字体格式一致；
- 不要上传或分发无授权字体。

洛书不会随仓库或发布包附带商业字体。用户自行提供字体及生成结果的使用和分发责任由字体权利人及使用者承担。

## 目录

```text
/sdcard/LuoShu/
├── fonts/      # 用户文字字体
├── import/     # 待导入的字体模块 ZIP
└── reports/    # 脱敏诊断报告
```

模块内部主要目录：

```text
common/         # 字体检查、复合、事务与 ROM 适配
webroot/        # WebUI
android-app/    # 原生 Android 管理端源码
scripts/        # 校验、构建和运行时准备
licenses/       # 第三方及历史许可证
config/         # 运行状态与任务记录
```

## 安全设计

- 不执行导入 ZIP 中的脚本。
- 不覆盖系统字体 XML。
- 不在刷写、`post-fs-data` 或后台服务阶段生成复合字体。
- 不通过重启 SystemUI 或字体服务热刷新宣称字体已完整生效。
- 输出字体在提交前重新打开并验证字符覆盖与轮廓。
- 字体负载和配置状态共同参与事务恢复。
- 任务异常、内存不足或超时不会先删除当前有效字体。
- 日志与诊断报告在分享前应检查隐私信息。

发现安全问题时请按 [SECURITY.md](SECURITY.md) 私下报告。

## 构建

构建正式包需要 Linux、Python 3、Node.js、Android SDK/NDK 和网络连接：

```sh
sh ./scripts/prepare_composite_runtime.sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

构建产物位于 `dist/`。发布流程见 [docs/RELEASING.md](docs/RELEASING.md)，候选版本验证范围见 [docs/TEST_MATRIX.md](docs/TEST_MATRIX.md)。

## 反馈与贡献

提交 Issue 时请附上设备型号、ROM/Android 版本、Root 管理器、挂载环境、字体格式与体积、复现步骤，以及检查过隐私信息的诊断报告。请勿上传无授权字体文件。

贡献规范见 [CONTRIBUTING.md](CONTRIBUTING.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

洛书当前源码采用 **GNU General Public License v3.0 only**（SPDX：`GPL-3.0-only`），完整条款见 [LICENSE](LICENSE)。

分发洛书或其修改版本时，需要按照 GPLv3 提供对应源代码、保留版权与许可证声明，并将基于洛书的整体修改版本继续置于 GPLv3 下。私人使用且不对外分发的修改不要求公开。

历史标签和发行包继续适用其发布时附带的许可证；历史 MIT 文本保存在 [`licenses/LuoShu-MIT-HISTORICAL.txt`](licenses/LuoShu-MIT-HISTORICAL.txt)。第三方组件适用各自许可证，详情见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 `licenses/`。
