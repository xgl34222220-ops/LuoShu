# 洛书 v2.2.9

洛书 v2.2.9 是元模块兼容回归的第二次热修。v2.2.8 虽然停止改写 Magic Mount 配置，并取消了探针不可见时的字体回滚，但仍会主动修改 Mountify 的模块选择列表、删除挂载状态标记，并通过额外热修脚本覆盖原始挂载逻辑。这些行为仍然可能破坏原本已经可用的元模块环境。

## 本次修复

- Mountify、Magic Mount、Magic Mount RC、Magic Mount RS、Hybrid Mount 与原生 Root 管理器统一按标准模块目录工作。
- 对上述直读引擎，洛书只维护 `/data/adb/modules/LuoShu`，不创建猜测镜像目录。
- 不再写入 Mountify 的模块选择列表；选择模式由用户和 Mountify 自身管理。
- 不再读取、改写或补全 Magic Mount／Magic Mount RC 的外部配置文件。
- 不再删除 `skip_mount`、`skip_mountify`、`mount_error`、`disable` 等状态标记。
- 不再为直读引擎生成或强制验证合成挂载探针，避免诊断逻辑再次阻断字体事务。
- 启动后的字体结果继续由洛书现有的真实系统字体可见性验证器检查。
- 仅真正采用第二内容目录的 meta-overlayfs／双目录元模块执行负载镜像同步。
- 双目录同步继续使用原子分区替换和逐分区探针；元模块未声明支持的 OEM 分区会记录并跳过，不会使整个字体负载失败。
- 删除 `mount_compat_hotfix.sh` 叠加覆盖层，将兼容逻辑收回单一实现，避免加载顺序重新恢复旧行为。

## 回归验证

- Mountify、Magic Mount、Magic Mount RC／RS、Hybrid Mount 和原生挂载不会修改外部配置、模块选择列表或状态标记。
- 上述引擎不会创建额外内容镜像，也不会因合成探针不可见而回滚字体。
- meta-overlayfs 的双目录同步、原子替换、支持分区验证和失败保留旧目录均通过测试。
- 未声明的 OEM 分区会正确记录为已跳过。
- 字体引擎 smoke、无 Hook 引擎、预发布门禁和完整源码检查均通过。

## 安装与升级

1. 在 Magisk、KernelSU、SukiSU Ultra 或 APatch 中刷入 `LuoShu-v2.2.9.zip`。
2. 完整重启设备。
3. 打开洛书重新应用一次字体，再完整重启。
4. Mountify 使用选择模式时，请在 Mountify 中自行确认 `LuoShu` 已被选中；洛书不会再擅自修改该列表。

从 v2.2.8 升级不会清除字体库、App 数据或外观设置。模块 ZIP 内置同版本正式签名 App，也提供独立的 `LuoShu-App-v2.2.9.apk`。

## 版本信息

- 模块版本：`v2.2.9`
- 模块 versionCode：`20209`
- App versionCode：`2020901`
- 最低 Android：Android 9 / API 28
- 目标 Android：API 36

## 校验

Release 同时提供模块 ZIP、正式签名 APK 及各自的 SHA-256 文件。下载后可使用对应 `.sha256` 文件核验完整性。
