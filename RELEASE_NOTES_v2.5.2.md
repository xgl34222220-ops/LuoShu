# 洛书 v2.5.2

v2.5.2 是 v2.5.1 的界面与 Play/GMS provider 兼容性修复版本，不回退 v2.5.1 已强化的字体基线、monospace、事务回滚和 stale-lock 机制。

## UI / 体验
- 收口 MIUIx 全局圆角与卡片层级，减少大圆角和卡片套卡片的气泡感。
- 设置中心顶部导航改为更轻的 tonal 层级；字体库搜索框改为柔和填充式，并将删除操作收进更多菜单。
- 组合工具由大 AlertDialog 改为 Modal Bottom Sheet，字体组合页、首页与任务中心同步减重。
- 悬浮底栏变薄，选中指示器与图标过渡更克制；页面切换缩短并降低横向位移，减少双页面重叠感。

## Play / GMS provider 修复
- 修复下载字体 provider bridge 在目标 mount namespace 中直接把 `/proc/1/root/...` 作为 bind 源时可能因 foreign vfsmount 触发 `EINVAL` 的问题。
- 目标 namespace 可见普通模块路径时直接 bind；不可见时仅通过 `/proc/1/root` 读取 clone 内容，复制到目标 namespace 的 `/data/local/tmp` staging 文件后再 bind。
- staging 文件继承 provider 目标字体 SELinux 标签，bind 成功后立即删除，不污染 GMS / Play 字体缓存。
- 新增 plain / staging / failed / 缺源统计和首个错误聚合，避免 provider service 多次重试时刷爆日志。
- 新增 provider mount namespace 回归测试，并接入 v2 source audit。

## 发布
- 模块版本：`v2.5.2`
- 模块 versionCode：`20502`
- App versionCode：`2050201`
- 正式发布继续执行完整源码/模块检查、Android Lint/单测、签名 APK、证书校验、模块 ZIP 与 SHA-256 校验。
- ColorOS 16、HyperOS 3、Magisk 与 APatch 真机矩阵仍保持原始 pending 记录；本次正式发布基于维护者明确授权，不伪造真机验证结果。
