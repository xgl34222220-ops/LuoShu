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

## Google WOFF2 与 Brotli

- 用途：导入 WOFF2 网页字体时在 Android ARM64 设备上离线解码，得到 SFNT/TTC 后再交给洛书自己的字体校验。设备端 Python 运行时是纯 Python FontTools，没有 Brotli 扩展，因此单独打包一个静态解码器 `common/python/bin/luoshu-woff2-decode`。
- 来源：[`google/woff2`](https://github.com/google/woff2) 固定提交 `fb9c3379f2605b10f3e8f1d9636664ab5576775c`；[`google/brotli`](https://github.com/google/brotli) 固定提交 `ed738e842d2fbdf2d6459e39267a633c4a9b2f5d`（v1.1.0）。源码包在构建时按 sha256 校验（见 `scripts/build_woff2_decoder.sh`），只编译两者的解码部分，入口为洛书自写的 `tools/woff2/luoshu_woff2_decode.cc`（GPL-3.0-only）。
- 许可证：两者均为 MIT License。
- 完整文本：[`licenses/WOFF2-LICENSE.txt`](licenses/WOFF2-LICENSE.txt) 与 [`licenses/Brotli-LICENSE.txt`](licenses/Brotli-LICENSE.txt)（构建脚本会与上游原文逐字节比对）。

## 字域 Ziyu（WOFF/WOFF2 转换与 ZIP 安全解压）

- 来源：字域 Ziyu v1.4.8（作者 酷安@柔性体，仓库 [`shishui611-art/Ziyu`](https://github.com/shishui611-art/Ziyu)），本身是洛书的衍生项目；移植依据为 v1.4.8 发布包，未记录对应的仓库提交号。
- 许可证：GPL-3.0-only，与洛书一致。
- 移植文件：
  - `common/font_web_convert.py`：源自字域 `common/font_web_convert.py`。改动：解码器改为洛书的 `luoshu-woff2-decode`（输入/输出双参数）、WOFF 使用 FontTools 默认惰性加载以加快纯 Python 运行时、去掉字域专用的 `font_structure` 依赖、转换结果默认保留原文件名、解码器缺失或无执行权限时给出明确中文提示。
  - `common/font_zip_extract.py`：源自字域 `common/font_zip_extract.py`。改动：额外提取 OTC/WOFF/WOFF2，跳过 `__MACOSX/` 与 `._` 资源分叉文件。
- 洛书侧的接入（`font_check.sh` 先转换后校验、`font_import.sh`/`native_import.sh` 的导入流程与 App 入口）为洛书自写代码。

## 用户字体与第三方模块

洛书不会在仓库或发布包中附带商业字体。以下内容不受洛书 GPL-3.0-only 授权：

- 用户自行放入 `/sdcard/LuoShu/fonts/` 的字体；
- 从其他模块 ZIP 中读取的字体；
- ROM、厂商、Google 或应用自带字体；
- 使用这些字体生成的复合输出中由原字体权利人拥有的字形数据。

使用者必须自行确认字体的使用、修改和再分发权限。不要在 Issue、PR、Release 或其他公开渠道上传无授权字体。
