# 洛书通用字体引擎重构总路线

> 本文档是洛书“全系统通用换字体”重构的唯一权威路线图。后续实现、PR、测试和兼容补丁必须以本文档为准；如果设计发生变化，先更新本文档，再改代码，避免边做边偏。

长期追踪 Issue：#254。Phase 2 实现 PR：#255。

## 最终目标

把洛书从“按 ROM / 文件名堆规则的字体替换模块”重构为：

**Android Universal Font Compiler**
= 设备字体拓扑识别 + 字体角色分类 + 字体兼容编译 + 最小路由补丁 + Systemless 挂载 + 自动验收。

目标系统包括但不限于 HyperOS、ColorOS/OxygenOS、OriginOS、One UI、MagicOS、Flyme、Pixel/AOSP，以及未来未见过的新 ROM。

## 不可偏离的原则

1. **不使用 Zygisk / LSPosed / App Hook。**
   系统字体链能覆盖的范围全部通过 ROM 原生字体配置、systemless overlay 和可验证的动态字体机制完成。

2. **ROM 名称不是主逻辑。**
   HyperOS / ColorOS 等识别仅允许作为兼容提示和回退，不允许继续成为核心替换规则的 source of truth。

3. **设备真实拓扑是唯一输入。**
   任何替换计划必须来自本机扫描得到的字体 family、XML 路由、物理槽位、运行时 FontManager 和 /data/fonts 状态。

4. **先识别角色，再决定替换。**
   不允许因为一个文件“看起来像系统字体”就直接替换。

5. **未知默认保护。**
   未能高置信度分类的字体一律先保留，不允许为了“覆盖更多”而盲换。

6. **Emoji / Icon / Symbol 永久禁止通用替换。**
   只有独立专用功能可以显式处理这些角色。

7. **Serif / Code Monospace 默认保留。**
   用户只选择“系统字体”时，不改变 serif 与代码等宽字体。

8. **Clock / Numeric 是专用角色。**
   它们可以替换，但必须经过独立数字覆盖与度量契约，禁止直接套普通 UI 字体逻辑。

9. **OEM 原始 XML 结构必须保留。**
   洛书只能最小化 patch 当前设备自己的 XML；不允许拿一份通用 AOSP XML 覆盖 OEM 配置。

10. **/data/fonts 是独立层。**
    允许识别、验证和有条件处理，但禁止粗暴清空、盲写或把它当普通 /system/fonts 目录。

11. **所有新引擎先 Shadow Mode。**
    新算法必须先只生成计划，与当前实现比较；未通过真实设备和回归测试前不得接管实际替换。

12. **切换路径必须可回滚、可验证、无后台死循环。**
    失败必须 fail-safe；不得靠永久 watcher、无限重试或重启循环掩盖问题。

## 阶段路线

### Phase 1 — Device Font Topology
状态：**已完成 / PR #253**

产物：

- `config/device_font_topology.json`
- 合并原厂 inventory、fonts XML、FontManager runtime evidence、mountinfo、`/data/fonts`
- OTA / 安装 / 首次开机补扫 / App 手动重扫后可重建

完成标准：

- 不修改任何实际字体
- 能表达 family → slot → partition → XML → runtime 的关系
- 未知 OEM 分区可以进入拓扑

### Phase 2 — Role Classifier + Shadow Replacement Plan
状态：**已完成 / PR #255 / device-font-roles-v1 + device-font-shadow-plan-v1**

目标：

对每个拓扑槽位分类，并生成“如果新引擎接管会怎么处理”的只读计划。

标准角色：

- `ui-sans`
- `cjk`
- `latin`
- `numeric`
- `clock`
- `monospace`
- `serif`
- `emoji`
- `symbol-icon`
- `special-fallback`
- `unknown-protected`

Shadow 动作：

- `replace`：普通系统 UI 候选
- `conditional`：依赖源字体覆盖能力
- `specialized`：数字/时钟等需要专用编译
- `preserve`：必须保留
- `review`：证据不足，禁止自动替换

产物：

- `config/device_font_roles.json`
- `config/device_font_shadow_plan.json`

额外要求：

- 同时记录当前旧引擎 `replaceable` 结论
- 输出 `agree / current-gap / current-overreach / not-comparable`
- 第二阶段不允许实际写入字体或 XML

