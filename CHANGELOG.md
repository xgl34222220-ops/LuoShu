# 更新日志

## v13.6 Beta4

- 修复 HyperOS 3 + Zygisk Next 下 Play 启动后进入新挂载命名空间、开机时已经完成的 GMS 字体桥接随之丢失的问题
- 新增 Play PID 命名空间守护：只在 Play PID 变化或定期校验时补挂载，不在守护流程中反复结束 Play 进程
- 将 `zn-nsdaemon-zygote` 纳入桥接，并通过 `/proc/1/root` 从隔离命名空间访问洛书字体源
- 每次 bind 后比较源与目标设备号/ inode，确认挂载真实可见并避免重复叠加挂载

## v13.6 Beta3

- 修复 HyperOS 3 上 Google Play 仍显示默认字体：GMS 下载的 `Google_Sans_Flex` 现在会优先桥接真正的可变字体，没有可变字体时改用当前字体常规字重兼容覆盖，不再跳过
- 保持 Direct Bind 无分区负载结构，避免为了在元模块列表中显示而重新引入空 Overlay、staging 或 `mount.error`
- 新增静态字体覆盖 Google Sans Flex、可变字体优先和代码字体保留三项桥接测试

## v13.6 Beta2

- 默认切换为通用 Direct Bind，不再依赖已知元模块名称或目录才能启用；标准 Magisk/KernelSU 与 Hybrid Mount、Mountify、meta-overlayfs 共用同一套文字字体映射
- 正式包将 `luoshud` 与“洛书”命令行工具移到模块私有 `bin/`，默认 Emoji 下不再保留任何 `system/` 分区负载
- 修复安装和开机脚本重新创建空 `system/fonts`、`system_ext/fonts` 后仍触发元模块 Overlay/staging 的问题
- 无分区负载时只清理旧 staging，不再创建空内容目录；自定义 Emoji 仍按小型分区负载兼容同步
- 升级、Direct Bind 应用及校验成功后，仅清理洛书自身的 `mount.error`、`.mount.error` 与 `mount_error`，允许 Hybrid Mount 安全重试
- 扩展 Hybrid Mount、Mountify 与 meta-overlayfs 自动检测，同时保留 `module` 传统模式作为手动回退
- 新增“空负载不得生成 staging”“不得清理其他模块错误标记”“发布包不得包含 `system/`”构建测试

## v13.5 Stable Hotfix5

- 紧急撤回 Hotfix4 的系统字体符号链接方案；部分 ROM 在字体路径中解析符号链接时会出现严重卡顿、SystemUI 无响应甚至系统假死
- 文字字体和 Emoji 恢复为 Android 已验证稳定的普通文件/硬链接，不再让系统字体服务读取隐藏目录中的符号链接目标
- 新增 Hybrid Mount staging 安全体积预算，按其逐文件展开后的真实大小计算，而不是按模块目录中的硬链接占用计算
- 优先保留简体中文、繁体中文和 ROM 核心字体目标；达到 128 MiB 预算后自动跳过低优先级英文、数字和跨分区别名
- 大字体至少保留一个核心系统目标，避免因为预算限制导致字体完全不生效
- ColorOS 映射顺序调整为简体中文 Hans 优先，再处理 Hant、英文和其他低优先级字体
- 构建测试新增“禁止字体符号链接”“别名必须为普通文件/硬链接”“超出 staging 预算必须跳过”验证
- Hotfix4 不建议继续使用；已经刷入的设备应先禁用洛书恢复开机，再刷入 Hotfix5 并清理 Hybrid Mount 旧 staging

## v13.5 Stable Hotfix4

- 按 Hybrid Mount 公开源码中的真实扫描规则修复误报：它会扫描模块根目录 `.sh`，并把每行第一个单词为 `mkdir` / `touch`，或包含 `mount` / `bind` 的脚本标记为“建议 Ignore”
- 洛书顶层脚本中的正常目录初始化改为 `command mkdir` / `command touch`，执行结果不变，但不再被误认为模块自行挂载
- 文字字体的 ColorOS、HyperOS、AOSP 别名由硬链接改为相对符号链接，每个真实字重只保存一份
- `system_ext` / `product` 字体别名改为指向 `/system/fonts/` 的符号链接，避免跨分区别名被重复复制
- Emoji 的 `NotoColorEmoji.ttf` 与 Legacy 别名同样改为紧凑符号链接
- 解决 Hybrid Mount ext4 staging 逐文件复制硬链接、把一份 20～50 MB 字体展开成几十份后触发 `No space left on device (os error 28)` 的问题
- 新增与 Hybrid Mount `has_suspicious_shell_commands` 等价的构建扫描，今后若发布包仍会触发该提示将直接构建失败
- 新增符号链接与跨分区别名测试，确保发布包不会再次退化为大量完整字体副本

## v13.5 Stable Hotfix3

