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

## 991c0320 真实竖屏模态窗口与 response 等待失败

`991c0320e2575d551127a1ab5c2067fb8963ed1b` 的 [candidate 37702305936](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37702305936) 于 2026-10-07 23:49:10 UTC 成功终态，App、模块、候选验证及上传均通过。原 artifact 11517984547 为 12,340,212 bytes、SHA-256 `1b9b732db4233c0bfff0b290940d323660fd5977bce3692bb631c47f806248fc`，内部保留校验，不交付安装。完整字体与 App 生产改动沿用原提交，没有重做。

同 SHA [UI 37702305934](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37702305934) 于 23:41:13 UTC 失败终态。build 实际 34 suites / 217 tests、0 failure/error/skip，75+26 host、lint 和新诊断 helper 的完整 Android SDK 编译通过。API 36 原 artifact 11518806308（50,755,419 bytes、SHA-256 `069e1fc908dd87b5cf521f400ecc8626db5e615eda77cc9154b9f23fcfa9dd44`）完成 31 次捕获 / 30 张独立 PNG / 20 项检查，223.24 秒；真实 selected 与正文、11 项跨 tab 锚点、19 项后台锚点、旋转和 Google 中文入口通过。本次功能 API 36 原记录没有发现旧 942 的 GMS ANR，不沿用旧 PID/ANR。

API 28 原 artifact 11518477392（17,539,419 bytes、SHA-256 `96701f4954174cbae35a635782ec32a685d8806dfe125924ca9222079a47cfef`）于 433.59 秒完成 22 屏 / 15 项检查后失败：`App hierarchy window (120, 622, 960, 1234) exceeds logical input display 1920x1080`。此前零矩形异常已消除，真实 Quick Return 7.137 秒及字体库跨 tab 的 11 项锚点通过。本次失败尚未执行旋转或后台/Google 检查，不能称为旋转测试失败或完整 API 28 通过。

独立原 XML 和失败 PNG 明确是“Family 与收藏管理”模态框；hierarchy-0058.xml 的真实 `rotation=0`，窗口为 `(120,622,960,1234)`，原 display/window 为 1080×1920、r0。工具以模态框自身 840×612 的宽高比推断显示方向，错误交换了 wm override 的尺寸。这个几何缺陷可以直接复现；较短手势起点位于管理卡片与随后弹窗出现只是上下文，原输入没有逐条 journal，不能把手势被当作点击写成已证根因。

后续几何仅使用完整实际 snapshot 的严格 0/1/2/3 rotation 决定逻辑 wm 尺寸是否交换，缺失或非法旋转仍拒绝；原越界断言保留。恢复顶部复用已有真实两秒手势、可观察进展与稳定、可见目标和原收藏选中/页面正文条件，每阶段在同一 90 秒/最多 8 次预算内执行。模态框不能因尺寸纠正就被当作字体库内容通过，也不能自动关闭来掩盖失败。原模态框与其前一份真实库页按原字节保留为带来源的夹具。

启动视觉原 artifact 11518985099（810,697 bytes、SHA-256 `2e150eef9a195f7c203026ec3c63f1b17850eccd55aaa534423b7518574c1f81`）有 91 个成员及 33 对原始命令输出，但仍为 0 MP4、0 基线 raw/gzip/PNG/XML。与 942 不同，本次 matching ready 在约 4.099563 秒内成功读取，helper PID 2279 原生连接耗 325 ms，ready 写入到发布 416 ms；同 nonce 请求原子写入命令正常返回 0。随后 response 读取原 stderr 持续为 ENOENT，第 30 命令仅剩 0.065056 秒预算，0.067877 秒后超时。暗冷继承同 fatal 状态，warm PID 为空未录制。没有保存服务端 root 的结果，不能据此断言 root 未执行或超过八秒；GMS ANR 在这次 host deadline 之后，也不能据此定为根因。启动视觉仍为 INCOMPLETE/FAIL，原 178 双徽标、6af 暗冷黑帧、97 秒 prezygote 异常与两台真机完整切换/整机 reboot 证据继续独立保留。

几何修正的适用 host 回归为 UI 84、会话 26、逐帧分类器 20、启动源约束 11，共 141 项通过；原生产 Java 24 个兼容案例包含在 UI host 中。新增九项 UI 回归覆盖原竖屏宽模态框、四种 rotation、缺失/非法 rotation 与真实越界拒绝，以及两阶段的实际两秒手势、预算耗尽和选中状态拒绝。原 XML 夹具与原失败断言均保留；host 改写的旋转案例不冒充新增设备证据。完整 SDK、模拟器和四段启动原录像仍须统一新 SHA CI 验收。

仅给原 native helper 的现有最终 Instrumentation Bundle 补有限 `helper_last_*` 字段：最后真实 accepted 请求 ID、文件名和状态，root 查询开始/返回、原八秒 root wait、导出及 response 原子发布的设备 uptime，最后 snapshot 的有限 scalar 摘要。新请求先清旧阶段，字符串最多 1024 字符；完整 XML、root observations 和未加前缀的 snapshot/error 不进入诊断。原响应、正常结束返回码、RPC、连接、权限、deadline 与 cleanup 均不变；晚到的成功只能作证据，不能补救原 host 超时或重新连接。没有实施独立 cold 用例换 session，也没有改变 App 启动动画、玻璃或字体功能。

诊断补丁后实际重新执行 UI 84、会话 29、逐帧分类器 20 全通过，沿用未改变 App 源约束的 11 项日志，总计 144 项适用 host 通过，另外六项玻璃源/层级回归通过。新增三项会话测试包含实际生产 Java 诊断方法与 `onStart` 的 host 编译执行，验证清旧字段、白名单限长、failed snapshot 不改变正常 -1 结束，以及原异常/晚到结果继续失败。完整 Android SDK helper APK 尚未本地编译，必须由统一新 SHA CI 验证；旧 venv 首次运行因缺 numpy 的错误摘录保留，不能冒充完整原日志或实际代码失败。

## b07ff66 终态与原环境恢复后的采集修正

`b07ff66f204a1272c3604ca792e8919359298e07` 的 [candidate 37707333172](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37707333172) 成功；[UI 37707333140](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37707333140) 两次均失败。API 28 和 API 36 的完整功能流程成功，真实 API 28 summary 为 35 次屏幕捕获记录 / 24 项检查 / 0 录像，API 36 为 31 / 20 / 0；这些是非 Root 模拟器界面证据，不是两台手机的字体覆盖或整次切换耗时。API 28 原件 SHA-256 `e8b54e24723f01d522625e292f2b2e7c5590e3dc6c480cbac2f1fdcd19f91400`，一次同 SHA 视觉重试原件 SHA-256 `c5bb0076bc3b7e529bfd5fb541c0851c6452cb54a1e80d80733b1681ee95f91d`；原件及原失败门禁保留。

