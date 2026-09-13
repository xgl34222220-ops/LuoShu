# Google 商店英数反弹：组件级无 Hook 备选方案

## 来源与纠正

2026-09-13 用户反馈 v4.4.4 的 Google 商店英数再次恢复默认。本次实际联网检查了：

- MrCarb0n/killgmsfont：https://github.com/MrCarb0n/killgmsfont ，`customize.sh` blob `a92cec4b8020c2c4bc12543b355dae95bd3c5d86`。上游精确停用 GMS 的 FontsProvider 与 UpdateSchedulerService，并会删除 `/data/fonts` 和 GMS 字体目录。本工具不复制删除逻辑，只借鉴组件级切断来源的思路。
- TsinbeiLabs/GoogleSansMax 技术说明：https://github.com/TsinbeiLabs/GoogleSansMax/blob/main/docs/technical-analysis.md ，同样采用 KillGMSFont 路线。其“全家桶绝对统一”的文案不是本项目已验证结论。
- Android Downloadable Fonts：https://developer.android.com/develop/ui/views/text-and-emoji/downloadable-fonts 。字体提供应用与客户端缓存是独立于系统字体文件的链路。
- AOSP PackageManagerShellCommand：https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/pm/PackageManagerShellCommand.java ，`runSetEnabledSetting` 对完整组件名调用 setComponentEnabledSetting，flags=0；这不是停用整个包，但可能导致相关进程重启。
- AOSP Settings：https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/pm/Settings.java ，核对 installed package、User、firstInstallTime 和 enabled/disabledComponents 输出范围。

此前把持续监听或补挂载说成了完整拦截，或者认定需要 Hook，均不准确。组件级停用是一条真实存在的无 Hook 备选路线，但不能据此证明用户手机每个页面的唯一根因。

## 本次实现与影响

新增 `tools/google_font_fallback.py` / `.sh`，是显式选择的独立维护工具，不进入开机服务、不默认执行、不修改 4.4.4 已发布 APK/ZIP、不新增正式或预发行 Release。

仅对当前 Android 用户的固定组件 `com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider` 进行停用。更新调度服务不动；无需为阻断该 Provider 的新请求扩大到整个 GMS 或清空缓存。按用户隔离而不是扫所有工作资料/应用分身。

这是可持久化的包管理器设置，不是 systemless 挂载。**重启不会自动撤销，单独停用洛书模块也不会撤销；停用或卸载洛书之前先运行 restore。** 工具需要已安装洛书的 Python 运行环境。恢复记录保存在 `/data/adb/luoshu-google-font-fallback/user-<id>.json`，不能随意删除。

影响该用户所有依赖这个 Provider 的下载字体请求，也可能涉及下载式表情字体；不会仅按 Google 商店单一 App 生效。Android 修改组件状态可能重启 GMS 相关进程，不能承诺登录/支付/通知等完全无瞬时影响。工具不调用清除账户/数据、停用整包、强停前台 App、注入进程、删除 `/data/fonts` 或扫描无关 App 数据的操作。

应用收到失败后使用哪个字体由应用实现决定，可能回退系统字体，也可能使用内置字体或出现异常。因此这只是候选修复及定位工具，不是“所有谷歌应用永不反弹”的保证。旧字体对象/文件描述符需要完整重启后重新验证；应用自带字体和网页字体不由本开关控制。

## 使用

仓库版 `.sh` 与 `.py` 放在同一目录，Root 执行：

```sh
sh google_font_fallback.sh status
sh google_font_fallback.sh enable
sh google_font_fallback.sh restore
```

会自动读取当前用户；明确需要另一个用户时加 `--user 10`，不接受 all。默认参数是 status，不会静默开启。

单文件分发版由 `.sh` 引导头与同一个 `.py` 内容组合而成，可直接在已安装 4.4.4 的设备使用。保存为 `/sdcard/Download/LuoShu-Google-Fallback.sh` 后：

```sh
su -c 'sh /sdcard/Download/LuoShu-Google-Fallback.sh enable'
# 确认输出 component-disabled 后手动完整重启，再检查原来的商店页面。
su -c 'sh /sdcard/Download/LuoShu-Google-Fallback.sh restore'
```

若组件本来已停用，会报告 externally-disabled，不接管原有停用状态。这意味着继续反弹应排查其他来源，而不是重复强制同一开关。未知包状态、组件缺失、GMS 重装身份变化或恢复记录损坏时，报错而不是猜测成功。发生异常时保留输出，不要删除恢复记录。

## 验证

本地 24 项主机单元测试通过：当前安装与旧 ROM 副本区分、用户隔离与安装时间、默认/显式启用恢复、已停用不接管、写前日志、重复调用、失败回滚、仅返回成功但未改状态、PID 无关的文件锁、恶意组件/错误用户/符号链接拒绝等。测试只模拟 Android 包管理器输出与调用，不是真机包管理器或字体渲染测试。

没有连接用户 K80 或一加手机，没有读取当前 Google 商店字体进程证据，也没有确认该设备启用此开关后的最终效果。版本规则保持下一个正式版 5.0.0；不凭单元测试发布新的“已彻底解决”版本。
