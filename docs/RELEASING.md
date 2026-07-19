# 发布洛书

`module.prop` 是模块、App、WebUI、缓存键与产物名称的唯一版本源。修改版本后，验证工作流会编译原生 App、运行模块检查并生成测试模块；它不会自动创建测试版 Release。

## 首次配置固定 App 签名

在仓库 `Settings → Secrets and variables → Actions` 添加：

- `LUOSHU_KEYSTORE_BASE64`：JKS/PKCS12 文件的 Base64 内容；
- `LUOSHU_KEYSTORE_PASSWORD`：密钥库密码；
- `LUOSHU_KEY_ALIAS`：签名别名；
- `LUOSHU_KEY_PASSWORD`：签名私钥密码。

密钥库和密码不可提交到仓库。正式 App 必须长期使用同一把密钥，否则 Android 会拒绝覆盖安装。

## 候选版本门禁

1. 基于最后一个干净候选基线建立独立分支，不从已废弃实验分支继续打补丁。
2. `Validate source` 必须通过源码检查、角色覆盖门禁、App 编译与单元测试、Lite 包构建和成品检查。
3. `Build module` 必须通过复合字体烟雾测试并生成可解压的模块 ZIP。
4. 按 `docs/TEST_MATRIX.md` 完成真机回归；未验证项目保持“待测”。
5. 任一设备出现黑屏、SystemUI 重启、批量闪退或乱码，停止发布并恢复可用模块包。

## 发布步骤

1. 将通过自动化和真机回归的候选版本整理到发布分支。
2. 确认存在与版本完全匹配的发布说明，例如 `RELEASE_NOTES_v14.3.md`。
3. 稳定版必须使用不含 Alpha、Beta、RC 的版本名，并提升 `versionCode`。
4. 将稳定版本合并到 `main`；`Publish signed release` 会从 `module.prop` 创建唯一 Tag，例如 `v14.3`。
5. 工作流重新运行完整源码检查、App lint/单元测试、固定签名构建、APK 证书校验与 Full/Lite 成品校验，然后创建不可覆盖的 GitHub Release。
6. 预发行版仍可手动创建唯一 Tag；已存在的 Tag 或 Release 不会被覆盖，修订内容必须提升版本号。

正式 Release 包含：

- `Full.zip`：模块及内置正式 App；
- `Lite.zip`：完整字体模块，不内置 App；
- 独立正式 APK；
- 每个产物对应的 SHA-256 文件。

Full 包会在刷写阶段优先自动覆盖更新 App；刷写环境无法调用 Android 包管理器时，会在首次完整开机后自动补装一次。若自动安装失败，可通过 Root 管理器中的模块“操作”按钮重试。
