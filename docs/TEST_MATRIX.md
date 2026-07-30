# 洛书发布测试矩阵

本文件记录自动化门禁和已经完成的真机验证进度，**不是 ROM 或机型支持白名单**。

洛书安装时会扫描每台设备的真实字体目录和字体配置，生成设备独立的原厂字体清单；运行时优先按照该清单映射系统 UI 字体。未列出的设备仍会执行完整扫描，只是尚未完成整套真机回归。

## 设备自适应机制门禁

- 扫描 `system`、`system_ext`、`product`、`my_product`、`vendor` 的字体目录与配置；
- 扫描 `odm`、`oem`、`my_region`、`hw_product` 作为扩展诊断来源；
- 解析实际存在的 `fonts.xml`、`font_fallback.xml`、`fonts_customization.xml`；
- 记录真实路径、分区、family、alias、字重、样式、TTC index、UPEM、`hhea` 与 `OS/2` 度量；
- 使用设备号和 inode 去重；
- 主题字体和活动字体挂载只记为覆盖证据，不混入原厂清单；
- 应用字体时必须优先使用有效的设备原厂清单；
- OTA 或系统指纹变化后必须使旧清单失效并重新扫描。

## v2.3.x 私有原子自挂载门禁

- 真实分区负载必须位于 `.luoshu-payload/<partition>`；
- 安装后的标准 `system`、`system_ext`、`product`、`my_product`、`vendor` 目录必须为空；
- 模块必须保留 `skip_mount` 与 `skip_mountify`，阻止外部挂载组件接管标准模块树；
- 生产路径固定使用 `self-mount`，不得读取或修改任何元模块配置；
- Mountify、Hybrid Mount、Magic Mount、meta-overlayfs 存在与否不得改变洛书挂载策略；
- KernelSU、SukiSU Ultra 与 APatch 必须在各自 OverlayFS 完成后的 `post-mount` 阶段自挂载；
- Magisk 必须在 `post-fs-data` 阶段自挂载；
- 自挂载只能覆盖洛书实际包含负载的 `fonts` / `etc`，必须保留 ROM Emoji 与 fallback；
- 实际包含负载的全部分区和目录必须一次性提交，任意组件失败都必须逆序回滚，禁止 `degraded` 半挂载；
- 提交前必须从 PID 1 主命名空间逐文件验证字体与配置负载；
- 重复执行不得叠加第二层挂载；
- 挂载失败必须 fail-open，不得阻断系统启动；
- 覆盖升级必须保留全部受支持 OEM 分区，旧启动挂载状态和验证结果不得迁移；
- App 和 Root 管理器仅在字体事务已确认且自挂载状态正常后把所选字体描述为当前已生效；正常开机不得重复遍历或哈希完整字体树；
- 深度 FontManager 与可见字体证据验证必须仅作为显式手动诊断，不得由开机脚本自动调度；
- 卸载必须逆序解除洛书记录的挂载并清理私有负载。

## 自动化门禁

- Shell、Python 语法检查通过；
- 原生 App Kotlin 编译、Lint 与单元测试通过；
- 唯一模块 ZIP 可构建，ZIP 完整性与 SHA-256 校验通过；
- 模块内 APK 与独立 APK 字节一致；
- 模块不得包含 `webroot/`，`module.prop` 不得声明 `webroot=`；
- 不得生成 Lite、App-less 或其他无内置 App 的模块变体；
- 全局字体必须通过中文、英文、数字和标点覆盖率门禁；
- 字体事务失败必须保留旧有效负载；
- 安装脚本不得在刷写阶段生成大型复合字体；
- 安装输出不得推荐、要求或引导配置任何元模块；
- 正式发布前必须执行完整源码检查、App Lint/测试、APK 签名校验与模块成品检查；
- Tag 和 Release 只能在所有验证完成后创建，已有正式发布不得覆盖。

## App-only 单包专项回归

- Root 管理器中不出现模块 WebUI 入口；
- 模块包始终内置 App，可通过模块“操作”按钮安装或更新；
- App 在任务运行中被划掉或系统回收后，重新打开仍能显示同一任务 ID 和真实进度；
- 字体任务完成后关闭再打开，仍显示待完整重启状态；
- 可变字体显示范围与最终实例化结果一致；
- 中文、英文和数字角色缺失时，在任务入队前直接拒绝；
- 模块内 App 与独立正式 APK 使用相同签名和字节内容。

## 真机验证进度

| 系统 | Root 管理器 | 其他挂载组件 | 私有负载隔离 | 自挂载 | 字体应用 | 恢复/卸载 | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ColorOS 16 / Android 16 | KernelSU / SukiSU Ultra | 无 | 待测 | 待测 | 待测 | 待测 | 待测 |
| ColorOS 16 / Android 16 | KernelSU / SukiSU Ultra | 已安装但不接管洛书 | 待测 | 待测 | 待测 | 待测 | 待测 |
| HyperOS 3 / Android 16 | KernelSU / SukiSU Ultra | 无 | 待测 | 待测 | 待测 | 待测 | 待测 |
| HyperOS 3 / Android 16 | KernelSU / SukiSU Ultra | 已安装但不接管洛书 | 待测 | 待测 | 待测 | 待测 | 待测 |
| 通用 Android | Magisk | 任意 | 待测 | 待测 | 待测 | 待测 | 待测 |
| 通用 Android | APatch | 任意 | 待测 | 待测 | 待测 | 待测 | 待测 |

真机至少确认：刷入后标准分区目录为空、`.luoshu-payload` 存在、能够完整开机、字体应用生效、ROM Emoji 保留、恢复系统字体正常、卸载后洛书挂载和私有负载消失。

## 发布规则

- Alpha/Beta/RC 只发布为 GitHub prerelease；
- 稳定版必须同步更新 `docs/device_validation.json`，最低要求 ColorOS 16 + KernelSU、HyperOS 3 + KernelSU、通用 Magisk、通用 APatch 四项均为 `passed`，并包含测试时间与验收证据；
- 正式版必须使用固定签名，并保留同一签名的历史 APK；
- 标签只创建一次，禁止移动或覆盖；
- 任一系统出现黑屏、二屏卡死、SystemUI 重启、批量闪退或方框乱码，立即停止发布并恢复上一可用模块包。
