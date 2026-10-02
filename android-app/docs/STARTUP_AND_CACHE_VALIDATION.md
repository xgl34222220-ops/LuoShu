# 字体列表启动与缓存核查（正式版 v1.1.1 基线）

## 行为

- 移除首页所有主题的「全局粗细微调」入口、状态与 Root 调用。字体自身的离散字重、可变轴、组合生成保留。
- 本地原子索引在 IO 线程读取后立即展示，不等待 Root、模块状态、ROM 状态或字体扫描。
- 无 App 索引时先请求 `app_bridge.sh fonts cached` 读取模块已有索引，先显示并标为待核查。首次无任何索引时请求 `fonts`，由模块初始化目录并生成真实索引。
- 有索引时检查轻量指纹，核查期间保留列表但暂停应用/删除。未改变不重扫、不重复刷盘；改变或主动刷新才请求重新生成索引。扫描响应使用开始前的指纹，再与扫描结束后的实时指纹比较，相等才标记已核查；扫描期间再次变化只提示重试，不在单次操作中循环重扫。
- 首次核查、每次返回前台、进入字体库/组合页面均可触发核查；连续入口 2 秒内合并。字体库/组合页面保持前台时每 30 秒核查一次，离开前台取消查询、停止定时检查，没有常驻扫描服务。
- 导入完成、删除后主动失效并刷新；过期请求不得把删除前的列表重新写回界面。合法空库会清除旧列表，权限失败、模块不可用或缺失目录不会假装空库成功。
- 已保存列表在核查失败时保留浏览并明确提示未核实；应用字体、删除、组合生成需要通过实际库核查。旧确认对话框提交时还会核对目标 ID 仍在当前列表，应用要求该字体有效。错误不永久缓存，恢复授权后回前台或刷新即可重试。
- 字体预览和轴缓存包含索引修订号，可识别同名、同显示大小、同日期文件替换；读取轴失败不进入成功缓存。
- 移除点击字体时的主动预热。仅实际显示的预览导出，以及用户已启动/恢复的字体任务需要相应工作；没有新增 Android 后台服务。

## 可重复检查

在独立 `GRADLE_USER_HOME` 和已有 JDK/Android SDK 下：

