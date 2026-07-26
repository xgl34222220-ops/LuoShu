<!-- prerelease -->
# 洛书 v2.3.3 Alpha3

Alpha3 修复 Alpha2 在 Android 16 + KernelSU 真机上确认的 `system/fonts-bind-incomplete`。该故障会让已经成功的逐文件字体挂载被整体回滚，因此无论是否安装元模块，完整重启后都会安全退回系统默认字体。

## 核心修复

- 当只读 OverlayFS 不可用并回退到逐文件 bind 时，只替换当前 ROM 中真实存在的目标文件。
- 模块中为其他 ROM 准备、但本机原系统不存在的新增字体别名不再被误判为挂载失败。
- 每个参与事务的 `fonts` 或 `etc` 组件仍必须至少成功接管一个真实文件；没有任何兼容目标时拒绝提交。
- 任意实际 bind 失败、内容不一致或 PID 1 主命名空间不可见时，仍会逆序解除本轮全部挂载并安全恢复 ROM 字体。
- 首页“挂载引擎”卡片读取真实自挂载状态，不再因为模块文件存在就错误显示“正常”。
- 增加 Android 16 / KernelSU 对应的兼容 bind 成功测试，以及零兼容目标必须失败的保护测试。

## 安装与测试

1. 在 Root 管理器中直接覆盖刷入 Alpha3 模块包，不需要安装元模块。
2. 确认安装日志显示 `v2.3.3 Alpha3 / 20303`，然后完整重启。
3. 打开洛书并刷新；若之前已选字体，先观察它是否直接生效。
4. 再应用一次单字体或复合字体，任务完成后完整重启。
5. 检查状态栏、设置、通知、锁屏、浏览器和常用应用，并再重启一次确认持续生效。

若仍失败，请导出新的隐私诊断摘要。成功后的关键字段应为：

```text
moduleVersion=v2.3.3 Alpha3
selfMountState=mounted
selfMountBackend=self-overlay-bind
selfMountFailed=none
```

## 版本信息

- 模块版本：`v2.3.3 Alpha3`
- 模块 versionCode：`20303`
- App versionName：`2.3.3-alpha3`
- App versionCode：`2030301`
- 发布类型：预发行测试版

本版本不会修改正式版 `update.json`。
