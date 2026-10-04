# 通用字体引擎：切换超时与覆盖缺口修复记录（2026-10-04）

> **已被取代（2026-10）**：本文描述的 Phase 4–9 流水线（FontPlan / XML Route / 编译器 / 部署构建 / 接管闸门）已删除，由字体引擎 v3 取代，见 `docs/LUOSHU_ENGINE_V3.md`。拓扑、角色分类、下次启动暂存与自挂载仍沿用本文对应部分。本文仅作历史记录。

分支：`claude/laughing-hypatia-ogd2oz`，基于 main `0388b57`（Phase 1–9）。

## 背景

通用引擎未发布的直接原因：单字体切换耗时过长，超时后回到 1.1.1 旧引擎。排查时另外发现，即使不超时，HyperOS / ColorOS 的主字体也不会被新引擎替换。

## 修复内容

| 提交 | 类型 | 内容 |
|---|---|---|
| `95d27e4` | 正确性 | 原厂可变 glyf 字体（Android 12+ Roboto，经 `<axis>` 路由）走 stock-shell 时，先替换轮廓、后解码 gvar，fontTools 抛 `AssertionError`，所有此类产物 blocked → 回退旧引擎。改为替换前完整解码 gvar。 |
| `9402e1e` | 覆盖 | 角色分类只认 `sans-serif/system-ui/ui-sans/sans`，HyperOS `mipro/misans`、ColorOS `sysfont/oplus-sans` 主字体被归为 `unknown-protected`，从不替换。复用旧引擎的 `font_config_overlay.is_safe_family`；Mitype 走时钟专用路径。`ROLE_REVISION` → 2。 |
| `b80be52` | 覆盖 | 切换闸门只要有一个可替换目标就放行，未分类的中英文字体会被静默保留原厂。现在有含 Han/Latin 覆盖的 `review` 目标时回退旧引擎（`unclassified-text-slot`）。 |
| `10baeaf` | 超时 | 新引擎没有独立时限，耗尽整个切换时限后旧引擎也被一起终止。新引擎默认最多使用切换时限的一半（`LUOSHU_UNIVERSAL_BUDGET_SECONDS` 可覆盖），编译器在截止后不再开始新单元。 |
| `5bff346` | 提速 | 每个 XML `<font>` 节点单独编译：同一可变字体被 9 个字重引用就重建 9 次。路由器把源字体轴能覆盖的节点合并为一份 `source-variable-preserve` 产物（Android 运行时按 `<axis>` 实例化）；编译结果按 artifactId + 原厂/输出哈希跨次复用。 |
| `309e0ce` | 提速 | variable-preserve 先整字体实例化预检、再对输出实例化校验，两次重复；只保留输出校验。 |
| `4c4b95d` | 正确性 | 计划阶段用原厂可变字体默认实例的字重判断范围；中文可变字体常默认 Thin(100)，导致 200–900 的源字体整槽被拦。分组产物改按节点实际字重检查。 |
| `a9b0663` | 提速 | stock-shell 只需要原厂字体已有字符的字形，却实例化整个源字体（中文约 3.1 万字形）。先懒加载并裁剪到所需字符再实例化。 |
| `18e5874` | 提速 | 原厂几何与输出校验只读全局度量和探测字形，却实例化整个字体。先裁剪到探测字再实例化。 |

## 测量（HOST_ONLY）

工具：`tools/universal_engine_benchmark.py`，桌面 x86 CPython 3.11 + fontTools 4.63.0，**不是 Android ARM64 耗时**。

输入：模拟 Android 15 `fonts.xml`——Roboto VF（`sans-serif` 9 个字重 + `sans-serif-condensed` 9 个字重，带 `<axis>`）与一个可变中文槽（`zh-Hans` 9 个字重）；源字体 Noto Sans SC VF（31036 字形），中文原厂替身 Noto Serif SC VF。共 27 个 XML 节点。

| 版本 | 编译单元 | Phase 6 编译耗时 |
|---|---|---|
| 改动前（仅含 gvar 修复，否则 Roboto 全部 blocked），cProfile 下 | 27 × stock-shell | 2032 s |
| 全部改动，cProfile 下 | 2 × variable-preserve + 9 × stock-shell | 117 s |
| 全部改动，无 profiler | 同上 | 34.8 s |
| 全部改动，再次切换同一字体（缓存命中） | 11 个复用 | 0.09 s |

等价性：裁剪优化（`a9b0663`、`18e5874`）在真实字体上对比改动前后——stock-shell 输出 SHA-256、几何规划、替换字形数一致；几何画像在 5 组字重/字宽下逐字段一致；完整编译 manifestId 与全部产物哈希一致。

## 尚未验证

- 未在 Android 真机或 ARM64 上运行；手机耗时预计为上表的数倍。
- 未使用真实 HyperOS 3 / ColorOS 16 的 `fonts.xml` 与原厂字体，OEM 族名来自旧引擎名单与仓库记录。
- 分组产物使用整个源字体：源字体缺失的字形改由系统后备字体显示，不再保留原厂 Roboto 字形（与旧引擎“直接字体”的整体替换一致）。
- condensed 等需要源字体不具备的轴（`wdth`）的节点仍逐个编译。
- `/data/fonts` 主题字体层仍只作警告，未改。
