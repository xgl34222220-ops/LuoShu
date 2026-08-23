# 洛书 v3.3.1

这是针对 v3.3.0 无法应用字体的紧急修复版。

## 核心修复

- 修复 ColorOS / HyperOS 某些机型没有 `/system_ext/fonts`、`/product/fonts` 或其他可选字体目录时，原子自挂载错误回滚全部字体挂载的问题。
- 只有 `system/fonts` 继续作为强制目标；`product`、`system_ext`、`mi_ext` 等跨 ROM 可选分区或子目录不存在时会安全跳过。
- 修复 KernelSU / SukiSU / APatch 在 `post-mount` 阶段直接读取私有 `.luoshu-payload` 时出现 `system_ext/fonts-target-missing` 的真实调用链。
- 保持严格失败保护：`system/fonts` 缺失、挂载不完整或 PID 1 不可见时仍会完整回滚，避免混合字体树和开机异常。

## 回归测试

- 同时覆盖基础原子挂载、KernelSU 最终自挂载后端和私有 payload 运行层。
- 新增与脱敏报告一致的场景：私有 payload 含 `system_ext/fonts`，系统仅存在 `/system_ext` 而没有 `/system_ext/fonts`；验证 `system/fonts` 保持挂载、状态为 `mounted`、可选目标不进入强制验证清单。
- 保留 ColorOS、HyperOS、挂载兼容、启动链、系统健康与 Google provider 回归检查。
