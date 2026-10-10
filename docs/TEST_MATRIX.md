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

## 弥散渐变 + 玻璃拟态启动（2026-10-11，替代 2026-10-07 单层方案）

- Android 12+ 系统 Splash 仍按平台规则只用不透明单色底（取弥散背景中心色 `launch_background`）＋中央静态玻璃球图标（内含同色弥散与原图标画面，`design/launch/build_launch_assets.py` 生成）。系统 Splash 以默认退出尽早露出原生准备帧＝启动壳第一帧（全屏弥散＋玻璃卡片＋「洛书」字标），无自定义退出监听、无 core-splashscreen。
- Android 9–11：启动窗口 `luoshu_launch_window`（全屏弥散位图＋颗粒＋首帧尺寸玻璃卡片），随后同一 Compose 启动壳。
- 启动壳 `LuoShuLaunchShell` 叠在已组合完成的真实首页之上（同一帧），色块缓慢漂移、玻璃上一次性高光扫过、卡片轻微落定，约 1.35 s 内淡出到首页；首帧交付、权限请求、模糊初始化均不等待它。系统动画缩放为 0 时静态显示并在首帧提交后立即移除。仅冷启动（非恢复、非任务入口）。
- `python3 scripts/android_launch_source_test.py` 校验接线、冷启动限定、不阻塞就绪、几何常量与生成脚本一致、亮暗资源、Splash 色与背景中心一致、字标对比度。`scripts/android_startup_visual.py` 逐帧识别：原生 Logo → Splash 溶解（混合拟合）→ 启动壳（字标裁剪＋低分辨率弥散场，容忍漂移）→ 首页交叉淡化 → 首页；启动壳回到首页之后、暖启动出现、黑帧和未识别帧均失败。
- 真实冷启动仍需分别观察亮/暗系统屏、Splash→启动壳衔接、淡出到首页、重复冷启动及崩溃/ANR。

平台边界依据：[Android Splash screens](https://developer.android.com/develop/ui/views/launch/splash-screen)。

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

## 切换状态读取性能回归（2026-10-06）

`python3 scripts/font_state_read_test.py` 必须使用真实 mksh 与 dash，支持通过
`LUOSHU_TEST_MKSH` 指定 mksh。候选工作流同时检查源码和最终 ZIP 内的读取器。
覆盖重复键取首项、缺失文件/键、无换行末行、CR 清理、空格/中文/反斜杠/等号、
状态内容不作为命令执行，以及现有混合配置 JSON 响应的一致性。

`python3 scripts/font_state_read_test.py --benchmark` 交错运行新旧读取器各六次，
输出全部样本和中位数。基准旧读取器对应 d890f89 的 sed/head/tr 管线。
本次 Linux 云主机结果：

- 19 行状态文件、200 次字段读取：mksh 373.8 → 74.1 ms；dash 346.7 → 55.3 ms。
- 真实 `mix_config_json_fast` 处理函数、隔离配置、10 次调用：mksh 262.4 → 141.4 ms；dash 240.9 → 119.3 ms。
- 每个字段不再启动 sed/head/tr；无外部程序 PATH 的测试核验新读取器仅用 shell 内建能力。

这是状态解析/配置响应处理阶段的主机基准，不含 Root 桥初始化、字体生成、校验、
挂载或设备 I/O，不能解释为整次手机字体切换的加速比例。未测量手机端耗时。
不缓存进程身份、清理证明或事务状态；进程安全检查、完整字形/覆盖校验、原子回滚和
冻结的 1.1.1 挂载核心均保持原逻辑。

## 2.2.2 的单次发布例外

维护者于 2026-10-06T13:36:26Z 明确确认将当前测试线以 2.2.2 合入 main、发布新包并更新 OTA，同时在发布说明保留手机组合与全覆盖仍未验完的限制。既有 `config/stable_release_authorization.conf` 仅为 v2.2.2 设置 `allowPendingDeviceMatrix=true`，不改变上方实际测试状态，也不免除源码、签名和最终成品门禁。下一版本须重新完成真机矩阵或取得独立授权。

## 3.0.0 的单次发布例外

维护者于 Sun 2026-10-11 1:26 AM CST (UTC+08:00) 明确授权合并组合字体对齐、英数微调、实例缓存与日志修复，并以 3.0.0 正式发布（非预发行）。`config/stable_release_authorization.conf` 仅为 v3.0.0 设置 `allowPendingDeviceMatrix=true`，不改变上方实际测试状态，也不免除源码、签名和最终成品门禁。下一版本须重新完成真机矩阵或取得独立授权。
