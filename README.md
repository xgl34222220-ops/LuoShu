# 洛书（LuoShu）

面向现代 Android 的通用全局字体管理模块，支持文字字体与 Emoji 独立切换，并针对 Android 16、ColorOS 16、HyperOS 3、Google/GMS 动态字体和微信 XWeb 做兼容处理。

项目最初用于自用。随着 Android 字体来源分散到系统字体、ROM 私有字体、GMS 动态字体和应用独立 WebView，仅替换单个字体文件已经无法获得一致效果，因此逐步整理为可维护的开源模块。

## 主要功能

- 从 `/sdcard/LuoShu/fonts/` 扫描 TTF、OTF、TTC 文字字体
- 从 `/sdcard/LuoShu/emoji/` 独立管理 Emoji 字体
- 检查真实文件头，拦截仅修改扩展名的 WOFF、WOFF2、ZIP 或损坏文件
- WebUI 字符抽样覆盖分析：中文、英文、数字、标点、符号、日文、韩文、Emoji 与私用区
- 解析可变字体 `fvar` 表，显示 `wght`、`wdth` 等轴的最小值、默认值和最大值
- 支持可变字体连续粗细预览，以及静态多字重家族档位选择
- 安全重启工作流：一次开机只允许准备一次文字字体和一次 Emoji，避免连续热切换造成系统卡死
- 保留 ROM 自带 `fonts.xml`、fallback、符号字体和其他语言字体
- 适配 Google Play、GMS、Google 搜索、Gemini 相关进程的动态 Google Sans 挂载命名空间
- 适配微信 XWeb/公众号字体命名空间
- 支持 Magisk、KernelSU、SukiSU、APatch 常见模块环境

正式构建包把 ARM64 原生扫描器保留在模块私有目录 `bin/luoshud`，用于旧目录诊断与故障回退；它不会作为系统分区负载交给元模块挂载。WebUI 默认仍使用安全 Shell 扫描，扫描器不参与字体映射核心流程。

## v13.5 稳定性中心

v13.5 将恢复能力与主 WebUI 分离。构建包会在 `app.js` 之前加载独立的 `stability.js`，因此即使字体列表或主界面脚本异常，右下角的“自救”入口仍可使用。

自救中心提供：

- 检查模块目录、脚本权限和公开字体目录
- 自动识别 ROM、Android 版本、Root 管理器及实际存在的系统字体配置路径
- 清除 WebUI 与模块字体列表缓存
- 修复模块脚本和公开目录权限
- 重建字体索引并记录真实扫描耗时、退出结果和完成时间
- 生成独立自救报告到 `/sdcard/LuoShu/reports/`
- 恢复上一个稳定的文字字体、Emoji 和字体粗细配置

系统每次完整启动后会记录当前稳定配置。检测到配置发生变化时，旧配置自动轮换到 `config/recovery/previous.state`，供下一次故障时回滚。回滚仍遵循一次开机一次切换保护，完成后需要完整重启。

## 已测试设备

- 一加 15（ColorOS 16）
- Redmi K80 至尊版（HyperOS 3）

其他设备和 ROM 可自行测试。字体自身的字形覆盖、私用区字符和应用内置字体会影响最终效果。

## 安装与使用

1. 把文字字体放入 `/sdcard/LuoShu/fonts/`。
2. 可选：把 Emoji 字体放入 `/sdcard/LuoShu/emoji/`。
3. 在 Magisk、KernelSU 或兼容管理器中刷入模块。
4. 完整重启手机。
5. 在模块 WebUI 中选择字体，准备完成后按提示再次完整重启。

切换字体后不要连续热切换。洛书会在同一次开机内阻止第二次文字/Emoji 准备，这是稳定性保护，不是故障。

## Hybrid Mount

- v13.6 Beta5 默认使用 Direct Bind，未选择自定义 Emoji 时安装包和已安装模块都不保留 `system/` 分区负载，因此无需 Hybrid Mount 建立字体 staging。HyperOS 的 Play/GMS 桥接使用独立稳定源，避免应用命名空间隔离。
- 支持 Hybrid Mount、Mountify、meta-overlayfs 及其他遵循 Magisk 模块脚本生命周期的元模块；Overlay 或 Magic 均可，优先保持元模块默认策略。
- 不要设置为 **Ignore**，否则模块文件不会参与挂载。
- 升级时会清理且只清理洛书自身的 `mount.error`，不会修改其他模块或元模块全局配置。
- 洛书自己管理字体目标，避免与其他字体模块重复覆盖同一路径。

## 字体粗细调节

- **可变字体**：读取 `fvar` 的 `wght` 轴，提供连续滑块和实时预览。
- **静态多字重家族**：识别 Thin / Light / Regular / Medium / SemiBold / Bold / Black 等独立文件，在详情页提供离散档位选择，同时保留正文、标题和粗体的层级映射。

应用粗细时会写入 Android 全局 `font_weight_adjustment` 并请求字体服务立即刷新。WebUI 预览即时变化，大多数新打开界面无需完整重启；已运行应用可能需要重新打开，系统界面未更新时可单独点击“重启系统界面”。

卸载模块时会恢复首次调整前的系统原值；ROM 不支持对应接口时自动降级为仅预览。

## 构建与稳定性检查

```sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

`check.sh` 会执行：

- 全部 Shell 语法检查
- `app.js`、字体分析器、KernelSU 桥接和独立自救脚本的 ES Module 语法检查
- WebUI 资源缓存号和自救入口构建注入检查
- 空字体库、1 个字体、20 个字体的状态测试
- 稳定配置快照轮换测试
- 缓存清理、扫描计时和自救报告生成测试

产物位于 `dist/`。更新 `module.prop` 版本并推送到 `main` 后，GitHub Actions 会自动构建并创建对应 Release。

## 反馈

提交 Issue 时请附上：

- 设备型号、ROM 与 Android 版本
- Root 管理器和版本
- 使用的字体格式（不要上传无授权字体文件）
- 复现步骤
- `/sdcard/LuoShu/reports/` 中的脱敏检测报告或 `LuoShu-recovery-*.txt`

## 开源协议

[MIT License](LICENSE)