### Phase 3 — Imported Font Analyzer / Compiler Input
状态：**已完成 / PR #256 / source-font-profile-v1**

目标：

统一解析 TTF / OTF / TTC / OTC / Variable Font；导入 WOFF/WOFF2 时先转换。

必须读取：

- cmap
- name
- OS/2
- head
- hhea
- maxp
- GSUB / GPOS
- fvar / avar / STAT
- HVAR / VVAR / MVAR
- TTC face index

输出：

- 字形覆盖
- language/script 能力
- 可变轴
- 字重
- 度量
- 字体角色适配能力

标准产物：

- `config/source-font-profiles/*.json`
- Schema：`source-font-profile-v1`
- WOFF/WOFF2 必须先通过 `font_web_convert.py` 解包为真实 SFNT，禁止仅改扩展名
- Phase 4 只能消费 Source Profile，不得重新散读多个旧探测器

### Phase 4 — Universal Replacement Planner
状态：**已完成 / PR #257 / universal-font-plan-v1**

输入：Phase 1 拓扑 + Phase 2 角色 + Phase 3 源字体能力。

输出一份确定性 `FontPlan`，不得直接修改系统。

标准产物：

- `config/universal-font-plans/*.json`
- Schema：`universal-font-plan-v1`
- `planId` 必须由设备 buildKey、Source Profile 与确定性 targets 计算，重复输入必须得到同一 ID
- Phase 4 可以选择具体 source face、目标字重、目标槽位与后续 compiler requirement
- Phase 4 不允许生成字体文件、不允许 patch XML、不允许 mount、不允许声明 `executableNow=true`
- Phase 5/6/7 只能消费 FontPlan，不能重新绕过它自行挑目标槽位


计划必须说明：

- 哪些槽替换
- 哪些槽保留
- 哪些 family 改路由
- 哪些角色需要独立编译
- 为什么这么决定
- 风险与回退方案

### Phase 5 — Minimal XML Router
状态：**已完成 / PR #258 / minimal-xml-route-plan-v1**

目标：

从设备自己的：

- `fonts.xml`
- `font_fallback.xml`
- `fonts_customization.xml`
- OEM 自定义字体 XML

生成最小 patch。

禁止：

- 用通用模板覆盖整个 ROM XML
- 删除未知 OEM family
- 打乱 fallback 顺序
- 丢失 lang / variant / fallbackFor / axis 等属性

标准产物：

- `config/minimal-xml-route-plans/*.json`
- Schema：`minimal-xml-route-plan-v1`
- 只允许消费已经通过完整性校验的 `universal-font-plan-v1`
- 只按 `sourceXml + family + weight + style + index + declared + postScriptName` 精确定位原厂节点
- 找不到唯一节点、原厂快照缺失、同一节点发生 artifact 冲突时必须 fail-closed，禁止部分 XML 渲染
- 允许的 XML 变化只有目标 `<font>` 的文本引用；family/family-list/alias/fallback 顺序、全部属性、TTC index、postScriptName、axis 子节点必须保持
- XML 原有 index/axis/postScriptName 不再被删除，转成 Phase 6 的 artifact contract，由编译器满足
- `/data/fonts` 动态层只标记 deferred，不在 Phase 5 修改
- Phase 5 不发布系统 XML、不 mount，仍强制 `mutatesSystem=false`、`executableNow=false`

### Phase 6 — Metrics / Variable Font Compiler
状态：**已完成 / PR #259 / universal-font-artifacts-v1**

目标：

针对目标槽位生成兼容字体。

重点解决：

- HyperOS baseline 偏移
- 状态栏 / QQ 标签 / 秒表数字偏移
- static ↔ variable font 不兼容
- 多字重
- UPEM / ascent / descent / lineGap / capHeight / xHeight
- 数字宽度和 clock exact-width

标准产物：

- `config/universal-font-artifact-manifests/*.json`
- 私有编译缓存 `cache/universal-font-artifacts/*`
- Schema：`universal-font-artifacts-v1`
- Phase 6 只能编译 Phase 4/5 已冻结的 target/artifact contract，不得重新选择目标槽位
- 普通静态 UI 优先保留用户字体自身 GSUB/GPOS，再按原厂脚本几何与 line contract 编译
- Clock/Numeric、collection、XML 固定 axis 目标优先保留原厂容器/advance/face contract，只替换目标脚本字形
- 纯物理 variable 目标只有在 axis range 与天然几何均通过原厂校验时才保持 variable；不允许静默静态化
- TTF/glyf 与 OTF/CFF/CFF2 都必须显式处理，禁止靠扩展名伪装轮廓格式
- TTC/OTC 必须保留非目标 face，按 FontPlan/RoutePlan 指定 face index 编译
- 编译产物仍不得发布或 mount；Phase 6 强制 `mutatesSystem=false`、`executableNow=false`

