<!-- prerelease -->
# 洛书 v2.3.5 Alpha5

Alpha5 修复 Alpha4 在 Android 16 + KernelSU 真机上继续暴露的 `system/etc-bind-incomplete`。Alpha4 已成功越过 `system/fonts` 的绑定和内容验证，但 `system/etc` 负载可能只包含挂载探针、动态配置等附加文件，而当前 ROM 的 `/system/etc` 原本不存在对应文件。逐文件 bind 无法凭空创建目标，旧逻辑因此误判失败并回滚已经验证的字体挂载。

## 核心修复

- bind 回退明确区分实际挂载失败与零兼容目标。
- 非核心 `fonts`/`etc` 组件没有任何本机可替换目标时安全跳过。
- 被跳过的附加组件不会写入必需挂载清单，也不会触发后续假验证。
- `system/fonts` 仍是强制核心组件，必须至少成功接管一个真实字体文件。
- 任意实际 bind、挂载记录或可见性验证失败仍会完整回滚。
- 保留 Alpha3 的本机缺失别名兼容与 Alpha4 的符号链接真实目标去重。
- 新增“字体挂载成功、附加 `system/etc` 零目标”回归测试，并保留“零字体目标必须失败”保护。

## 安装与测试

1. 在 KernelSU 中直接覆盖刷入 Alpha5 模块 ZIP，不需要元模块。
2. 确认安装日志显示 `v2.3.5 Alpha5 / 20305`，然后完整重启。
3. 打开洛书刷新首页，检查当前字体和挂载引擎状态。
4. 应用单字体或复合字体，任务完成后完整重启。
5. 检查状态栏、设置、通知、锁屏、浏览器和常用应用。

正常诊断应包含：

```text
moduleVersion=v2.3.5 Alpha5
selfMountState=mounted
selfMountBackend=self-overlay-bind
selfMountFailed=none
```

## 版本信息

- 模块版本：`v2.3.5 Alpha5`
- 模块 versionCode：`20305`
- App versionName：`2.3.5-alpha5`
- App versionCode：`2030501`
- 发布类型：预发行测试版

本版本不会修改正式版 `update.json`。
