<!-- prerelease -->
# 洛书 v2.3.4 Alpha4

Alpha4 修复 Alpha3 在 Android 16 + KernelSU 真机上继续暴露的 `system/fonts-visibility-mismatch`。Alpha3 已能完成兼容 bind，但部分 OEM ROM 的多个字体名称实际是指向同一真实文件的符号链接，后挂载的别名会覆盖前一个挂载，最终被严格内容验证识别并整体回滚。

## 核心修复

- bind 前解析 ROM 字体路径的真实目标。
- 同一真实目标只挂载一次，避免多个符号链接别名相互覆盖。
- 优先处理 ROM 中的真实文件，再处理没有独立真实负载名的符号链接别名。
- bind 后验证使用完全相同的目标顺序与去重规则。
- 本机不存在的跨 ROM 新增别名继续安全跳过。
- 每个 `fonts` 或 `etc` 组件仍必须至少挂载一个真实目标；实际挂载或可见性失败仍执行完整回滚。
- 新增符号链接共享目标的回归测试，并保留 Alpha3 的零兼容目标失败保护。

## 安装与测试

1. 在 KernelSU 中直接覆盖刷入 Alpha4 模块 ZIP，不需要元模块。
2. 确认安装日志显示 `v2.3.4 Alpha4 / 20304`，然后完整重启。
3. 打开洛书刷新首页，检查挂载引擎不再显示异常。
4. 应用单字体或复合字体，任务完成后完整重启。
5. 检查状态栏、设置、通知、锁屏、浏览器和常用应用。

正常诊断应包含：

```text
moduleVersion=v2.3.4 Alpha4
selfMountState=mounted
selfMountFailed=none
```

受影响的 KernelSU 设备通常会显示：

```text
selfMountBackend=self-overlay-bind
```

## 版本信息

- 模块版本：`v2.3.4 Alpha4`
- 模块 versionCode：`20304`
- App versionName：`2.3.4-alpha4`
- App versionCode：`2030401`
- 发布类型：预发行测试版

本版本不会修改正式版 `update.json`。
