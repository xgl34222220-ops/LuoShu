# 洛书 v3.0.0

洛书 3.0 是当前无 Hook 全局字体引擎的一次正式主线升级。它不是单一功能补丁，而是把 2.x 后期完成的字体 XML 安全覆盖、测试基础设施、运行时批处理、源字体缓存、后台任务限流和 Google Play/GMS 字体桥优化统一收敛到新的稳定大版本。

## 字体覆盖与安全边界
- 扩展 OEM/UI sans family 的安全识别，同时继续明确排除 serif、mono、Emoji、图标、symbol、时钟及受保护 fallback family。
- 保留 `ui-sans-serif` 回归保护，避免 family 形状判定把 UI sans 错判成 serif。
- 动态目标扫描与 XML overlay 复用一致的 family 判定，减少不同路径对同一 OEM family 得出不同结果。

## 字体配置与切换性能
- 字体 XML 捕获、生成、校验和动态目标发现统一改为批处理，减少 ROM 字体配置较多时反复启动内置 Python 的冷启动开销。
- batch 按文档隔离异常，单份损坏 XML 不会阻断后续正常文档。
- 源字体 SHA-256 加入安全记忆化，同一切换流程不再重复哈希同一大字体。
- 文件身份使用设备、inode、大小和亚秒级 mtime/ctime；同路径、同大小字体快速替换也会正确使摘要缓存失效。

## 后台 CPU 与重试稳定性
- 设备对齐缓存加入连续失败预算，默认失败 3 次后停止自动重试，避免不可满足任务在每次开机持续高负载运行。
- 成功完成缓存后自动清零失败历史。
- 后台构建统一使用低优先级路径；支持时采用 `ionice -c 3` 与 `nice -n 19`，降低与前台 UI/应用争抢 CPU 和 IO 的概率。
- `.device-font-cache.lock` 复用 PID + process starttime + boot_id 身份判断，并在后台启动入口回收 stale lock，避免重启/OOM 后残留锁永久阻断任务。

## Google Play / GMS 下载字体桥
- 去掉对大量 `/proc/<pid>` 逐个执行 `tr`、`basename` 的高 fork 扫描。
- 常见进程通过 `pidof` 获取，再用单次 `/proc/*/cmdline` 合并扫描补齐 `com.google.android.gms:*`、Vending 子进程和 zygote 变体。
- 同一轮 apply / restore 只解析一次 provider PID 列表，减少重复扫描。
- 保留原有 GMS/Vending 子进程 wildcard 语义，不以牺牲 Google Play / GMS 字体覆盖换取性能。

## 回归测试体系
- shell 回归统一使用显式断言工具，降低裸命令失败被误判为通过的风险。
- duplicate-function guard 已加入常规检查，阻止新的未记录重复函数继续进入主线。
- 新增并常驻批处理、摘要失效、设备缓存失败预算、stale/live lock、provider PID 扫描等回归测试。
- ColorOS、HyperOS、runtime policy、transaction、cache、mount、字体导入和 XML overlay 等关键路径继续纳入常规源码门禁。

## 版本信息
- 模块版本：v3.0.0
- 模块 versionCode：30000
- App versionCode：3000001

## 发布验证
正式发布工作流会重新执行完整源码检查、Android Release Lint、单元测试、固定签名 APK 构建与证书校验、模块 ZIP 与内嵌 APK 一致性、SHA-256 校验和稳定版发布就绪门禁。ColorOS 16、HyperOS 3、Magisk、APatch 的完整真机设备矩阵仍保持 pending；本次稳定版由维护者明确授权放行，不伪造未执行的真机 PASS。
