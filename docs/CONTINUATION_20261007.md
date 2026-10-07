# 2026-10-07 洛书接续验收

## 基线与约束

接续 `claude/laughing-hypatia-ogd2oz` 的 `17888663a0fb64a7a63ed96c56f423d94a36a76d`。交接时的 main 为 `1776ed953b4b159b4ac8d112644c519522059e11`。本轮仅提交测试分支，不合并 main、创建正式发布、部署、操作用户设备或扩大安全敏感权限。

`scripts/stable111_frozen_runtime.json` 固定基线 `be39f598bfb921526851c5c4a2e92905dacf4ea7` 的 **22 个启动/挂载文件**，由 `scripts/stable111_rework_gate.py` 校验源码和最终模块 ZIP；不是“任意字体代码都不能修”。本轮保持这 22 个文件逐字节一致，保留 nohook、符号/Emoji 排除、原子暂存验证及失败保留旧负载。

## 原候选的真实结果

- [Build Test Candidate 37658629183](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37658629183) 在上述 SHA 构建通过。
- [Android UI smoke 37658629186](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37658629186) 在上述 SHA 失败。API 28 在字体库小视口没有观察到真实滚动；API 36 未找到匹配的自定义系统 Splash 移除日志。
- 同轮启动任务虽然绿色，原始 [Startup Visual artifact 11500294703](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37658629186/artifacts/11500294703) **视觉仍失败**。独立帧核对确认：亮色首页约 5 秒可见后，约 6 秒徽标再次覆盖；暗色首页约 6 秒可见后，约 7–8 秒再次覆盖，且此前有黑帧。缺少 `art_` 文件名不是无第二启动页的证据。

## 系统启动交接修正

移除自定义 `SplashScreen.setOnExitAnimationListener`，不再要求 Android 将系统启动视图复制进 Activity 的 decor。使用平台默认退场；真实 Window 和首页保留弥散渐变背景。第一内容帧、返回任务、stop、dispose 的状态通知仍保留。

