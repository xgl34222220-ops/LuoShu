# 洛书 v2.9.0

本次正式版聚焦运行时性能与回归可靠性：把字体 XML 捕获、生成、校验和动态目标发现从“每份文档反复启动一次 Python”改成批处理，并对大字体源文件的 SHA-256 做安全记忆化，减少字体切换时的重复冷启动与重复哈希开销。

## 字体配置批处理
- `font_config_overlay.py` 新增 batch 协议，可在一个 Python 进程内连续完成多份 XML 的 generate / validate。
- `font_config_runtime.sh` 将原始 XML 捕获、备份校验、overlay 生成与生成结果校验改为批量处理，减少 ROM 字体配置文件较多时的解释器启动次数。
- 动态目标发现同样改为批处理，避免每份 XML 单独启动扫描器。
- 批处理按文档隔离错误：单份损坏或不可解析 XML 会返回独立 error 结果，不会中断后续正常文档。

## 字体摘要与缓存性能
- 对源字体 SHA-256 增加基于文件身份的记忆化，同一次切换流程中同一份大字体不再被重复哈希多次。
- 文件身份包含设备、inode、大小以及亚秒级 mtime / ctime；同路径、同大小字体在极短时间内被替换时也会正确失效旧摘要。
- 当运行环境无法提供足够可靠的亚秒级文件身份时，宁可重新计算 SHA-256，也不复用可能过期的缓存。
- 保留原有 metrics cache 与归一化版本隔离，不改变字体度量安全契约。

## Family 判定一致性
- 动态目标扫描与 XML overlay 复用一致的 UI sans / serif 安全判定，减少两条路径对同一 OEM family 得出不同结果的风险。
- 延续 v2.8.0 对 `ui-sans-serif`、OEM sans、serif、Emoji、图标、symbol 与 locale fallback 的保护边界。

## 回归与测试
- 新增 `font_config_batch_test.py`，覆盖 batch generate / validate、路径含空格与 `|`、OEM sans/serif 判定，以及坏 XML 不阻断后续正常任务。
- 新增 `font_digest_memo_test.sh`，验证同一文件只计算一次摘要，以及同大小快速替换后缓存必须失效。
- 两项测试已接入 `scripts/check.sh`，进入常规源码门禁。
- 合并前已通过 Validate App-only source、Font engine smoke tests、v2.5 Beta 1 feature checks 与 Pre-release Readiness；正式发布工作流会再次执行完整源码检查、Android Release Lint、单元测试、固定签名 APK 构建与证书校验、模块 ZIP 与内嵌 APK 一致性检查、SHA-256 校验和稳定版发布就绪门禁。

## 版本信息
- 模块版本：v2.9.0
- 模块 versionCode：20900
- App versionCode：2090001

## 真机状态
ColorOS 16、HyperOS 3、Magisk、APatch 的完整设备矩阵仍保持 pending。本次稳定版由维护者明确授权放行，不伪造未执行的真机 PASS；只有正式签名发布链全部通过后才创建不可覆盖的 v2.9.0 Release。
