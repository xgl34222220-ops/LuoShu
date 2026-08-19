# 洛书 v2.8.0

本次正式版聚焦两部分：继续收紧无 Hook 字体 XML 覆盖边界，以及系统性补强测试基础设施，确保 ColorOS、HyperOS、动态字体、事务、缓存、挂载和字体导入等关键链路在 CI 中能够真正失败、真正报警，而不是因为 shell `errexit` 状态变化出现“测试执行了但失败没有被捕获”的假绿。

## 字体 XML 覆盖继续收紧
- 扩展 XML UI family 识别范围，同时保留 `ui-sans-serif` 回归保护，避免把不应替换的 family 错误纳入覆盖。
- 补强 OEM sans / serif XML family 规则，提升不同 ROM 字体 XML 的兼容性与一致性。
- 新增独立 XML overlay regression CI，持续验证 family 识别与安全边界。
- 保持图标、Emoji、时钟及厂商私有 family 的原有安全过滤，不因扩大识别范围而放宽危险映射。

## 测试基础设施硬化
- 新增 `scripts/assert.sh`，提供显式 `ok` / `no` / `eq` 断言，避免 sourced runtime 模块改变 `errexit` 后让失败断言静默通过。
- 将受影响的 shell 回归测试迁移到显式断言，覆盖 ColorOS、HyperOS、runtime policy、transaction、cache、mount、meta-module sync 与字体导入等路径。
- 新增 duplicate-function baseline guard，并接入 `scripts/check.sh`，防止关键 shell 文件因重复函数定义导致后定义静默覆盖前定义。
- 扩大 `scripts/check.sh` 的 always-on 测试范围，让核心回归在普通源码门禁中直接执行，而不是只依赖少数专项 workflow。
- 修正 ColorOS / HyperOS 测试夹具和 variable-font backend 夹具，让测试真正走到预期分支。
- 删除已经失去意义的 legacy data-font cleanup 回归测试，避免维护过时路径。

## 字体导入兼容
- 规范更多样式后缀组合，包括 `Black-Italic`、`Italic-Black` 等命名，减少字体文件命名差异造成的样式识别偏差。

## 回归与自动化
本次变更在合并前已完成完整 7/7 CI：
- Validate App-only source
- Build Test Candidate
- v2.5 Beta 1 feature checks
- Device font inventory tests
- Pre-release Readiness
- No-Hook font engine tests
- Font engine smoke tests

其中扩展后的 `scripts/check.sh`、严格断言、duplicate-function guard、Android 构建与候选包验证均已通过。

正式发布工作流还会重新执行完整源码检查、Android Release Lint、单元测试、固定签名 APK 构建与证书校验、模块 ZIP 与内嵌 APK 一致性检查、SHA-256 校验和稳定版发布就绪门禁。

## 真机状态
ColorOS 16、HyperOS 3、Magisk、APatch 的完整设备矩阵仍保持 pending。本次稳定版由维护者明确授权放行，不伪造未执行的真机 PASS；只有正式签名发布链全部通过后才创建不可覆盖的 v2.8.0 Release。
