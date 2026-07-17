# 洛书（LuoShu）

面向现代 Android 的全局字体管理模块，支持完整中英数字体复合、文字与 Emoji 独立管理，并针对 Android 16、ColorOS 16、HyperOS 3 和常见 Root 环境优化。

## v14.1 核心变化

v14.1 新增完整复合字体引擎：以用户选择的中文字体作为完整基底，仅把英文和数字源字体对应的字形及度量导入基底，最终生成一份同时包含中文、英文和数字的完整字体。所有 ROM 物理字体槽使用同一份输出，因此不依赖缺字回退，也不会因为英文或数字源字体自带中文而抢占中文。

- 中文覆盖始终来自中文基底
- 英文字形来自所选英文字体
- 数字字形来自所选数字字体
- 不修改 `fonts.xml` 或 `font_fallback.xml`
- 不在刷写或开机阶段生成字体
- WebUI 主动生成、进度可见、成功后事务提交
- 失败时保留当前字体负载
- 相同组合使用 SHA-256 缓存，最多保留三份

应用内置字体、游戏自带字体及网页下载字体不受系统字体模块控制。

## 主要功能

- 扫描 `/sdcard/LuoShu/fonts/` 中的 TTF、OTF、TTC 文字字体
- 从 `/sdcard/LuoShu/emoji/` 独立管理 Emoji 字体
- 从 `/sdcard/LuoShu/import/` 安全导入字体模块 ZIP，仅提取字体，不执行其中脚本
- 检查真实文件头，拦截伪装格式和损坏字体
- WebUI 字符覆盖分析与可变字体轴预览
- 支持 Magisk、KernelSU、SukiSU Ultra、APatch
- Mountify 元模块负载同步

## 已测试设备

- 一加 15（ColorOS 16）
- Redmi K80 至尊版（HyperOS 3 / Android 16）

## 安装与使用

1. 将文字字体放入 `/sdcard/LuoShu/fonts/`。
2. 可选：将 Emoji 放入 `/sdcard/LuoShu/emoji/`。
3. 刷入模块并完整重启。
4. 在 WebUI 中分别选择中文、英文、数字字体。
5. 点击“应用字体组合”，等待生成成功。
6. 完整重启使字体生效。

同一次开机内只允许准备一次文字字体，避免连续热切换导致系统不稳定。

## Root 与元模块

- 无元模块时使用 Root 管理器原生模块挂载。
- 需要元模块时推荐 Mountify。
- 不建议同时启用其他覆盖相同字体路径的模块。

## 构建

正式构建会下载官方 Android ARM64 CPython 运行时，并打包纯 Python FontTools：

```sh
sh ./scripts/prepare_composite_runtime.sh
sh ./scripts/check.sh
sh ./scripts/build.sh
```

构建产物位于 `dist/`。

## 反馈

提交 Issue 时请附上设备型号、ROM、Android 版本、Root 管理器、复现步骤，以及 `/sdcard/LuoShu/reports/` 中的脱敏报告。请勿上传无授权字体文件。

## 开源协议

洛书自身采用 MIT License。随包第三方运行时及库的许可证位于 `licenses/`。
