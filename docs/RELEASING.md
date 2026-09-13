# 发布洛书

`module.prop` 是模块、原生 App 与产物名称的唯一版本源。修改版本后，验证工作流会编译原生 App、运行模块检查并生成测试模块；它不会自动创建测试版 Release。

## 正式版本编号（2026-09-13 起）

维护者指定正式版按两步一组编号：`n.0.0 → n.n.n → (n+1).0.0`。

完整示例：`1.0.0 → 1.1.1 → 2.0.0 → 2.2.2 → 3.0.0 → 3.3.3 → 4.0.0 → 4.4.4 → 5.0.0 → 5.5.5 → 6.0.0 → 6.6.6`。

本次为 **v4.4.4**，下一正式版应为 **v5.0.0**，再下一版为 **v5.5.5**。后续不要继续沿用 4.4.5、4.5.0 等逐补丁编号。规则同时记录在 `config/stable_version_policy.json`；发布时更新其中 currentStable / nextStable，并同步 module.prop、version_notes.conf 和本版发布说明。

既有历史标签不改名、不重写。旧 v14.x 标签不用于推导下一正式版本。模块版本代码继续为 `major*10000 + minor*100 + patch`，App 为 `moduleVersionCode*100 + 1`；4.4.4 对应 40404 / 4040401。每次必须确认高于当前已发布版本代码；不因编号规则自动创建发布。

## 首次配置固定 App 签名

在仓库 `Settings → Secrets and variables → Actions` 添加：

- `LUOSHU_KEYSTORE_BASE64`：JKS/PKCS12 文件的 Base64 内容；
- `LUOSHU_KEYSTORE_PASSWORD`：密钥库密码；
- `LUOSHU_KEY_ALIAS`：签名别名；
- `LUOSHU_KEY_PASSWORD`：签名私钥密码。

密钥库和密码不可提交到仓库。正式 App 必须长期使用同一把密钥，否则 Android 会拒绝覆盖安装。发布工作流将最终 APK 的证书 SHA-256 与固定证书 `e0043b560a10111d3ffddd3a7afba680b854e14ed793c7a3fdb7f8b7aa95ff27` 精确比较，并要求只有一个 signer；换错证书会阻断发布。

## 候选版本门禁

1. 基于最后一个干净候选基线建立独立分支，不从已废弃实验分支继续打补丁。
2. 验证源码、角色覆盖、原生 App 编译和单元测试、单模块包构建及成品检查。
3. 执行复合字体烟雾测试，生成可解压的模块 ZIP；内置 App 与独立 APK 字节一致，不包含 webroot。
4. 按 `docs/TEST_MATRIX.md` 完成真机回归，将时间和证据写入 `docs/device_validation.json`；未验证项目保持待测。
5. 出现黑屏、SystemUI 重启、批量闪退或乱码，停止发布并恢复可用模块包。

## 发布步骤

1. 整理发布分支，使用上述正式编号，确认同名发布说明，例如 `RELEASE_NOTES_v4.4.4.md`。
2. 稳定版不含 Alpha、Beta、RC，不含 prerelease 标记；提高 versionCode，保持 module.prop 为唯一版本源。
3. 默认要求最低真机矩阵有证据。维护者明确授权某一版本在矩阵仍待测时正式发布，可以使用既有 `config/stable_release_authorization.conf`，必须绑定该版本，不得写成长期通用豁免，也不得把待测记录改成通过。
4. 合并 main 后，Publish signed release 重新运行源码检查、App lint / 单元测试、固定签名、证书、单模块成品和发布门禁，再创建 GitHub Release。
5. 已有 Tag 或 Release 不覆盖；修订内容使用新版本。预发行必须有 prerelease 标记；正式版本更新正式和预览通道。
6. 检查 Release 的模块 ZIP、独立 APK、两份 SHA-256 均已上传，核对在线更新元数据与真实下载地址，再交付安装包。

正式 Release 包含 `LuoShu-<版本>.zip`、`LuoShu-App-<版本>.apk` 及各自 SHA-256。Lite 变体已取消；模块必须内置相同签名 App，必要时手动覆盖安装独立 APK。

## v4.4.4 一次性版本清理

本次授权时间为 2026-09-13T02:32:33Z。发布前最近六项是 v4.3.2-Beta1、v4.3.1-Beta1、v4.3.0、v4.2.0、v4.1.0、v4.0.0；其中 **v4.0.0 永不进入本次删除名单**。前五项和该授权时间之前已发布的全部预发行版，在 v4.4.4 安装包与两条更新元数据就绪后删除。

清理脚本固定本次范围，重跑不得向更早正式版滑动；不删除标签、分支、源码历史或草稿，不删除之后新发布的版本。保留清理审计报告。此删除授权仅用于本次，不自动推广为今后无限重复的清理任务；正式版本编号规则持续生效。
