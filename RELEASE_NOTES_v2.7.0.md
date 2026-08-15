# 洛书 v2.7.0

本次正式版在 v2.6.0 的 Liquid Glass 基础上继续打磨 MIUIX 界面，并扩展无 Hook 字体引擎对通用 OEM 字体 XML 的安全覆盖能力。重点不是放宽映射边界，而是在保持图标、Emoji、时钟等 family 安全过滤的前提下，提高不同 ROM 字体配置链路的适配率与失败容错。

## MIUIX 界面继续收口
- 继续优化 edge-to-edge 页面层级、首页、设置页和任务中心的布局关系，减少多层卡片堆叠与不必要留白。
- 首页、设置与任务中心统一圆角、间距、分段控件和状态层级，让一级信息更突出、次级操作更克制。
- 字体库与字体工坊同步悬浮底栏安全区，避免内容与底部导航产生视觉冲突。
- 保留 v2.6.0 的 Liquid Glass 底栏、真实内容采样、镜面高光、Fresnel 风格边缘光与主题色 caustic。
- Material 模式继续保持独立实现，不把 MIUIX 控件逻辑混入 Material 页面。

## 通用 OEM 字体 XML 覆盖
- 在预定义字体配置名单之外，自动发现各字体配置分区中真实存在且符合安全规则的 `*font*.xml`、`*Font*.xml`、`*FONT*.xml`。
- 静态字体 cache miss 时允许走有界的前台 XML family overlay，减少必须等待后台 aligned cache 的情况。
- 可变字体继续交给后台 aligned cache，避免在前台执行昂贵实例化；相同源路径只检测一次。
- `font_config_generate()` 返回成功后必须确认 overlay 已启用、实际 XML 数量匹配且每份 XML 均通过验证，才计为真正 XML 成功。
- 仅物理字体槽 fallback 不再冒充 XML 成功；XML 失败时仍保留安全 fallback 和后台重建路径。
- 单个分区 XML 生成失败不会撤销其它已经验证通过的分区，至少一份安全 XML 成功即可提交，其余继续保留原厂配置。

## 动态目标与安全校验
- 动态字体目标支持真实 partial coverage：分别记录 `targets`、`mapped` 和 `status=full|partial`，不再把部分成功伪装成 100% 覆盖。
- `mapped=0` 仍然视为硬失败并清理状态，避免发布完全无效的动态目标负载。
- `targets=0 / mapped=0` 明确视为“设备没有动态目标”的合法状态，不再错误要求 alias manifest。
- `font_safety`、finalize hotfix 与最终 payload bridge 三层 validator 使用同一套 full/partial 规则，并核对 manifest 数量、目标路径和字体有效性。
- 继续保留现有 family 安全过滤，不因发现未知 OEM XML 而改写图标、Emoji、时钟或任意厂商私有 family。

## 回归与自动化
合并前的完整 `main` 基线门禁已全部通过，包括：
- Validate App-only source
- Build Test Candidate
- Android build diagnostic
- No-Hook font engine tests
- Device font inventory tests
- Font engine smoke tests
- Safety and update feature checks
- v2.5 feature checks
- Pre-release Readiness

正式发布工作流还会重新执行完整源码检查、Android Release Lint、单元测试、固定签名 APK 构建与证书校验、模块 ZIP 与内嵌 APK 一致性检查、SHA-256 校验和正式发布就绪门禁。

## 真机状态
ColorOS 16、HyperOS 3、Magisk、APatch 的完整设备矩阵仍保持 pending。本次稳定版由维护者明确授权放行，不伪造未执行的真机 PASS；自动化和正式签名发布链必须全部通过后才创建不可覆盖的 v2.7.0 Release。
