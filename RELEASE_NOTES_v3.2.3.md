# 洛书 v3.2.3

洛书 3.2.3 是针对 v3.2.2 KernelSU 自挂载修复未进入最终执行路径的正式热修版。

## 根因修复

- `mount_compat.sh` 虽然加载了已修正的 `mount_self_atomic.sh`，但随后加载的 `font_runtime_policy.sh` 和 `font_runtime_mount.sh` 又定义了同名 `luoshu_self_mount_ensure`；最后一份旧实现覆盖了修复。
- 因此部分 Android 16 / KernelSU 设备仍会把不存在的 `/system_ext/fonts` 记录为 `system_ext/fonts-target-missing`，随后完整回滚已经成功的 `/system/fonts` 挂载。
- v3.2.3 移除两份运行时覆盖实现，自挂载统一由 `mount_self_atomic.sh` 负责；该实现会在实际调用时解析 `.luoshu-payload` 私有负载，不再依赖重复复制策略。

## 安全边界

- `system_ext`、`product` 和 OEM 分区仍是跨 ROM 可选组件：本机没有对应真实分区或目录时安全跳过。
- `/system/fonts` 仍是强制核心组件，继续执行原子提交、PID 1 可见性验证和失败完整回滚。
- 本修复不把部分挂载或降级状态当成成功，也不降低字体主树验证标准。

## 回归验证

- 新增真实 `mount_compat.sh` 生产加载顺序测试，而非只单独测试 `mount_self_atomic.sh`。
- 测试负载同时包含 `system/fonts` 和 `system_ext/fonts`，设备侧仅存在 `system_ext` 根目录但没有 `system_ext/fonts`；预期主字体挂载成功、可选组件跳过、状态为 `mounted` 且失败原因为空。
- 自挂载原子事务、私有负载、重复函数守卫和挂载兼容测试均通过。
- 正式发布工作流会重新执行完整源码检查、Android Release Lint、单元测试、固定签名 APK 构建、证书 SHA-256 校验、模块 ZIP/App 字节一致性检查以及发布就绪门禁。

## 版本信息

- 模块版本：v3.2.3
- 模块 versionCode：30203
- App versionCode：3020301

## 发布验证

本热修根据 Android 16 / KernelSU 脱敏诊断报告中 v3.2.2 仍出现的 `system_ext/fonts-target-missing` 完成根因定位与生产加载链回归。ColorOS 16、HyperOS 3、Magisk、APatch 的完整真机设备矩阵仍保持 pending；本次稳定版由维护者明确授权放行，不伪造未执行的真机 PASS。

<!-- release-trigger: v3.2.3 -->
