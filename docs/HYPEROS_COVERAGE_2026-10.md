# HyperOS 覆盖补全（2026-10）

本轮只改 HyperOS 覆盖面与诊断，不涉及稳定性/CI/发布、斜体与字重合成、`.ttc` 重建、App 性能。主模块仍然无 Hook（不做 Zygisk/LSPosed）。

## 1. 文件名名单单一来源

- 唯一来源：`common/hyperos_physical_policy.py`（`classify` / `safe_physical_font_name` / `xml_file_allowed` / `MAPPER_FAMILY_PREFIXES`）。
- Shell 副本由 `python3 common/hyperos_physical_policy.py --write` 生成到三个文件的标记块中：
  `legacy_v14_4/hyperos_clock_compat.sh`、`legacy_v14_4/hyperos_full_coverage.sh`、`hyperos_global.sh`。
  `--check` 在 `scripts/check.sh` 与 `hyperos-latin-policy-regression.yml` 中运行。
- 扫描器（`font_inventory_scan.py`）、暂存批处理（`hyperos_metrics_batch.py`）直接 import；XML 路线（`hyperos_source_xml.py`）通过 `xml_file_allowed` 使用同一规则：等宽文件只接受等宽感知构建（`LuoShuMono*` 或 role 为 mono/clock 的逐槽构建），MiSansL3 与关闭的分组永不改写。

## 2. 分组开关（`config/hyperos_slot_groups.conf`）

| 键 | 文件 | 默认 |
|---|---|---|
| `miui_ex` | `MiuiEx*`、`Miui-*` | 开 |
| `misans_ext` | `MiSansRounded*`、`MiSansC*`（不含 `MiSansClock*`）、`MiLanVF*` | 开 |
| `lockscreen_styles` | `Interscaled*`、`C800*`、`Qinghe*`、`ChamberiDisplay*`、`DelaGothicOne*`、`BebasNeue*`、`NeumaticCompressed*`、`GulfsDisplay*` | 关 |

- 扫描器按“全部分组”采集原厂度量，开关切换不需要重扫；映射器按配置生效（重新应用后）。开机补槽会删掉已关闭分组的旧别名。
- `HYPEROS_COVERAGE_REVISION` 4 → 5，已安装设备下次扫描检查时会重扫。
- 行为变化：此前在 dali OS3.0.303 上，库存补全会把 verified-scan 的 `Interscaled-*`、`ChamberiDisplay-*` 换成用户字体；现在它们属于默认关闭的锁屏样式组，默认保留原厂。

## 3. 始终保留原厂

- （#295 起）等宽与时钟字体（`RobotoMono*`、`NotoSansMono*`、`DroidSansMono.ttf`、`MitypeMonoVF`、`MitypeClockMono`、`MiClockMono`、`InterMono-*`、`BebasNeue-Mono` …）改为替换；`NotoSansCJK-Regular.ttc`、`NotoSerifCJK-Regular.ttc` 在暂存时按本机字体面数量与顺序编译替换（每面按字重取用户字体，等宽/斜体面保留）。
- 日文/韩文/其他文字语种字体（`MiSansJP*`、`*Japanese*`、`*Korean*`、`*Tibetan*`、`*Telugu*` …）。
- `MiSansL3.otf`（GB18030-2022 三级生僻字，官方 FAQ：https://hyperos.mi.com/font/zh/faq ）。

## 4. XML

