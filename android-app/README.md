# LuoShu Native App

洛书 v14.2 Alpha5 的原生 Android 管理端。App 不复制字体引擎，而是通过 Root 调用 `/data/adb/modules/LuoShu/common/app_bridge.sh`，复用模块已经验证的字体扫描、复合、可变轴、事务切换和回滚逻辑。

## Alpha5 架构

- Jetpack Compose 原生 MIUIx 风格界面，不在核心功能中使用 WebView。
- 原生字体库、搜索、预览、切换、删除、复合字体和任务进度。
- 仅为屏幕中实际显示的字体导出预览，缓存最多保留 6 份、总计约 96 MiB。
- 只有字体真实包含 `wght` 轴时才显示连续字重滑杆；静态字体显示实际离散字重。
- 所有 Root 命令在 IO 协程中运行，参数经过 Shell 引号处理。

App 必须与同版本洛书模块配套使用。未安装模块时只能显示桥接不可用状态。

## 本地构建

需要 JDK 17、Android SDK 与 Gradle 9.5：

```bash
gradle :app:assembleDebug
```

APK 输出：

```text
app/build/outputs/apk/debug/app-debug.apk
```

GitHub 的 Alpha5 集成工作流会同时产出：

- 可直接安装的 `LuoShu-App-v14.2-Alpha5.apk`；
- 内置同一 APK 的 `LuoShu-v14.2-Alpha5.zip`。

刷入完整模块包时会尝试安装或更新 App；若安装环境暂不可用，可在重启后点击 Root 管理器中的模块“操作”按钮再次安装。
