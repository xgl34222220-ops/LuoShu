# 字体能力补齐（2026-10）

叠在 HyperOS 覆盖 PR #290 之上。只改字重、TTC/OTC、斜体/衬线、Emoji、补充字库五项；
主模块仍然无 Hook，不涉及启动/卸载/OTA/CI/发布流程，冻结文件未改动。

## 单一判断来源

`common/font_capability.py`（Shell 包装 `common/font_capability.sh`）负责所有“字体能力”判断，
映射器只负责把结果写到 ROM 的文件名上：

| 问题 | 规则 |
| --- | --- |
| 字重 | `OS/2.usWeightClass` 为准；值为通用的 400（或缺失）而样式名明确写了别的字重时以样式名为准；同族多个静态面撞在同一字重时按样式名拆开。名称解析按完整词：ExtraBold/UltraBold=800、SemiBold/DemiBold=600、ExtraLight/UltraLight=200 先于 Bold/Light；`Highlight`、`Nothing` 不会被当成 Light/Thin；支持 `W1–W9`、`100–900`、常见中文字重词。 |
| 100–900 槽位 | 有同字重静态面 → 直接用；可变字体覆盖该字重 → 按 `wght` 轴实例化（其他轴取默认值，度量保持，由后续原厂度量阶段统一处理）；都没有 → 就近字重（距离相同时 ≥400 取更粗、<400 取更细，接近 CSS 字体匹配），可变字体超出轴范围时实例化到最近端点。不再“缺档全落 Regular”。 |
| 声明为可变的 ROM 槽 | `MiSansVF*`、`*-VF`、`*VF`、`*Variable*`、`*Flex*` 保留带 `fvar` 的用户字体（`.luoshu-font-store/variable.font`），不再塞静态 400 实例。用户字体是静态字体时沿用原先的静态选择，度量报告里标记 `variableSlotSource: static-fallback`。 |
| TTC/OTC | 按字体面枚举，按索引取用；锚点永远是单字体 SFNT，不会把整份集合写进 `.ttf` 槽位。 |
| 斜体 | 斜体面（`fsSelection` bit0 / `macStyle` / 样式名）只服务斜体槽，正体槽永远拿不到斜体。 |
| 彩色字体 | 含 `COLR/CBDT/CBLC/sbix/SVG` 的字体不参与文字槽规划。 |
| 补充字库 | 语言专用回退槽（`MiSansTCVF`、`NotoSans*TC/HK/Hant`、`NotoSansSC/CJK*`、`DroidSansFallback`）：原厂文件覆盖该文字而用户字体覆盖率 < 90% 时保持原厂，缺字仍走 ROM 回退链。主 UI 槽 `MiSansVF`/`MiSansVF_Overlay` 不受此限；`MiSansL3` 已由 #290 保持原厂。 |

## 接入点

- 旧版（v14.4）映射器 `legacy_v14_4/rom_adapters.sh`：HyperOS、ColorOS、通用 AOSP 三个分支都先生成
  `.luoshu-font-store/wght-<N>.font`（HyperOS 额外含 350）与 `variable.font`，再按槽位名映射。
  Python 不可用、复合任务（`LUOSHU_MIX_REQUEST_ID`）或字体族为空时返回原有逻辑，行为不变。
- `hyperos_metrics_batch.py`：`weight_for_name` 改用同一解析器；VF 槽优先带 `fvar` 的来源；补充字库门槛；
  报告新增 `variableSlotSource`、`preservedFallbackSlots`。
- `legacy_v14_4/hyperos_clock_compat.sh`（开机补槽）：修正 ExtraBold/UltraLight 推断（审计 B3），
  VF 槽只接受带 `fvar` 的来源（审计 B4），静态槽优先 `wght-<N>.font`。
- `hyperos_global.sh`（v4 路线）：同样的字重解析修正；VF 槽使用可变来源；缺少精确字重文件时使用能力层就近锚点。
- `common/rom_adapters.sh`（v4 路线）：不再把正体写进 `Roboto-*Italic`（审计 B5）。
- `legacy_v14_4/font_switch_safe.sh`：安全切换缓存键纳入能力层代码与可选槽设置，避免复用旧负载。

## 斜体策略（选择与理由）

用户字体族里**有**斜体面：通用 AOSP 路线的 `Roboto-Italic`/`Roboto-BoldItalic` 按斜体面的字重映射。
用户字体族里**没有**斜体面：斜体槽**保持原厂斜体**。没有选择“合成斜体”（对正体做倾斜变换），因为
合成会改变字形与包围盒、需要重算度量，且无法真机验证；保持原厂是现有策略中最安全的一种。
HyperOS 的斜体槽按 #290 的名单策略始终保持原厂。ZIP 导入仍不把斜体文件放进字体库（避免旧的
文件名推断把 `*-Italic` 当成 Regular），直接导入的斜体文件由能力层按 `fsSelection` 识别。

## 可选分槽：衬线与 Emoji

`common/font_slot_options.sh`，设置文件 `config/font_slot_options.conf`：

```
sh common/font_slot_options.sh status
sh common/font_slot_options.sh set-serif <字体ID>     # clear-serif 恢复原厂
sh common/font_slot_options.sh set-emoji <彩色字体文件>  # clear-emoji 恢复原厂
```

- 默认都不启用：衬线槽（`NotoSerif*`、`MiSerif*` 等）与 Emoji 文件（`NotoColorEmoji*`）保持原厂。
- 衬线：只写正体单字体衬线槽；斜体、等宽、集合保持原厂；中文衬线槽（SC/TC/HK/CJK/MiSerif）要求所选字体覆盖汉字，否则保持原厂。
- Emoji：只接受彩色字体；`_font_alias` 拒绝任何文字字体写入 `*Emoji*` 文件名，只有可选 Emoji 槽能写。
- 直接导入彩色字体时不再当作文字字体，存入 `/sdcard/LuoShu/emoji/`。
- 设置修改后需重新应用字体并重启。App 界面入口尚未接入（后续 PR）。

## 导入

- 原生导入接受 `.otc`；TTC/OTC 拆分失败时给出拆分器的明确原因。
- 拆分器逐个字体面处理：位图/无轮廓、缺 cmap、彩色字体面跳过并在结果 `skipped` 里列出原因；
  全部不可用时拒绝导入。拆出的文件名为 `<family>-<hash8>-<Weight>`（斜体 `-Italic[-Weight]`），
  同一集合的同族字体面在字体库里组成一个字体族。
- ZIP 字体包内的 `.ttc/.otc` 先按字体面拆分再参与字体族判断，字体库不再保存整份集合。
- 导入探针的字重同样使用 “usWeightClass + 样式名” 规则，斜体同时检查 `fsSelection`。

## 需要真机确认

1. 可变 CJK 字体在手机上实例化 9–10 个字重的耗时（预热任务超时 360 s）。
2. HyperOS `100/200/300/400/700.ttf` 与 `Roboto-*` 换成实例后，设置页/通知/桌面粗细层级是否正确；`MiSansVF` 保留 VF 后 MiPro 动态字重是否生效。
3. TC/HK 语言下 `MiSansTCVF` 在用户字体缺繁体时保持原厂的显示效果。
4. 启用 Emoji 槽后，`/data/fonts/files` 中可更新的 `NotoColorEmoji` 是否会覆盖模块文件（Android 可更新字体优先）。
5. 启用衬线槽后，阅读/笔记类应用的衬线文字行高（衬线槽没有原厂度量契约，沿用用户字体度量）。
