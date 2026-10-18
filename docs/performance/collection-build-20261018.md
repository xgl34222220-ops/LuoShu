# CJK 集合编译耗时实测（2026-10-18）

范围：`common/composite_collection_build.build()` 单独计时（不含挂载、不含主字体流程），沙箱主机 2 核、Python 3.12.15、**纯 Python fontTools 4.63.0**（与手机一致：`prepare_composite_runtime.sh` 删除全部 `*.so`，cu2qu/qu2cu 无编译扩展）。手机 CPU 更慢，绝对值只作相对比较。

| 代码 | sha256(composite_collection_build.py) 前 16 位 |
|---|---|
| 基线 #295 head `9972765c` | `8d6ba638ac955341` |
| 基线 + 仅修无 on-curve 点轮廓（对照组，未提交） | — |
| 本分支 | `109df87e0c6cfa9f` |

字体（sha256 前 16 位）：本机集合 `NotoSansCJK-Regular.ttc`（10 面，5 面编译）`b76b0433203017ca`、`NotoSerifCJK-Regular.ttc`（5 面）`5d9c31a059600193`；TrueType 供体霞鹜文楷 `wenkai.ttf` `84f6b051d36eb328`；CFF 供体 `NotoSansSC-Regular.otf` `faa6c9df652116dd`。

## TrueType 供体（霞鹜文楷）

| 代码 | NotoSansCJK | NotoSerifCJK | 合计 | 峰值 RSS | 输出大小（Sans / Serif） |
|---|---|---|---|---|---|
| 基线 `9972765c` | 2.8s 失败（`NotImplementedError: oncurve-less contours with all_cubic`，整组保留原厂） | 2.9s 失败 | — | — | — |
| 基线 + 仅修无 on-curve 点（分别运行） | 156.4s | 146.0s | **302.4s** | 990 / 1008 MB | 55,153,580 / 40,146,956 |
| 本分支（分别运行，无跨集合缓存） | 67.1s | 64.9s | 132.0s | 1089 / 1132 MB | 61,610,692 / 46,650,616 |
| 本分支（同一进程连续编译，按供体 sha 复用转换） | 59.4s | 11.0s | **70.4s** | 584 / 635 MB | 61,610,692 / 46,650,616 |

每面替换字形数在各版本间一致（Sans 第 0 面 CJK 28,247 / 拉丁 374 / 数字 24，冲突保留 657 槽）。精确升阶比曲线拟合多保留点，集合输出增大约 6.5 MB（每个集合）。

## CFF 供体（NotoSansSC-Regular.otf）

| 代码 | NotoSansCJK | NotoSerifCJK | 峰值 RSS |
|---|---|---|---|
| 基线 `9972765c` | 37.1s（输出 35,150,620） | 未测 | 567 MB |
| 本分支（同一进程） | 27.2s（输出 35,150,620，字节数相同） | 7.6s（输出 20,087,228） | 436 / 440 MB |

## 结论

* 基线在常见 TTF 供体上整组放弃集合；本分支可以编译，且耗时比"仅修崩溃"再快 4.3 倍（302s→70s），内存约减 40%。
* 跨集合缓存只在同一次应用中生效（ColorOS/HyperOS 依次编译 Sans→Serif），第二个集合降到 11s。
* 真机耗时未测（推断按主机比例缩放）。

## 真机导出分析（Redmi HyperOS OS3.0V816 / SDK36 / KernelSU，模块 #295 `9972765c`，组合字体 + legacyMode）