首轮 HOME 采集十秒超时：helper 最后实际请求根节点等待 7828 ms，导出 2149 ms，response 发布 518 ms；最后只有 5 个 Launcher 节点，不能证明热座/工作区已加载。第二次连接就绪耗 6.594871 s，根节点等待 8470 ms，最后查询返回已超过原八秒截止点，未进入导出；失败响应发布 158 ms。不同设备 uptime 与 host monotonic 不相减，迟到响应不补救原 deadline，四段启动原录像仍为未验收。Launcher 的资源路径配置重建与采集重叠；不能仅凭这些时间认定根因，也不能把 DRAWN_APPLICATION 窗口误当平台 APPLICATION_STARTING。

原环境恢复后，仅去掉 nonce 私有、一次性采集 JSON/XML 的 `FileDescriptor.sync()`：这类文件只要求同一运行内核中的完整可读性，不用于断电恢复。JSON 写入和关闭完成后仍通过临时文件 rename 原子发布；XML 的 writer flush、关闭完成后才允许发布绑定该请求的响应。写入、flush、关闭、rename 错误仍失败；请求身份、根节点可见后代、根节点超期拒绝、正常结束和任务私有清理均保留。不改变 App、字体生产代码、玻璃、nohook 或 frozen22，不增加预热、重连、等待预算或视觉放行条件。

新增有限 native child-query 次数/耗时，以及导出序列化、flush、close 的阶段时间，下一真实运行可区分 Binder 节点读取与文件导出；这不预先声称根节点迟到已修复。新增 host JVM 回归执行实际生产 Java 方法、真实文件写入及独立 JVM 读取，验证完整跨进程可见性、失败发布拒绝、原八秒截止和有限诊断；两条工作流均运行该回归。完整 SDK、同一新 SHA 的 candidate、API 28/36、亮暗冷/热四段录像与逐帧独立复核仍以新 CI 终态为准。

双系统覆盖、ColorOS/Google 回退、连续实时 A→B→A、重启保持、生成复用与阶段计时的既有实现保留，全局字重入口已移除；仍缺两台真机完整覆盖、整次切换、超时清理及重启后的证据。旧 600/630 属于合成/应用生成，host 热缓存改善不折算整次手机提速；ColorOS 整机重启两分多钟、App 冷启/加载与旧 97 秒首次 zygote 前异常继续分项记录。

## 741ef24 原始 ANR 与单变量视觉环境试验

`741ef24c8343df348c081493c6ba0587ffa66d3e` 的 [candidate 37714359939](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37714359939) 成功，包字节、签名、frozen22、实际定义的 7 个 helper 与 9 个 Google 文件经独立核验；App 与字体运行文件没有新增变化。完整 API 36 功能原件成功，API 28 的最终结论以该准确 SHA 原作业终态为准，不停止它。

同 SHA [UI 37714359927](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37714359927) 的视觉作业仍失败：原 artifact 11523551324，775001 bytes，SHA-256 `5f3e84cdbc6fc7f2a4a8556a91a68ef7e51dc5bc2fc72e3743ec106b73c0db2a`，81 成员、0 MP4、0 XML；原失败截图没有实际 Launcher 工作区或洛书首页。Host ready 8.043415 s；native root wait 11744 ms，最后单次查询 5003 ms，原八秒 deadline 后返回，0 child queries、没有导出，失败 response 发布 1 ms。短发布时间不能抵销根节点阻塞或四段缺失。

新原件保留 Launcher PID 1324 的 ANR：NotificationListener 服务执行等待 20019 ms；主线程等待 `RenderProxy::destroyContext`，调用链含 `HardwareRenderer.createHardwareBitmap` 与 Launcher bitmap/shadow 构造。RenderThread 在 ART/JNI frame-metrics 回调等待；不能把该栈直接断言为 Vulkan 驱动死锁。GMS startup/broadcast ANR 与 Launcher 资源路径重建也记录在原件，`last-anr.txt` 的空结果不能否定实际 traces 和窗口。未标注时钟的 ANR marker 不与 helper uptime 相减；97 秒旧异常与手机整机 reboot 不由此代替。

