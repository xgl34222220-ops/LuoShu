# 发布到 GitHub

仓库：`xgl34222220-ops/LuoShu`

## 推荐方式

1. 克隆仓库：
   ```sh
   git clone https://github.com/xgl34222220-ops/LuoShu.git
   cd LuoShu
   ```
2. 在独立分支完成修改并通过 Pull Request 校验，不要直接覆盖或推送 `main`。
3. 如需在本地复核候选模块，先准备固定签名的正式 APK，再执行：
   ```sh
   LUOSHU_APP_APK=/path/to/LuoShu-App.apk sh scripts/publish.sh
   ```
4. 合并通过检查的 PR 后，由 `.github/workflows/release.yml` 重新检查源码、固定签名、证书指纹、模块 ZIP、SHA-256 和真机门禁，再创建不可覆盖的 Release。

`scripts/publish.sh` 只构建并验证本地候选，不会提交、推送 `main` 或创建 Release。预发行允许真机矩阵保持待测；稳定版必须在 `docs/device_validation.json` 中提供 ColorOS、HyperOS、Magisk 与 APatch 的通过时间和验收证据。