| 现象 | 根因（代码核对） | 本 PR 处理 |
|---|---|---|
| `metrics.available=false`，NotoSansCJK/NotoSerifCJK 从未生成（96 个进程中 93 个报未覆盖） | 组合字体应用路径本身会跑 `hyperos_stage_complete.sh → hyperos_metrics_batch.py → build_collections` 并写报告（`mix_router.sh commit_mix_stage_if_needed → complete_hyperos_stage`）。但**模块更新**迁移（`module_update_hotfix_v4.sh`）只按 schema 判断兼容，只复制各分区字体树：`.luoshu-metrics-report.json` 不随负载迁移，组合/集合编译器变更也不会要求重新应用。于是更新后继续挂着旧版本生成的、没有集合的负载，报告也没了。同时日志目录是新的，导致导出里只剩开机后的 4 行 WEBVIEW-ROUTE。 | 更新迁移：编译器文件（含 `composite_collection_build.py`、`composite_collection_contract.py`、`coloros_latin_policy.py`、两个 stage helper）一致且旧负载有报告时随负载迁移报告；编译器变化或 HyperOS/ColorOS 物理负载缺报告时，保留当前字体并写 `font-payload-rebuild-pending.conf`（`reason=font-builder-changed`，`detail=builder-files-changed / metrics-report-missing`），只能由一次明确应用消除。覆盖定位不再写“未记录原因”，而是说明“模块更新后沿用了旧版本负载，请重新应用一次”。 |
| payload 里 `/system/fonts/100.ttf…900.ttf`、`GoogleSans-Regular.ttf`、`GoogleSansText-Regular.ttf` 系统不可见 | `font_mix_engine.sh populate_hyperos_payload` 的 `alias_core` 无条件写这 12 个名字，本机没有这些文件；度量批处理从不清理。12 个文件**共用 inode 2220690**（硬链接），实际只占一份约 20 MB，而不是 240 MB；若该 inode 就是 `.luoshu-font-store/mix-composite.font` 锚点则额外占用为 0。逐文件绑定不会挂载不存在的目标，没有挂载引用。 | `prune_orphan_aliases`：HyperOS 与 ColorOS 度量批处理最后一步，删除本机没有对应原厂文件、且内容在暂存区另有保留（同 inode 或同大小同 SHA-256）的字体名；唯一副本（例如开机修复可能读取的字重源）保留。结果写入报告 `prunedOrphanAliases`。 |
| `fontswitch.log` 只剩 4 行 | 见第一行（更新后日志目录为空）；另外导出的 `fontswitchLog` 按关键字过滤，`[SAFE-TIMING]` 与 stage 输出本来就会被滤掉。 | 更新时把旧日志末尾 1500 行带到新模块；导出新增 `lastApply`：最近一次应用的全部行（从该次 `[SAFE-TIMING]`/`[MIX-PHASE]` 首行起，不过滤，最多 800 行）和每个阶段耗时；新增 `rebuildPending`。度量批处理的 stdout（写入日志）新增已编译集合、保留原因和清理数量。 |
| `weightLossSlots`（MiSansVF/MiSansLatinVF/MiSansTCVF/MitypeVF/MitypeMonoVF） | 组合字体是单个静态文件，放进可变槽位后系统只能合成粗体。 | **评估后不做**：给静态字体写 `fvar`/`STAT` 让 wght 轴指向同一轮廓，会让 Minikin 认为 700 是原生字重而**不再合成粗体**，粗体会显示成常规体，比现状更差；用多字重源 `varLib` 合成要求各字重轮廓兼容，用户组合字体通常来自不同家族，且 CJK 3 万字形在手机纯 Python 上耗时远超预算。用户字体本身可变时已直接放入可变槽位（`variable_slot_source`）。 |
| `engineState=missing`、`bootScanResult=unknown`、`app-font-task-timing records=0` | `engineState` 读 `config/device-font-engine.conf`，安全切换提交时会删除它、legacy 组合模式也不使用该引擎，属于预期；`bootScanResult` 需要开机扫描回执，本次开机 `stockScanPending=no` 没有触发扫描；`records=0` 是 App 侧计时记录（`FontTaskTiming.kt`），推断只记录 App 发起并观察到终态的任务、更新/重装后为空（未逐行核对 App 代码）。前两项为预期状态，第三项为记录缺失而非故障。 | 不改代码；导出新增的 `lastApply.phases` 可替代查看阶段耗时。 |
