# Zygisk 全局字体增强设计

> 2026-10 更新：维护者决定不再单独安装第二个模块，Zygisk 库已并入主模块（`zygisk/<abi>.so`，
> 源码 `zygisk-native-font/`，App 开关“全局字体增强（Zygisk）”）。字体替换本身仍不依赖 Hook：
> **Hook 仅在开关开启时由 Zygisk 库安装，默认关闭**；没有 Zygisk 时该库不会被加载。
> 实现与配置见 `zygisk-native-font/README.md`。下文“独立模块”一节为早期设计记录。

所有系统字体覆盖都通过物理文件槽与 XML 完成。本文记录 Zygisk 层的设计边界。

## 解决什么

物理槽覆盖做不到的三类场景：

1. App 自带字体（微信 XWeb、QQ/X5、支付宝、抖音内置 ttf）与网页 `@font-face`；
2. 小米框架绘制前的 `Typeface` 替换（`checkMiuiFont()` / `MiProFontManager`）绕过 XML；
3. `/data/fonts/files` 可更新字体（主要是 Emoji）优先于系统字体。

## 设计原则

- **独立模块**：单独的模块 ID 与安装包，主模块只读取它的状态，不依赖它运行；卸载伴随层不影响主模块。
- **默认关闭、按应用启用**：只对用户勾选的包名生效，系统进程（system_server、SystemUI）默认不注入。
- **只读数据面**：伴随层只读取主模块已生成并校验过的字体负载（同一份 `.luoshu-payload`），不自行合成字体。
- **失败即退出**：任何解析/映射失败都放弃替换并保留原字体，不重试、不崩溃进程。
- **可诊断**：每个进程一行日志（包名、替换次数、失败原因），由主模块诊断导出收集。

## 拦截点（候选）

| 场景 | 拦截点 | 说明 |
| --- | --- | --- |
| App 打开自带字体 | `Typeface.createFromAsset/createFromFile`、`Font.Builder` | 按字体名/覆盖率决定是否换成用户字体 |
| 小米绘制替换 | MiPro/Theme 字体管理器返回的 `Typeface` | 仅 HyperOS，需按 ROM 版本适配 |
| WebView | 不在伴随层处理 | 由主模块的 theme_webview 路由负责 |

## 与主模块的接口

- 主模块写 `config/companion.json`：`enabled`、`packages[]`、负载路径与内容哈希。
- 伴随层只在哈希匹配时生效；不匹配时视为未配置。
- 主模块 App 只展示伴随层状态与开关，不提供安装逻辑（用户自行安装）。

## 风险

- 银行/支付类 App 的完整性检测可能把注入视为风险；默认不对这类包启用。
- Zygisk 实现差异（Magisk/KernelSU ZygiskNext/APatch）需要分别验证。
- 违背“无 Hook”承诺的担忧：默认关闭、开关只在重启后生效、未启用 Zygisk 时完全不加载、主模块字体链路不依赖它。
