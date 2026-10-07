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