```sh
gradle --no-daemon --max-workers=2 :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

`FontLibraryLoaderTest` 覆盖：阻塞核查期间已出现缓存、跳过 status、cache miss、增删/空库、手动刷新、旧索引迁移、权限失效及恢复、取消、扫描中变更、同名文件替换、字重保留，以及畸形/错误响应不清空字体库。

`RootShellTest` 继续覆盖请求取消与超时清理、标准输出/错误输出大缓冲、后台子进程持有管道不拖延返回、取消请求不误杀已分离的生成任务。

## 真机验证仍需执行

不能把主机单元测试或 Shell 指纹 benchmark 当成手机端“秒开”证据。未提供设备时，不宣称首帧、首个字体列表或预览实际延迟已达标。建议真机分别测量：

1. 完成一次字体扫描后强制结束 App，再启动并立即进入字体库，记录列表首见时间与后台核查结束时间。
2. 清 App 数据后保留模块索引，验证模块缓存首显；无任何索引的首次启动按真实扫描完成时间报告。
3. 外部增加、删除和同名换文件，分别测试切换页面、前后台切换和持续停留 30 秒以上。
4. 撤销 Root/目录读取权限，确认旧列表明确标示未核查且无法应用；恢复后刷新。
5. 导入/删除与后台核查同时发生，快速进出页面与前后台，确认无旧列表复活、无无限加载、无重复查询堆积。
6. 验证中文/英文/数字独立选择、静态字重和 `wght`/`wdth`/`opsz` 等真实轴仍正常。

## 调试构建观测标记

debug 变体包名为 `io.github.xgl34222220.luoshu.stabletest`，显示名「洛书·稳定重构测试」，与正式、`.debug`、`.audit` 并行安装；release身份保持不变。该测试变体不复用release签名，验收构建应使用独立 `ANDROID_USER_HOME` 生成本地测试证书。

只有 `BuildConfig.STARTUP_DIAGNOSTICS=true` 的debug构建记录 `LuoShuStartup` 本地logcat；release常量为false，无网络上传、无字体名或文件路径。每条包含 `event`、`elapsed_ms`（开机单调时间），列表事件另含 `count`、`verified`：

- `app_start`：Application创建
- `library_open`：字体库页面打开
- `font_index_visible`：已知缓存提交给界面
- `font_index_verified`：实际目录核查/扫描完成
- `library_frame`：列表组合后跨越两帧的观察信号

冷启动以 `app_start` 到第一条 `library_frame` 为App内观测区间；热进入以 `library_open` 到随后的 `library_frame` 计算。另报 `verified=true` 的可操作时间，不能将缓存首显混为最新目录已核查。0/100/1000字体必须验证事件的 `count`。这些是App内时序信号，不等价于设备GPU首帧或从桌面触摸开始的完整体验时延。

字体库根节点测试ID为 `luoshu_font_library`（testTagsAsResourceId），状态描述为「字体列表：数量；加载中/待核查/已核查」。自动化还应核实实际列表内容。

## 首次无缓存库存与同步请求（2026-10-02 后续修复）

真实 Android 验收显示缓存热打开已经较快，但旧版首次 100 个字体的完整 Shell 索引仍约需 100 秒。空列表帧不能算字体库首显。现改为：

- `font_inventory_batch.py` 以一次目录快照、一次字族分组、每个代表文件四字节 header 检查生成库存，不再每个文件/字族启动 basename/stat/awk/sed/tr。
- App 在没有任何已知索引时先请求 `preview`。它返回真实文件 stat/config 元数据，但每行 `valid=false`、`provisional=true`、索引指纹为空；只展示文件，不允许应用或生成组合，也不启动该行的字体预览导出。
- 后台 `scan/refresh` 完成后，实时指纹相等才解锁。`font-list-v5:` 指纹包含配置文件及符号链接目标身份，旧 v4 索引只用于待核查展示。
- 原有家族后缀处理顺序、字重优先级、格式 magic、配置首值、大小显示规则保留；符号链接的列表 size/date 仍保留旧 lstat 行为，目标变化会使指纹失效。深字体检查继续在应用任务执行。
- 模块缓存读取最多 4 MiB，单个配置文件最多 64 KiB。超大/损坏缓存视为 miss；超大配置明确报错，不执行配置内容。

库存调用改走 `font_inventory_request.sh request <action> <seconds>`，由独立有限 `font_request_scope.py` 管理同步请求。仅这些读请求把 App 的 stdin 管道作为存活凭据；App 取消/超时关闭管道，并给回收最多 6 秒宽限。worker 的 stdin 是 `/dev/null`，其他 fd 不继承；supervisor 是唯一 waitpid owner。

退出码：worker 正常退出沿用其退出码；请求预算超时 124；stdin EOF 130；TERM/INT/HUP 为 128+信号；无法证明全部 owned 子孙清理时返回 125，并保留准确身份供恢复。成功、失败、超时、取消都会尝试回收 double-fork/setsid 与信号处理期间新生的 owned 后代；无关进程不在范围内。没有常驻轮询服务，也不改变分离字体生成任务的生命周期。

新增测试：

- `python3 scripts/font_inventory_batch_test.py`：旧字族/字重函数兼容、格式/config、增删/替换/权限指纹、预览不解锁、有界输入、1000 文件批量输出
- `python3 scripts/font_request_scope_test.py`：同步 success/error/timeout/SIGTERM/stdin EOF，owned 后代与僵尸归零、无关 sentinel 存活
- `FontRequestLeaseTest`：实际 JVM Process 管道取消和超时传到实际 Python supervisor，再检查后代身份已消失

调试日志新增 `event=font_request stage=cached|preview|scan|refresh|fingerprint duration_ms=... code=...`；服务端 stderr 另有库存段耗时及 request started/finished 清理结果。必须结合正确字体数的 `library_frame` 与 `verified=true` 分开评估真实 Android 首显/可操作时间，主机批量测试时间不能冒充设备表现。
