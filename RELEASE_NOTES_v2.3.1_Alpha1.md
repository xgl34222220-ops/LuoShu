<!-- prerelease -->
# 洛书 v2.3.1 Alpha1

这是用于验证无元模块环境自挂载修复的预发行测试版，重点处理部分 ColorOS 16 设备出现的两类问题：删除元模块后重启乱码，以及洛书提示应用成功但完整重启后仍为系统默认字体。

## 核心修复

- 字体文件与字体配置改为原子自挂载事务。
- `system`、`system_ext`、`product`、`my_product`、`oplus_product` 等实际包含负载的分区必须全部成功。
- 任意 `fonts` 或 `etc` 挂载失败都会逆序解除本轮全部挂载，安全回到 ROM 字体。
- 删除旧的 `degraded` 半成功判定，半挂载状态不会再被报告为成功。
- 逐文件 bind 兜底必须完整覆盖全部必需文件，缺少目标或部分失败立即回滚。
- 挂载提交前检查 PID 1 主命名空间中的真实字体与配置文件，并核对大小和快速指纹。
- 使用本次启动的 boot ID 隔离挂载记录，避免读取旧启动日志后误卸载其他挂载。
- KernelSU、SukiSU 等 KernelSU 家族统一推迟到 `post-mount` 阶段执行。
- 开机字体加载验证会先检查自挂载是否完整可见；失败时不再显示字体已成功生效。
- 同步更新重复执行回归门禁，确认第二次调用复用原子事务且不会叠加挂载。

## 测试重点

请优先测试以下流程：

1. 暂时禁用或卸载原有元模块并完整重启，确认系统字体正常、没有方框或乱码。
2. 覆盖刷入本测试版并完整重启。
3. 在洛书中应用一个之前可以正常使用的字体，任务结束后再次完整重启。
4. 确认系统界面、微信/QQ、浏览器、设置、通知栏和锁屏字体均正常生效。
5. 再次完整重启一次，确认字体不会恢复默认。
6. 在洛书中恢复系统默认字体并重启，确认不存在残留乱码。

如测试失败，请不要反复切换字体。恢复系统默认字体或禁用洛书后重启，并导出：

```sh
su -c 'cat /data/adb/modules/LuoShu/config/self-mount.conf'
su -c 'cat /data/adb/modules/LuoShu/config/self-mount-required.conf'
su -c 'cat /data/adb/modules/LuoShu/config/device-font-load-verification.conf'
su -c 'cat /data/adb/modules/LuoShu/logs/self-mount.log'
su -c 'cat /data/adb/luoshu/self-mount/mounts.list'
su -c "grep -E '/(system|system_ext|product|my_product|oplus_product)/(fonts|etc)' /proc/1/mountinfo"
```

## 版本信息

- 模块版本：`v2.3.1 Alpha1`
- 模块 versionCode：`20301`
- App versionName：`2.3.1 Alpha1`
- App versionCode：`2030101`
- 发布类型：预发行测试版

本版本不会修改正式版 `update.json`，普通用户不会收到自动更新提示。测试完成并确认无乱码、重启后字体持续生效、恢复默认正常后，再发布正式版本。
