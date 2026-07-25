# 洛书 v2.2.7

洛书 v2.2.7 是卸载清理修复版本，解决模块卸载后 `/data/adb/modules/LuoShu`、待安装副本或 meta-overlayfs 内容镜像仍可能保留文件的问题。

## 卸载清理

- 移除卸载阶段重新创建 `logs` 目录和写入“已卸载”持久日志的行为。
- 卸载事件只写入 Android 系统日志，不会在模块目录重新产生文件。
- 恢复字体粗细设置、动态字体 bind、旧 provider 备份与 Flyme 持久字体后，删除当前洛书模块目录。
- 同时清理 `/data/adb/modules_update/LuoShu` 待安装副本。
- 清理 meta-overlayfs／双目录元模块保存的 `LuoShu` 内容镜像。
- 删除洛书生成的 Magic Mount 配置锁、备份及临时文件，但保留用户当前的 Magic Mount 主配置。
- 删除路径增加 basename 安全检查，只允许清理名称明确为 `LuoShu` 的目标树，避免误删其他模块。

## 回归验证

- 新增真实临时目录卸载测试，模拟主模块、待安装副本和两份元模块镜像。
- 测试确认卸载后洛书目标目录全部消失。
- 测试确认其他模块目录和 Magic Mount 主配置保持不变。
- 完整源码门禁、字体引擎测试、App Lint／单元测试、候选 APK 和模块成品校验均需通过后才发布。

## 安装与升级

1. 在 Magisk、KernelSU、SukiSU Ultra 或 APatch 中刷入 `LuoShu-v2.2.7.zip`。
2. 完整重启设备。
3. 此版本不修改现有字体配置或 UI，已正常使用的字体无需重新应用。

模块 ZIP 内置同版本正式签名 App。独立的 `LuoShu-App-v2.2.7.apk` 可用于覆盖升级，但卸载清理逻辑位于模块脚本中，仅安装 APK 不会更新该修复。

## 版本信息

- 模块版本：`v2.2.7`
- 模块 versionCode：`20207`
- App versionCode：`2020701`
- 最低 Android：Android 9 / API 28
- 目标 Android：API 36

## 校验

Release 同时提供模块 ZIP、正式签名 APK 及各自的 SHA-256 文件。下载后可使用对应 `.sha256` 文件核验完整性。