### Phase 7 — Unified Mount Backends
状态：**已完成 / PR #260 / universal-font-deployment-v1**

上层只接受同一份 `FontPlan`。

后端分别处理：

- Magisk
- KernelSU
- APatch

禁止三套字体判断逻辑。

标准产物：

- `config/universal-font-deployments/*/deployment.json`
- Schema：`universal-font-deployment-v1`
- Magisk / KernelSU / APatch 必须消费完全相同的 payloadDigest；差异只能是 hook 时机
- XML route artifact、physical-only artifact、`/data/fonts` dynamic artifact 均来自 Phase 6 manifest，Mount Backend 不得重新扫描或重新选槽
- XML route artifact 放在原 target font 目录并由 Phase 5 XML 指向；physical-only 保持原逻辑路径；dynamic artifact 只读 bind 回原 `/data/fonts` 目标
- system/product/vendor 等 payload 与 dynamic bind 必须视为同一事务；任一动态 bind 失败必须回滚本次 systemless mount
- 新部署通过 `.luoshu-payload-next` 在 next boot 原子切换，旧 payload 保留到 Phase 8 验证完成
- 当前迁移阶段正式换字体按钮仍不自动 stage-next；只有显式内部 stage-next 才进入新 runtime

### Phase 8 — Runtime Verification
状态：**已完成 / PR #261 / universal-font-runtime-verification-v1**

重启后自动验证：

- family 是否加载
- 物理槽是否真实暴露 Phase 7 的同一份 payload 哈希
- CJK / Latin / digits 是否覆盖
- 多字重 / variable axis 是否满足冻结 contract
- /data/fonts 是否仍为只读 bind，且未被运行时层反向覆盖
- 目标 FontManager 是否真实命中新字体
- Phase 6 baseline / bounding box 几何校验是否仍与运行时可见文件身份一致

标准产物：

- `config/universal-font-runtime-verification.json`
- `config/universal-font-runtime-verification.conf`
- Schema：`universal-font-runtime-verification-v1`
- 只消费 Phase 4 FontPlan、Phase 6 Artifact Manifest、Phase 7 Deployment 与当前 boot runtime evidence，不允许重新扫描或重新选择目标槽位
- `PASS`：payload 身份、可见哈希、动态挂载、脚本覆盖、字重/轴和编译几何证据均成立
- `WARN`：systemless payload 已被强证据确认，但 FontManager dump 被 OEM 隐藏/裁剪等软证据不足
- `FAIL`：部署身份、文件哈希、动态挂载、脚本覆盖、字重/轴或几何 contract 任一关键条件失败
- 只有 `PASS` 才释放 Phase 7 保留的 retired payload；`WARN/FAIL` 必须继续保留回滚材料
- 验证器是一次性 boot-scoped 任务，禁止常驻 watcher 和无限重试

最终给用户 PASS / WARN / FAIL，而不是让用户盲测。

### Phase 9 — Controlled Production Cutover
状态：**已完成 / PR #262 / universal-font-production-cutover-v1**

目标：

让 App 正式“换字体”入口开始优先使用 Phase 1–8 的 Universal Font Engine，同时保留旧物理字体引擎作为 fail-safe fallback，禁止一次性删除生产退路。

生产切换顺序：

1. 正式入口先进入统一 Cutover Controller，不再直接调用旧 `font_switch_safe.sh`
2. `default`、复合字体临时 family、Universal 前置条件缺失时继续走旧引擎
3. 普通单字体优先执行 Universal prepare → readiness gate → stage-next
4. Universal prepare / route / compile / deployment / gate 任一步失败时，清理未提交的新引擎 next payload，并在同一任务中回退旧引擎
5. Universal 成功只写 next-boot payload；当前 Android boot 的 live payload 永远不原地改写
6. 重启后由 Phase 8 自动验证；PASS 才释放 retired payload，WARN 保留回滚材料
7. FAIL 不允许继续宣称字体已生效，必须安全准备上一生产 payload 的 next-boot rollback；禁止当前 boot 强拆挂载、禁止自动重启、禁止回滚循环
8. 旧 HyperOS / ColorOS / Generic 路由在 Cutover 稳定前继续保留，只能作为 fallback，不再作为新入口的第一选择

