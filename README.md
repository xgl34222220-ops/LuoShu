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
- **安全提交**：生成、验证、暂存和替换均采用事务流程；失败时保留旧字体。
- **低风险启动**：刷写和开机阶段不生成大字体，复合任务只由 WebUI 主动触发。
- **可恢复任务**：WebUI 支持真实阶段、百分比、缓存命中、后台恢复和明确错误提示。

## 功能

- 扫描 `/sdcard/LuoShu/fonts/` 中的 TTF、OTF、TTC 字体。
- 中文、英文和数字字体分别选择并生成完整复合字体。
- 支持常见 TrueType `glyf`、CFF、CFF2、TTC 和可变字体。
- 校验真实文件头、字符覆盖、轮廓和生成结果。
- 相同组合使用 SHA-256 缓存，默认最多保留三份。
- 从 `/sdcard/LuoShu/import/` 安全导入字体模块 ZIP。
- 导入时只读取字体文件，不执行第三方模块脚本。
- 自动过滤图标字体、彩色字体、损坏文件和伪装扩展名。
- 支持 Magisk、KernelSU、SukiSU Ultra、APatch。
- 支持 Mountify 元模块同步。
- 提供诊断报告、字体覆盖分析和可变字体信息展示。
- 提供原生 Android 管理 App；完整模块包内置 APK，也可从 Releases 单独下载安装。

## 功能边界

洛书只管理**系统文字字体**，不提供 Emoji、图标字体、符号字体或应用资源替换功能。

以下内容通常不受洛书控制：

- 应用自行打包的字体；
- 游戏、阅读器等使用的私有字体引擎；
- 网页通过 CSS 下载的网络字体；
- 图片、Canvas、SVG 路径化文字；
- 与洛书同时覆盖相同系统字体路径的其他模块。

为避免把图标或彩色字体误当作文字字体，相关识别与拦截规则会继续保留，但这些字体不会被导入或挂载。

## 兼容性

已重点适配：

- Android 16；
- ColorOS 16；
- HyperOS 3；
- Magisk；
- KernelSU；
- SukiSU Ultra；
- APatch；
- Mountify。

已测试设备包括：

- 一加 15（ColorOS 16）；
- Redmi K80 至尊版（HyperOS 3 / Android 16）。

不同 ROM、厂商更新和 Root 挂载方式可能改变字体路径。未列出的设备请先备份，并优先测试候选版本。

## 安装

1. 从 Releases 下载模块 ZIP，并核对随附 SHA-256。Full 包内置 App，Lite 包不内置 App、字体功能保持完整。
2. 通过 Root 管理器刷入模块；安装器会尝试同时安装内置的洛书 App。
3. 如果 App 未自动安装，重启后点击模块“操作”按钮，或下载 Release 中的独立 APK。

维护者发布步骤见 [docs/RELEASING.md](docs/RELEASING.md)，候选版本验证范围见 [docs/TEST_MATRIX.md](docs/TEST_MATRIX.md)。
4. 完整重启手机。
5. 将文字字体放入 `/sdcard/LuoShu/fonts/`。
6. 打开洛书 App 或 WebUI，分别选择中文、英文和数字字体。
7. 点击“应用字体组合”，等待进度达到 100%。
8. 完整重启后生效。

覆盖升级时，安装脚本不会在刷写阶段重新生成字体。升级后的首次启动保持系统默认字体，需要在 WebUI 中重新应用一次组合。

同一次开机内只允许提交一次文字字体变更，避免连续热切换造成系统字体缓存和挂载状态不一致。

## 字体要求

建议三种角色都选择可正常打开、字符覆盖完整的正规字体文件：

- 中文基底必须至少包含常用中文、英文字母和数字槽位；
- 英文字体必须包含 `A–Z`、`a–z`；
- 数字字体必须包含 `0–9`；
- 文件扩展名必须与真实字体格式一致；
- 不要上传或分发无授权字体。

洛书不会随仓库或发布包附带商业字体。用户自行放入的字体文件及生成结果不受洛书 GPL-3.0-only 授权，其使用和分发责任由字体权利人及使用者承担。

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
- 不在 `post-fs-data` 阶段生成复合字体。
- 输出字体在提交前重新打开并验证字符覆盖与轮廓。
- 字体负载和配置状态共同参与事务回滚。
- 任务异常、内存不足或超时不会先删除当前有效字体。
- 日志与诊断报告应在分享前检查隐私信息。

发现安全问题时请按 [SECURITY.md](SECURITY.md) 私下报告，不要直接公开利用细节。

## 构建

构建正式包需要 Linux、Python 3、Node.js、Android NDK 和网络连接。构建脚本会下载官方 Android ARM64 CPython 运行时，并打包 FontTools：

```sh
sh ./scripts/prepare_composite_runtime.sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

构建产物位于 `dist/`。

运行时准备脚本会：

- 校验 CPython 压缩包 SHA-256；
- 编译 ARM64 启动器；
- 安装并精简 FontTools；
- 删除测试、开发头文件和无用工具；
- 保留并校验 CPython、FontTools 的许可证文件；
- 使用精简后的实际负载执行导入检查。

## 反馈与贡献

提交 Issue 时请附上：

- 设备型号；
- ROM 与 Android 版本；
- Root 管理器及版本；
- 是否启用 Mountify；
- 中文、英文、数字源字体的格式与大致体积；
- 完整复现步骤；
- `/sdcard/LuoShu/reports/` 中经过检查的脱敏报告。

请勿上传无授权字体文件。贡献规范见 [CONTRIBUTING.md](CONTRIBUTING.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

洛书自身源码自本次许可证变更起采用 **GNU General Public License v3.0 only**（SPDX：`GPL-3.0-only`），完整条款见 [LICENSE](LICENSE)。

分发洛书或其修改版本时，需要按照 GPLv3 提供对应源代码、保留版权与许可证声明，并将基于洛书的整体修改版本继续置于 GPLv3 下。私人使用和不对外分发的修改不要求公开。

历史标签和发行包继续适用它们发布时附带的许可证；本次变更不会撤回已经授予的 MIT 权利。历史 MIT 文本保存在 [`licenses/LuoShu-MIT-HISTORICAL.txt`](licenses/LuoShu-MIT-HISTORICAL.txt)。

内置或构建时引入的第三方组件继续适用各自许可证，详情见：

- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [`licenses/CPython-LICENSE.txt`](licenses/CPython-LICENSE.txt)
- [`licenses/FontTools-LICENSE.txt`](licenses/FontTools-LICENSE.txt)
- [`licenses/FontTools-LICENSE.external.txt`](licenses/FontTools-LICENSE.external.txt)

GPL-3.0-only 不覆盖用户自行提供的字体、第三方模块、ROM 文件、商标或其中由第三方权利人拥有的字形数据。
