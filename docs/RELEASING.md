# 发布洛书

`module.prop` 是模块、App、WebUI 与产物名称的唯一版本源。修改版本后，PR
工作流会生成独立 debug App、Full 模块和 Lite 模块；它不会创建 Release。

## 首次配置固定 App 签名

在仓库 `Settings → Secrets and variables → Actions` 添加：

- `LUOSHU_KEYSTORE_BASE64`：JKS/PKCS12 文件的 Base64 内容；
- `LUOSHU_KEYSTORE_PASSWORD`：密钥库密码；
- `LUOSHU_KEY_ALIAS`：签名别名；
- `LUOSHU_KEY_PASSWORD`：签名私钥密码。

密钥库和密码不可提交到仓库。正式 App 必须长期使用同一把密钥，否则 Android
会拒绝覆盖安装。

## 发布步骤

1. 合并通过真机回归的版本。
2. 按 `module.prop` 创建唯一 Tag，例如 `v14.2-Alpha6`。
3. 推送 Tag；`Publish signed release` 会验证 Tag、固定签名和三个产物。
4. 已存在的 Tag 或 Release 不会被覆盖。修订内容必须提升版本号并创建新 Tag。

正式 Release 包含：

- `Full.zip`：模块及内置正式 App；
- `Lite.zip`：完整字体模块，不内置 App；
- 独立正式 APK；
- 每个产物对应的 SHA-256 文件。
