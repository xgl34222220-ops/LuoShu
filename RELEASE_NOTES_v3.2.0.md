# 洛书 v3.2.0

洛书 3.2.0 是基于 v3.1.0 的稳定性、兼容性与性能更新，重点优化九档字体准备开销、真实 ROM XML 覆盖链路和 HyperOS 紧凑行框。字体覆盖仍保持无 Hook 方案。本版本按正式稳定版发布。

## 九档字体准备性能
- 可变字体的九档字重实例化和名称归一化改为批处理，减少嵌入式 Python 解释器反复冷启动和相同源字体的重复读取。
- 批处理任务会显式传播失败状态；任一阶段失败时会删除半成品，并自动回退到原有逐字重构建路径，避免产生不完整 payload。
- 静态字体继续走原直接链接/读取路径，不额外引入实例化开销。

## 真实 ROM XML 兼容
- 修复 `fonts.xml` / 字体配置中注释、处理指令等非字符串 tag 导致 overlay 遍历异常的问题。
- XML 辅助逻辑现在会把这类节点视为无本地标签并安全跳过，同时保留 ROM 原有注释，不再因为真实系统配置中的注释节点中断整个无 Hook 覆盖流程。

## 复合字体校验性能
- 复合字体输出自检改为 lazy 加载，只解析 cmap、maxp 和实际探针字形，不再为了检查少数字形而提前展开完整 CJK 字体。
- 保留对中文、英文和数字关键探针的输出完整性验证。

## HyperOS 紧凑行框修复
- HyperOS 物理字体槽正式改用 `font_metrics_normalize.py --compact` 模式。
- 移除旧的 `_outline_extremes = lambda font: None` monkey-patch 与 0.98em 硬裁切行为；紧凑行框现在会以常用中文、拉丁字母、数字和下伸字形的真实墨迹边界为安全下限。
- 修复部分字体在 HyperOS 上出现标题压行、上下行互相侵入、下伸部或标签边缘被裁掉的问题，同时避免少见极端字形把普通 UI 行框无谓撑大。
- 新增紧凑行框专项回归，要求 HyperOS 必须使用 `--compact`，并阻止旧 monkey-patch 回归。

## 回归与 CI
- 将此前未实际执行的一批字体配置、设备 payload、模板、目标发现等回归重新接入常驻 `scripts/check.sh`。
- aggregate source checks 在已准备模块内置 Python runtime 时会使用洛书自带的 FontTools，避免 runner 未全局安装 FontTools 导致假失败。
- v3.2.0 正式发布工作流会重新执行完整源码检查、Android Release Lint、单元测试、固定签名 APK 构建、证书 SHA-256 校验、模块 ZIP/App 字节一致性检查以及发布就绪门禁。

## 版本信息
- 模块版本：v3.2.0
- 模块 versionCode：30200
- App versionCode：3020001

## 发布验证
ColorOS 16、HyperOS 3、Magisk、APatch 的完整真机设备矩阵仍保持 pending；本次稳定版由维护者明确授权放行，不伪造未执行的真机 PASS。

<!-- release-trigger: v3.2.0 -->
