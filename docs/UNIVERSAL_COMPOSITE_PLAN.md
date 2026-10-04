# 组合字体接入通用字体引擎：方案（草案）

> **已被取代（2026-10）**：本文描述的 Phase 4–9 流水线（FontPlan / XML Route / 编译器 / 部署构建 / 接管闸门）已删除，由字体引擎 v3 取代，见 `docs/LUOSHU_ENGINE_V3.md`。拓扑、角色分类、下次启动暂存与自挂载仍沿用本文对应部分。本文仅作历史记录。

状态：**方案 B 已实现（B1–B4），待真机验证**。维护者决定组合与单字体都不再回退旧引擎（见 `docs/UNIVERSAL_FONT_ENGINE_REFACTOR.md` Phase 10）。

所属阶段：Phase 9 之后的扩展，记为 **Phase 10 — Role-Assigned Composite**。按路线图“变更纪律”，实施前先在 `docs/UNIVERSAL_FONT_ENGINE_REFACTOR.md` 登记。

## 1. 现状（代码事实）

App 的“组合”入口：

```
app_bridge.sh mix_start
  → font_mix_controller.sh
  → legacy_v14_4/mix_router.sh          搭建 .legacy-v14-runtime（MODDIR=运行时目录），在 MIX_STAGE 上工作
  → v14_mix.sh → v142_weighted_mix.sh / v143_auto_multiweight_mix.sh
      每个字重：font_instance 实例化中/英/数 → composite_font.py 合成一份静态字体
      9 个字重 → 临时家族 LuoShuAutoMix
  → 运行时内 font_manager.sh action switch LuoShuAutoMix   （LUOSHU_REAL_MODDIR 已设置）
  → universal_font_cutover.sh：LUOSHU_REAL_MODDIR / LuoShuAutoMix → 直接 legacy
  → font_switch_safe.sh 写 MIX_STAGE，mix_router 提交为下次启动负载；active_font=mix
```

- 新引擎从未参与组合切换，组合的覆盖完全取决于旧引擎。
- 每次组合切换都要把三款源字体按 9 个字重各合成一次完整字体（中文基底约 3 万字形），这一步本身是组合切换最慢的部分之一。
- 每个角色的模式：`auto`（随目标字重取实例）或 `fixed`（所有字重用用户指定的同一实例）。

## 2. 目标与约束

- 用户指定的分工必须严格保持：中文字形来自 A，英文来自 B，数字来自 C。新引擎目前“按能力自动挑源”的选择逻辑不能用于组合。
- 不增加 Hook、不常驻；旧引擎保留为完整退路（同一任务内回退，沿用 `LUOSHU_UNIVERSAL_DEADLINE` 时间预算）。
- 复用新引擎已有的身份链（FontPlan → RoutePlan → Artifacts → Deployment → Phase 8 验证），不另建第二套。

## 3. 两种接法

### 方案 A：合成后再交给新引擎

旧流程照常生成 `LuoShuAutoMix` 9 个静态字重，然后把它当作普通单字体交给新引擎。

- 优点：改动最少；`composite_font.py` 是已验证的合成器。
- 缺点：
  - 源是 9 个**静态**字体，无法使用“多个字重共用一份可变产物”，可变原厂槽位（Roboto、可变中文）每个 XML 字重都要单独 stock-shell 编译；
  - 9 次完整合成的成本仍在，又叠加新引擎编译，总耗时大概率超过现在；
  - 运行在 `.legacy-v14-runtime` 内，需要把切换改回真实模块目录，并让 mix_router 的 MIX_STAGE 提交与新引擎的 `.luoshu-payload-next` 互斥。

结论：**不推荐**。它把两套引擎的成本相加，却拿不到新引擎的主要收益。

### 方案 B（推荐）：新引擎原生按角色取源

不再预先合成。新引擎直接拿到三款源字体和用户的分工，按每个原厂槽位实际需要的字符决定从哪款源取字形。

各类槽位的处理：

| 原厂槽位 | 需要的字形 | 编译方式 |
|---|---|---|
| 拉丁界面（Roboto、GoogleSans 等，无汉字） | 英文←B，数字←C | B 与 C 为同一字体且模式为 `auto`：直接用现有 `source-variable-preserve` 分组产物；否则多源 stock-shell |
| 中文回退（`lang=zh-*` 家族） | 汉字←A | 模式为 `auto` 时：A 的 `source-variable-preserve` 分组产物 |
| OEM 主字体（MiSans、SysFont 等，含汉字与拉丁） | 汉字←A，英文←B，数字←C | 多源 stock-shell（按字符类别分别取源） |
| 时钟/数字（Mitype、AndroidClock） | 数字←C | 现有 specialized 路径（原厂精确字宽） |

关于中文回退槽位只取 A 的依据：Android 为每个字符按家族顺序查找字形，`sans-serif` 段落中的英文数字通常由前面的拉丁界面槽位提供，中文回退家族主要承担汉字。这一点在 OEM 上可能不同（例如 HyperOS 把 MiSans 放在主家族），所以 OEM 主字体走多源合成；具体顺序需要在真机 `fonts.xml` 上确认。

