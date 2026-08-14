# 洛书 v2.5.1

v2.5.1 是 v2.5.0 的字体显示修复版本，不回退 v2.5.0 已强化的切换锁与恢复机制。

## 修复
- 修复组合字体中英文与数字可能被中文基底自带 ASCII 垂直位置带偏、导致同行文字基线不一致的问题。
- Latin / Digit 位移改为使用平底探针对齐 OpenType 基线 `y=0`，同时继续纠正源字体自身的整体 Y 偏移。
- 修复普通单字体切换与自动多字重路径未启用无 Hook XML 覆盖，导致 `monospace` 等宽字体仍保持系统默认的问题。
- 自动多字重配置改为回读真实 `font-config-overlay.conf` 状态，不再固定记录 `xmlOverlay=false`。

## 回归保护
- 新增“中文基底 ASCII 被抬高、用户英文/数字字体正常坐基线”的反向基线回归测试。
- 新增 monospace XML 覆盖回归测试，验证 LuoShuMono 映射、default 守卫和 fail-open 行为。
- 新增 XML overlay 事务回滚测试：模拟 overlay 已生成但后续负载校验失败，旧 XML、overlay 配置与字体负载必须完整恢复。
- 保留 v2.5.0 的 PID + process starttime + boot_id 身份锁、初始化宽限与跨重启 stale-lock 恢复。

## 发布
- 模块版本：`v2.5.1`
- 模块 versionCode：`20501`
- App versionCode：`2050101`
- 正式发布继续执行完整源码/模块检查、Android Lint/单测、签名 APK、证书校验、模块 ZIP 与 SHA-256 校验。
- ColorOS 16、HyperOS 3、Magisk 与 APatch 真机矩阵仍保持原始 pending 记录；本次正式发布基于维护者明确授权，不伪造真机验证结果。
