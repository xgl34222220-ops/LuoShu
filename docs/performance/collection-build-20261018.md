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
