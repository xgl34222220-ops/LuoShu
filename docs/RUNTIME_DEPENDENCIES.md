# 内置运行时依赖

洛书的复合字体生成器离线运行，不会在手机上临时下载解释器或 Python 包。构建输入统一锁定在
`scripts/runtime_versions.conf`，构建后写入 `common/python/runtime-manifest.json` 并随模块发布。

当前运行时包含：

- CPython 3.14.6（Android arm64 预编译归档，构建前校验 SHA-256）；
- FontTools 4.63.0；
- Android NDK 27.0.12077973；
- `arm64-v8a` 启动器，最低 API 26。

CI 缓存键同时包含准备脚本和版本锁文件。依赖升级必须在同一变更中完成运行时重建、许可证核对、
导入测试、复合字体行为测试和最低 API ELF 检查。定时安全审计只报告上游依赖风险，不会让设备端
运行时脱离完整模块单独更新，避免代码与运行时版本错配。
