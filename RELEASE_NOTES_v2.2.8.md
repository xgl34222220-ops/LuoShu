# 洛书 v2.2.8

洛书 v2.2.8 是元模块兼容回退修复版本，重点恢复 Mountify 与 Magic Mount RC 在旧版本中已经可用的标准模块挂载方式，并撤销会误判、误回滚的过度兼容逻辑。

## 问题原因

v2.2.5 起，洛书新增了逐分区挂载探针与元模块配置适配，但把诊断结果错误地作为字体事务是否成功的硬条件：

- 要求所有字体负载分区都必须从固定系统路径读回探针。
- Magic Mount 的外部 `config.toml` 会被洛书主动改写。
- 元模块挂载时机、缓存方式或路径布局稍有不同，就会被判定为挂载失败。
- 已经通过字体文件原子校验的负载，仍可能因探针不可见而被回滚或隔离。

这套逻辑破坏了 Mountify 与 Magic Mount RC 原本可用的标准模块目录契约。

## 本次修复

- Mountify、Hybrid Mount、Magic Mount、Magic Mount RC 与原生 Root 管理器统一直接读取 `/data/adb/modules/LuoShu`。
- 仅真正采用双目录内容树的 Overlay 元模块继续同步第二份内容镜像。
- 洛书不再修改 Magic Mount 或 Magic Mount RC 的配置文件。
- 补充 Magic Mount RC 常见模块 ID 与可执行路径识别。
- Mountify 处于模块选择模式时，自动尝试把 `LuoShu` 加入已有选择列表。
- 清理洛书自身遗留的 `skip_mount`、`skip_mountify` 与 `mount_error` 标记，避免一次失败永久影响后续应用。
- 取消逐分区硬性探针，改为主系统分区诊断，并增加真实字体文件可见性验证。
- 探针路径或挂载时机不同只记录诊断，不再回滚、隔离或撤销已通过原子校验的字体负载。
- 保留多元模块同时启用的警告，但不再擅自修改其他元模块状态。

## 回归验证

- Meta Overlay 双目录同步及 OEM 分区同步通过。
- Mountify、Hybrid Mount、Magic Mount 与原生挂载均不会创建猜测目录。
- Magic Mount 配置文件在字体事务前后保持字节级不变。
- Magic Mount RC 路径识别与洛书遗留标记恢复通过。
- 探针不可见时字体启动事务仍能安全确认，不再触发误回滚。
- 真实系统字体文件可见时可完成挂载确认。
- Shell 语法检查与完整仓库发布门禁由正式发布工作流执行。

## 安装与升级

1. 在 Magisk、KernelSU、SukiSU Ultra 或 APatch 中刷入 `LuoShu-v2.2.8.zip`。
2. 完整重启设备。
3. 打开洛书重新应用一次字体，再完整重启。
4. Mountify 使用选择模式时，确认模块列表中存在 `LuoShu`；新版会自动尝试补充。

从 v2.2.7 升级不会清除字体库、App 数据或外观设置。模块 ZIP 内置同版本正式签名 App，也提供独立的 `LuoShu-App-v2.2.8.apk`。

## 版本信息

- 模块版本：`v2.2.8`
- 模块 versionCode：`20208`
- App versionCode：`2020801`
- 最低 Android：Android 9 / API 28
- 目标 Android：API 36

## 校验

Release 同时提供模块 ZIP、正式签名 APK 及各自的 SHA-256 文件。下载后可使用对应 `.sha256` 文件核验完整性。