Cutover readiness gate 必须至少满足：

- FontPlan / RoutePlan / Artifact Manifest / Deployment 身份链一致
- FontPlan 不存在 `blocked` replacement target
- `missingRoleSlotCount=0`
- 自动替换角色只允许 `ui-sans / cjk / latin / numeric / clock`
- Emoji / Symbol / Serif / Monospace / unknown-protected 继续保持 preserve/review
- RoutePlan `routingComplete=true`
- Artifact Manifest `blockedCount=0` 且 `deploymentReady=true`
- Deployment `activationReady=true`
- Phase 7 payload 完整性校验通过后才允许写入 `.luoshu-payload-next`

生产回退要求：

- Universal 前置构建失败：同一次前台任务直接回退旧引擎，不要求用户重新点一次
- Universal 已重启但 Phase 8 FAIL：只准备上一生产 payload 供下次完整重启恢复，不在当前 boot 改写 live payload
- rollback 自身如果再次验证失败，只报告 FAIL 并保留诊断材料，禁止在两个 payload 之间无限来回
- legacy/default payload 重新接管时必须清除 Universal runtime 状态，避免旧 payload 被 Universal Mount Backend 错误解释

> **2026-10 更新（维护者决定）**：旧引擎自动回退已停用。单字体、组合字体与恢复系统字体全部只走通用引擎；通用引擎无法安全应用时直接报错（附闸门/准备阶段原因），不暂存任何负载，当前字体与已排队请求保持不变。上文第 2、4、8 条及“生产回退要求”中“回退旧引擎”的部分由此取代；Phase 8 验证失败后恢复上一生产负载的回滚机制保留。旧引擎代码暂留在包内但不再被调用，待真机矩阵通过后删除。

### Phase 10 — Role-Assigned Composite
状态：**已实现，待真机验证**（方案与分步提交见 `docs/UNIVERSAL_COMPOSITE_PLAN.md`）

- App 组合入口 `font_mix_controller.sh` → `universal_composite.sh`，沿用原任务协议，不再进入 `.legacy-v14-runtime`、不再预合成 9 个字重
- 源字体档案记录中/英/数分工与每个角色的 auto/fixed 模式；FontPlan 只在被指派的字体中选源（`compositeSources`）
- 编译器 `composite-shell` 按旧组合引擎的 LATIN/DIGIT 码位集合从对应字体取字形，其余跟随中文基底；单一 auto 可变来源的槽位共用 `source-variable-preserve` 产物
- 组合失败不回退旧引擎

## 当前迁移策略

旧的 HyperOS / ColorOS / Generic 路由暂时保留，只作为“当前生产实现”。

新引擎按以下顺序迁移：

1. Shadow 分类
2. Shadow 替换计划
3. 与旧实现比较
4. 真机验证
5. 按角色逐类接管
6. 删除被证明多余的 ROM 专用硬编码

绝不一次性删除所有旧规则。

## 第二阶段验收门槛

Phase 2 只有满足以下条件才允许进入 Phase 3：

- Emoji、Symbol/Icon 不出现 `replace`
- 未知槽位默认 `review` 或 `preserve`
- Clock/Numeric 不出现普通 `replace`
- Serif/Monospace 默认不被系统字体替换
- CJK fallback 只有明确 CJK 证据才成为候选
- Latin fallback 只有明确 Latin 证据才成为候选
- HyperOS / ColorOS 合成测试可重复
- Shadow 计划本身不修改任何系统文件
- CI 能报告旧引擎过度替换与漏替换差异

## 变更纪律

以后每个通用字体引擎 PR 都必须：

1. 写明属于哪个 Phase。
2. 写明修改了哪条 invariant。
3. 如果改变本文设计，先改本文档。
4. 新增至少一个回归测试。
5. 不允许用“某手机临时能用”替代通用逻辑。
6. ROM 特例必须有真实拓扑无法表达的证据，否则不得新增。

