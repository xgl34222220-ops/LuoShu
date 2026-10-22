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

## 字域 Ziyu

- 来源：字域 Ziyu v1.4.8，作者 酷安@柔性体，仓库 [`shishui611-art/Ziyu`](https://github.com/shishui611-art/Ziyu)（字域本身是洛书 refactor-v3.0.0 的 GPL 衍生）。
- 许可证：GPL-3.0-only，与洛书一致，完整文本见根目录 [`LICENSE`](LICENSE)。
- 移植内容（受保护字体 fs-verity）：
  - `common/font_verity.py`、`common/font_verity.sh`：移植自字域同名文件。洛书改动：所有权按模块自身路径判定（含 `modules_update` 和 `/proc/1/root` 前缀），区分「内核/文件系统不支持 fs-verity」（退出码 3），`FS_IOC_ENABLE_VERITY` 使用 4096 字节块并在旧内核上回退到页大小。
  - `common/google_font_provider_patch.py`：受保护目标（`/data/fonts/`）复制原厂 `head.fontRevision`、校验 PostScript 名一致、保存后复核并 seal；思路来自字域同名文件，洛书新增 PS 名校验、复核和不支持时不产出克隆。
  - `common/google_font_provider_bridge.sh`：受保护目标 bind 前 seal、bind 后比对可见文件的 verity 摘要、不一致立即 umount 回滚、回滚失败登记日志，撤销旧的未封装挂载；思路来自字域同名文件的 verity 分支。洛书改为仅受保护目标使用 `provider-v4-verity` 缓存键，其他目标保持 `provider-v3` 不变；设备不支持 fs-verity 时放弃该目标并按启动记录，不再重复尝试。

## 用户字体与第三方模块

洛书不会在仓库或发布包中附带商业字体。以下内容不受洛书 GPL-3.0-only 授权：

- 用户自行放入 `/sdcard/LuoShu/fonts/` 的字体；
- 从其他模块 ZIP 中读取的字体；
- ROM、厂商、Google 或应用自带字体；
- 使用这些字体生成的复合输出中由原字体权利人拥有的字形数据。

使用者必须自行确认字体的使用、修改和再分发权限。不要在 Issue、PR、Release 或其他公开渠道上传无授权字体。