- 修复 Hybrid Mount 扫描到旧版 `play_font_bridge.sh` / `wechat_xweb_bridge.sh` 后，把洛书误显示为 v12.x 并提示“包含挂载相关命令”的问题
- 发布包删除未使用的旧 `.sh` 桥接副本，保留实际使用的无扩展名 GMS/Gemini 与微信 XWeb 桥接工具
- 将元模块负载同步组件改为无扩展名 `common/meta_overlay_compat`，避免被 Hybrid Mount 的 `.sh` 规则误判
- 将诊断报告工具改为无扩展名 `common/font_report`，发布包内 `.sh` 不再包含 mount、umount、mountpoint 或 `/proc/mounts` 操作
- 扩展 Hybrid Mount、meta-overlayfs、Mountify 常见内容目录识别，并取消对“目录必须已经是挂载点”的过严限制
- 构建阶段自动清理旧桥接脚本、旧兼容脚本与 `skip_mount` / `skip_mountify`
- 新增发布包扫描测试，防止旧 `.sh` 或实际挂载命令再次进入 Release
- 截图中的 `/data/adb/modules/com.omarea.vtools` 属于其他模块的失效路径，洛书报告会继续提示清理 Hybrid Mount 的陈旧记录

## v13.5 Stable Hotfix2

- 稳定性中心明确区分“当前配置”“当前稳定快照”和“可回滚配置”，避免首个快照已建立却被误认为未建立
- 显示当前稳定快照与可回滚配置的保存时间，并提示当前配置是否与快照一致
- 新增“立即保存当前配置”，无需等待下一次完整开机即可建立或刷新稳定快照
- 保存不同配置时自动把原稳定快照轮换为可回滚配置；保存相同配置时只刷新快照时间
- 没有可回滚配置时自动禁用恢复按钮，并在按钮下说明建立方式
- 自救报告增加当前快照、可回滚配置及其保存时间，方便定位回滚状态
- 增加手动快照、配置不一致、自动轮换和回滚可用性测试

## v13.5 Stable Hotfix1

- 修复“自救”悬浮按钮被主界面 `body > *` 宽度规则拉伸成整条横栏、遮挡字体列表和底部导航的问题
- 自救按钮增加直属 ID 强制尺寸、旧 WebView 回退值和内联关键样式，独立 CSS 尚未加载时也不会错位
- 新增 `common/mount_compat.sh`，识别 Magic Mount、Hybrid Mount、Mountify 与 meta-overlayfs
- 针对 meta-overlayfs 的双目录架构，把 `system/`、`product/`、`system_ext/` 等负载同步到 `/data/adb/metamodule/mnt/LuoShu/`
- 文字字体、Emoji、恢复系统默认都会同步元模块真实内容目录，避免 WebUI 显示切换成功但重启后仍使用旧字体
- post-fs-data 与 service 增加负载补同步，处理元模块镜像内容落后、更新模块后首次启动不同步等情况
- 构建包主动移除 `skip_mount` / `skip_mountify`，避免洛书被部分元模块直接跳过
- 新增元模块镜像、旧字体清理、字体/Emoji 钩子、post-fs-data 与 service 注入测试

## v13.5 Stable

- 新增独立 WebUI 自救中心：即使主 `app.js` 或字体列表异常，仍可清缓存、修权限、重建索引、导出报告和回滚配置
- 新增开机稳定配置快照：系统完成启动后记录当前文字字体、Emoji 和字体粗细；配置变化时自动保留上一个稳定版本
- 新增一键恢复上一个稳定配置，继续沿用一次开机一次切换与完整重启保护
- 新增 ROM、Android 版本、Root 管理器和实际存在的字体配置路径自动诊断
- 新增字体扫描真实耗时、结果和时间记录；WebUI 同时记录最近一次列表展示耗时
- 字体库加载超过 18 秒时显示自救入口，不再让用户只能面对无限转圈
- 新增 `scripts/stability_test.sh` 发布门槛，覆盖空字体库、1 个字体、20 个字体、快照轮换、缓存清理、扫描和报告生成
- 新增构建期 WebUI 注入与缓存号统一，确保独立自救脚本先于主界面脚本加载
- 保留 Hotfix6 已验证稳定的字体扫描核心，不改动字体切换、ZIP 导入和多字重主链路

## v13.4 Beta2 Hotfix6

- 稳定性回退：字体库加载核心完整恢复为用户实机验证正常的 Hotfix1 实现
- 撤回 Hotfix4/Hotfix5 的索引扫描、按需首屏预览、空目录重试和 Root 队列实验逻辑
- 恢复基于字体目录修改时间的列表缓存；字体未变化时直接返回缓存
- 恢复 Hotfix1 的 WebUI 命令执行、字体列表生成和预览同步流程
- 修复名称包含“字重”时 Regular 被误判为 Black 的问题
- 保留 ZIP 安全导入、中文模块名称、可变字体、静态多字重和新版 UI

## v13.4 Beta2 Hotfix4

- 修复升级后 WebView 继续缓存旧版损坏 `app.js`，导致页面有样式但所有按钮失效的问题
- CSS/JavaScript 静态资源版本号与模块 versionCode 强制同步，升级后立即加载新资源
- 字体库列表不再在启动阶段复制全部字体到模块目录，避免大字体库长期停留在“加载中”
- 字体预览改为打开详情时按家族准备，列表和切换功能优先可用
- 为字体列表与 Emoji 列表增加超时保护，异常时显示错误而不是无限旋转
- 构建检查新增资源缓存版本断言，避免再次发布缓存号未更新的包

