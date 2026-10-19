# 速度与覆盖迭代实测（2026-10-19，PR #296）

主机：沙箱 2 核、Python 3.12.15、纯 Python fontTools 4.63.0（与手机一致，无编译扩展）。手机 CPU 更慢，主机数字只作前后对比；“设备预估”按主机比例推算，**未在真机复测**。

真机基线取自 2026-10-18 11:23 导出（HyperOS OS3.0，组合字体 legacy 模式）的 `lastApply.phases`。

## 1. CFF2 集合共用供体轮廓转换缓存

`composite_collection_build.py`：CFF2 集合也走 `OUTLINE_CACHE`，取缓存的 CFF 字形字节去掉末尾 `endchar`（0x0e），不是 endchar 结尾直接报错。sha256 前 16 位：之前 `84f6b051d36eb328`（`e3ec4541`），之后 `8077ebb4a9ac390f`。

| 场景（供体霞鹜文楷，同一进程依次编译） | 之前 `e3ec4541` | 之后 | 
|---|---|---|
| NotoSansCJK-VF.otf.ttc（CFF2，5 面） | 69.2s | 60.7s |
| NotoSerifCJK-Regular.ttc（CFF） | 60.8s | 10.9s |
| 合计 | **130.0s** | **71.6s** |
| 峰值 RSS | 1108 MB | 692 MB |

一致性：Serif 输出逐字节一致；Sans 输出 5 个面逐字形比较（`RecordingPen` 轮廓 + 宽度，131,070 个字形，另比对除 CFF2/CFF/head 外所有表字节）0 不一致。

设备预估：导出中 `finalize/complete_hyperos` 183.4s 含两 ttc 编译；集合编译部分按主机比例约减少 45%。

## 2. 模块更新迁移缓存

* `luoshu_migrate_update_cache` 无条件迁移 `cache/hyperos-collections-v1`（键 = 集合编译器 sha + SCHEMA + 原厂/供体 sha，使用前重新校验）与 `cache/axes-mix/prepared-v1`（键含源字节、轴、`font_instance.py` sha，带 sha256 回执）。`cache/` 是 `.luoshu-state/cache` 兼容链接或只有状态目录时都能找到。
* 设备日志 `[MIX-PREPARE] reused instance role=digit` 出自 `common/legacy_v14_4/v142_weighted_mix.sh prepare_instance_cached`，目录为 `$MODDIR/cache/axes-mix/prepared-v1`（不是 `weighted_mix_task.sh` 的按请求临时目录）。
* `collection_cache_key` 去掉 `hyperos_metrics_batch.py` 自身 sha。

设备预估：更新模块后第一次应用同一组合，集合编译与拉丁/数字实例化都命中缓存（此前分别为完整重建）。

## 3. 拉丁/数字实例化前子集化

`legacy_v14_4/font_instance.py --subset latin-digit`（仅 v142 latin/digit 角色传入）：先按 `LATIN_CODEPOINTS ∪ DIGIT_CODEPOINTS` 子集化（保留全部 OpenType 特性闭包、名称表、hinting），再固定轴。实例缓存键升级为 v2 并加入子集范围，CJK 角色不会复用子集实例。

| 场景（NotoSansCJK-VF.otf.ttc 第 0 面，wght=500，latin 角色） | 之前 | 之后 |
|---|---|---|
| font_instance.py 耗时 | 140.0s（输出 15.9 MB） | 2.5s（803 字形，89.5 KB） |

一致性：用两种实例分别生成复合字体（`legacy_v14_4/composite_font.py`），TrueType 基底霞鹜文楷与 CFF 基底 NotoSansSC-Regular.otf 两种情况的输出均**逐字节一致**。

设备预估：导出中 `prepare/prepare latin` 42.3s → 约 1–2s（拉丁源仍需读入与子集化；主机比例 56×，真机读盘开销占比更大，取保守值）。

## 4. ttc 后台异步构建

本轮未做（规模较大，未在时限内完成可验证的完整实现，未提交半成品）。

## 5. 覆盖诊断

* `Noto_COLR_Emoji_Compat*`（AndroidX EmojiCompat 从 Google 字体提供方下载的表情字体）不再作为 app-embedded 依据，列入 keptByDesign。导出中 `io.github.xgl34222220.luoshu`、`com.anthropic.claude` 的唯一“未覆盖”依据就是这个文件。
* 扫描读取进程已映射的 APK（base + split，最多 8 个，仅中央目录，复用 `font_layout_diagnostic.apk_font_names`，整次扫描 APK 读取限时 ≤12s），导出 `apkFontAssets`（res/font、assets 字体资源名）；有非图标类文字字体时给出 app-embedded：“应用很可能用自带字体绘制英文/数字”，对应用户反馈的 Claude、Hark 等 App 数字英文仍是默认、中文已替换。
