# 洛书 v2.10.0

本次正式版聚焦后台运行时的 CPU、重试与锁恢复稳定性。在 v2.9.0 已完成字体 XML 批处理和摘要记忆化的基础上，继续收敛设备对齐缓存和 Google 下载字体桥在开机/切换后的后台开销，避免不可满足任务反复重跑以及逐进程 `/proc` 扫描造成的额外负载。

## 设备对齐缓存重试收敛
- 为后台设备对齐缓存加入连续失败预算，默认连续失败 3 次后停止自动重试并清除 pending；字体本身仍由物理槽映射生效，缓存只作为增强项。
- 无效失败上限会自动回落到安全默认值，避免配置异常导致无限重试。
- 成功生成并激活缓存后会清除失败计数，后续正常任务不受历史失败影响。
- 两条后台启动路径统一走低优先级执行；支持时使用 `ionice -c 3` 与 `nice -n 19`，降低重建任务和前台 UI/应用争抢 CPU/IO 的概率。

## Cache lock 恢复
- `.device-font-cache.lock` 现在复用 PID + process starttime + boot_id 身份判断，避免重启后的 PID 重用被误判成仍在运行的旧 worker。
- 开机/模板释放后的后台启动入口会先识别并回收 stale lock，再决定是否启动任务；不会再因为残留锁在进入 builder 之前就永久返回。
- 活跃 worker 的 live lock 仍会被保留，不会为了“清锁”误并发启动第二个缓存构建任务。

## Google 下载字体桥 CPU 优化
- 移除对大量 `/proc/<pid>` 逐个执行 `tr` + `basename` 的高 fork 扫描。
- 常见进程先通过 `pidof` 获取，同时用单次 `/proc/*/cmdline` 合并扫描补齐 `com.google.android.gms:*`、Vending 子进程与 zygote 变体，再统一去重。
- 同一轮 provider apply / restore 只解析一次目标 PID 列表，避免针对每份字体重复扫描进程表。
- 保留原有 GMS/Vending 子进程 wildcard 语义，不以牺牲 Google Play / GMS 字体覆盖换取性能。

## 回归与测试
- 新增设备字体缓存预算测试，覆盖失败计数、达到上限后停止重试、成功后复位、stale lock 回收与 live lock 保留。
- 新增 provider PID 扫描测试，使用 fake `/proc` 验证 `pidof` 命中时仍能发现 GMS/Vending 子进程，并禁止恢复逐进程 fork 模式。
- 两项测试已接入 `scripts/check.sh`，成为常规源码门禁。
- 合并前已通过 Validate App-only source（含完整 source checks、Android lint/test/build 与模块候选包检查）、Build Test Candidate、v2.5 Beta 1 feature checks 与 Pre-release Readiness；正式发布工作流会再次执行完整源码检查、Android Release Lint、单元测试、固定签名 APK 构建与证书校验、模块 ZIP 与内嵌 APK 一致性检查、SHA-256 校验和稳定版发布就绪门禁。

## 版本信息
- 模块版本：v2.10.0
- 模块 versionCode：21000
- App versionCode：2100001

## 真机状态
ColorOS 16、HyperOS 3、Magisk、APatch 的完整设备矩阵仍保持 pending。本次稳定版由维护者明确授权放行，不伪造未执行的真机 PASS；只有正式签名发布链全部通过后才创建不可覆盖的 v2.10.0 Release。