原 emulator 37.2.12 的 `-gpu software` 实际选择 GLES swangle/SwiftShader 和 Vulkan Lavapipe，guest HWUI 为 skiagl。下一轮仅将独立视觉 job 指定为 Android 官方支持的 `-gpu swiftshader`，作为单变量兼容性试验；[官方模式说明](https://developer.android.com/studio/run/emulator-acceleration) 区分 software 自动选择、swiftshader 与 swangle。功能 API 28/36 保持原后端；API、系统镜像、KVM、RAM、视口、动画、boot 600 s、HOME 10 s、root 8 s、host 20 s、录制 30 s、原生帧/PTS、同 PID、ANR 和视觉阈值均保持。没有禁用 Vulkan、额外等待/预热、隐藏 API 或全局任务清理。必须核新日志的真实后端并重录四段原片到终态，试验尚不证明启动问题已修复。

## 0e3895f 真实失败与发布通知传输

`0e3895fd35ac0deceed361467ab963102d0a88ce` 的 [candidate 37716314618](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37716314618) 已成功终态；原候选 ZIP 12,340,170 bytes，SHA-256 `fbae84ff29fcda1374deeda6a6ef53232f7c8951b03211eeb4970351a68b7951`，仅内部核验。同期 [UI 37716314638](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37716314638) 构建实际 217 JVM tests、0 failure/error/skip，lint 40 Warning / 1 Hint；API 36 完整功能验收为 31 捕获记录、20 检查、308.88 秒成功。GMS Safety Center broadcast ANR 仍保留，未观察到洛书 ANR/fatal；不宣称系统无 ANR。API 28 也已成功终态：35 捕获记录 / 24 检查 / 1043.03 秒，86 份请求/响应/XML 原字节匹配；原件 27,259,903 bytes，SHA-256 `942389c226992ee809a9f148f547c93ea8fc18bfc17305bf10ea7f648a7dfcaf`。旧 741 的 API 28 现已核完整成功终态，35 捕获记录 / 24 检查 / 1020.21 秒，不覆盖新 SHA。

单变量视觉后端实际由 Vulkan lavapipe/llvmpipe 换为 SwiftShader/Subzero，仍失败：原 artifact 11523724134，809,290 bytes，SHA-256 `284a5dc829762d6653b5ddef0dc302ef4acbff88e9f20cd0b2a3e51280a0166d`，93 成员均核验，0 MP4 / 0 XML。新失败截图实际为壁纸与中央浅色椭圆，没有 Launcher 网格或洛书首页；原 ANR 文件/对应日志未发现此次 ANR，但 Launcher assets-path 配置重建、未显示的 base 窗口仍在。不能把后端切换或缺少 ANR 当作根因已定或视觉已通过。

此轮 native ready 发布 1 ms；host ready 4.253333 s。实际 root wait 8536 ms / 41 次尝试，末次查询耗 1441 ms、返回时已超过原八秒截止点 142 ms，随后可见子节点读取 394 ms；末次树被原截止断言拒绝，没有导出，失败 response 发布 188 ms。成功功能 API 36 首次 helper readiness 反而更慢，不能单凭 host 连接耗时解释 Launcher 根节点失败。不同运行并未成对，不把 ready 改善外推到 App、手机切换或整机启动。

原始命令记录显示等 ready/response 共启动 30 次 adb/run-as/cat，其中 29 次读不到最终文件；这些命令的 wall elapsed 合计 5.848964 秒，与 native 工作并发，不能相加到设备阶段或宣称 CPU 占用。本轮修正通过已有、任务拥有的 `am instrument` stdout 使用公开 `Instrumentation.sendStatus`，在 JSON close/rename 与发布时间记录之后，仅发送 protocol/nonce/basename 发布通知。主机收到严格匹配的完整通知后只读取一次同一私有 JSON，随后仍核 request ID、filename、root wait、结果/返回码和匹配 XML。没有额外远端 waiter、旧文件回退、预热或重新连接。

stdout/stderr 持续读取并保留原字节；错误身份、重复/中断通知、EOF、进程退出和迟到 JSON/XML 继续失败，协议出错后仍保留后续原始输出。退出仍限当前隔离 CI 的测试 helper，不能停止 App/GMS/系统进程。原 HOME 10 s、native root 8 s、host 首次连接与捕获共享 20 s、recording 30 s、三次稳定 Launcher 捕获、亮暗冷暖原片、同 PID、黑帧/徽标回盖/未分类帧拒绝条件全部保留。额外在 root/refresh 查询返回后立刻检查原截止点，避免对已迟到的根节点继续读后代；这只收紧失败路径，不让迟到树通过。

本轮未改 App、字体生产功能、玻璃、nohook 或 frozen22。字体双系统覆盖/Google 回退/连续实时与重启/生成复用/全局字重移除沿用既有实现；仍缺两台真机整次切换及阶段计时、ColorOS 整次手机 reboot 与 App 冷启、旧 97 秒 prezygote 复现。新传输与后续四段原片须在同一新 SHA 的全量 CI 实际到终态后独立复核，不能由 host 管道或 JVM 边界回归提前宣布修复。

提交前实际适用 host 回归为 UI 84、会话 39（原有 29 项与新增 10 项真实子进程管道）、生产 Java JVM 边界回归 1、逐帧分类器 20、启动源约束 11、玻璃 6，共 161 项通过，frozen22 门禁也通过；完整原 stdout/stderr 与源码哈希已保留。管道/文件测试不是真机字体或真实 App 原录像。新通知单独记录 native notice started/finished，和 JSON 发布时间分开，包括异常完成；这些计时不增加 RPC 或预算。独立协议审查没有剩余阻塞。


## 6eb3bc9 终态与采集瓶颈的最小对照

`6eb3bc9be8f988d231963bb3a390423ac33c63d2` 的 [candidate 37719108199](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37719108199) 自然成功终态，实际 96 次套件 / 1701 次测试执行，含重复 source gate；两处真实 mount namespace 因权限跳过，不能写为真机挂载通过。成品 v1/v2/v3 签名、22 个 frozen 文件、7 个实际定义 helper、9 个 Google 文件经新批原件字节核验。

同 SHA [UI 37719108174](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37719108174) 为失败终态：构建 217 JVM / 124 host 通过；API 36 的 31 捕获记录 / 30 PNG / 20 检查 / 78 次请求-响应-XML 绑定通过。API 28 仅完成 2 个屏幕记录和 5 个检查，随后 `capture(light-library)` 的 `assert_running` 读取全部 main/system/crash logcat 超过原 20 秒；该异常部分输出被原 wrapper 丢弃，之后保存的 all-buffer 日志仍保留，不能据此确认超时原因。后续 API 28 页面、导航、滚动、旋转、旧主题和 Google 嵌套检查未运行。

启动视觉仍失败：0 MP4 / 0 XML。亮冷 HOME 超时，暗冷复用已 fatal 会话失败，两次 warm 没有已有 App PID而未录；不能宣布四种独立视觉通过。实际原 native root wait 1107 ms、XML export 5535 ms，其中 4 次成功可见子节点查询合计 5251 ms，JSON 发布 0 ms / notice 调用 23 ms。host ready 7.269683 s 来自另一时钟域，不与 native uptime 相加或相减。原截图仅壁纸、中央浅多边形和导航条；本批 ANR 属于 GMS 资产读取，不能沿用旧 Launcher ANR 因果。127 成员原证据包、完整独立审计和检查点 v32 已保存，安装包未交付。

本小批不关闭预取、不更换 API/image/GPU/视口/动画，也不新增 HOME 前预热。Java 分开记录公开 process-start、onCreate、onStart、连接、配置、ready 的 native uptime；逐 getter 记录 stage、root/window/class/id、index、耗时、返回/异常和是否越过原根节点期限，保留最后 32 条完整 JSON、总数、遗漏数和异常统计。cached 属性读取不追加 Accessibility RPC，诊断不能覆盖原异常。

已确认的重复工作是同一次观察与导出对相同 root 直接 child 再次 `getChild`。新保留至多 32 个已返回、可见节点，仅按当前 root 对象和原 index 复用；每次观察清理旧记录，snapshot 结束回收余项。null、不可见、超出边界和其它 parent 仍走原查询；不跨 request/root/refresh/attempt。原八秒已过时停止追加观察查询，记录 partial/examined/total，已迟到调用仍完整保留且仍 failed/no XML。完整 XML 与同生产代码关闭保留的重查对照、另行原 6eb 源执行对照用于验证输出和真实 JVM getter 次数，不是原生 App 录像或手机速度证据。

host 仍用已通过的严格 stdout 通知协议；补记本地 Popen、reader 第一段字节、完整合法状态帧解析、通知消费与单次私有 JSON 读取的 host monotonic。保留 ready 与有界 128 条尾记录及明确遗漏数；`json_read_attempt_count` 包含等通知的尝试，真实 cat 执行以原命令记录为准。不会把未执行读取计为实际 ADB 调用，也不会混 native 时钟、重连或重启预算。

smoke 的 ADB wrapper 保存每条命令完整原 stdout/stderr、bytes/hash、开始/结束/结果/returncode 和 TimeoutExpired 已收到的部分原字节。超时仍失败、returncode 为未知而非伪造 0；nonzero 的控制台尾部不代替完整证据。证据写失败进入最终失败 summary，不能将命令失败转成功。全部 logcat buffer、崩溃/ANR/进程、最后日志检查和原 20 秒预算保留；默认 20 秒真实 host 子进程超时对照保留其原始失败与部分流，不属于设备 logcat 实测。

App/font/runtime、玻璃/Dock、全局字重移除、nohook 和 frozen22 不变。下一准确新 SHA 必须自然跑完完整 candidate、API 28/36 与亮暗冷暖四段原录像并独立审原画面；HOME 10 秒 / 3 个稳定帧、root 8 秒、共享 host 20 秒、录像 30 秒、同 PID 与所有逐帧门禁保持。两台 OEM 字体/Google/连续实时/重启、完整生成和整次切换、ColorOS 整次手机 reboot、App 冷启与旧 97 秒 prezygote 仍如实待验，不能由采集修正外推为解决。


## b7f1f74 新原件与 HOME 起始状态的接续

准确提交 b7f1f74fc87b1f6f0238c1a6ad8c8d878534dc0e / tree ffcb5d80847d0f843100e3551b0aa00a2190cc49。candidate 37724458913 success；UI 37724458881 的 build/API36 success，API28 success，visual 113140977432 failure；两个 workflow 已终态。170 项适用本地 host 检查不能充当 CI 执行数；新 UI build 实际 217 JVM 单元与 133 host 执行通过。API36 原件的 31 屏幕记录、20 检查、78 请求绑定已通过独立审；99 次完整 main/system/crash logcat 在原 20 秒内，最慢 4.9727 秒。这是本次采集结果，不能证明旧 API28 超时根因、真机字体覆盖或手机整体提速。

本次 visual 原始 99 成员有 0 MP4/0 XML，四种启动仍未评估。原生连接 78ms；host Popen 到 read1 首次返回约 5.149610s，完整 ready frame 解析仅 0.318ms，ready 总计 5.437408s；不能跨 host monotonic/native uptime 相减。首请求 45 次无 active window，root wait 8447ms，最后一次 getRoot 返回晚于原 8 秒预算 447ms；getChild 0、export 0、reuse 0。失败 response code0 的文件发布 414ms，实际 notice 被 reader 观察时已晚原 HOME deadline 4.849554s，未接受。正常 instrumentation finish -1 不把失败 snapshot 变成成功。不得用旧 5.251 秒 child 导出解释此批无 root 的失败，也不得以尾32调用记录声称全部调用可见。

原 log 保留 SystemUI KeyguardService 与 GMS broadcast ANR、锁竞争及窗口末态。末态 awake/screenOnFully 与 keyguard showing 同时存在，Launcher 不可见、focus=null；其中 delegate currentUser=USER_NULL/showing=true/secure=true 可由服务断线后的保护默认值产生，不能回填首请求整个时间区间。现有 wm dismiss-keyguard 的 return0 只是请求已发出，不能代表 HOME 已实际解除或可用。

下一小批保持 renderer、AVD、动画、原采集顺序、8/10/20 秒预算及三次 fresh XML/真实 raw frame/稳定内容门禁。在 HOME 同一 10 秒 deadline 内记录起始 window/focus/keyguard 观测；后续既有 batch 携带状态确认。这里的起始状态是保留既有 setup WAKEUP/dismiss 之后、baseline 首次 helper 之前的观测，不称所有 dismissal 前的状态。有确切有效初始状态才允许每段 baseline 在同预算内请求一次既有 dismissal，UNKNOWN/USER_NULL/缺字段/冲突必须保留，exit0 仅为 request-sent，真实后续解除才称 completed。不得计时前预等、预热、重连、禁锁屏、杀 GMS、放宽预算或用合成画面验收。本段是本次实现约束。101 项 Smoke 全套与 11 项既有真实 pipe 回归通过，独立 Smoke101 审读和冻结前后 SHA 核对通过；原91项保留，run/adb/logcat/ANR 等其它函数及 native/session 四文件与 b7f 相同。新起始探针多一个有界 adb 调用（两个 dumpsys），既有 batch 增加 policy 而不多建连接，成本仍计入原10秒，可能减少剩余空间；不是已证明的 ANR 或性能修复，未来 CI/原录像不能预先判 PASS。

b7f 成品内部校验通过：外包 SHA256 3ff629d438fe1d2f44e11a178cca45f6b0920e3379e78dcf404b6df80bf4831f；模块 4c6963e8f58a2e08412a1c0441dfd3feeb10ac93c066a68b4d3360de214d6d97；APK f1b0a937bbe07031e8d4ce6114c95ecb36fc1c1021007206b1e06f565b5f1680。frozen22/defined7/Google9、CRC/hash/安全路径和 v1/v2/v3 内容签名通过，包仍内部留存。原 log 实际96次套件/1701次执行/96OK，namespace 实际跳过两处、readiness三类警告及四项真机待测均保留；没有发布、安装或修改用户设备。

两台 OEM 的具体 glyph/Google 运行时回退、连续实时 A→B→A、重启持续覆盖、整个生成和切换阶段、实际内核 namespace/owned cleanup 仍缺本轮真机证据。ColorOS 整台手机重启超过两分钟、App 冷启/加载及旧 97 秒首次 zygote 前异常分别待查；600/630 秒旧失败仍属于合成/应用生成。现有字体功能、UI/玻璃/Dock、nohook 与 frozen 1.1.1 约束全部保留。原 v32、6eb/b7f 失败及收到的完整/超时/迟到字节继续保存，原录像缺失不以截图替代。


## 0b3fe3b 原件恢复与新的小批

原工作目录丢失后，执行连接恢复；在原路径恢复准确远端 `0b3fe3b8630414477d5ca2c31db56a3387869968` / tree `a2b267238eab494eaedbebd09e5bf50ec57031df`，没有声称找回原未提交 diff。没有旧活跃开发任务或 adb/emulator 进程；只沿测试分支工作。原候选 [37728042005](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37728042005) 成功，原 UI [37728041998](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37728041998) 的 build/API28/API36 成功，visual 失败，均已终态。

原启动证据 107 个成员、0 MP4、0 XML、1 PNG，PNG 是 Launcher 的加载状态，不是 App 画面。HOME 原十秒的 host 截止 422.537420，实际成功 response notice 在 425.206178，迟到 2.668758 秒；host 没有读取 response JSON/XML。native 请求到提交 5628 ms，其中 root 等待 3952 ms/20 次，四次 child 查询 142/591/570/349 ms。原 first19 root 查询分布缺失，不能补造，也不能把 native uptime 与 host monotonic 对齐。Popen 仅约 0.95 ms，首字节等待 5.638744 秒不是 Popen 阻塞。即使四次 child 查询降至零，其它固定成本仍约迟到 1.017 秒，不能预告 HOME 已解决。

独立核验原模块的 22 frozen / 7 实际定义 helpers / 9 Google 字节及 APK v2/v3 签名、217 JVM 测试与 2416 份命令 raw stream。原 API36 有四次系统 ANR；API28 lastanr-traces 返回 Unknown command，不能以退出码零声称 trace 完整。原 UI 测试安装 debug App，同 Git SHA 不代表 release candidate 本体的 UI 已测试。

本小批的活跃 v143 持久组合缓存原本只绑定输入字节，忽略 composite_font/layout/runner，非空损坏缓存也可能错误返回成功。新 key 绑定生成内容身份，receipt 绑定 payload 摘要、生成身份和当前真实 validator；无 receipt 要实际验证，不符重建，热命中仍校验完整摘要。生成与发布边界再次核身份，拒绝变化。worker/prepared/progress 与 composite 临时 font/report/error/receipt 放在已有 owned task scope 内，取消/超时沿原监督器清理；不删除没有拥有证明的历史残留或外部 task root，不碰全局进程/GMS。原11加新9项真实字体回归通过，含旧源损坏/身份变化失败复现、实际发布 race、超时/取消和独立 sentinel；frozen22 不变。

固定同一真实九档 production helper driver 三轮交错 before/after，所有冷/热输出共80244字节，摘要一致，11 instances/冷9 generators/热0。主机阶段中位 prepare 2.886946→3.056406秒、cold composite 1.351971→1.669540秒、warm composite 0.085867→0.215149秒。新增安全证明有约0.129秒热成本，这是安全修复而非提速；不代表手机整次切换。旧 prepared 27→11 优化保留，未重复实现。

采集仅做 API33+ 公开 getChild(index,0) 的单变量兼容性试验；API28/32 保留默认 getter，根查询、服务配置、缓存/回收、预算与所有视觉断言不变，不使用隐藏 root overload。新增现有 root/window/refresh 调用的总量、完整尾32和遗漏数，不增加 RPC。固定 JVM tree 下各 API/策略 XML 字节一致，真实 Android 速度仍以新准确 SHA 原件判定；取消预取也可能减少缓存命中，不能将原1.652秒整体归因预取。

字体库未筛选空态的“打开导入与管理”现在下一 Compose 帧展开并定向滚动到固定管理区，重复点击取消旧滚动，顶部按钮保持原地展开，页面退出释放 scope。玻璃、Dock、首帧和原样式条件保留。新增真实 smoke 要求点击后不借助手势找到完整可见“导入字体”，随后收起、恢复顶部再执行原全部滚动/跨页/旋转检查；未 Root 导入禁用是合理状态，不能当作点击失败。

本地检查使用原候选忽略的 FontTools4.63.0 payload、host FreeType2.13.2和私有官方 Temurin17；没有 Android SDK/adb/emulator/mksh，不把本地 JVM/sh 结果当作 SDK编译、mksh 或设备结果。完整 source gate、新准确 SHA candidate/API28/API36 与亮暗冷暖四段原录像必须自然终态，再独立看原画面；没有原录像就继续失败，不交付未验收安装包。两台 OEM 覆盖/Google/连续实时与重启、全程速度、ColorOS 整机启动、App冷启/加载、97秒 prezygote 各项仍分别待真机证据。

本批独立本地全量 source 自然 exit0，报告41套件/718次执行；原 namespace class 按真实环境条件跳过。适用 UI109（原101保留）、session41（原失败夹具已修，原41保留）、native JVM1、逐帧分类器20、launch11、字体20均通过。session原失败日志另存，未用跳过方法修门禁；新Android结果尚待准确提交CI。


## aaa4787 准确终态与下一批的真实原因

准确 `aaa47876d4564a280e91f24d4e4db23ecc4df11e` / tree `bfe68dca1f470920ec99780ec37fcd88d499b4bb` 的 [candidate37756992806](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37756992806) 成功，[UI37756993521](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37756993521) 失败，均自然终态。真实SDK helper编译、优化debug APK、lint、34套件217 JVM通过；candidate日志96个unittest汇总共1719次执行含重复，不能当作独立测试数量。其安装包未交付。原件一份一次取得，逐ZIP核GitHub digest/CRC，候选审计按准确Git object，不混下一批工作区。

两API均在新增空态管理入口检查失败，不能套旧API通过：API28实际20屏幕记录＋failure PNG共21图、14前序checks；API36实际17屏幕记录＋failure PNG共18图、11前序checks。独立看完全部39原PNG。入口点击之后没有测试input，23/32份新根中导入按钮、文字与收起按钮一直完整可见，但没有Dock，故selected字体库要求未通过。原上滑隐藏Dock，QuickReturn明确忽略程序SideEffect；原index3定位已经成功。产品修正仅空态明确导航动作同步调用Library范围的显示Dock请求：reset policy＋hidden=false，再启动原可取消滚动；不改变普遍SideEffect规则，不在延迟帧/完成/finally抢回Dock。玻璃/首帧/showDock条件、原所有UI断言保留。restored-top及后续favorites/preservation/background/rotation/disabled animation/repeatcold/Google均未运行，不能回填。

启动视觉原159文件中0MP4/4XML/3PNG，4XML对应3次独立原采样；3张PNG均独立查看，暗PNG与无损raw/gzip像素一致。亮首次raw batch在HOME8.999954秒开始，仅余1.000042秒，stdout23504字节仅window＋separator、零gzip；暗实际桌面在9.629秒才完成一个稳定样本。三次native root wait738/754/159ms，rootQuery各1且无null/omitted；child334/1601/302ms，其中第二次export仍1236ms。四notice均及时消费且正常closed，旧unconsumed/response late本批没有重现，但采样总体仍失败，无App启动/暖PID/四段视觉通过。GMS ANR和系统accessibility锁竞争原件保留；lastanr none不能推翻trace，不能跨钟或跨run归因。

新HOME调度只在原十秒started/deadline建立后launch owned reader，与实际resolve/initialpolicy重叠；增加独立ready状态，未验证ready不发真实root请求，首次capture继承min(begin＋原20秒,caller deadline)，不能晚调用再给20秒。原3个真实稳定帧、每帧新root、原raw捕获与内容比较、sleep、通知/迟到/close/ANR全部保持。不把整个start丢后台线程，也不移到HOME预算之前。单变量收益必须以新准确SHA原件验收，不能承诺原约1.14秒重叠足够。

下一功能证据是活跃fixed链App/router→v14_mix→all-fixed v142→runtime/engine→真实mapper→真实next transaction。真实输入变化会正确重建，但composite_layout策略+37时旧persistent key不变、generator0、旧A bbox[0,0,427,700]；当前真实生成器预期[0,37,427,737]，两者validator均PASS。8664字节invalid SFNT cache让generic真实mapper/next/outer成功，TTFont与真实font_validate均拒绝；7字节被mapper最小尺寸拒绝，无本请求commit。该坏缓存完整链仅generic，不是HyperOS/ColorOS后处理、live挂载或设备。新修正固定engine绑定生成身份与payload证明，抽出auto既有3个小proof helper共用；auto原4-line receipt/key保持。共享helper位于既有legacy目录，payload manifest已有递归entry，不添加会破坏top-level对照的重复嵌套entry。新增真正fixed回归加入source gate，旧生命周期夹具只补真实新依赖，所有原断言保留。

下一准确提交必须重新跑完整candidate、API28/36与四段原视频，并独立审原画面。不将新source/host通过当设备视觉通过。1.1.1 frozen22/nohook、既有覆盖/Google/连续切换与重启、全局字重移除均保留；两台OEM真实glyph/Google/live A→B→A/reboot/full速度、ColorOS整机reboot、App冷启/加载、97秒prezygote、600/630合成现场分别仍缺真机证据。

本批发布前 root 独立完整 source gate 自然 exit0：42个 unittest 报告/731次执行，原 namespace class 因当前/proc PID映射条件跳过并保留原因；session53、smoke112分别完整通过，原41/109方法及断言保留。真实fixed13、共享后auto20、lifecycle9均通过。三轮交错真实小字体fixed driver包络冷中位0.232230→0.248453秒、热0.035601→0.049753秒，是完整内容证明的成本，不是提速；每轮cold/warm字体字节相同，热仍0 generator/0 shell validator。仅host driver且可能有并发噪声，不能外推整手机切换。最终SDK编译、原屏幕/动效和四段原录像尚待新SHA。

## be285fb0 真实终态与下一批计时证据

准确 `be285fb0b19c9541645893359329395fde41bb16` / tree `593a79687435733b182e7a2b27a5f89ae6c2e4d1` 的 [candidate37762425685](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37762425685) 成功，[UI37762425702](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37762425702) 的 build/API28/API36 成功、visual失败，均自然终态。真实SDK编译/lint和34套件217 JVM通过；candidate98个unittest汇总/1745次执行含重复及两处真实namespace权限跳过。模块10662489字节/SHA256 `c0925c1cf21c10b22777faabef3f1c433f87ee52c071a2b95ad1343c616e3166`，release APK4072078字节/SHA256 `ee5fe83d8be0e32b468bda7c812176ad8eaf8e377dda4ae94eb0bf95d9cf3fa2`。frozen22、defined7、Google9及新增proof/fixed/router/auto按该Git对象逐字节核验，内嵌APK一致，签名v2/v3通过；包仍内部留存。

功能原图逐张审完：API28 37张、API36 33张。空态入口点击后、零额外测试输入，导入与收起按钮和完整字体库Dock同时可见；此前缺Dock的问题在这两个未Root模拟器中通过。原跨页/筛选/后台/旋转/动画关闭/再次冷启动及Google说明仍执行。横屏验证保持路由和滚动状态，不代表下方全部管理按钮可见；静态PNG不证明首帧或动效。1347条实际命令/2694份原流的长度、摘要、身份、JSON/XML、调用汇总一致。API28原20秒logcat118次均及时，最大10.385秒；没有据此宣布旧20秒超时根因已解决。API36有真实GMS broadcast ANR，不称全系统无ANR。

启动仍0 MP4/0 XML/仅一张Launcher加载状态的后置PNG，无App启动、暖PID或四段录像验收。HOME begin仅重叠约0.204秒既有准备。host ready5.341秒、notice仍迟原十秒2.114秒且未消费，close FAIL保留；native同钟process→ready2895ms、ready→accepted1006ms、request→response提交6076ms，其中root3696ms和序列化2368ms。35次root仅保留尾32及3次遗漏汇总，不补造单次分布；四次child共2822ms。原GMS ANR只有670字节头部，没有本次线程栈，不能借旧栈作此次根因。

下一批仅启动视觉显式试验公开平台默认`getChild(index)`，功能API28/36继续缺省`zero`，API33以下仍默认getter。ready和每份response envelope必须包含配置mode、整数SDK和实际strategy；host核配置/准备/response一致性，冲突先于XML失败。default仍可使用平台cache，既有API34+公开clearCache保持；不是禁用cache或强制每个节点RPC，也不能由固定JVM树字节一致证明Android提速。HOME10秒/root8秒/host20秒/录像30秒、每次fresh root与原raw帧、三次稳定HOME、通知/迟到/close、同PID/ANR及全部视觉断言保留。该跨run兼容试验未固定系统负载，不能当成严格性能因果对照。

功能计时分三种钟与范围：active fixed/auto用内建`/proc/uptime`记录prepare/cache/cold/validate/publish/mapper/child/finalize阶段，约10ms分辨率、含suspend；outer task_scope既有Python-monotonic cleanup receipt提供后台任务包络；App用elapsedRealtime记录接受请求至第一次准确operation+task观察终态。重叠阶段不相加；后台包络不含router预检和App观察，App总时长也不证明文字已在系统或Google像素生效。optional日志失败不改变业务返回/字体/四行proof/事务；超时取消中断记录incomplete而不伪造结束。脱敏reader限定原log256KiB/256events/3匿名requests及小额准确outer receipt，boot/PID-start不符拒绝关联，不导出原任务ID、路径、boot或绝对时钟。

App仅process内最多8条随机request证据，没有额外Root请求/每操作IO/轮询预算变化。未知恢复起点、启动失败、错/缺status taskID、observer取消/失败与实际后台终态区分；清理未确认总时长unknown，后续确认不能复活已清空总时长。正常start把本次captured request传给观察器，仅恢复时按准确pair attach；重复backend ID绑定被拒绝后也不会借旧WAITING的click时钟。导出使用既有只读报告命令的固定字段。host官方Kotlin2.4.10编译真实RootShell/TaskPollBudget/计时类，38 JVM（19新增+16原RootShell+3原budget）通过，原37结果单独保留；SystemClock仅host签名stub，不能代替完整AndroidViewModel/Compose SDK编译。此批准确新SHA和所有设备/录像终态仍须实际运行后填写。

新增完整auto夹具发现两个不同事实：旧fixed夹具未创建当前live目录，原SAFE正确拒绝不可读clone，补齐实际目录后才继续；其后发现既有真实生产目录标签缺口。router创建`legacy-v14-runtime`，manager仅识别`.legacy-v14-runtime`，自动九档真实SAFE/mapper/next完成后next.font仍`LuoShuAutoMix`、没有mix提交证明、fast status维持running99。只在manager既有REAL_MODDIR保护内补新精确basename，同时保留旧alias；不向夹具强塞active-label、不改SAFE核心或接受无证明终态。原失败和修后同环境链路结果必须分别保存。这是generic host完整链路发现，不回填OEM手机实测。

真实SAFE会重入独立safe-switch scope，身份并非auto outer。本批仅计原manager调用外围`safe_apply`跨度；SAFE原细阶段日志继续保留，但匿名diagnostic的SAFE关联记为unavailable/identity-not-associated，不按相近时间窗或相同字符串猜父子，也不合计重叠时长。

root首轮完整source门禁真实exit1，ColorOS双caller回归只得到一次helper调用：孤立函数摘录没有source新增真实phase helper，第二caller在计时函数名处失败而未执行度量helper。原非零与两次调用断言保留，只给摘录补真实helper依赖；HyperOS同类摘录也补真实依赖并新增两次marker，不能用command-not-found假通过失败传播。两项专项分别27/28通过；原首轮失败及运行中24文件完全未变的摘要保留，随后整库重跑另存。新源/host均不替代同SHA设备/录像结果。

发布前root第二轮完整`check.sh`自然exit0，366.700540秒，43个unittest报告/751次执行/43 OK，运行中26文件逐字节未变。真实`/proc` PID映射类及mount namespace权限条件跳过的原证据保留。该门禁后的唯一改动是本文修正HyperOS专项数量和补实际全量结果；其余25个待提交代码/测试/工作流文件与本轮通过输入一致。native独立61/117/Java1、App真实Kotlin38/boot8及后台20/10/20/13/9已分别保存，SDK/两API/四原录像仍必须按准确新SHA实际跑到终态。

1.1.1 frozen22/nohook、现有可信字体槽位/Google回退/连续切换与重启事务、已移除全局字重、玻璃渐变/Dock/首帧条件保留。两台既有设备一加15 ColorOS V16.1.0、Redmi K80 Ultra HyperOS3.0.303仍缺真实字形/Google运行时、live A→B→A、重启持续覆盖、整次速度与清理证据；不操作用户设备。ColorOS整机reboot超过两分钟、App冷启/加载、旧97秒prezygote、旧600/630合成超时分别待查，不能以此批采集或host计时替代。

## 33cf3203 实际失败证据与下一最小批

准确 `33cf3203a8953191aa2274b285b613e6595ee8de` / tree `8210df555d60dd98a31cf0818a7978dc7a55262c` 的 [candidate37770831931](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37770831931) 与 [UI37770831963](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37770831963) 均自然 failure。SDK 构建、35套件236 JVM、API28和API36成功；candidate源门禁43汇总763次执行通过后，补充namespace原16项中目标方法的mksh/dash六分支返回127。旧夹具只抽取 `apply_mix` 外层，漏新 `_mix_apply` 与真实计时依赖，后续readiness、签名、App/模块构建和候选验证未运行，未生成候选包。修正仅让夹具抽取两真实函数并source真实helper；原返回2、错误信息、空stderr、模块不变与恢复哨兵断言和矩阵保留。

官方私有Ubuntu Jammy mksh59c-16经签名Release→Packages→deb→binary校验；真实KSH_VERSION和原不支持的 `--version` 失败均保留。修后目标原六分支在root和独立任务中分别通过；两次完整16方法本机运行仍31 failures/1 error，包含29处明文caller PID mapping mismatch、两处readiness exit126与一处holder procstat缺失，不将后三项伪称同一明文错误。宿主pid与 `/proc/self` 外层pid不同，NSpid保留内外两值，是实际限制而非降低门禁理由。完整兼容性仍须新CI实际通过。

API28/36原件70张不同PNG均逐张独立看过，共72屏幕记录、46功能检查、无MP4；PNG/XML并非原子同帧。API36再次冷启动PNG显示正在检测，原先传入的XML已显示Root不可用，不能以XML覆盖原图、倒推首帧或声称秒加载。API28原20秒logcat116次及时，最大13.570558秒；API36为110次、最大2.648903秒。旧20秒超时根因未据此宣布解决。实际2736份命令输出流及6份instrumentation流完整绑定，API28尾记录37次deadline_reached保留；lastanr-traces不支持等采集缺项不能当全系统无ANR。

启动视觉原156成员实为0MP4、4XML（含latest别名）、3PNG；原PNG都只有Launcher加载画面，前三请求XML仅5个ProgressBar相关节点，没有桌面内容或洛书画面。亮冷首ready消耗原HOME预算5.359587秒，首hierarchy8.269899秒，真正截图只剩0.091539秒并超时；暗冷两次完整raw帧batch1.989611/2.338588秒，但Launcher内容均为空，稳定计数保持0；第三请求notice迟到1.629468秒未消费，close继续失败。两次warm无已有App PID而未录，不补造四段视频。

同native uptime的process→ready提交3089ms、公开连接1139ms、配置130ms有真实证据；不能与host首次read5.260秒相减。原截图batch串行policy/display查询及screencap/gzip没有内部时间，不能凭总2秒归因某一步。下一批只在同一设备 `/proc/uptime` 加best-effort内建stderr分段诊断，保留原stdout/raw/gzip、真实exit与全部异常。拆screencap返回需要保留一个左段shell上下文，必须记录可能测量成本；不称零扰动或提速。并行pipeline全长不是gzip独占时长，其尾段也只代表消费/收集及上下文收尾。缺坏诊断只为unknown，不能隐藏坏原流/业务失败/超时。UI宿主准备真实官方mksh以强制管道兼容门禁，不随模块或APK交付。

字体库管理按钮改为同一箭头0↔180度可逆旋转，沿用展开220ms/收起170ms及既有缓动，在graphics layer读取状态；布局、触控、文本、语义、玻璃、Dock和已有展开容器不改。旧布局及六项玻璃层级检查通过，完整SDK编译、实际反向动效、动画关闭与重建仍待新SHA；70张旧静图不证明新动画。

此批HOME10秒/root8秒/host20秒/录像30秒、三次fresh root与真实稳定raw帧、Launcher内容、迟到通知/close、同PID、ANR与所有视觉断言保持。两台OEM/Google/连续实时及reboot持续覆盖、整次字体切换与阶段速度、ColorOS整机reboot、App冷启/加载、97秒prezygote、600/630合成清理仍分别待真机证据，不以UI或采集诊断替代。

发布前root完整source门禁374.311158秒自然exit0，43个unittest汇总/751次执行/43 OK；运行中六文件字节全部未变。原MissingNamespaceLifecycleTest因native一对一/proc PID映射条件setUpClass跳过一次，原原因和日志保留；JSON中字体slot skipped并非测试skip。另行完整namespace16的31fail/1error依然保存，不用source通过覆盖。root独立smoke122全部通过，真实mksh强制存在；所有108 shell原流与18组对照经独立审字节核同。此门禁后只有本文补实际结果，其余五代码/测试/工作流文件与已通过输入一致；SDK、实际动效及四启动原录像仍须准确新SHA实跑。

## 3712887 原件终态与失败后独立诊断

准确 `3712887fcb53d1b456df141e2ed9ee2790b9c38a` / tree `d32a568b75609b158a26303f62c1c2db0d4107eb` 的 [candidate37778170707](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37778170707) 自然 success，[UI37778170694](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37778170694) 的 SDK/API28/API36 success、visual failure。实际35套件236 JVM无fail/error/skip，lint40 warnings/1 hint。候选日志100个unittest汇总、1785次含重复执行；补充和解包验收中的完整namespace16各通过，宿主原31fail/1error及两处Google provider mount namespace权限条件跳过仍分别保存，不套旧计数。

模块10672807字节/SHA256 `390ba2a8a350b232905e2158e6a0253eccf27cb1779a4b20d8fb633031eb3522`，release APK4088468字节/SHA256 `4abc8b4635fcbf27a9e119057cdcbebb4505747b3508e187780e7779192f3896`。v2/v3、内嵌APK逐byte、frozen22、实际HELPERS7、Google9及phase helper按371 Git对象核同；安装包仍内部留存。两API的命令原流绑定核同不替代手机像素；API36真实GMS persistent的SIM_STATE_CHANGED ANR与lastanr/data_app_anr缺项分别保留，不报全系统无ANR或给HOME因果结论。

视觉原100成员只有0MP4/0XML/1PNG，独立原图是Launcher壁纸与中央加载图形，没有桌面内容或洛书画面。native process→ready2061ms、公开连接850ms、配置8ms均同钟；首请求40 attempts、79 root calls、40次root null，root wait8152ms，child查询0。getWindows非空list对象不证明有非空/active/focused窗口。host ready在HOME+5.712303秒，原notice迟到4.140848秒，未消费、close失败；暗路径承接fatal reader，原warm两次PID为空，四标准视频没有生成。截图分段command已配置但真实batch执行0次，不能把未执行诊断叫缺marker失败，不能解释此前约两秒的batch成本。

下一最小批显式opt-in只在原HOME失败、标准视频及原App PID证据均为空且当前pidof可靠为空时，在原diagnostics、原close、原summary与exit1已经冻结以后采一段独立诊断原片。它使用独立diagnostic-only目录/命令账本，低层ADB一次MainActivity启动和自有30秒screenrecord，不调用原launch、hierarchy、session重连或视觉classifier，不回填原recordings/checks/PID，不覆盖原截图/logcat/ANR/summary，不消费旧迟到结果。录像、启动、拉取、解码失败也保留本阶段实际输出和错误；只清理自有host reader及本次唯一临时录像，不能kill App/GMS或清系统缓存。

该独立原片不是合格HOME基线后的标准亮暗冷暖视频；现有Popen加0.2秒不能证明codec已记录启动前帧，必须标unknown。原MP4、真实PTS/timebase及逐原帧解码供人工审画面；只有解码hash不能证明像素视觉通过，后置诊断速度也不能外推原cold/warm或字体整次提速。原HOME10/root8/host20/录像30秒及fresh3、同PID、ANR、首帧、Dock/玻璃、迟到close门禁全保留。两台真机覆盖/Google/live A→B→A/reboot/整次切换与清理、ColorOS整机boot、App冷启动、97秒prezygote与600/630合成仍分别缺证据。

同批还有一项已定位的输出遗漏：原native root循环已经读取并记录 `window_counts` 的elapsed/windows/active/focused，但最终instrumentation的JSON字段投影只保留root/child度量，HOME迟到时host不能再读取response，已有窗口内容统计便缺失。修正只让该既有JSON串走同一完整输出路径，不增加getter/Binder调用、不改root循环、预算或通知。该旧array没有last32 cap；沿用JSON长度不超过70000的守卫，超界时省略只能视为unknown，不能称零窗口或有界last32。不能放到scalar1024截断路径产生坏JSON，不能把此证据保留修正称启动根因或性能改善。


## 2026-10-08 真实手机事故与本批隔离修正

用户已报告禁用洛书后完整重启仍慢、严重发热、Play 不可用及换字体更慢；“开洛书”指打开 App 还是启用模块尚不明确。实际交付包为 be285fb0，ZIP SHA256 c0925c1cf21c10b22777faabef3f1c433f87ee52c071a2b95ad1343c616e3166；是否安装这个精确包、机型和模块管理器仍未确认。本批不操作用户手机、不要求热机重启/日志复现、不交付新未验包；模拟器或 CI 成功不能证明用户手机安全。

两张原照片已实际读取：聊天多个气泡内文字不可见，部分英文可见；不猜空白原文或具体字体表根因。日志显示 ColorOS V17.0.0、同一 mix 的内层 apply32.593 秒和外层33.4 秒，清理均成功；这是任务清理耗时证据，不能相加、当成两次切换或推导完整点击到生效耗时，也不能当字体输出正确性证明。

已复现并修正的非冻结安全缺口：早期 router 调用共享目录字体迁移；boot/service 禁止 Google restart 的环境标志未被 refresh 消费；Google 恢复失败仍继续卸载；App 仅用 installed 信任已禁用模块。新增门禁保留原 Google 恢复入口、持久 undo、完整身份检查与失败日志。挂载失败 UI 不再保证“已安全/完整回滚”，而明确回退状态待核实。冻结1.1.1 的22文件字节与 nohook 约束保持，不扩系统/GMS进程清理范围。

UI 并行修复目录导入：请求不再提前推进基线或吞掉差异；超过32项可显式选批、同批重试；仅显式记录基线清差异，反馈为“已请求”且复用当前权限/扫描/忙状态。没有新增常驻刷新、计时器或耗电动画。保留玻璃、Dock 和既有布局条件；新对话框的完整 Android/小屏视觉仍需同SHA CI。

字体正确性与性能同时验收：实际包脚本在隔离构造字体上曾对有 cmap 但无轮廓的 B/2/部分中文返回成功；这是可复现代码缺口，不能认定是真机照片根因。最终输出及同源/旧无receipt缓存路径必须执行新验证，真缓存继续以精确源/引擎/产品身份复用。ColorOS 的原厂集合字体/face index 契约也需与 existing-alias路径一致保护。性能优先减少可安全合并的重复读取，保留全SHA、独立代、锁、失败清理与回滚；I/O字节减少不等于 host/真机整次时间改善。App点击到观测terminal、后台阶段、清理、手机整次reboot是不同证据，仍不能拿部分热缓存百分比或普通启动通过宣称全部解决。

原371候选/API28/API36成功和启动视觉失败原件保留；本批继承未提交的诊断录像补丁不提升原HOME预算，不忽略迟到notice/close，不将diagnostic-only或合成codec样本算四段原录像。最终准确提交SHA、全量CI终态与独立原画面验收须另记录。
