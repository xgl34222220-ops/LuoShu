# 发布洛书

`module.prop` 是模块、原生 App 与产物名称的唯一版本源。修改版本后，验证工作流会编译原生 App、运行模块检查并生成测试模块；它不会自动创建测试版 Release。

## 重构系列正式版本编号（2026-09-13T04:47:32Z 起）

维护者本次指定重新从 **重构版 1.0.0** 起算：**1.0.0 → 1.1.1 → 2.0.0 → 2.2.2 → 3.0.0 → 3.3.3**。规则仍为 `n.0.0 → n.n.n → (n+1).0.0`，本次 currentStable 为 v1.0.0，nextStable 为 v1.1.1；旧的“下一正式版 5.0.0”计划已被替代。

`module.prop` 写入 `versionSeries=refactor`，显示版本只写 v1.0.0，不加 Beta/RC。内部版本代码不能重置：固定采用 `50000 + major*10000 + minor*100 + patch`；App 为 `moduleVersionCode*100 + 1`。1.0.0 对应 60000 / 6000001，高于已交付 4.4.4 (40404 / 4040401) 和 5.0.0-Beta1 (50000 / 5000001)。1.1.1 对应 60101，2.0.0 对应 70000，2.2.2 对应 70202。旧系列没有此属性时保留原公式。

`release_version_policy.py` 统一校验编号和系列；发布门禁不再把“显示版本重置”误报为内部编号错误。App 包名、模块 ID、固定签名和数据路径不得随重编号改变，安装时不得要求用户卸载或清除数据。

新系列标签独立为 **refactor-v1.0.0**，发布说明为 **RELEASE_NOTES_refactor-v1.0.0.md**；附件沿用 **LuoShu-v1.0.0.zip / LuoShu-App-v1.0.0.apk**。以后 refactor-v4.0.0 不得覆盖旧 v4.0.0。GitHub 正式发布显式标为 Latest，在线更新依据递增 versionCode，而不是将显示字符串与旧 4.x/5.x 比大小。

同步更新 `config/stable_version_policy.json` 的 currentStable / nextStable、module.prop、version_notes.conf 与本版说明；只有明确发布请求才创建 Release。本次不删除任何额外旧版本。

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

1. 整理发布分支，使用上述正式编号，确认同名发布说明，例如 `RELEASE_NOTES_refactor-v1.0.0.md`。
2. 稳定版不含 Alpha、Beta、RC，不含 prerelease 标记；提高 versionCode，保持 module.prop 为唯一版本源。
3. 默认要求最低真机矩阵有证据。维护者明确授权某一版本在矩阵仍待测时正式发布，可以使用既有 `config/stable_release_authorization.conf`，必须绑定该版本，不得写成长期通用豁免，也不得把待测记录改成通过。
4. 合并 main 后，Publish signed release 重新运行源码检查、App lint / 单元测试、固定签名、证书、单模块成品和发布门禁，再创建 GitHub Release。
5. 已有 Tag 或 Release 不覆盖；修订内容使用新版本。预发行必须有 prerelease 标记；正式版本更新正式和预览通道。
6. 检查 Release 的模块 ZIP、独立 APK、两份 SHA-256 均已上传，核对在线更新元数据与真实下载地址，再交付安装包。

正式 Release 包含 `LuoShu-<版本>.zip`、`LuoShu-App-<版本>.apk` 及各自 SHA-256。Lite 变体已取消；模块必须内置相同签名 App，必要时手动覆盖安装独立 APK。

## v4.4.4 一次性版本清理

本次授权时间为 2026-09-13T02:32:33Z。发布前最近六项是 v4.3.2-Beta1、v4.3.1-Beta1、v4.3.0、v4.2.0、v4.1.0、v4.0.0；其中 **v4.0.0 永不进入本次删除名单**。前五项和该授权时间之前已发布的全部预发行版，在 v4.4.4 安装包与两条更新元数据就绪后删除。

清理脚本固定本次范围，重跑不得向更早正式版滑动；不删除标签、分支、源码历史或草稿，不删除之后新发布的版本。保留清理审计报告。此删除授权仅用于本次，不自动推广为今后无限重复的清理任务；正式版本编号规则持续生效。
