# 第三方组件与许可证

洛书当前源码采用 GPL-3.0-only，详见根目录 [`LICENSE`](LICENSE)。历史 MIT 发行版本的许可证文本保存在 [`licenses/LuoShu-MIT-HISTORICAL.txt`](licenses/LuoShu-MIT-HISTORICAL.txt)。

发布包会包含或在构建过程中引入以下第三方组件。它们不因被洛书打包而改变原许可证。

## CPython

- 用途：在 Android ARM64 设备上运行离线复合字体构建器。
- 来源：Python 官方 Android ARM64 发行包。
- 许可证：Python Software Foundation License 及其历史许可条款。
- 完整文本：[`licenses/CPython-LICENSE.txt`](licenses/CPython-LICENSE.txt)。

洛书只进行打包精简：删除测试、开发头文件、IDLE、ensurepip 和运行时不需要的工具，不修改解释器核心许可。

## FontTools

- 用途：读取、转换、写入和验证 OpenType 字体。
- 许可证：MIT License。
- 完整文本：[`licenses/FontTools-LICENSE.txt`](licenses/FontTools-LICENSE.txt)。
- FontTools 上游附带的外部字体项目声明：[`licenses/FontTools-LICENSE.external.txt`](licenses/FontTools-LICENSE.external.txt)。

发布运行时不会使用 FontTools 测试字体作为洛书内置字体，但仍保留上游外部声明以便完整追溯。

## Miuix 与 AndroidLiquidGlass

- 用途：Android 13 及以上悬浮底栏的背景取样、RuntimeShader 模糊与折射、边缘高光和平滑连续圆角。
- 来源：[`compose-miuix-ui/miuix`](https://github.com/compose-miuix-ui/miuix)；折射透镜按其官方示例改写，该示例注明源自 [`Kyant0/AndroidLiquidGlass`](https://github.com/Kyant0/AndroidLiquidGlass)。
- 许可证：Apache License 2.0。
- 完整文本：[`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt)。

洛书修改了示例的包名、配色、分层、尺寸和导航状态接入；底层库及原示例的许可证与署名不变。

## 字域 Ziyu：缺失空白字形补全

- 文件：`common/font_space_compat.py`（由 `common/device_font_slot_build_base.py`、`common/composite_font.py`、`common/font_instance.py` 调用）。
- 来源：字域 Ziyu v1.4.8，作者 酷安@柔性体，仓库 [`shishui611-art/Ziyu`](https://github.com/shishui611-art/Ziyu)，原文件 `common/font_space_compat.py`。该文件在字域提交 [`025e6428`](https://github.com/shishui611-art/Ziyu/commit/025e64286b3daf286bdb887d514c570ea9353e03)（ziyu-v1.2.20）首次加入，最后修改于 [`d9b9b618`](https://github.com/shishui611-art/Ziyu/commit/d9b9b61898b0ff00f0db5d7d149ab2ec81b8a8fd)；v1.4.8 发行包与字域 main [`5694469c`](https://github.com/shishui611-art/Ziyu/commit/5694469c601abac864c19ce5ddd882dd1751c651)（2026-10-18）内容一致。
- 溯源：字域是洛书的衍生项目，但洛书仓库全部分支历史中没有 `luoshuSpace` 字形名或同类代码，该功能为字域新增，因此按字域署名。
- 许可证：GPL-3.0-only，与洛书相同，全文见根目录 [`LICENSE`](LICENSE)。
- 洛书改动：缺少 Unicode cmap / hmtx、轮廓格式不支持、CID 字体缺 FDArray 时，在修改任何表之前返回 `skipped`，不再抛错中断构建；CID 编号耗尽记为 `unresolved`；报告增加 `schema` 字段；命令行去掉硬链接复制分支，统一完整复制。字形追加、可变字体只复用已有空格、宽度 unitsPerEm/4 等核心逻辑保持原样。

## 用户字体与第三方模块

洛书不会在仓库或发布包中附带商业字体。以下内容不受洛书 GPL-3.0-only 授权：

- 用户自行放入 `/sdcard/LuoShu/fonts/` 的字体；
- 从其他模块 ZIP 中读取的字体；
- ROM、厂商、Google 或应用自带字体；
- 使用这些字体生成的复合输出中由原字体权利人拥有的字形数据。

使用者必须自行确认字体的使用、修改和再分发权限。不要在 Issue、PR、Release 或其他公开渠道上传无授权字体。

## 字域 Ziyu（KernelSU 软重启阶段）

- 用途：KernelSU `emulated-soft-reboot` 阶段释放洛书自有挂载并重置同 boot 挂载决策。
- 来源：字域 Ziyu v1.4.8，作者 酷安@柔性体，仓库 [`shishui611-art/Ziyu`](https://github.com/shishui611-art/Ziyu)（参考时 main 为 `5694469c601abac864c19ce5ddd882dd1751c651`）。字域本身是洛书的衍生项目。
- 参考文件：`emulated-soft-reboot.sh`（阶段钩子结构、boot_id 校验、逆序回滚并允许惰性卸载、`state=ready|failed` 阶段记录）；`common/soft_reboot.sh`、`common/mount_provider_reload.sh` 仅用于确认 ksud 阶段顺序。
- 洛书侧文件：`emulated-soft-reboot.sh`、`.luoshu-runtime/core/emulated-soft-reboot.sh`。
- 改动说明：按洛书的 self-mount / module-view 日志重写；增加“仅当路径最上层为洛书挂载才卸载”的所有权检查与 `KSU=true` 门控；未移植 provider 软重载、NoMount、mountify 清理与 ksud 软重启请求（这些会操作其他模块的挂载）。
- 许可证：GPL-3.0-only（与洛书一致），见根目录 [`LICENSE`](LICENSE)。
