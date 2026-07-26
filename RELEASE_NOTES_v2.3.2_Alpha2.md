<!-- prerelease -->
# 洛书 v2.3.2 Alpha2

Alpha2 修复 Alpha1 中“已经选择字体，但完整重启后仍为系统默认字体”的剩余问题。它保留原子自挂载与失败全量回滚，并进一步修正覆盖升级、APatch 启动阶段和 App 生效状态展示。

## 核心修复

- 覆盖升级不再只迁移 `system`、`product`、`my_product` 等少数目录。
- 完整保留 `oplus_product`、全部 `oplus_*`、`my_*`、`mi_ext`、`cust`、`hw_product` 等受支持 OEM 字体与配置负载。
- 仅存在于 OPlus 分区的有效字体负载也会被正确识别，不再被当作无效安装恢复默认。
- APatch 从阻塞且过早的 `post-fs-data` 改到 OverlayFS 完成后的 `post-mount` 执行自挂载。
- Magisk 保留 `post-fs-data` 路径；KernelSU、SukiSU 与 APatch 统一在各自支持的 `post-mount` 阶段执行。
- 模块状态接口同时返回已配置字体、实际生效字体、自挂载状态和开机验证结果。
- 首页不再把 `active_font.conf` 直接描述为当前已生效字体。
- 自挂载回滚或开机验证失败时，首页明确显示“系统默认字体（所选字体未生效）”和对应原因。
- 兼容映射没有系统加载证据时不再显示“字体可正常使用”。
- 修复重复执行测试错误读取 `/mounts.list`、Shell 报错后仍通过的问题。
- 补齐原子挂载、升级迁移、APatch 阶段和状态桥的 CI 触发与回归门禁。

## 测试重点

请优先让 Alpha1 中重启后仍为默认字体的用户测试：

1. 直接覆盖刷入 Alpha2 并完整重启。
2. 打开洛书，确认首页不会把旧的未验证字体显示为已经生效。
3. 重新应用一个字体，等待任务完成后完整重启。
4. 检查设置、状态栏、通知、锁屏、浏览器及常用应用。
5. 再完整重启一次，确认字体持续生效。
6. 恢复系统默认字体并重启，确认没有残留或乱码。

重点覆盖：

- ColorOS 15/16 + APatch；
- ColorOS 15/16 + KernelSU / SukiSU Ultra；
- HyperOS + Magisk；
- 从 v2.3.0 或 v2.3.1 Alpha1 保留当前字体覆盖升级。

若仍未生效，请导出：

```sh
su -c 'cat /data/adb/modules/LuoShu/config/self-mount.conf'
su -c 'cat /data/adb/modules/LuoShu/config/self-mount-required.conf'
su -c 'cat /data/adb/modules/LuoShu/config/device-font-load-verification.conf'
su -c 'cat /data/adb/modules/LuoShu/logs/self-mount.log'
su -c "grep -E '/(system|system_ext|product|my_product|oplus_product)/(fonts|etc)' /proc/1/mountinfo"
```

## 版本信息

- 模块版本：`v2.3.2 Alpha2`
- 模块 versionCode：`20302`
- App versionName：`2.3.2-alpha2`
- App versionCode：`2030201`
- 发布类型：预发行测试版

本版本不会修改正式版 `update.json`。完成上述真机矩阵前不要转为正式版。
