# 第三方组件与许可证

洛书自身源码采用 MIT License，详见根目录 [`LICENSE`](LICENSE)。

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

## 用户字体与第三方模块

洛书不会在仓库或发布包中附带商业字体。以下内容不受洛书 MIT License 授权：

- 用户自行放入 `/sdcard/LuoShu/fonts/` 的字体；
- 从其他模块 ZIP 中读取的字体；
- ROM、厂商、Google 或应用自带字体；
- 使用这些字体生成的复合输出中由原字体权利人拥有的字形数据。

使用者必须自行确认字体的使用、修改和再分发权限。不要在 Issue、PR、Release 或其他公开渠道上传无授权字体。