固定模式（`fixed`）的角色：该角色的源先实例化为用户指定的单一实例，所有 XML 字重共用它（静态源，不分组）。

### 方案 B 的额外收益

省掉“9 个字重 × 整份中文合成”这一步：拉丁槽位只处理几百个字形；中文回退槽位直接复用 A 的可变产物；只有 OEM 主字体需要做汉字 + 拉丁的合成，并且可以沿用这次加入的“先裁剪再实例化”优化。

## 4. 分阶段实施（方案 B）

每一步单独提交，单独测试，未完成前组合切换继续走旧引擎。

**B1 — 角色化源字体档案**（`font_source_profile.py`）
- 新增入口：接受 `{cjk: 文件, latin: 文件, digit: 文件}` 及每个角色的模式与轴，输出的每个 face 带 `assignedRoles`。
- `profileId` 纳入分工与模式，保证不同分工产生不同身份。
- 测试：同一组文件、不同分工的 `profileId` 不同；缺字检查沿用组合预检的三条规则。

**B2 — FontPlan 按分工选源**（`universal_font_plan.py`）
- 当档案带分工时，`_select_face` 只在被指派该角色的 face 中选择；目标需要多个角色时，记录 `sources: {cjk, latin, digit}`，不再只有单一 `source`。
- 校验：组合计划中任何目标的拉丁/数字字形不得来自未被指派的字体。
- 测试：B≠C、A=B=C、OEM 主字体三种组合的计划快照。

**B3 — 多源编译**（`universal_font_compiler.py`）
- stock-shell 增加按字符类别分别取源：汉字类←A、拉丁类←B、数字←C，复用 `_eligible_codepoint` 的分类与按源裁剪。
- 路由分组只在“目标只需一个来源”时启用 `source-variable-preserve`。
- 测试：输出中逐字符核对字形来源；与旧引擎 `composite_font.py` 在同输入下的英数字形一致性对比（允许度量对齐差异，记录差值）。

**B4 — 入口与状态**
- `mix_router.sh start`：在搭建 `.legacy-v14-runtime` **之前**，用真实模块目录调用新的 `universal_font_cutover.sh switch-composite`；成功则不进入旧运行时；失败或超出预算时清理未提交的 next 负载，再进入原有旧流程（同一任务）。
- 身份：新引擎记录家族为 `mix`，`font_mix.conf` 照旧写入；Phase 8 验证与回滚使用同一身份，避免 `LuoShuAutoMix` 与 `mix` 混用。
- 测试：沿用 `universal_font_cutover_test.sh` 的伪模块方式，覆盖成功、闸门拒绝、超时回退、旧 next 负载被新请求取代四种情况。

**B5 — 基准与真机**
- `tools/universal_engine_benchmark.py` 增加组合模式，与旧流程（9 字重合成 + 旧引擎）在同输入下对比耗时。
- 真机矩阵：HyperOS 3、ColorOS 16、AOSP 各一台；检查状态栏、锁屏时钟、设置、桌面、Google 应用中的中/英/数来源。

## 5. 待决问题

1. **OEM 主字体在家族中的顺序**：需要真机 `fonts.xml`（HyperOS 3、ColorOS 16）确认，决定 OEM 主字体是否必须三源合成。
2. **固定模式 + 可变原厂**：用户把某角色固定为单一实例时，可变原厂槽位所有字重共用一个静态实例，系统粗体（700）会显示为用户选的字重。这与旧引擎行为一致，但应在 App 中提示。
3. **源字体缺字**：多源产物中，B 缺少的拉丁扩展字符是保留原厂字形还是交给系统后备。建议保留原厂（与 stock-shell 现有行为一致），需在 B3 中定下来。
4. **缓存键**：组合的编译缓存按 artifactId 复用，artifactId 已包含 FontPlan（含分工）。切换回之前用过的组合可直接复用，无需额外设计。

## 6. 实现后的测量（HOST_ONLY）

桌面 x86 CPython，非 Android 耗时。中文 Noto Sans SC VF、英文与数字 Roboto VF（同一可变字体，auto）；原厂槽位各 9 个 XML 字重：Roboto（拉丁界面）、Noto Serif SC（`zh-Hans` 回退）、Noto Sans TC 充当 `mipro` OEM 主字体。

| 槽位 | 产物 | 方式 |
|---|---|---|
| Roboto | 1 | 单一 auto 来源，共用 `source-variable-preserve` |
| 中文回退 | 1 | 单一 auto 来源，共用 `source-variable-preserve` |
| OEM 主字体 | 9 | 三源 `composite-shell`，逐字重 |

首次编译 245 s（11 个产物全部 ready），同一组合再次切换（缓存命中）0.24 s。耗时几乎全部来自 OEM 主字体的 9 次逐字重合成（约 25 s/次）。

**风险**：手机通常慢 2–4 倍；若真机 OEM 主字体同样有 9 个带 `<axis>` 的字重节点，首次组合可能超过 600 s 预算并报错（不会改动当前字体）。候选优化：为多来源的可变 OEM 槽位生成单一可变产物（以中文基底为底，拷入英文/数字字形及其变化数据），需对齐两款字体的轴、换算 gvar/HVAR，待真机耗时数据确认后再做。
