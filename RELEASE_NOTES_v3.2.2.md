# 洛书 v3.2.2

洛书 3.2.2 是针对 KernelSU 自挂载回滚和 App 状态误判的正式热修版。

## KernelSU 可选分区挂载修复
- 修复部分 Android 16 / KernelSU 设备不存在 `/system_ext/fonts` 时，洛书把 `system_ext/fonts-target-missing` 当成整笔原子事务失败的问题。
- 跨 ROM 预置的 `system_ext`、`product` 等可选 OEM/扩展负载，现在只在本机存在真实分区和目录目标时参与挂载；不存在的目标会安全跳过。
- `/system/fonts` 仍是强制核心组件，继续执行原子提交、PID 1 可见性检查以及失败完整回滚，不降低主字体树安全门禁。

## 状态一致性修复
- App、状态桥和设备可信页现在统一认可 `verified + mount-confirmed`，不再把已确认的挂载事务显示成“字体未生效”。
- 本次自挂载明确失败时，旧的 `boot-confirmed` 记录不能再把状态提升为 verified。
- 自挂载失败会显示可理解的中文说明，不再把 `mount-active-visible-layout-differs` 等内部诊断码直接暴露给用户。

## 回归验证
- 新增“设备存在 `system_ext` 分区但没有 `system_ext/fonts`”专项回归，确认系统主字体挂载不会被回滚。
- 新增可选分区根目录缺失、旧启动记录与本次回滚冲突、`mount-confirmed` App 状态解析回归。
- 正式发布工作流会重新执行完整源码检查、Android Release Lint、单元测试、固定签名 APK 构建、证书 SHA-256 校验、模块 ZIP/App 字节一致性检查以及发布就绪门禁。

## 版本信息
- 模块版本：v3.2.2
- 模块 versionCode：30202
- App versionCode：3020201

## 发布验证
本热修根据 Android 16 / KernelSU 脱敏诊断报告中的 `system_ext/fonts-target-missing` 完成针对性修复与自动化回归。ColorOS 16、HyperOS 3、Magisk、APatch 的完整真机设备矩阵仍保持 pending；本次稳定版由维护者明确授权放行，不伪造未执行的真机 PASS。

<!-- release-trigger: v3.2.2 -->
