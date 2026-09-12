# PR 217 Test6：K80 原厂链接与主字体入口

## 问题与证据

用户确认 K80 至尊版状态栏已正常，但酷安标题/热度和 QQ 年龄标签仍偏移；同类页面在一加 15 正常。
本轮直接检查 dali 官方 OS3.0.305.0.WONCNXM 的原厂文件，不再使用其他小米机型代替 K80。

原始来源：[小米官方 Recovery ROM](https://bigota.d.miui.com/OS3.0.305.0.WONCNXM/dali-ota_full-OS3.0.305.0.WONCNXM-user-16.0-3298197d54.zip)。
按 ZIP64 目录、OTA manifest 和 EROFS 文件路径提取所需块，各 OTA operation 校验 SHA-256。
该样本为 Android 16 / SDK 36。它证明该版 K80 的原厂结构，不代表已经读取用户手机的当前进程 Typeface。

### 跨分区链接读回替换字体

K80 的 `/system/fonts/MiSansVF.ttf` 和 `MiSansLatinVF.ttf` 是指向 `/product/fonts/` 的绝对链接。
旧扫描器虽然选择了可信的 `lower/system-fonts` 目录，打开其中的链接时仍会跳到正在覆盖的
`/product/fonts/`。目录校验没有保证最后读取的字体实体来自原厂。

用户上传记录中，所谓 stock MiSansVF 的 head 横向边界、flags、最低 PPEM 与 active font-1 一致，
而纵向值已经被旧版校准过，容易被误判为原厂读取正确。用项目自己的 `_read_metrics` 对比：

| MiSansVF 数据 | 官方 dali 样本 | 用户库存记录 |
| --- | --- | --- |
| head.xMin / xMax | -990 / 1805 | -999 / 1059 |
| head.flags | 3 | 553 |
| lowestRecPPEM | 7 | 8 |
| Han 数量（项目统一口径） | 27782 | 34412 |
| Unicode 数量 | 29571 | 36853 |

若西文槽也把替换字体的汉字覆盖误记为原厂，Test4 的回退保护会提前返回 `stock-han-slot`，
不能恢复真正的中文回退。上传报告未抽到 MiSansLatin，因此此后果由真实链接结构与回归场景验证，
没有把它描述为已观测到 QQ 进程的具体字体选择。

### 名为 MiSans 的主入口默认实际来自 Roboto

原厂 `system_ext/etc/hyper_fonts.xml`、`hyper_font_fallback.xml`、`miui_fonts.xml`、
`miui_font_fallback.xml` 均将默认 `sans-serif` 指向 `MiSansVF_Overlay.ttf`。
该文件链接到 `/data/system/fonts/theme_webview/Roboto-Regular.ttf`。

同一 ROM 的 `system_ext/etc/init/init.miui.ext.rc` 在 post-fs-data 阶段先把原厂
`/system/fonts/Roboto-Regular.ttf` 复制到此位置，再尝试用用户主题中的 Roboto 覆盖。
所以可变的 `/data` 文件不能被当作不可变原厂；默认 ROM 对应的字体参考是原厂 Roboto。

| 原厂文件 | UPM | hhea ascent / descent / gap | head yMin / yMax | Latin / Han |
| --- | --- | --- | --- | --- |
| Roboto-Regular.ttf | 2048 | 1900 / -500 / 0 | -555 / 2163 | 52 / 0 |
| RobotoStatic-Regular.ttf | 2048 | 1900 / -500 / 0 | -555 / 2163 | 52 / 0 |
| MiSansLatinVF.ttf | 1000 | 1044 / -282 / 0 | -282 / 1044 | 52 / 1（仅 U+3007） |
| MiSansVF.ttf | 1000 | 1044 / -282 / 0 | -282 / 1044 | 52 / 27782 |

字体 SHA-256：

- Roboto-Regular: `9ca9debb09459bf4e3e7f826f5cd0f35f253902b85684921fce2ba3f28dd0f50`
- RobotoStatic-Regular: `06cba01eb71ea5cbd3a7df498910624db68953beead4be18fd91f8ec7dc72351`
- MiSansLatinVF: `0e9cd4d867fa61cecd7b6a315bc67a54bee91bd1c693d865cbbcc9e030b051db`
- MiSansVF: `0ddef90648998900175cfdca9a6f087a2544c182f130b0ad4f7e94a03a115e79`

真实字体端到端回归又确认：MiSansLatin 带有 `〇`（U+3007），项目的 Unicode 覆盖统计把它
正确计入 Han，但旧路由将“含一个汉字数字”错误等同于“中文字体”，仍会跳过整个中文回退修复。
本轮路由按真实汉字数量判断；保留原厂 `〇`，只让新添的大量汉字回到 MiSans。

另见 [Skia 官方修复 ce19122](https://skia.googlesource.com/skia/+/ce19122e3982a94ba8c401dda0ec42928bc6d595)：
它记录了小米 XML 的 MiSansVF_Overlay 与 NDK 实际返回 Roboto 的差异。该记录是另一款小米机型，
仅作为独立渲染路径的参考，不等同于已经修复全部 Google 应用内置或下载字体。

## 本轮实际修正

- 逐文件解析字体链接，将跨分区逻辑路径重新映射到相应的可信 lower/mirror，防止读回 live 覆盖。
- 对已验证的 K80 Overlay 链接，使用原厂 Roboto 作为明确记录的 ROM 参考，不读取可变主题字体。
- Overlay 的中文覆盖和 Bitmap 底部校准走已验证西文 UI 路径；中文经真实 MiSans 回退，英文数字仍使用用户字体。
- 修复 MiSansLatin 仅含 `〇` 就被误判为中文字体的分支，保留原本的数字与标点映射。
- HyperOS 原厂扫描覆盖其现有物理 mapper 的安全目标，补齐此前会落入通用度量的 NotoSans / XiaomiSans 等槽位。
- 旧 HyperOS 库存通过专用修订自动更新，仍要求可信原厂视图，失败保留旧文件并由既有启动流程重试。

不移动整套字形，不改已正常的 MiSans 主字体和专用时钟的校准规则。ColorOS 不增加物理覆盖。
官方原厂文件仅用于分析，测试包不携带小米字体或整个 ROM。

## 验证与实机范围

主机回归覆盖跨分区绝对链接、相对链接、间接链接、循环和主题目录拒绝；覆盖用户字体
有汉字而 stock Latin 没有汉字的污染场景，以及 Overlay 原厂参考、最终 cmap、行度量和字形表保留。
原有 ColorOS 与时钟回归继续执行。

这是针对已定位代码路径的测试修复，尚未在用户的 K80 / 一加上验证最终截图。
刷入后先重启，让库存更新；再重新应用当前字体或组合，并按提示重启，使旧负载被重新生成。
App 无变更，可继续使用 Test4 配套 App；默认卸载模块保持关闭。