- `hyperos_source_xml` 默认开启，只有 `config/hyperos_source_xml.conf` 中精确的 `enabled=0` 才关闭；没有种子 XML 的 ROM 不受影响（缓存键也不变）。
- 覆盖：`/system_ext/etc/{hyper,miui}_font*.xml` 种子；`/product/etc/fonts_customization.xml`（主渲染器未暂存时，生成字体放入 `product/fonts`）；`/system/etc/{fonts,font_fallback}.xml` 为普通文件且主渲染器未暂存时。HyperOS 2+ 上这两个是指向 `/data/system/fonts/theme_webview/` 的符号链接，由 init 从（已改写的）种子复制，只记录不替换。
- 严格校验：结构/属性不变、每个 family 字体数不变且文件名非空、改写后的文件名必须存在于暂存树、原本能解析的原厂引用不能变成不可解析、落盘后再解析一次。任何一项失败 → 整体不生效，回退原厂 XML。
- `lang="zh-Hans|zh-Hant|zh-HK|zh-TW|zh-Bopo…"` 族：仅当用户字体（默认 sans-serif 的生成构建）的 CJK 统一汉字数 ≥ 6000（简体）/ 13000（繁体）时，把其中单面、非 TTC、非衬线的字体路由到最近字重的构建；混合语种（如 `zh-Hans ja`）、`variant`/`fallbackFor` 族不动。
- v4 路线：`common/util_functions.sh` 的 post-fs-data 钩子（卡开机保护之后）调用 `hyperos_boot_routes.sh`，补上 `MiSansVF_Overlay` → `theme_webview` 路由；路由在 v4 负载没有 `Roboto-Regular.ttf` 时回退到字体仓库的 regular/composite 源。legacy 路线保持原调用点。

## 5. 主题商店字体

- 检测：`/data/system/theme/fonts` 中有 > 64 KiB 的字体即视为用户主题字体（约 8.9 KiB 的空主题占位不算）。App 首页强提示。
- 可选接管（`config/hyperos_theme_takeover.conf` `enabled=1`，默认关）：`common/hyperos_theme_takeover.sh` 在 zygote 前把该目录下全部单面字体（不只 Roboto-Regular）按字重只读 bind 为负载字体；与 webview 路由同样的按开机 journal + inode 回滚；关闭、恢复默认字体、禁用/卸载模块时还原；`.ttc` 不接管。卸载与 Google 字体服务的 restore 路径已加入。

## 6. 未覆盖界面定位

`common/font_coverage_locator.py`（App 经 `app_bridge.sh coverage_locate <包名>` 调用）对目标进程运行现有 `device_font_process_audit`，以 `/proc/<pid>/root` 作为可见根，分类为：主题接管 / 白名单外文件 / 命名空间看不到模块 / App 内置或 WebView 字体 / 开机后链接切换 / 字重丢失 / 已覆盖，并给出操作建议。

## 需真机确认（第三方提取或推断）

- 锁屏/小部件样式字体名单、`MiSansRounded*`/`MiSansC*`/`MiLanVF*`/`Miui-*` 文件名：来自第三方提取（gizdev HyperOS 3 列表，https://www.gizdev.com/xiaomi-hyperos-fonts-misans-miserif/ ，未注明机型与分区）与 lxgw issue #7（https://github.com/lxgw/simple-cjk-font-magisk-module-template/issues/7 ）。需用 App 导出的 `device_font_inventory.json` 或 `ls /system/fonts /product/fonts /system_ext/fonts /mi_ext/fonts` 校准，并用定位功能确认锁屏/AOD 实际读取的文件。
- 种子 XML 默认开启：需在 HyperOS 2/3 × KernelSU/Magisk/APatch 上确认 init 在 post-fs-data 复制种子时能看到洛书覆盖层（挂载时序），以及主题商店切换字体后框架的 hyper_/miui_ 切换不受影响。
- `fonts_customization.xml` 改写与 zh-Hans/zh-Hant 路由：需真机确认繁体/港澳字形与回退顺序。
- 主题接管：需确认 `ThemeFontManager`/`checkMiuiFont` 在绘制时读取的是被 bind 的同名文件（推断自 `docs/FONT_RUNTIME_FOLLOWUP_2026-09-12.md` 的 framework 分析，未独立反编译核实），以及 SELinux 上下文（`chcon --reference`）在各机型可用。
- v4 路线的 `MiSansVF_Overlay` 路由：需在尚未重新应用的 v4 用户设备上确认 post-fs-data 时字体仓库已就位。
- 定位器的“命名空间看不到模块”判断依赖 `/proc/<pid>/root` 可读（需 Root），以及 OverlayFS 下的内容比对。
