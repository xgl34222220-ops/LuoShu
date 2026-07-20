# 发布洛书

`module.prop` 是模块、原生 App 与产物名称的唯一版本源。修改版本后，验证工作流会编译原生 App、运行模块检查并生成测试模块；它不会自动创建 Tag 或 Release。

## 首次配置固定 App 签名

在仓库 `Settings → Secrets and variables → Actions` 添加：

- `LUOSHU_KEYSTORE_BASE64`：JKS/PKCS12 文件的 Base64 内容；
- `LUOSHU_KEYSTORE_PASSWORD`：密钥库密码；
- `LUOSHU_KEY_ALIAS`：签名别名；
- `LUOSHU_KEY_PASSWORD`：签名私钥密码；
- `LUOSHU_RELEASE_CERT_SHA256`：固定发布证书的 SHA-256 指纹，可带或不带冒号。

密钥库和密码不可提交到仓库。正式 App 必须长期使用同一把密钥，否则 Android 会拒绝覆盖安装。发布工作流会从最终 APK 重新提取证书指纹，并与 `LUOSHU_RELEASE_CERT_SHA256` 精确比较；仅仅“存在签名”不能通过门禁。

## 候选版本门禁

1. 基于最后一个干净候选基线建立独立分支，不从已废弃实验分支继续打补丁。
2. `Validate App-only source` 必须通过源码检查、角色覆盖门禁、App Lint、编译与单元测试、单模块包构建和成品检查。
3. `Font engine smoke tests` 必须通过复合字体和 TTC 字体烟雾测试。
4. 模块成品必须内置与独立 APK 字节一致的原生 App，不得包含 `webroot/`，`module.prop` 不得声明 `webroot=`。
5. 按 `docs/TEST_MATRIX.md` 完成真机回归；未验证项目保持“待测”。
6. 任一设备出现黑屏、SystemUI 重启、批量闪退或乱码，停止发布并恢复可用模块包。

## 发布步骤

1. 将通过自动化和真机回归的候选版本合并到 `main`。
2. 确认 `module.prop` 已提升到新版本和新 `versionCode`，并存在与版本完全匹配的发布说明，例如 `RELEASE_NOTES_v14.3.4.md`。
3. 在 GitHub Actions 中选择 `Publish signed release`，必须从 `main` 分支手动运行。
4. 在 `confirm_tag` 中输入 `module.prop` 对应的完整 Tag，例如 `v14.3.4`。输入不一致、Tag 已存在、Release 已存在或运行提交不是最新 `main` 时，流程立即停止。
5. 工作流先完成源码检查、App Lint、单元测试、固定签名构建、证书指纹校验、模块构建、嵌入 APK 一致性和四个发布文件的 SHA-256 校验。
6. 已验证候选文件会先保存为 Actions Artifact；构建期间若 `main`、Tag 或 Release 状态发生变化，发布停止。
7. 只有所有门禁通过后，最后一步才通过一次 `gh release create --target <verified commit>` 操作创建 Tag 和 GitHub Release。工作流不再提前执行 `git tag` 或 `git push refs/tags/...`。
8. 已存在的 Tag 或 Release永不覆盖、移动或删除；修订内容必须提升版本号后重新发布。

正式 Release 只能包含四个文件：

- `LuoShu-<版本>.zip`：唯一模块包，内置正式原生 App；
- `LuoShu-<版本>.zip.sha256`；
- `LuoShu-App-<版本>.apk`：相同签名的独立正式 APK；
- `LuoShu-App-<版本>.apk.sha256`。

Lite 变体已取消，不再构建、上传或维护不内置 App 的模块包。模块会在刷写阶段优先自动覆盖更新 App；刷写环境无法调用 Android 包管理器时，会在首次完整开机后自动补装一次。若自动安装失败，可通过 Root 管理器中的模块“操作”按钮重试。
