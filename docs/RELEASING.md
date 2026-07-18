# 发布洛书

`module.prop` 是模块、App、WebUI、缓存键与产物名称的唯一版本源。修改版本后，验证工作流会编译原生 App、运行模块检查并生成测试模块；它不会自动创建 Release。

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
2. 确认存在与版本完全匹配的发布说明，例如 `RELEASE_NOTES_v14.2_RC2.md`。
3. 按 `module.prop` 创建唯一 Tag，例如 `v14.2-RC2`。
4. 推送 Tag；`Publish signed release` 会重新运行完整源码检查、App lint/单元测试、签名构建、APK 证书校验与 Full/Lite 成品校验。
5. 已存在的 Tag 或 Release不会被覆盖。修订内容必须提升版本号并创建新 Tag。

正式 Release 包含：

- `Full.zip`：模块及内置正式 App；
- `Lite.zip`：完整字体模块，不内置 App；
- 独立正式 APK；
- 每个产物对应的 SHA-256 文件。

Full 包刷写阶段不会直接安装 App。完整重启后，通过 Root 管理器中的模块“操作”按钮安装或更新内置 App。