## v13.4 Beta2 Hotfix3

- 修复 WebUI 主脚本中换行转义被写成真实换行，导致 JavaScript 整体解析失败
- 修复字体库持续显示“加载中”、刷新无结果以及所有按钮无响应
- 强化构建前 JavaScript 模块语法检查，避免同类错误再次进入 GitHub Release
- 保留 Hotfix2 的 UI、静态多字重、可变字体和 ZIP 导入优化

## v13.4 Beta2 Hotfix2

- 静态多字重家族新增可操作档位选择，不再只是不可点击的标签
- 详情页区分可变字体、静态多字重和单一字重
- 静态家族预览加载真实字重文件，选择后即时显示差异
- 字重调整即时写入系统并请求刷新，不再标记为必须完整重启
- 已打开应用可能需重新打开，系统界面未更新时可单独重启 SystemUI
- 字体列表增加“可调”标记

## v13.4 Beta2

- 新增可变字体 `wght` 轴粗细滑块，范围根据字体实际 `fvar` 表自动生成
- 字体详情页支持实时预览 300–700 字重，并提供 300/400/500/600/700 快捷档位
- 使用 Android `font_weight_adjustment` 应用全局字重，保存后开机自动恢复
- 卸载模块时恢复安装前的系统字体粗细设置，避免残留
- 不支持系统字重接口时自动降级为仅预览，不强行修改字体文件
- 保留 v13.4 Beta1 的 ZIP 字体包安全导入、中文模块名识别及 CJK 主字体优先选择

## v13.4 Beta1 Hotfix2

- ZIP 导入后优先读取原模块 `module.prop` 的 `name=` 作为中文显示名称
- 字体文件仍按安全字体 ID 保存，WebUI 通过侧边配置显示原模块名称
- 同步保留原模块版本和作者信息，找不到 `module.prop` 时才回退 ZIP 文件名

## v13.4 Beta1 Hotfix1

- 修复 ZIP 自动识别优先选中 2 MB 英文字体、导致常用中文覆盖为 0% 的问题
- 新增简体中文、繁体中文、东亚字体与拉丁字体候选分级
- 支持识别 `ASCH-w1`～`ASCH-w6` 这类非标准多字重命名，并导入完整字体家族
- 可变字体不再无条件最高优先，改为结合中文候选、家族完整度和文件体积综合判断
- 将字体表检测改为只读取文件头部，明显缩短多字体 ZIP 的识别时间
- 点击“自动识别”后立即显示进度，不再长时间无反馈

## v13.4 Beta1

- 新增 ZIP 字体包导入：将其他字体模块压缩包放入 `/sdcard/LuoShu/import/` 后可在 WebUI 一键识别
- 安全解压：只读取 TTF / OTF / TTC，不执行压缩包中的任何脚本，并限制文件数量与解压体积
- 自动推荐可变字体；没有可变字体时优先 Regular / Book / Normal
- 支持导入完整静态字重家族，避免只保留 Regular 后丢失粗体层级
- 自动识别并单独导入 Emoji，不会与文字字体混用
- 对大量重复系统别名进行内容去重，避免一次导入二十多个完全相同的字体副本
- 忽略图标字体、斜体候选与真实格式检测失败的文件
- 新增导入结果报告，显示通过、无效、忽略和实际导入数量

## v13.3 Beta2

- 恢复 ARM64 原生扫描器 `luoshud`，作为旧目录诊断和故障回退工具，WebUI 默认仍走安全 Shell 扫描
- 字体列表接口新增扫描器状态，诊断报告增加原生扫描器、公开目录和桥接状态
- WebUI 解析可变字体 `fvar` 表，显示轴标签、范围、默认值和命名实例数量
- GMS 动态字体桥接增加 Google 搜索、Gemini、Chrome 和 WebView 相关挂载命名空间
- Google Sans Flex 仅在存在可变字体源时桥接，避免用静态正文字体冒充 Flex/Code 字体
- 更新公开目录、Hybrid Mount、重启保护和字体风险说明
- 重构 GitHub Actions 发布流程，版本号包含 Beta/RC 后缀，自动生成预发布 Release

## v13.3 Beta1

- 新增 `/sdcard/LuoShu/fonts/`、`emoji/` 和 `reports/` 公开目录
- 文字字体与 Emoji 独立管理
- 增加真实文件头检测，拦截伪装格式和损坏字体
- 默认保留系统 fallback、符号、其他语言字体与 `fonts.xml`
- 加入一次开机一次切换的重启保护，减少连续热切换死机
- 增加 Hybrid Mount Magic 标记和存储、inode、挂载诊断

## v13.2 Beta2

- 增加真实 cmap 字符抽样分析与字体风险评分
- 增加后台任务状态轮询、使用次数和排序
- 增加字体检测报告复制功能
