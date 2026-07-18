# LuoShu Hybrid App

洛书 v14.2 的混合 Android 客户端。App 不复制字体引擎，继续调用 `/data/adb/modules/LuoShu` 中已经验证的 Shell/Python 复合、可变轴、事务提交和回滚逻辑。

## Alpha1 架构

- Jetpack Compose 原生概览、运行环境、后台任务状态与日志页。
- Android WebView 承载现有字体工作台、多轴编辑、字体对比和健康评分。
- `ksu` JavaScript 接口由 App 实现，现有 WebUI 无需为 App 单独维护一套调用逻辑。
- `common/app_bridge.sh` 为原生页面提供稳定 JSON 状态和日志接口。
- Root 命令全部在协程 IO 线程执行，不阻塞 Compose 或 WebView 主线程。

## 本地构建

需要 JDK 17、Android SDK 37、Build Tools 36.0.0 和 Gradle 9.5：

```bash
gradle :app:assembleDebug
```

APK 输出：

```text
app/build/outputs/apk/debug/app-debug.apk
```

## 后续迁移

1. 原生化字体列表和文件导入。
2. 原生化中文、英文、数字组合与任务进度通知。
3. 原生化完整可变轴工作台。
4. WebUI 缩减为模块管理器中的备用控制台。
