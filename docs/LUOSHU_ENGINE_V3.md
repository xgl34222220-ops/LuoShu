# 洛书字体引擎 v3（重构）

状态：**实施中**。维护者决定（2026-10）：完全重构；生成方式为“直接替换 + 只对齐行高”；在 `claude/laughing-hypatia-ogd2oz` 上逐步替换。

## 为什么重构

旧通用引擎（Phase 4–9）按原厂字形几何逐槽位对齐生成字体：每个原厂文件、每个 XML 字重单独编译，再用十几项几何/身份检查决定能否部署。真机上的问题几乎都来自这一层：编译慢、HyperOS/ColorOS 的 OEM 字体常被检查拦下、任何一个槽位失败整次切换失败。

v3 的原则：**换掉文字字体文件本身，只保留原厂的行高**。字形大小与基线按用户字体自身的设计，不再逐字形对齐原厂。

## 保留的部分

- 设备字体拓扑（`font_topology_snapshot`）与角色分类（`font_role_shadow`）：决定哪些文件是文字字体。
- 下次启动暂存、自挂载、回滚（`universal_next_boot.sh`、`universal_mount_runtime.sh`）：v3 输出同一 `deployment.json` 格式（`universal-font-deployment-v1`），启动层不变。
- App 协议：单字体与组合字体任务、进度、状态文件不变。

## 流程

```
拓扑 + 角色 + 用户字体
  → 选目标（哪些文件替换、哪些保留原厂）
  → 生成（每个目标文件一份输出，只改行高表）
  → 改写 XML（仅在需要时）
  → 负载 payload/ + deployment.json
  → 暂存到下次启动
```

### 选目标

| 角色 | 处理 |
|---|---|
| ui-sans、cjk、latin、clock、numeric | 替换 |
| 未知但同时含汉字与拉丁字母的文字字体 | 替换（OEM 主字体常见） |
| emoji、symbol-icon、serif、monospace、special-fallback | 保留原厂 |
| `/data/fonts` 动态字体 | 保留原厂 |

单字体时，若目标含汉字而用户字体没有汉字（或目标只有拉丁而用户字体没有拉丁），该目标保留原厂。组合字体包含中/英/数，所有文字目标都用组合结果。不再有“核心失败整体报错”之外的拦截：只要至少一个界面字体被替换，切换就成功；保留原厂的文件在完成提示中列出。

### 生成

- **行高**：输出的 `hhea` ascent/descent/lineGap、`OS/2` typo/win 与 USE_TYPO_METRICS 位取自原厂（按 UPEM 换算）；删除 `MVAR`（避免可变字体在不同字重改变行高）。其余表来自用户字体。
- **可变保留**：单字体且用户字体有 `wght` 轴 → 输出就是该可变字体（只改行高），所有 XML 节点写入 `<axis tag="wght" stylevalue="节点字重"/>`。
- **静态**：用户字体是静态多字重，或组合字体 → 按每个需要的（字重, 斜体）生成静态实例。**只替换已存在的文件，不新增文件名**（KernelSU 等按文件 bind 的挂载只能替换 ROM 中已有的文件，HyperOS 3 真机诊断包证实新增文件不可见、开机验证失败回滚）：内容与原厂字重实例相同的字重直接沿用该文件；不同的字重作为同一文件的额外字体面（输出为 TTC），XML 节点用 `index` 选择。全部固定模式的组合因此只有一个字体面。
- **组合**：中文基底 + 英文/数字字形拷入（码位集合与旧组合引擎相同，按基底大写字母高度缩放、落到基线）。
  - 中文为可变字体（auto）时输出**可变组合**：英文/数字在基底的 5 个字重位置采样，写成 gvar 变化数据（删除 HVAR，字宽变化走 gvar 幻影点），一份文件覆盖所有字重；固定模式或静态的英文/数字以静态字形导入。
  - 中文为固定模式或静态字体时，按字重生成静态组合并改写 XML。
  - HOST_ONLY 基准（Roboto + Noto Serif SC + Noto Sans TC 槽位各 9 字重）：可变组合首次 14 s / 53 MB；静态逐字重 160 s / 286 MB；旧引擎 245 s。
- **TTC**：原厂是字体集合时输出同样数量的面，XML 的 `index` 不变。
- **缓存**：实例按（源字体、模式、字重、斜体）缓存；相同行高的目标共享同一输出（硬链接）。

### XML 改写

只改写引用了被替换文件的 `<font>` 节点：设置轴、改文件名、去掉 `postScriptName`。其余内容（注释、别名、其他家族）保持原样。只有改动过的 XML 进入负载。

- **主题覆盖层**：HyperOS 的 `sans-serif` 第一位是 `MiSansVF_Overlay.ttf`（指向 `/data/system/theme` 主题字体的链接，HyperOS 3 上是 8.9 KB 的英文/数字桩）。不改写时英文和数字一直取自它。`<原厂名>_Overlay.ttf` 节点改指向被替换的原厂文件。
- **旧引擎残留名**：在旧通用流水线 XML 挂载期间采集的快照含 `LuoShu-<原厂名>-<字重>.ttf`（文件已不存在，家族整体失效），映射回原厂文件。快照采集不再记录含 LuoShu 文件名或与当前负载相同的 XML。
- **OEM 副本**：`system_ext` 的 `hyper_fonts.xml`、`miui_fonts.xml` 等与 `fonts.xml` 内容相同，系统可能加载它们，按文件名（同分区优先，再 `/system/fonts`）同样改写；仅在设备上真实存在时写入负载。
- 节点字重从 XML 本身读取（拓扑对未解析名只记一条）。

## 不做的事

- 不逐字形对齐原厂几何，不做时钟等宽对齐。
- 不旁路 `/data/fonts` 动态字体更新。
- 不回退旧引擎。

## 实施阶段

- E1：核心生成器 `common/luoshu_engine.py` + 组合合成 `common/luoshu_merge.py` + 测试。
- E2：接入单字体/组合切换入口与暂存（`common/luoshu_engine.sh`；`universal_font_cutover.sh` 的 `_uc_universal` 改为“生成 → 暂存”，不再经过旧闸门）。负载格式与校验独立为 `common/luoshu_payload.py`，下次启动、自挂载与回滚改用它。
- E3：开机验证适配（`common/luoshu_verify.py`）：运行/挂载身份一致、每个负载文件在系统路径可见且摘要一致，否则 FAIL 并自动回滚；FontManager 未引用替换文件只记 WARN。
- E4：诊断包与电脑复现改用 v3。
- E4：诊断包记录引擎报告与源字体，`tools/replay_diagnostics.py` 在电脑上用 v3 重放。
- E5a（已完成）：删除旧通用流水线（FontPlan、XML Route、编译器、部署构建、接管闸门、源字体 Profile）及其测试与专用 CI 工作流；测试夹具移到 `scripts/font_fixtures.py`。旧 Phase 8 验证器保留，用于升级前已生效的旧格式负载。
- E5b：删除旧引擎 `legacy_v14_4`（导入、校验、启动与安装脚本仍在引用，需逐项迁移）。
