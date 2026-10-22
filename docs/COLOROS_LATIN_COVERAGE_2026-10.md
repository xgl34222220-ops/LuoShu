# ColorOS 拉丁/数字覆盖补全（2026-10）

本轮只改 ColorOS / OxygenOS / realme UI（OPlus 系）的英文与数字覆盖面和诊断。不涉及冻结核心、挂载、XML 改写、App 界面；主模块仍然无 Hook。

## 现场症状

ColorOS 上不少应用中文已换成用户字体，英文和数字仍是原厂字体。

## 原厂布局（公开固件 dump 核对）

来源：dumps.tadiphone.dev 公开 dump —— oppo/op5e07l1（ColorOS 15 CN，AP3A）、oppo/op5e8bl1（ColorOS 16 CN/EUEX，BP2A）、oneplus/op595dl1（OxygenOS/ColorOS 16 ROW，BP2A）；`system_ext/etc/init/init.oplus.rootdir.rc`、`system_ext/etc/fonts_base.xml`、`fonts_ule.xml`、`system/etc/fonts.xml`、`font_fallback.xml` 以及 `system/fonts` 目录。

- 字体文件全部在 `/system/fonts`；`my_product`、`my_stock`、`my_region`、`my_heytap`、`my_bigball` 均无 `fonts/` 目录，`product/etc/fonts_customization.xml` 为空壳。
- 生效配置在 `/system_ext/etc/fonts_base.xml`（另有 `fonts_ule.xml`）：
  - 默认 `sans-serif` = `Roboto-Regular.ttf`（可变，`supportedAxes="wght,ital"`）；`fonts.xml`/`fonts_ule.xml` 的 `sans-serif` = `SysFont-Regular.ttf`（+ `SysFont-Static-Regular.ttf`）。
  - `sys-sans-en` = `SysSans-En-Regular.ttf`（OPlus Sans En，wght 100–1000）；`op-sans-en` = `OPSans-En-Regular.ttf`（O Sans，wght 100–700）。
  - **`osans-solid-digits` = `OSans-Solid-Digits-VF.ttf`**：只有 0–9、货币符号和数字标点（53 个码位，wght 100–1000，带 tnum/pnum）。
  - 默认回退链里 `lang="osans-rc"` = `OSans-RC-Regular.ttf`（HYZhongHei，约 6 万汉字的生僻字库，无拉丁），`lang="osans-ext"` = `OSans-Ext-Regular.otf`（7 个码位的占位）。
- `/system/fonts/SysFont-{Regular,Static-Regular,Hans-Regular,Hant-Regular,Myanmar}.ttf` 是**符号链接**，指向 OPlus flip 字体目录 `/data/format_unclear/font/OplusOSUI-*.ttf`；init（`OPLUS_FEATURE_FONT_FLIP`）再把 `OplusOSUI-*.ttf` 链回 `/system/fonts/Roboto-{Thin,Light,Regular,Medium,Bold,Black,…}.ttf`、`RobotoStatic-Regular.ttf`、`SysFont-Hans/Hant-Regular.ttf`。ColorOS 15/16 只有 `Roboto-Regular.ttf`，所以多数字重链接**悬空**；`SysFont-Hans-Regular.ttf ↔ OplusOSUI-Hans-Regular.ttf` 在 16 上**成环**。设置/主题商店选字体后，框架会把这些条目改指向自己的文件。

## 根因

1. **数字族不在任何名单里**：旧映射器、v4 映射器、发现规则都不认识 `OSans-*`，`osans-solid-digits` 族绘制的数字永远是原厂（库存补齐只在扫描清单就绪且实测判定为数字字体时才可能补上）。
2. **符号链接槽位被存在性检查跳过**：两条映射器用 `[ -e ]`/`[ -f ]` 判断槽位存在，链条悬空或成环时为假，`SysFont-*` 槽位（`fonts.xml`/`fonts_ule.xml` 的默认 `sans-serif`）就不生成别名，文字继续走 flip 链条解析到的原厂文件。
3. **flip 字体接管（只能诊断）**：系统设置/主题字体把 `OplusOSUI-*.ttf` 指向 `/data` 内的文件时，走 flip 字体的文字根本不读 `/system/fonts`；拉丁 flip 字体优先，汉字回退到已被替换的 `SysSans-Hans`，正好表现为“中文换了、英文数字没换”。这一层在 `/data`，无 Hook 模块不改写它。
4. v4 路线的 ColorOS 目标缓存只以系统指纹为键，模块更新后的新名单要等 OTA 才生效。

## 修改

