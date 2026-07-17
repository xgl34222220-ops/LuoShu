# 洛书（LuoShu）

Android 全局字体管理模块，支持整套字体切换，以及中文、英文、数字独立组合。重点适配 Android 16、ColorOS 16、HyperOS 3、Google Play / GMS 和微信 XWeb。

## 功能

- 扫描 `/sdcard/LuoShu/fonts/` 中的 TTF、OTF、TTC 字体
- WebUI 预览、搜索、切换、删除与 ZIP 安全导入
- 中文 / 英文 / 数字独立组合；通用 Android 无独立数字入口时自动提示跟随英文
- 可变字体与静态多字重识别
- 字体文件头与基础表校验，拦截伪装、损坏文件
- 事务式生成字体目录：新配置完整验证后才替换当前配置，失败不会破坏正在使用的字体
- 切换任务可在 WebUI 被关闭后继续执行，重新进入会自动确认结果
- 支持 Magisk、KernelSU、SukiSU Ultra、APatch

## 安装前必看

**请关闭 Root 管理器中的“默认卸载模块”功能。** 否则重启后模块可能被自动移除。

需要元模块时仅推荐 **Mountify**。不要同时启用其他覆盖相同字体路径的模块。

## 使用方法

1. 将字体放入 `/sdcard/LuoShu/fonts/`。
2. 在 Root 管理器中刷入模块并完整重启。
3. 打开洛书 WebUI，整套选择字体，或分别选择中文、英文、数字。
4. 等待“字体已准备”提示后完整重启。

同一次开机只允许准备一次文字字体，这是避免连续热切换导致系统异常的稳定保护。

## APatch

v14.1 针对 APatch 做了单独兼容：

- `customize.sh` 按 APatch 的 source 安装方式返回，不再在成功路径调用 `exit 0`
- 不携带 `magic`、`remove`、`disable`、`skip_mount` 等可能影响模块持久化或挂载的标记
- `post-fs-data` 只执行极轻量初始化，避免超过 APatch 阻塞阶段时限
- 新增 `post-mount.sh`，在模块挂载后同步 ColorOS 字体目录与状态

APatch 旧版本升级后若全部模块消失，需要先按 APatch 官方说明重新安装模块；APatch 已停止使用旧 `module.img` 机制。

## 目录

```text
/sdcard/LuoShu/fonts/    字体文件
/sdcard/LuoShu/import/   待导入字体模块 ZIP
/sdcard/LuoShu/reports/  诊断报告
```

洛书 v14.1 不再管理 Emoji，也不会创建 Emoji 目录或覆盖系统 Emoji。

## 构建

```sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

构建产物位于 `dist/`。每个正式版本使用独立标签和 Release，不再覆盖已发布版本。

## 反馈

请附上设备型号、ROM、Android 版本、Root 管理器、复现步骤和 `/sdcard/LuoShu/reports/` 中的脱敏报告。请勿上传无授权字体文件。

## 开源协议

[MIT License](LICENSE)
