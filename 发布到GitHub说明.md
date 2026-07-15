# 发布到 GitHub

仓库：`xgl34222220-ops/LuoShu`

## 推荐方式

1. 克隆仓库：
   ```sh
   git clone https://github.com/xgl34222220-ops/LuoShu.git
   cd LuoShu
   ```
2. 将本源码包内容完整覆盖到仓库根目录，保留 `.git` 目录。
3. 执行：
   ```sh
   sh scripts/publish.sh
   ```
4. 推送到 `main` 后，`.github/workflows/release.yml` 会自动检查源码、构建模块 ZIP、生成 SHA-256，并创建或更新 `v13.3-Beta2` 预发布版本。

运行脚本前请确保 Git 已登录你的 GitHub 账号。脚本不会保存或写入访问令牌。