- `common/coloros_latin_policy.py`：ColorOS 拉丁/数字名单单一来源；`OSans-*Digits*` 归 `osans_digits` 分组（默认开），`OSans-RC*`/`OSans-Ext*` 永远保留原厂。两个 shell 映射器各带一份 `LUOSHU_COLOROS_LATIN_POLICY` 副本，测试校验一致。
- `common/legacy_v14_4/rom_adapters.sh`（App 实际使用的安全切换映射器）与 `common/coloros_global.sh`（v4）：
  - 映射 `OSans-Solid-Digits-VF.ttf` 并发现 `OSans-*Digits*` 改名；
  - 原厂存在的符号链接（含悬空/成环）视为真实槽位；
  - 发现规则跳过 `OSans-RC`/`OSans-Ext`，v4 发现规则与旧映射器一样排除 `*Myanmar*`（缅文回退）；
  - 应用后调用只读 flip 字体诊断。
- `common/coloros_metrics_batch.py`：数字槽按原厂度量对齐；库存补齐不会恢复 `OSans-RC`/`OSans-Ext`，`osans_digits=0` 时也不补数字槽。
- `common/coloros_flipfont.sh`：`status` 输出 JSON（`luoshu-coloros-flipfont-v1`），切换日志在拉丁 flip 字体被接管时给出中文提示，并写 `logs/coloros_flipfont.json`。只读，不碰 `/data/format_unclear/font`。
- `common/device_font_payload_policy.sh`：ColorOS 目标缓存键加入名单修订号与分组状态；ColorOS 下悬空的原厂链接也算槽位（其他 ROM 仍只认存在的文件，HyperOS 框架链接不受影响）。
- `common/legacy_v14_4/font_switch_safe.sh`：本机对齐缓存身份加入 `coloros_latin_policy.py` 与 `config/coloros_slot_groups.conf`。

等宽（`DroidSansMono`、`CutiveMono`）、时钟（`AndroidClock`）、衬线、缅文等原有保留规则不变。

## CJK 集合（2026-10-18）

- `NotoSansCJK-Regular.ttc` / `NotoSerifCJK-Regular.ttc` 此前在 ColorOS 上一律保留原厂（基线理由“TTC 多字面集合”）。现在 `coloros_metrics_batch.py` 在主槽位处理完后调用与 HyperOS 相同的 `build_collections`：按本机字体面数量与顺序编译，每面保留原厂 cmap/GSUB/GPOS/name/行距，等宽/斜体面保留原厂，供体取暂存目录里未改写的锚点（`.luoshu-font-store/wght-*.font`、`mix-composite.font` 或 `regular.font`）。
- 暂存目录里已经有经过证明的集合（组合流程编译的）时不再重复编译；任何失败只保留该集合原厂并写入报告 `preservedCollections`。
- 结果按“原厂字节 + 各面供体 sha256 + 编译器源码”缓存（与 HyperOS 共用 `hyperos-collections-v1`），重复切换只做硬链接。
- `config/coloros_cjk_collections.conf`：只有精确的 `enabled=0`（最后一行为准）关闭；Python 规则在 `coloros_latin_policy.cjk_collections_enabled`，shell 副本 `coloros_collection_names_for_root` 供 `rom_coverage_gate.py` 使用，测试比对两者。安全切换缓存身份加入 `composite_collection_build.py` 与该配置。
- 覆盖定位：ColorOS 上集合未生成时报“在替换范围但本次负载没有生成”，关闭后按“多语言字体集合”保留。

## 开关

`config/coloros_slot_groups.conf`（不存在时用默认值）：

| 键 | 文件 | 默认 |
|---|---|---|
| `osans_digits` | `OSans-*Digits*` | 开 |

精确的 `osans_digits=0` 关闭（例如用户字体是比例数字、计数器跳动时）。改后重新应用字体生效。

## 需真机确认

- `osans-solid-digits` 实际被哪些界面使用（推断：OPlus 系统应用里的大号数字/金额），替换后计时类界面有无跳动。
- flip 链条：真机上 `ls -l /data/format_unclear/font /system/fonts/SysFont-*` 的实际指向，以及设置里选“系统默认/Roboto/OPPO Sans”或主题字体后的变化；诊断里 `verdict=redirected` 是否与“中文换了英文没换”的应用一致。
- 用覆盖层替换悬空/成环的 `SysFont-*` 符号链接：需在 KernelSU（meta-overlayfs / magic mount）与 Magisk 上确认挂载后 `SysFont-*` 解析为用户字体。
- `fonts_base.xml` 与 `fonts_ule.xml` 的切换条件（推断与 flip 字体是否启用有关），以及 ColorOS 14 是否同样带 `OSans-*` 文件（本次 dump 只覆盖 15/16）。