原录像对应日志显示首页已经 Displayed 后才创建 SplashScreenView 副本。AOSP [ActivityRecord.java](https://android.googlesource.com/platform/frameworks/base/+/android16-qpr2-release/services/core/java/com/android/server/wm/ActivityRecord.java) 的 `transferSplashScreenIfNeeded` 与 [ActivityThread.java](https://android.googlesource.com/platform/frameworks/base/+/android16-qpr2-release/core/java/android/app/ActivityThread.java) 的 `createSplashScreen` 表明，自定义退场会触发复制及 `decorView.addView`，再交给回调。结合日志，迟到复制是本轮双页的有力解释；移除监听的效果仍必须由新候选的原录像验证。这是根据源码和实测顺序作出的推断，不覆盖所有 OEM 启动行为。

## 两台手机证据边界

用户既有设备记录为一加 15 / ColorOS 与 Redmi K80 Ultra / HyperOS。已有工程诊断确实含 Redmi/dali、HyperOS OS3.0 和 MiSansVF 槽位。最新脱敏诊断则为 SysSans-Hans 槽位，模块 2.2.2、SDK 37、25/25 诊断槽位、`templatePendingState=pending-stock-boot`，并有负载缺失记录。脱敏报告没有机型字段，不能据此认定它来自哪一台手机；较早 MiSans 报告的 25/79 是**诊断采样量**，不能解释为只替换 25 个槽。

所有本轮 host 夹具、非 Root 模拟器 UI、签名构建结果与两台 OEM 真机挂载/字形结果分别记录。原来的 `engineState=missing` 在 legacy 模式下也不能单独当作引擎缺失故障；要结合实际应用路径和负载证据。

## 字体覆盖与缓存修正

ColorOS 原厂度量对齐现在补齐可信库存中真实存在、可安全替换的直立文本 TTF/OTF 槽位，覆盖既有别名表未生成的目标，并沿用已有字重供体和逐槽度量壳。禁止向库存声明但物理不存在的文件写入；集合字体、集合 face、斜体、符号/Emoji、其他文字系统与框架符号链接保持排除。动态分区必须来自经过验证的分区清单；只有 `/system/<分区>/fonts` 别名、没有 `/<分区>/fonts` 实体的分区仍保守跳过，不能称为全覆盖。

切换缓存键升级为 `safe-switch-metrics-v2`，包含源文件精细时间戳、整个字体家族供体、库存/动态分区清单、ROM build 和映射 Python/度量策略；验证缓存单独覆盖验证器及源文件身份。家族字重编辑、增加或删除，及 Python 策略修改会使旧缓存失效。生成前记录完整键，保存前与发布前再核对；旧字重负载不能写入已变化供体的新键。缓存配置使用内建读取，文件尺寸优先使用 stat；保留失败回退与原子提交语义。

前台热切换在没有活跃预热任务时跳过等待函数中的重复缓存证明，随后的恢复仍执行完整校验；存在预热任务时继续检查其缓存并按原预算等待。SHA/配置字段解析使用 Shell 内建操作，策略文件以经过完整校验的规范记录参与最终键，避免重复派生哈希进程。

最终 [阶段基准原始数据](performance/safe-switch-20261007.json) 使用基线 `1788866` 和本轮精确源文件 SHA-256、同一 32 MiB 字节夹具、2 个供体、39 个别名、11 轮交错顺序。实际热阶段“验证缓存→预热等待→恢复”的中位数由 **68.442 ms 降至 37.428 ms（-45.31%）**；本轮最慢 43.703 ms 仍低于基线最快 63.033 ms。物理映射 237.104→232.714 ms 的采样重叠，不声称冷映射提速。夹具并非真实字体，环境是 Linux x86_64 / dash / GNU 9.4；不包含 Android 挂载、生成、提交或进程清理，不代表整次手机切换快 45%。该结果替代本轮较早的中间基准。

Google 兼容沿用基线已有实现，本轮重新运行回退、集成、Provider 生命周期和诊断回归共 144 项。上述回归仅证明这些分支的夹具行为，不能替代 Google 真机页面的像素验收。

## 验收方式

启动视觉门禁独立于功能 UI：解码原视频的每个帧及其原始显示时间，比较真实原生徽标和本次首页的两个语义文本区域，记录黑帧、未分类帧及首页后再次出现徽标。亮/暗冷/热启动都保留 MP4、Window、同 PID 和日志；热启动还核对进程未变化。测试不能通过截图文件名或仅有 `content_drawn` 日志得出视觉通过。

API 28 字体库滚动根据真实滚动容器边界发送手势，记录可见文本锚点的方向性移动与滚动结束，且必须触达展开管理区域下方的实际“清除筛选”控件。仍保留小视口、真实内容、跨页/后台滚动位置要求，不注入字体或 Root 状态。

提交前专项回归：缓存/别名 12 项、ColorOS 度量/补槽 18 项、HyperOS 度量 17 项、CJK 路由 24 项、启动源约束 11 项、UI 验收帮助函数 44 项、逐帧分类器 5 项、Google 兼容 144 项均通过。22 个冻结文件保持一致。完整源码门禁、mksh、Android 编译/lint/JVM 和模拟器真实画面结果以该提交的 CI 为准。

首次接续 SHA `89fd1ab1b21e4f4c45accfd6a1a69734cd775e2c` 的 [候选构建 37667455319](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37667455319) 在生命周期预热夹具的两项缓存生成断言失败：夹具没有带上新的策略依赖，生产代码按设计拒绝发布缓存。修正夹具只补充 12 个必要策略源码依赖后仍保留所有操作替身与原断言，没有削弱缺失依赖时的拒绝规则。同 SHA 的 [UI 37667455350](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37667455350) 已通过编译、JVM 和 lint，但视觉任务因 runner 没有 ffmpeg 在录像前失败；后续工作流显式安装并保存 ffmpeg/ffprobe 版本。API 28 功能验收在配置改变后遇到只有根节点的瞬时可访问性树；API 36 的 400 ms 拖动遇到约 1.2 s 重渲染帧，只移动 118–166 px，8 次未达中文帮助入口。修正为最多 8 s 等待真实后代节点，并将搜索拖动延长至 2000 ms；真实目标、端点、8 次手势/90 s 共享预算、位移/结束及 ANR 断言保持不变，原单节点 XML、手势证据仍保留。修正后的生命周期 9 项、UI 帮助函数 47 项通过。该首次失败不作为成品通过证据。字体运行文件与上述最终基准哈希保持不变。

## 必须继续保留的未验收项

- 97 秒首次 zygote 前异常的根因未确认。正常启动录像或新的默认退场通过，均不能把这项回填为已解决。保留旧同 PID、ANR、starting-window 与原录像，后续需复现并关联证据。
- 两台真机中英数字/各字重/系统与 Google 页面、单字体与组合的连续 A→B→A、完整重启后的覆盖效果。
- ColorOS Google 复发现场：先导出既有只读现场诊断，区分组件修订重置、旧 FD/mmap、内存 Typeface、Provider 缓存、应用内置与网页指定字体。组件状态通过不能代表像素效果通过。
- 手机端切换全程及生成、映射、验证、提交、进程清理阶段耗时。主机阶段基准不能换算为整次手机切换速度。

本轮最终 SHA、CI 终态、制品 SHA-256 和逐项结果由交付报告固定；在真实运行前不填写通过。

## c49e5ad 后续失败与修正

`c49e5ad7dd7d059608fa4a4b6dedd9f0b1d4c73f` 的候选构建 [37670249386](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37670249386) 在 `SwitchProviderTest.test_real_switch_router_commits_only_successful_stages` 断言没有缓存配置而失败，签名和 APK/模块构建均未运行。该独立夹具也没有复制完整 mapper 身份输入；补齐 13 个必需文件后原 6 项断言全部通过，生产缺依赖拒绝规则、实际 router、暂存/回滚测试不变。失败产物仅为源码检查日志，不是安装包。

同 SHA 的 [UI 37670249577](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37670249577) 编译、JVM 与 lint 通过，功能 API 28 和 36 仍失败。API 28 第一次平台快照耗费约 11 秒后，独立 helper 返回了只有根节点的树，外层 8 秒预算已经耗尽。helper 现在在原有内部 8 秒窗口中、同一 UiAutomation 连接上等待真实可见子节点，并记录不完整根节点数量；不把根节点当作可用内容，也不延长滚动/搜索预算。

API 36 保留真实同 PID ANR：主线程等待 `RenderProxy::setStopped`，RenderThread 阻塞在 `qemu_pipe_read` / `glCreateProgram_enc`。当时系统总体 CPU 约 99%，Launcher、SystemUI 和 GMS 也留下启动饥饿日志；helper 在该 ANR 之后才创建，不能用 helper 修正声称这项 ANR 消失。工作流针对这份证据将模拟器 RAM 从 2 GiB 调为 4 GiB，并将 emulator 37.2.12 的 `swiftshader_indirect` 改为官方支持的 `software` 后端（[Android 官方图形选项](https://developer.android.com/studio/run/emulator-acceleration)，旧选项自 36.4.9 弃用）。动画、API、真实内容和 ANR 拒绝规则保持不变。是否消除图形阻塞必须由后续运行确定。

逐帧门禁进一步拒绝缺失、非有限、负值或非严格递增的原始 PTS，以及 ffprobe/ffmpeg 返回 0 但输出错误日志的输入；失败诊断与部分已解码帧仍保存。冷启动必须实际拍到原生徽标，否则记为录像覆盖不足，不能据首页画面判定双页已修复。热启动必须先获得一个有效的现存 App PID，随后严格比较同 PID；原有空 PID 跳过路径已移除。新门禁 14 项、UI 帮助函数 49 项通过；尚不替代新原录像的独立人工核对。

## 6af650c 原录像否决与首帧提交修正

`6af650c388d966f3bb242f4c7241c9012bdd79bb` 的 [候选构建 37673679492](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37673679492) 完成所有步骤：源码门禁 39 suites / 677 tests（构建模块时原样再运行一次）、补充检查 54 tests、最终包验证 204 tests 全部通过。模块 70202、release App 7020201，最终 ZIP 内 APK 与独立签名 APK 字节一致，冻结 22 个文件及 helpers5 校验通过。这只证明构建及包验证，不构成安装交付许可。

同 SHA [UI 37673679437](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37673679437) 的 JVM 211 项与 lint 通过；API 36 功能完整通过，31 次捕获 / 30 张独立 PNG，包括字体库实际滚动、跨页/后台/旋转保持、主题、禁用动画、再次冷启动和完整中文 Google 说明。Google 整体使用共享预算中的 3 / 8 次真实手势。原日志没有洛书 ANR/崩溃，但有一项无关 GMS broadcast ANR，不能写成模拟器全系统无 ANR。API 28 在第 55 次 hierarchy 请求失败：前一次已有组合页 70 个真实节点，实际页面与焦点一直可见，同 PID、无 ANR；helper 的 8 秒内只有一次不完整根节点，其后查询为空。缓存/窗口跟踪原因尚属推断，不能据此忽略失败。

四段新原录像共 159 帧：亮冷 56、亮热 39、暗冷 40、暗热 24。独立解码/逐格审阅未见首页后徽标回盖，热启动同 PID 且未见 branded logo；但暗冷帧 23–27 在 3.072333–4.186622 秒为真实黑空屏，帧 28（5.104889 秒）才见首页，故候选视觉仍失败。原视频和原失败 JSON 不覆盖。`ffmpeg -vsync 0` 导出 rawvideo 使用默认 `1/framerate` 时基导致 DTS 舍入错误；显式使用 demux 时基后四视频错误输出清空、原始 PTS 和全部 RGB 字节哈希保持相同。这一工具修正不改变黑屏事实。

暗冷同 PID 4927 日志：19:28:39.975 开始 decor 绘制；40.976 SurfaceSyncGroup 在 1000 ms 后强制 ready；40.983 系统 Displayed；43.592 才交付真实内容提交。HWUI 第一帧 IssueDrawCommandsStart→SwapBuffers 约 3451 ms，而主线程录制约 181 ms。首次就捕获完整页面并初始化模糊/七采样折射链是优先待验证的开销来源；日志不能精确量化每个 shader，也没有默认退场 native-removal 回调时间。

后续实现保留默认平台 Splash 退场和首帧真实首页/渐变/玻璃底色/高光/边框，将离屏捕获、模糊与折射推迟到首帧真正提交后。API 29+ 硬件使用 [registerFrameCommitCallback](https://developer.android.com/reference/android/view/ViewTreeObserver#registerFrameCommitCallback(java.lang.Runnable))；它证明 rendered/submitted to swap chain，不证明已经显示。API 28 或软件渲染则使用绘制返回后的 post，并在日志中明确区分。没有设置等待秒数、最短 Splash 时长或复制第二启动页。直接用于 Activity 的纯策略覆盖六项提交/回退/销毁/重复/重建行为；Android 编译、这些 JVM 测试和新的原录像仍须由后续准确 SHA 验证，不能先写黑屏已修好。

API 28 helper 在同一连接、原 8 秒内用 public `AccessibilityNodeInfo.refresh()` 重查保留的不完整真实节点，并输出 package、windowId、可见子节点、refresh 成败及窗口计数。过时或超期节点不能写成有效 XML。其缓存解释仍是待新运行检验的推断，失败门禁保持。视觉录制之前则在最多 10 秒内解析真实 HOME component、确认 Window 焦点，并要求排除真实系统栏后的原截图内容连续三次完全相同；所有原 PNG/Window 都保存。该等待发生在启动前，只为确定原录像基线，不改变 App 动画或 30 秒录制，也不能用它替代启动耗时。

真实系统窗口缩放过渡使用有界统一变换匹配：scale .65–1.05（.005 步长），归一化 360 宽的 x±20/y±80；两个真实首页语义 crop 必须命中同一个 scale/dx/dy，取较低分数。完整原生/首页 .92、过渡 .72 的门槛不变；任意缩放徽标在首页之后或同 PID 热启动中出现仍失败。新回归夹具来自 `6af650c` 原视频，逐张记录视频 SHA、原帧、PTS 和 PNG SHA，没有按帧号/时间放行。20 项逐帧门禁回归通过，原 `1788866` 的真实回盖和黑帧仍拒绝；修正工具重读 `6af650c` 后仍拒绝暗冷的空背景/五个黑帧及亮热的未稳态基线。新的 App 修改必须重新录制验收，不以重读旧片通过替代。

首帧修正 `a8ccc9c24e4f4539b5aed51a9c8a65d171724849` 的 UI CI 在 51 项辅助测试中因未安装 Pillow 报出三个 import errors；JUnit 与后继模拟器未运行，lint/APK 编译成功不能覆盖这些缺项。工作流补齐与逐帧任务相同的 Pillow 12.3.0，且两条工作流的 paths 相互包含，保证仅修改验收工作流也会生成同一准确 SHA 的候选与 UI 证据；不取消旧作业。

同 SHA 的源码门禁在 671 项 Python 测试与字体缓存检查通过后，因 `font_library_ui_layout_test.sh` 的旧 `blurActive` 静态表达式断言而失败。独立 `sh -x` 复现了该位置；修正保留原 `appearance.blurEnabled`、`appearance.glassEnabled` 和 `dockCaptureRequired` 条件，同时明确要求新 `firstFrameCommitted` 条件，未删除布局或运行时门禁。该布局、六项玻璃层级与之后八个稳定性/缓存/安装器/任务交接/库存扫描脚本均通过本地主机回归；最终完整门禁与原录像仍以修正后的准确 SHA CI 为准。

## 9dcd11d 终态与验收工具接续

`9dcd11d8ffa089e76b98788895f05db205dc14cd` 的 candidate [37679734635](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37679734635) 与 UI [37679734873](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37679734873) 均已失败终态。candidate 的 38 suites / 671 tests 与字体验证缓存检查通过，随后命中上述旧布局文本断言。UI build 的 217 JVM tests、lint、helper 编译通过；API 36 在字体库实际滚动后，单次 300 ms 反向手势未移动可见锚点，30 秒内没有找到完整四项底栏，17 次捕获 / 11 项检查后失败。API 28 已通过库滚动、跨页、后台、旋转和两轮快速导航，最后第 70 次 hierarchy 请求在原 8 秒内始终没有实际可用子节点，28 次捕获 / 20 项检查后失败；未见 App ANR，不能直接归因为 App 卡死。原失败 ZIP、XML、日志完整保留。

同 SHA 视觉任务在 App 启动之前无法于 10 秒内取得三次稳定 HOME 内容截图；随后热启动的空 pidof 错误掩盖了冷启动原因。没有生成原 MP4，故不能验收首帧修正，更不能把 build 或旧候选的绿色结果作为新启动视觉通过。新的基线采样在一次真实 adb exec-out 中执行 `dumpsys window displays` 与 `screencap -p`，保存整个二进制响应、Window、原 PNG 与 stderr，并严格检查唯一分隔符、PNG、真实 HOME 焦点和真实系统栏 Insets；仍保持原 10 秒及三次完全相同内容要求。冷启动失败链和暖启动 PID 缺失分别保留，不改变 App 启动或录像时序。

UI helper 在原公开 UiAutomation 权限下改为一次真实长连接，nonce 私有目录与每次唯一请求 ID/文件名绑定；逐次读取真实树，不接受旧 XML、错配响应、部分 JSON 或失败根节点。原 8 秒根节点等待和整个首请求（含连接就绪）的 20 秒 host 上限保留，失败不重建连接掩盖现场。正常结束必须收到同 nonce 的关闭确认并清理自己的私有文件；退出失败仅停止该测试 helper，仍判失败，绝不停止 App、系统或 GMS。诊断失败也记录到失败 summary，保留原错误与 App ANR。

QuickReturn 仍按真实 App 边界执行单次同方向/同距离反向滑动，仅将 300 ms 调整为已有搜索手势的 2000 ms，避免同步 DOWN 等待耗尽 MOVE 时段；原 30 秒总预算包含该手势。必须真实发现完整可用四项导航，不点击不可见坐标；前后原 XML、锚点、手势实际耗时和失败原因均归档。布局及六项玻璃源检查、启动源 11 项、UI host 62 项、长连接 host 14 项通过；真实 Java 编译、API 28/36 和亮暗冷热原录像仍待新准确 SHA CI，不能声称已通过。

用户新增反馈作为独立优先项：HyperOS 与 ColorOS 的遗漏槽位和 ColorOS/Google 回退、连续 A→B→A/实时及重启后覆盖、整次切换及阶段计时、HyperOS 合成/应用生成超时与仅限拥有任务的清理、ColorOS 整机重启超过两分钟、App 加载耗时、全局字重移除。旧 600/630 秒属于合成/应用生成，97 秒首次 zygote 前异常和库存扫描启动计时都不等于整次手机 reboot；此前 45.31% 不等于手机整次提速。冻结 22 文件、1.1.1 挂载核心、nohook、玻璃和失败门禁均保持。新功能修正与真机证据分别报告。

## OEM 覆盖、全局字重与切换阶段的功能接续

HyperOS 补齐来源现在复用 ColorOS 已有可信库存证据：真实实体目标、扫描/XML UI 文本槽、直立单字体 TTF/OTF、face 0、可信原厂度量、安全分区清单以及独立暂存包含关系。Redmi 历史 engine ZIP（SHA-256 `e5b3501c6be89727d5ff7ab528c11c74520b8b72dbf44cf986a7d3d040aad9f7`）内 51 个 UI 库存路径中，原物理文件名规则涵盖 30 个，另有 16 个可信但遗漏的槽，5 个因集合/斜体/藏文时钟排除。主机使用占位实体路径与真实合成 TTF 供体复现后生成 46 个库存别名、16 个补齐槽、0 个度量 fallback；没有读取当前手机文件系统或原厂字体字节，不能称为手机覆盖率。框架动态别名和 nohook 保留。

ColorOS Google/Latin 主槽现在使用既有可证明的 stock CJK 路由：仅移走本次确实已生成的 fallback 供体覆盖的新增 Han/标点，保留 stock 标点、Latin/数字/全角、UVS 及不能证明有 fallback 的字形。缺乏 fallback 时仍保留原 Han。跨字体 A→B→A 的主机字体输出与复制回归通过。共享暂存写入拒绝分区父目录/字体 store 链接外逃；度量报告用唯一排他临时文件和原子替换，别名临时叶先隔离旧链接，原 live/外部 inode 不被软硬链接或中断残留文件改动。最终 ColorOS 27、HyperOS 28、CJK 25，共 80 项通过；独立核对实际 stage_verify→不可变 live 代→冻结 atomic bind/visibility 枚举保留新槽。内核挂载是主机替身，真机覆盖仍待验证。

全局字重界面原已移除，但后端仍可写系统 secure 值。此次删除后端实现；旧 set/reset/status action 在任何 helper/公共目录迁移之前直接返回已移除，备份不再导出/恢复旧字重配置。冻结核心内的旧回放/卸载恢复字节未改；正常模块入口通过非冻结 util/uninstall 包装中仅拒绝 `put secure font_weight_adjustment` 的 Shell 函数阻止回放（含 --user），其他 settings 参数和返回码原样传递。没有改系统二进制、跨进程 hook、用户已有值或旧记录；冻结安装器仍可能复制旧记录，但模块正常运行不会应用。实际冻结 service/uninstall 路径的拥有/无拥有配置测试和备份回归通过。Google/Provider 等相邻主机 207 项、修订字重策略 8 项通过；真实 mount namespace 因主机权限明确跳过，不提高权限。

安全切换 worker 添加 `[SAFE-TIMING]`：以 `/proc/uptime` 的 Shell 内建读取记录同任务初始化、源查找/验证、预热、锁恢复、克隆、清理旧文本、缓存恢复、映射、ROM 补齐、缓存保存、校验、状态/事务提交、实时挂载、收尾与 EXIT 清理的单调阶段及总毫秒。总记录明确 `scope=safe-switch-worker`，不包括独立合成或整次手机 reboot；子进程回收以外层同 token 的 `.cleanup.json` 为准。取消/超时真实主机行为回归清理 double-fork/setsid/忽略 TERM 的拥有子进程，保留无关 sentinel，8 项通过，没有复现当前进程泄漏，未扩大清理范围。初始化日志/trap 建立之前的失败仍只由 supervisor 清理证据覆盖。变化的 mapper 身份会使旧缓存一次失效，确保新覆盖策略不能复用旧负载；更新后的首次生成耗时须单列。

本次最终 safe-switch 字节的 [再次阶段基准](performance/safe-switch-20261007-current.json) 保留原 32 MiB/2 供体/39 别名、11 轮交错、基线 1788866：热验证/等待/恢复中位数 76.064→37.938 ms（-50.12%），当前最慢 44.414 ms 小于基线最快 68.139 ms。物理映射 248.234→256.781 ms（+3.44%）且样本重叠/噪声较大，不声称冷映射提速。此轮同样只是 host 合成字节夹具的子阶段，不证明手机整次切换、生成或 reboot 提速；旧 45.31% 原始数据不替换。

验收工具提交 `03cf4b38dcc0be3bd38c7fa847373daf69855d3a` 的 UI [37686345563](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37686345563) 在 App JVM/lint/APK 与 62+14 host 回归通过后，独立 helper 直接 android.jar 编译缺少 lambda 的 LambdaMetafactory 而失败；完整模拟器和原录像未运行。将唯一文件过滤 lambda 改为等价 FilenameFilter 匿名类，保留私有 nonce/request/20 秒及 8 秒协议不变，重新编译仍以新 SHA CI 为准。该中间提交 candidate [37686345456](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37686345456) 此时仍在运行，不取消，不提前记成功。

## 实际 App 多字重合成链修正

实际 App 路由为 font_mix_controller→legacy mix_router→v14_mix→v143/v142；既有 common/multiweight_mix_task 的 prepared-v8 静态合约并不执行这条链。真实小型 VF 复现 v143 完整 worker：旧 helper 无变量隔离，在首档后将外层 family/role 与 CJK/Latin/Digit 改为临时路径，200 字重查源失败（rc 1、仅 3 次实例化）。prepare_source/run_instance/build_composite_cached 改用 POSIX 子 shell 隔离，完整九档名字、字重及保存的原组合 family 都有行为回归，不以字符串 grep 代替 worker 执行。

同一任务的 fixed 源选择首次绑定后使用私有不可变快照。初次复制必须满足 source-before SHA、copy SHA、source-after SHA 一致，才发布；key 含源内容、角色、完整有效轴与实际实例生成器摘要，生成器变化、错误输出与失败验证拒绝发布。已准备字体命中也执行真实验证，损坏会重建；自动字重轴各自分键，不串用。快照/准备缓存优先放进 supervisor 拥有的 task tmp，取消/超时后连同后代回收，不加大超时、不清除其他任务/GMS/系统缓存。

[合成准备证据](performance/legacy-mix-prepare-20261007.json) 中独立成功的同输入 driver：中文 auto、Latin/digit fixed 的九档准备由 27→11 次实例化、5.1431→2.6819 秒，27 个输出总 240408 字节，前后 SHA-256 均 `251b6bace0ac2faf01103bcc59aabda97ea2a314ad4f06dabbad49692af1cedc`。单 fixed 槽由 9→1 次、1.6774→0.4338 秒，九份均 8904 字节且摘要一致。完整旧 worker 已失败，不能用这些数字声称旧完整任务提速；修复后完整 worker 九档成功、11 次调用、4.4446 秒只是当前 host 夹具结果。11 项新行为回归通过并独立复核，包括源删除/复制竞态、不同轴/角色/任务、损坏缓存、生成器竞态、真实 timeout/cancel 清理。没有 Android/手机生成耗时证明，也没有历史 600/630 秒现场收据，未把它定为历史超时根因。

未活跃 common/multiweight_mix_task 仍存在类似的旧 helper 全局状态问题，本次未重复重写该未由 App 执行的链；其静态合约仍保留，不能代替上述活跃链行为证明。最终候选 ZIP、mksh、Java helper 编译、API 28/36、亮暗冷热逐帧结论必须由随后提交准确 SHA 的 CI 固定。ColorOS 整机两分多钟、97 秒 prezygote 根因、两台手机实际字形/Google 回退/实时与重启后覆盖、完整切换前后计时都明确保留待真机验证。

## bdc0267 的真实终态与验收读取修正

`bdc026796efc095651cc83a2ef03670bf9bfd2d9` 的 [candidate 37689177978](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37689177978) 在新合成夹具中 10/11 项失败。原始生产生成器子进程实际报 `ModuleNotFoundError: No module named 'fontTools'`：源码门禁通过 PYTHONPATH 提供 pure FontTools，夹具却清除该路径，开发主机的全局安装掩盖了错误。相同无全局 FontTools 的 venv、外置 pure 4.63.0 复现原夹具 10 项失败，修正为显式使用已导入包的真实目录后原 11 项全通过，真实生成器、字节/轴/九档输出、超时与取消清理断言均保留；生产代码和预算未为此更改。夹具同时保存真实子进程 stderr，避免生产临时错误文件删除后失去原因。

同 SHA 的 [UI 37689178038](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37689178038) 终态失败。App 的 217 项 JVM、lint、APK、独立 Java helper 编译及 62+14 项 host 回归通过；API 28 完成 35 屏、24 项真实 UI 检查，包含滚动、跨页/后台、旋转、连续导航、旧主题和 Google 兼容入口。API 36 仅完成冷启动和首页，随后 45 秒字体库门禁失败。原 hierarchy 10/20/42 已有字体库正文和搜索文案，但底栏仍返回旧首页的 selected/clickable 状态；这支持持久连接缓存未更新的假设，尚非已证根因。读取器在 API 34+ 的原八秒预算内通过公开 UiAutomation.clearCache 清理**本连接的节点缓存**，失败直接拒绝并记录结果，API 28 保持原读取路径。没有清理 App、GMS、系统的文件缓存、重连、注入状态或采用 shell 权限；仍要求实际选中属性与正文同时正确，效果以新 SHA CI 为准。

本批启动视觉在 HOME 基线阶段未达到十秒内三张稳定帧，四段 App MP4 均未开始录制，不能称为启动视觉通过。原 batch、两张完整 PNG、截断输出、窗口、错误、完整作业日志和 ZIP 均保留。先前 `03cf4b3` candidate 的模块重跑在 legacy_mix_finalize_race_test 内静默退出；原 nested handoff 与 34% 进度门禁均已通过，具体内部断言没有被日志记录，十一轮有限 sh -x 复现全通过。此次仅让该隔离夹具在源码门禁保留命令追踪，不降低断言或据此修改生产 finalizer。

API 28 的再次冷启动原 am 输出为 ThisTime 2202 / TotalTime 173202 / WaitTime 2729 ms。同 PID 9449 在 21:43:28.994 创建，首 draw-return 内容日志约 1997 ms，21:43:31.193 的系统 Displayed 为本次 +2.202 秒并另列 total +2m53.202s。TotalTime 不能冒充本次命令等待或手机 reboot；累计起点遗留仅是解释这一平台字段的推断。脚本原 ui_ready_seconds 23.587 包含启动、层级等待、截图和日志/窗口采集，不是纯首帧耗时。API 28 的 draw-return、API 29+ 的 swap-chain 提交、系统 Displayed、原录像实际可见内容仍分开记录，普通本轮启动不能解决旧 97 秒 prezygote 异常。

HOME 基线改读原始 screencap 像素，保留 batch/独立 raw/窗口/stderr，并按实际 SDK 解码明确的 header、RGB/RGBX/不透明 RGBA 与 sRGB，拒绝未知格式、色域、alpha、截断或尾随字节。官方 Android 8.0 是十二字节 header，8.1 起是十六字节；主机 PNG 只逐像素无缩放编码，记录原 raw 与 RGB 摘要，不能作为原生 PNG 冒充设备输出。仍只排除实际系统栏、保持十秒内三张内容完全一致的帧，另要求 resolved Launcher 的真实可见 workspace/hotseat 与带文字的有效点击后代，不能把 Launcher 中央图标当就绪桌面。解析、存盘、原始采集和匹配的真实层级读取都共享该十秒预算；会话可选更短 host deadline，默认二十秒与设备八秒 root wait不增加，也不重连。切入独立读取后继续使用同一 backend，避免 CLI 抢占连接。新增阶段耗时将 HOME resolve/采集/解码/PNG/层级，以及 App 命令/页面等待/截图/证据采集分别记清。68 项工具与 18 项会话行为回归通过，实际速度和四段原录像仍须新 SHA CI 验证。

## ee7de2bb 真实采集阻塞与无损传输接续

`ee7de2bb38729e7104e0d3f90a1e8a4627254c48` 的 [candidate 37693635259](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37693635259) 已成功终态，实际两轮源码检查各 41 suites / 721 tests / 41 OK，补充 4 suites / 54 tests / 4 OK，最终包验证 9 suites / 204 tests / 9 OK；签名 App 和模块均构建成功。同 SHA [UI 37693635213](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37693635213) 的 build 完成实际 XML 34 suites / 217 tests、0 failure/error/skip，lint、Java helper 与 68+18 host 回归通过。API 36 完成 31 屏 / 20 项功能检查（238.46 秒），包括实际字体库选中与正文、滚动、跨页、后台、旋转、连续导航与 Google 说明入口；这是非 Root 模拟器 UI 证据，不能替代 Google 字形或 OEM 挂载验收。API 28 在写入这条记录时仍运行，不能提前填写通过。

启动视觉任务已失败终态，原 artifact 11514602583 为 4,884,277 bytes、SHA-256 `c0b2ca344d77b71d46877de9181ca4a5f998a3ab5954842a68c509e237a63d57`，32 个成员、0 MP4。独立审阅实际查看了原暗色 PNG 和亮色 raw 的原尺寸精确 RGB 解码图：都只有壁纸及中央 Launcher 图形，没有桌面 workspace/hotseat 内容。亮色首个 17,988,814 字节 batch 耗时 6.145695 秒，当时 navigationBars 是零尺寸且 invisible，6.587 秒在系统栏裁剪校验处失败。暗色首个 batch 耗时 6.618339 秒，系统栏已有真实尺寸，但首次测试连接握手只剩约 2.750414 秒，于总 10.004 秒超时。两个 samples 都为空，warm App PID 也未建立；不能把它当成新 App 黑帧、卡死或启动视觉成功。原 GMS persistent ANR 保留，尚不能归因于洛书或证明它就是采集阻塞根因。

必要修正只调整证据采集：设备用 gzip -1 无损传输 packed screencap，以 mksh pipefail 拒绝捕获或压缩失败；保存原 batch、原压缩帧、严格单 member/CRC/ISIZE/EOF/无尾随数据校验后的原 raw、完整 RGB PNG、Window 和 stderr。每个 sample 的全新匹配 hierarchy 请求改在 raw 传输之前，仍与 HOME resolve、连接就绪、原始采集、解压、存盘、PNG 编码和稳定比较共享原十秒 deadline；不在预算外预热、不重连、复用旧 XML、调整视口或动画。PNG 先完整保存，随后才做实际系统栏与桌面验收，保证失败现场也有逐像素证据；三张内容完全一致、真实可见桌面和原八秒根节点条件不变。实际传输速度和四段新原录像仍必须由下一准确 SHA CI 检验，不能用本地主机压缩或回归数字宣布完成。

本次两文件修正的适用 host 回归为 UI 帮助函数 72、会话 18、逐帧分类器 20、启动源约束 11，共 121 项全通过，原失败系统栏/桌面/共享 deadline 断言保留；实际 shell 管道还验证 Window 不进入 gzip，捕获退出码 7 由 pipefail 保留。该计数是本地主机工具回归，不能回填未生成的原录像或提前给下一批 CI 通过。

## 59cd6627 的独立终态失败与旧 API 读取兼容

同 SHA 的 [candidate 37696153142](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37696153142) 已成功终态，App、模块构建与最终包验收均完成；候选原 artifact 11516421640 为 12,340,203 bytes、SHA-256 `17412d64749d7ff5408c343b1d37c2bd850a3a0c5a2b8c9b4ada40379e7830c0`。这是该 SHA 的包构建结果，视觉失败仍禁止将其当作可安装交付。

`59cd66273712a4d94052d0720c692155016b6248` 的 [UI 37696153318](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37696153318) 已失败终态。build 原 XML 为 34 suites / 217 tests、0 failure/error/skip，lint、完整 Android helper 编译与 72+18 host 回归通过。API 36 原 artifact 11515973109（50,879,859 bytes，SHA-256 `93c0d8b3c5b41619315ecead10db3744c5bf1fcf8a05f8ea59f3c2b22e4434b8`）通过 31 次捕获记录 / 30 张独立命名 PNG / 20 项检查，300.54 秒；包括字体库正文及 selected 属性、真实滚动与 QuickReturn、后台/旋转、连续导航和 Google 说明。这是无 Root 模拟器功能 UI，未执行手机字体替换。原日志有 Google 服务 ANR；未记录洛书 App ANR，不写成整个环境无 ANR。

API 28 在原 45 秒首页门禁失败：四个同一会话、匹配请求各在原八秒窗口内未取得可访问性根节点，0 张验收截图 / 0 项完成检查。原 failure.png 实际是完整玻璃首页，原 am TotalTime 为 2568 ms；同 PID 4787 的系统 Displayed 为 +2.568 秒、内容 draw-return 日志约 2066 ms，最后 ANR 记录为空。截图和无 App ANR 均不替代层级门禁，也不能将失败直接归因为 App 卡死。原 artifact 11516170726（1,024,789 bytes，SHA-256 `9a92c9a93dd3a1f8e9dca2716b9382bce3e7ae93bbe5d4b093c29f6fa5f14074`）保留完整原日志和窗口诊断。

API 34 前没有公开的 UiAutomation.clearCache。旧 API 的读取器现在在同一原八秒窗口中，使用公开 getServiceInfo / setServiceInfo 重新提交原配置对象，随后回读，严格比对 flags、eventTypes、feedbackType、notificationTimeout、packageNames、capabilities 及 API 29+ 的两项 UI timeout。配置为空、变化或任一阶段超预算均失败，保存前后配置与阶段耗时。Android 9 公开 setter 清除客户端可访问性节点缓存，但本次空根节点是否由缓存造成仍是推断，须由下一准确 SHA 的真实模拟器验证；不修改配置、重连、增加权限或清理 App/GMS/系统缓存。API 34+ 原公开 clearCache 分支保持。

同 SHA 视觉作业在 ffmpeg 安装准备时于 180 秒退出 124，原 artifact 11515902600 为 300 bytes、SHA-256 `00d88ac5fd07cf0296856a7d34bf7e5efad392e7ca159d8aa1f026ab3515bb21`，仅两个空 apt 日志；模拟器、HOME 基线、gzip 传输和四段原录像均未执行。因此不评价新传输速度或首帧效果，更不交付安装包。后续仅去掉 install 的静默输出，保留原 180 秒/两次重试/网络单请求 30 秒预算及签名验证，并在失败时保存只读包状态和不含参数的进程表，保留安装与日志写入的真实退出码；不停止包管理器、不清缓存。原失败证据不覆盖，新 helper 的完整 SDK 编译、API 28/36 与原录像仍需下一准确 SHA 的完整 CI。

修正后的适用 host 回归实际为 UI 工具 73、会话 18、逐帧分类器 20、启动源约束 11，共 122 项通过。新增一项 host 测试真实编译并执行生产 Java 方法与原 SDK 分支的 24 个配置/空值/预算/现代 clearCache 行为案例；这是 host 控制流测试，不是 Android 窗口验证。完整 SDK helper 编译本地未运行。实际 Bash 管道另验证 upstream 0/124 与日志写入 0/7 的退出码均保存，工作流 YAML 和真实准备脚本 bash -n 通过；未扩大任何验收预算。

## 942255ab 真实零矩形失败与连接阶段诊断

`942255abbcb92f712dc85a4ae49b9ac43a63dcb5` 的 [candidate 37698733037](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37698733037) 已成功终态；两轮原源码检查各 41 suites / 721 tests / 41 OK，补充 4 suites / 54 tests / 4 OK，包验证 9 suites / 204 tests / 9 OK。重复轮次不能记成 1700 项独立测试。原 artifact 11517940045 为 12,340,200 bytes、SHA-256 `c34ebdabe5ee1750a28368b872685465f57dec45bddf1ae1083b7e7a9f0cb4a9`，仅保留内部校验，未交付安装。

同 SHA [UI 37698733087](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37698733087) 已失败终态。build 实际 34 suites / 217 tests、0 failure/error/skip，lint、更新 helper 的完整 Android SDK 编译与 73+18 host 回归通过。API 36 原 artifact 11517277252（50,757,338 bytes、SHA-256 `6915cf79419839d835581268d61293683d09898257e3fd60910eebfb02fa2add`）完成 31 次捕获 / 30 张独立 PNG / 20 项检查，309.48 秒，真实选中语义、正文、滚动/Quick Return、后台/旋转、Google 入口通过。原 Google persistent PID 1390 的 ANR 保留，与洛书冷启 PID 2380、再次冷启 PID 7768 分开；未记录洛书 App ANR，不称全系统无 ANR。

API 28 原 artifact 11517257816（13,549,454 bytes、SHA-256 `b903d7630358856e5c453d235f303c01a352b06c58edb9a6f0a857b594d3279e`）完成 18 屏 / 14 项检查后于 453.28 秒失败。40 份实际 snapshot 均有真实根节点，公开 legacy 刷新的原配置前后相同；这不能代替后续完整 API 28 验收。失败已由两次独立禁用所有 adb 的原 XML 重放定位：字体库检查将 viewport 改为 1080×1920/420，设置页存在 15 个 `[0,0][0,0]` 屏外后代；`ensure_dock` 候选矩形列表在过滤前就对零面积节点调用严格 `bounds`，在任何手势之前抛 ValueError，Quick Return 原失败耗时 0.007 秒。不是旧首次空根节点失败，也没有证明 App ANR。

修正仅安全筛掉非目标的不可见矩形，保留全部真实点击目标的正面积/可操作/完整四项导航约束；全部 App 矩形均无效仍失败且不发输入。原 30 秒 Quick Return、单次两秒手势、原视口与后续滚动/返回断言均不变。提交夹具逐字节来自原 hierarchy-0040.xml，SHA-256 `3217891af93db5db5a10affab3dcade2e7fad58f61413a7ff169e7713684428b`，来源记录绑定原 SHA/job/artifact；两项新增 host 回归覆盖原零矩形和全部不可见拒绝，UI host 共 75 项通过。它们是 host 控制流验证，不是新 Android 运行结果。

视觉准备与 KVM 成功后，原 artifact 11516653105（825,478 bytes、SHA-256 `fd5f035b5a25411b902a034a8a378ae8f98dba5e2636d97a93088f22372ec737`）仍有 23 个成员、0 MP4、0 基线 raw/gzip/PNG。亮冷在共享十秒中 HOME resolve 0.201654 秒、首次读取 ready.json 的 adb 命令约 9.799 秒超时，设备 snapshot 请求还未发布；暗冷继承同一 fatal session 于 28 微秒内拒绝，不能称为另一次独立超时。后来正常同 nonce closed/Instrumentation -1 不能证明十秒内已就绪。原失败 PNG 仍为壁纸和中央 Launcher 图形；helper PID 2409 启动、UiAutomation 注册的 1342 ms 锁等待、Google SIM_STATE_CHANGED ANR 全保留。未保留每次命令输出/时序或原生 ready 时间，不能据同期锁日志断言 PM/GMS 根因，也不能评价 App 启动画面或 gzip 速度。

后续只补命令的真正起止、原 argv/timeout/退出码/超时原 stdout-stderr，以及同 nonce/helper PID/连接和 ready 原生 uptime 阶段诊断。诊断不能改变原成功条件、掩盖原错误、增加 RPC/重连/权限、预算外预热或延长原十秒/八秒/二十秒及清理预算；较晚 ready 仅保留诊断。App 默认启动退场、首帧提交与玻璃、OEM/Google 字体和合成/切换实现均保留。最终完整 SDK、API 28/36 和四段原录像必须由下一准确 SHA 的真实 CI 重新核验，旧 97 秒及两台真机整次切换/ColorOS 整机 reboot 仍未解决或实测。

本次合并后的适用 host 回归实际为 UI 工具 75、会话 26、逐帧分类器 20、启动源约束 11，共 132 项通过；原 Java 24 案例也在 UI host 用例中实际编译执行。新增八项会话行为回归验证原始二进制输出、超时部分输出、原始 OS 错误、诊断存储失败、原生时间仅为证据、迟到 ready 拒绝及诊断 I/O 消耗原截止时间。正常结束仍为原七次 RPC，没有新增连接或清理调用。完整 Android SDK 编译和新的模拟器运行未在这些 host 结果中发生。统一原日志 SHA-256 为 `11272ba0e4cf78f34bc5b59dcfec607244582391d257a2138ec0540f50bac4d7`；942 原失败保持，下一提交未验收前不交付安装包。
