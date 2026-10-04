# 原分支的小批次改进与参考依据

继续 `fix/stable-composite-contract-20261003` / [PR #264](https://github.com/xgl34222220-ops/LuoShu/pull/264)。
本记录只引用本轮新运行的结果；上一轮 Root 验收不替本轮改动背书。

## 核实状态

开始时本地与远端均为 `1a329a1c0cb3cb8aaa70de6972fd10a39a1bf964`，工作区干净，PR 开放且为 Draft，没有运行中的构建或 Android 任务。
最近一次历史 Root 验收为 [37152531513](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37152531513)，已成功；本轮候选包和新增用例需要重新验收。

## 参考项目与采用范围

| 参考 | 源码、文档与许可证 | 洛书的具体差距与处理 |
| --- | --- | --- |
| Font Manager | [JSON 读取实现及函数文档](https://github.com/FontManager/font-manager/blob/ff593362d69a893ce59897b0e01952d1f57654d5/lib/json/font-manager-json.c)、[字体元数据实现](https://github.com/FontManager/font-manager/blob/ff593362d69a893ce59897b0e01952d1f57654d5/lib/common/font-manager-freetype.c)、[项目文档](https://github.com/FontManager/font-manager/blob/ff593362d69a893ce59897b0e01952d1f57654d5/README.md)、[GPL-3.0 许可证](https://github.com/FontManager/font-manager/blob/ff593362d69a893ce59897b0e01952d1f57654d5/COPYING) | 它使用结构化 JSON 和真实字体属性。洛书剩余组合任务错误路径仍用贪婪正则读 JSON；改为复用现有有界解析器。轴名称也应来自字体元数据。借鉴做法，独立实现，没有复制其代码。 |
| FontTools | [fvar 源码](https://github.com/fonttools/fonttools/blob/f4e996be2fd6207b7b8a9506e9c6b367c91c50db/Lib/fontTools/ttLib/tables/_f_v_a_r.py)、[TTFont 文档](https://fonttools.readthedocs.io/en/stable/ttLib/ttFont.html)、[实例化文档](https://fonttools.readthedocs.io/en/stable/varLib/instancer.html)、[MIT 许可证](https://github.com/fonttools/fonttools/blob/f4e996be2fd6207b7b8a9506e9c6b367c91c50db/LICENSE) | 已有按需读取和轴名称能力，无需换引擎或升级依赖。洛书轴读取器却先调用 `read_bytes()` 读取整个字体；应只检查四字节文件头，再读取需要的表。 |
| Inter Font Pack | [名称适配源码](https://github.com/kdrag0n/inter-font-pack/blob/d74a915d562e6cf1852546a97e18139a74e48475/patch-font-names.sh)、[兼容性文档](https://github.com/kdrag0n/inter-font-pack/blob/d74a915d562e6cf1852546a97e18139a74e48475/README.md)、[MIT 许可证](https://github.com/kdrag0n/inter-font-pack/blob/d74a915d562e6cf1852546a97e18139a74e48475/LICENSE) | 其兼容性文档强调保留系统名称与未覆盖字符的正常回退。洛书已有更严格的集合/系统框架保护，应继续验收这些契约。其修改字体配置的方式不适用于洛书既定边界，本轮不采用。字体资源的 OFL 与模块代码许可证分别处理，没有引入其字体资源。 |
| AndroidX Compose 字体解析 | [有界请求缓存源码](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/compose/ui/ui-text/src/commonMain/kotlin/androidx/compose/ui/text/font/FontFamilyResolver.kt)、[字体与可变轴文档](https://developer.android.com/develop/ui/compose/text/fonts)、[Apache-2.0 许可证](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/LICENSE.txt) | 请求身份、可缓存结果和有界缓存应一致；它将加载去重责任留给实际加载器。洛书默认轴与控件分开读取并缓存错误，应复用一个成功结果缓存。串行 Root 元数据读取、内容版本键和失败重试是针对洛书的独立实现，没有复制上游代码。 |

另参考 [OpenType fvar 规范](https://learn.microsoft.com/en-us/typography/opentype/spec/fvar)：轴名称来自 `axisNameID`，轴有各自的范围和默认值。本文的任务身份校验是洛书独立设计，不归因于参考项目。

## 第一批：组合任务交接和 JSON 错误读取

触发问题：启动输出出现旧任务号或嵌套字段时，原交接函数会直接接受输出里的任务号，跳过持久化记录的三种字体校验；剩余错误路径还沿用发生过 Android 原生段错误的贪婪 `sed` 形式。

改动：只接受新持久化任务号、匹配的中文/英文/数字字体和合法任务状态。标准输出丢失、截断或夹杂旧任务号都不改变任务归属。启动和实例化错误复用 `task_scope.py error-message` 的 256 KiB 有界 JSON 解析；正确解码转义并清理换行控制字符。高频进度仍读已有轻量百分比；消息用有界字节循环解码本项目原子写入器的 UTF-8 字符串，异常记录回退到持久化任务消息，不新增 Python 轮询。

本轮本地验证：

- `scripts/mix_handoff_contract_test.py`：25 个真实 shell/消息用例首先通过，补齐进度字符串后共 32 个用例；标注 `HOST_ONLY`。同一脚本可在隔离 Android 内用原 ARM64 Python 执行。
- `scripts/font_switch_error_message_test.py`：10 个测试通过。
- shell 语法和 `git diff --check` 通过。
- `scripts/stable_mount_boundary_test.py`：17 个冻结文件与 `refactor-v1.1.1` 一致。
- 本地嵌套任务集成门禁失败：第二次启动报告 `[task-scope] RuntimeError: Cannot verify task boot/process identity`。保留失败，不以本地纯解析测试代替进程门禁；正式 CI 必须重新通过该集成测试。

提交和本轮 CI/Android 结果将在实际完成后记录，不预填成功。

第一批提交：[`ac886690`](https://github.com/xgl34222220-ops/LuoShu/commit/ac886690d1902693aa6d89471ef5b99053f04057)。
首次 [CI 37157270444](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37157270444) 的嵌套集成测试已通过，但后续收尾性能门禁失败：它要求保留详细进度消息。本轮按日志恢复这个功能，并用有限字节读取替代旧正则；保留原门禁继续验收。

修正提交 [`1f9ea679`](https://github.com/xgl34222220-ops/LuoShu/commit/1f9ea679a1e2512ba009aba6d27ab4accf2afacc) 的 [完整候选 CI 37157593288](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37157593288) 已成功：源码、补充门禁、实际 Android CFF2 回归、App lint/单测/构建和候选包校验均通过。

## 第二批：按需读取轴元数据，显示真实能力

采用理由：Font Manager 的真实字体属性分类、FontTools 的按需读表和 OpenType 的轴名称/隐藏轴语义，适合补齐现有界面，不需要重做主题或挂载。

改动：

- 轴读取器只读四字节文件头，再按需读取 `fvar` / `name`。复用现有字体元数据名称解析，不复制上游代码、不换依赖。
- 自定义轴显示字体声明的名称；常见轴保留既有中文名称。隐藏轴保留元数据与默认值，但不作为普通调节控件。
- 非法范围、重复标签和非有限数值不能成为滑块；读取错误明确显示，避免被误当成固定字重。
- 能力标签改为“可变字体”，避免对只有字宽等轴的字体承诺“可变字重”。Material/Miuix 的既定样式保留。

本轮本地证据：`font_axis_info_test.py` 9 个真实 SFNT/TTC、损坏字体与内存回归通过；原生预览源码检查、紧凑布局检查和 17 文件冻结边界通过。新增 App 解析/能力单测须由本轮 Android 构建运行，尚未预填通过。

同一 64 MiB 原创 SFNT（含大尾部区域）的 `tracemalloc` 测量：旧读取器分配峰值 `67,114,265` 字节，新读取器 `16,938` 字节，两者均正确读出 2 个轴。[原始测量值](AXIS_READ_MEMORY_20261003.json) 标注 `HOST_ONLY`；该数据是此读取路径的宿主 Python 分配峰值，不是 Android 整机 RSS、延迟或真机结果。

仍沿用集合面 0 的轴描述策略；异构集合的按角色选面界面一致性不在本批宣称已解决。

第二批提交 [`17783f22`](https://github.com/xgl34222220-ops/LuoShu/commit/17783f2229e8ecb946bbd280a7c6343292e296da) 的 [完整候选 CI 37157991533](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37157991533) 已成功，包含上述新增 App 单测。
下载本轮 artifact `11286956067` 独立校验：外层 ZIP SHA-256 `c53aa732931955f8c0c81b104935e77756f7c895904542f1ddca5dd95a2397ad`；模块 `a56a54ea9618946f8a96cf9e3d91fea751f72f1aa9d318842e6865ad5b9b957c`；APK `a929619682dca646c1a2486ec42a0813de595e9be93c4f5571faa70c0a69a8e5`。
已对 17 个冻结文件、6 个运行源码、模块内外 APK 字节、构建来源和校验文件逐一核对，保存了[结构化包校验](TEST_CANDIDATE_VERIFICATION_37157991533.json)。

## 本轮隔离 Android 验收的新增门禁

Root workflow 只绑定上述已通过、已下载验真的候选包。新增门禁包括：

- 同一套 32 个交接/UTF-8/进度用例，用原 ARM64 Python 和 Android shell/toybox 在 Magisk/SELinux Enforcing 环境重新运行。
- 真实 Android CFF2 集合的轴名称、范围、默认值及隐藏标志读取。
- 只用项目原创几何字体构造无字重轴的可变字体，实际在 App 中文基底选择器选择它；检查“可变字体”、字体声明的“纹理细节”/`XTRA`、隐藏轴未曝光，保存新 UI XML 与实际截图，并确认系统字体哈希不变。
- 判定器拒绝 HOST_ONLY、缺失/重复用例、缺失名称、错误范围、隐藏轴曝光和不完整的 App 实际证据。

首次新增后，宿主 Root harness 的 85 个测试通过。[本轮 Root 37159156172](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37159156172) 的整体结果仍为 BLOCKED：基线/候选模块周期、集合组合、12 次模块重启、32 个原 ARM64 Python/Android shell 交接用例及 CFF2 轴元数据已通过，但 App 轴夹具直接复制到公共目录，没有走原生导入器生成的元数据，因此真实字体库返回 `variable:false`。App 轴检查、100/1000 库和实际 App 应用恢复尚未运行，不能以已过阶段代替完整门禁。

下载失败 artifact `11287526886`，外层 SHA-256 `3d359de852c6e87b3eb9af3dae23077cf00f81fdb9c25d73c9e932e2cd102138`，完整 ZIP 校验通过。[失败证据](ROOT_ANDROID_FAILURE_37159156172.json) 保留具体库存值和未运行项目。已有临时政策已撤销，工作空间为空，模拟器已回收，KVM 元数据未变。

修正提交 [`fa421625`](https://github.com/xgl34222220-ops/LuoShu/commit/fa42162554ccc5a0181df8baadedc2b29fe26542) 只涉及验收脚本：原创字体先在既有 `.stabletest/cache/native_import` 信任目录生成，再调用真实 `import_file` 桥；校验新导入、中文覆盖、源/目标 SHA-256 和真实库存。门禁额外拒绝缺失导入、重复导入、错字体 ID 或字节变化；没有伪造字体缓存或配置。只清理本门禁创建的字体、配置及私有夹具文件。该版宿主 harness 的 86 个测试在本地及 [完整 Root 重跑 37160499707](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37160499707) 的 CI 前置步骤均通过，17 个冻结文件再次通过。

第二次整体仍 BLOCKED：真实导入成功，库存已返回 `variable:true`；新增 UI 门禁却把顶部摘要和详细卡片的两个“中文基底”标题当成歧义，未点击选择器。下载 artifact `11287897610` 并校验 SHA-256 `1e2a133b73011a7042cb225e55114b4b836a72d965a88ba72e7c0eb042c9e287`，保存 [实际失败证据](ROOT_ANDROID_FAILURE_37160499707.json)。修正用详细卡片的精确说明、非点击标题和字体选择器位置来绑定目标；完整卡片终点必须是下一张详细卡片，顶部摘要不能充当终点。保存真实 XML 的选择器回归只证明脚本选择逻辑，不能代替新的 Android 执行；当前宿主 90 个测试通过。第三次完整重跑的结果见下文，未预填 App 成功。

## 第三批：共享按字体版本缓存的轴读取，定位实际 App 超时

[Root 37162597156](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37162597156) 实际选中了可变夹具，导航已跨过此前失败；App 显示“字体轴读取失败：命令执行超时”。整体继续 BLOCKED，100/1000 库及实际 App 应用/恢复未运行。[新失败证据](ROOT_ANDROID_FAILURE_37162597156.json) 保留 artifact 哈希、13 个 UI 帧、失败截图哈希和未验证项目。来源查找、Python 读取和 Root 请求哪一段超时尚未证明。

代码核对发现，选择器的默认轴读取和控件的轴读取分别调用 `weight_axis`，默认轴缓存只按字体 ID，失败还会缓存成 400。这是独立可证明的可靠性差距。参考 AndroidX 的按请求身份保存可缓存结果、有界缓存及实际加载器负责去重的设计，沿用已有 FontTools/OpenType 元数据路径，两处共享一个有界的成功结果缓存，以 `sourceRevision` 为键，最多 64 个版本，并串行化元数据请求。取消和失败不写缓存；同名同大小替换也会重新读取。宽度轴字体的元数据和默认轴不伪造字重轴。

提交 [`de69988d`](https://github.com/xgl34222220-ops/LuoShu/commit/de69988d61d313908532d0cfd80ec2815e91fbc5)。选择器总预算仍为 20 秒，包含等待正在运行的轴读取；控件的命令预算仍为 25 秒。本批不靠扩大超时通过门禁。隔离测试候选版增加数值阶段耗时标记，不记录字体 ID、路径、元数据或任意命令错误；正式版不开诊断。

[新构建 37165156535](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37165156535) 全部成功，含源码、补充、原厂 Android 15 CFF2 夹具回归、App lint/`:app:testDebugUnitTest`/构建及包校验。新增 6 个缓存回归覆盖并发、同名替换、失败重试、取消、缓存上限及无字重轴；不填未读取的 JVM 总测试数。下载 artifact `11288959193` 后，[独立核验](TEST_CANDIDATE_VERIFICATION_37165156535.json) 通过：外层 ZIP `d38402bb881fade9fe437e8a1a0ec1ed0fab34bbe90412213dbdbcc40c651758`，模块 `b398de7f4bcc5270f6aad7878872c42796c773425c54bc37c498d91c95bad7bb`，APK `bbd97255df688c447de8d884f861b11777f103d7b051a737fe1239c54760143f`；来源、内外 APK、7 个运行源码和 17 个冻结文件逐一一致。

完整 Root workflow 现改绑这个验真的新候选；App 门禁同时保存数值阶段日志，失败仍按 FAIL/BLOCKED 判定，并将原始失败报告及真实导入来源保留到模块报告。当前改动的宿主 harness 90 个测试通过，只证明脚本逻辑；新 Android 结果仍待实际执行。

验收脚本提交 [`babdbc54`](https://github.com/xgl34222220-ops/LuoShu/commit/babdbc5494c9320d3f04bf3b5f68190e444060e3) 的 [完整 Root 37165919726](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37165919726) 已成功。下载 artifact `11290496994` 并独立核验外层 SHA-256 `5de93840882b85897025ad505527e71b44142164c5eadaf60bd163a7b4da3105`，[结构化验收](ROOT_ANDROID_VERIFICATION_37165919726.json) 无 blocker：

- 原 ARM64 Python/Android shell 的 32 个交接用例重新通过；前置宿主 harness 为本轮 90 个测试。
- 真实原厂 5 面 CFF2 均编译并保留变化轴；14 次不同内核启动 ID、19 条挂载证明（含 2 个原厂别名）独立重算通过。组合及 App 单字体应用均按实际重启/挂载/字节恢复验证。
- 实际 App 的无字重轴字体显示“可变字体”“字宽”与“纹理细节”/`XTRA`，内部轴未进入普通控件。10 个实际 XML 帧、完整卡片终点、原创字体真实导入、源/目标哈希和原厂字体未变逐项核对。保留 [实际截图](evidence/root-axis-37165919726.png)、[完整卡片 XML](evidence/root-axis-37165919726.xml) 和 [实际阶段日志](evidence/root-axis-37165919726.txt)。三角形样张来自本门禁原创几何字体，不是字体缺失。
- 本轮实际轴请求只有 1 次，耗时 9,404 ms、退出码 0；来源查找约 50 ms，Python 分析约 1,470 ms。旧失败没有阶段日志，不能将不同运行的差异当成严格性能基准，也未严格确定旧超时的底层原因。
- 本轮 2 条原生 tombstone 均由任务号绑定到未改的原版基线失败注入（损坏字体与提交失败）；候选无意外原生崩溃，最终目标 App 无 fatal/ANR。初次无 Root 的 App 检查遇到系统 UI ANR，仍标 BLOCKED，不将它改写为通过。
- 100/1000 文件的真实 App 字体库分别运行 3 次启动、3 次重新进入。1000 库的重新进入首帧为 566/512/535 ms，核验完成为 37,639/7,549/6,527 ms；首轮指纹请求超时（14,546 ms，code 124）后成功重试，保留 [慢请求日志](evidence/root-library-1000-warm-0-37165919726.txt)，作为后续实际性能问题。每组只有 3 个样本，不能代表真机分位数；1000 文件只含两份唯一原创字体内容。
- 临时 Root 政策撤销、任务工作空间为空、两个模拟器已回收、KVM 元数据未变。

本轮 Root App 通过不覆盖原生 ARM64/OEM 真机、App 完整组合创建 UI、像素几何、备份恢复 API，以及上述无 Root 界面检查。

## 第四批：减少整库预览查找的子进程与无关文件检查

采用理由：继续参考 AndroidX 把加载工作交给实际加载器的设计和 Font Manager 的集中字体属性处理。本项目已有唯一的族名解析器，应复用它，降低每个可见预览对整库造成的进程/文件操作，不新增目录监听或后台服务。

本轮慢请求已经证实 1000 文件库的指纹调用曾超时后恢复，但未证明底层原因。源码核对发现，每次原生预览查找都对整库文件启动 `basename`，并通过 shell 子进程调用族名解析，且对无关族文件执行文件检查。改为同一解析函数的进程内返回值、shell 路径参数展开，并只检查匹配族名的文件。第一份变量源按原规则直接胜出；静态最近字重、同距离顺序和跨格式顺序保留。stdout 使用 `printf`，避免字体名中的反斜杠或 `-n` 被 `echo` 当成控制输入。

[宿主测量](PREVIEW_LOOKUP_HOST_MEASUREMENT_20261004.json) 使用冻结的改前/改后源码副本和 1000 个仅供来源选择的文件：外部 `basename` 调用从 1003 次降到 2 次；3 次无探针测量的中位数从 2099.244 ms 到 53.272 ms。统计通过该进程专用 PATH 包装器完成，没有使用/扩大进程跟踪权限。该测量为 HOST_ONLY，不是 Android 或原生 ARM64 提速比例，也不证明先前指纹超时的原因。

新增可在原 ARM64 Python/Android shell 执行的 18 个实际 shell 用例，覆盖变量源优先、静态最近/同距/跨格式、大小写后缀、中文空格、字面反斜杠、`-n`、单次后缀规则、目录/缺失源和 1000 独立文件；进入强制源码门禁。本轮本地 18 个选择用例、库存 17 个回归和冻结 17 文件通过。新候选 CI 和 Android 复测尚未预填通过。

第四批提交 [`dc497301`](https://github.com/xgl34222220-ops/LuoShu/commit/dc4973016c242d6ee71083644652083480f6ea4d) 的 [完整候选 CI 37169144226](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37169144226) 已通过，含上述新选择门禁、实际 Android 15 原厂集合夹具回归、App lint/单测/构建及包检查。下载 artifact `11290754515`，[独立包校验](TEST_CANDIDATE_VERIFICATION_37169144226.json) 通过：外层 ZIP `b14141399032168362254c3c153cdfb004cc8a9b2b3847357ec40896499909ee`，模块 `67aa350efb3b1fd6f0606b92d28f75419cb21428232a435099c01fccc149e2ae`，APK `e6819a7592efb1edb5909c60cffc9c5c898091f06ab928c0c90216c3bc345b53`。17 个冻结文件、8 个运行源码、内外 APK 和构建来源逐一一致。

Root workflow 改绑这个新验真的候选，并增加实际安装模块下的 18 个预览来源选择用例，要求同一启动身份、原 ARM64 Python、Android shell 和 Enforcing。门禁拒绝宿主、错模块/解释器、缺失/重复/失败用例；本轮宿主 harness 92 个测试通过，仅证明验收脚本逻辑。[第四批完整 Android 37169987413](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37169987413) 已结束，整体 BLOCKED，具体新证据见下节。

## 第五批：当前复合字体引擎的结构化错误回退

采用理由：延续 Font Manager 的结构化 JSON 处理原则，审查发现非冻结的 `common/font_mix.sh` 仍以贪婪 `sed` 提取错误消息。它是当前加权任务的基础引擎，不能把此前加权实例化路径的修复当成这里已经修复。仅复用已加载的 `luoshu_task_helper error-message`；保留返回码提示优先级和原有纯文本末行回退。冻结的 `legacy_v14_4/font_mix_engine.sh` 及 17 个挂载文件未改。

新增 15 个可在原 ARM64 Python/Android shell 执行的真实错误函数用例：UTF-8 中文/引号/路径、ASCII Unicode 转义、缩进和嵌套字段、长日志有界 JSON 尾部、解释器不可用回退，以及原 124/137/9/126/127/20/21 提示优先级。本地 15 个通过；固定改前 `dc497301` 源码在同一首例不能保留完整消息，确认回归测试能识别旧行为。测试提取实际源码函数以避开入口调度器，仅证明错误处理函数，不代替完整 CLI 生成/挂载。

既有字体切换错误集成测试首次运行 10 个中有 2 个在本地超过 8 秒；保留该失败，不扩大期限。随后隔离复现单例为 0.161 秒，重跑完整 10 个为 0.432 秒并通过，没有发现稳定根因，也未据此宣称修复了宿主间歇性超时。本轮 17 个冻结文件校验通过；新的候选 CI 和 Android 错误函数门禁仍待运行。

第五批提交 [`aec481e1`](https://github.com/xgl34222220-ops/LuoShu/commit/aec481e10a7796078232b41e4ea0a9043bc93b40) 的 [新候选 CI 37170909720](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37170909720) 完整通过：源码/补充门禁、15 个错误函数用例、上述既有集成测试、原厂 CFF2 夹具的宿主编译/FreeType 检查、App lint/单测/构建及包检查。下载 artifact `11291328122`，[独立核验](TEST_CANDIDATE_VERIFICATION_37170909720.json) 外层 `8c77f7eeed850518f8076771470893f12e050c3b8dbdf9f89cccbc5f61e133c0`，模块 `698ca4099970d5c56057e4eae9f0e16945821db8a4e809d21979e0ee9ccb312e`，APK `a45a47b74d4b9a9bf4e15bfb8f9925192a3ecb5e82021c57b998527089da3097`，17 个冻结文件及 9 个运行源码、来源/内外 APK 一致。额外核对旧冻结引擎与本轮起点 `1a329a1c` 的字节一致。

新的 Root 门禁绑定该包，分别记录 32 个交接、18 个来源选择及 15 个当前错误函数用例，不以错误函数测试代替完整 CLI 组合。新增判定器要求实际 Android、正确模块/解释器、同一启动身份、Enforcing 和完整唯一用例。本轮宿主 harness 94 个测试通过，[第五批完整 Android 37171895602](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37171895602) 已结束，整体 BLOCKED；下载 artifact `11292104489`，外层 SHA-256 `1057c19b4af9ae78c9864973003b8045b4e38b249358174c58963d085250090e` 独立核对，使用本轮固定 `d58e3021` 判定器重算。[新失败证明](ROOT_ANDROID_FAILURE_37171895602.json) 保留 32 个实际交接、18 个来源选择、15 个当前错误函数、5 面 CFF2、14 次重启、19 条挂载证明和实际 App 应用/恢复。1000 库重新进入核验为 7326/7684/7242 ms。最终冷启动的真实 [XML](evidence/root-final-anr-37171895602.xml) 显示 “System UI isn't responding”，[lastanr](evidence/root-final-anr-37171895602.txt) 为本启动无 ANR 记录；该步不是 App PASS，也不证明上一轮目标 App ANR已修复。临时 Root 政策撤销、工作区为空、两个 AVD 回收。没有取消已有任务或跳过末尾检查。

## 第四批复测阻断与第六批：冷启动系统查询和 ANR 证据

下载并验真第四批 Root artifact `11292160094`，外层 SHA-256 `c09fb94f958654594200538ae3db3e1e9f897e5271648ea7471423b38d3d7620`；使用该运行固定的 `fe06c319` 判定器重新计算。[失败证明](ROOT_ANDROID_FAILURE_37169987413.json) 保留整体 FAIL/BLOCKED、5 面真实 CFF2 编译、14 次实际启动 ID、19 条挂载证明、32 个交接/18 个来源选择用例和 9 个实际轴 UI 帧。2 份新 tombstone 均绑定未改基线的失败注入任务；候选无意外原生崩溃。

1000 文件库重新进入核验为 8064/7002/7095 ms，库采样没有指纹超时；实际 App 应用、重启挂载及默认恢复重启均完成。随后最终冷启动抓到目标 App PID 3461 的焦点 ANR：`FocusEvent(hasFocus=true)` 等待 5014 ms，整体仍 BLOCKED。保存[原始 lastanr](evidence/root-final-anr-37169987413.txt)、[实际 ANR 界面 XML](evidence/root-final-anr-37169987413.xml)、[本次启动日志](evidence/root-final-startup-37169987413.txt)和[原始系统诊断节选](evidence/root-final-anr-runtime-37169987413.txt)。此次冷启动还出现一次 15870 ms、code 124 的指纹超时；不能把库采样的改善写成所有超时均消失。现有 harness 没有保留 `/data/anr` 线程栈，因此具体主线程阻塞点尚未证明。临时 Root 政策已撤销、任务空间为空，两个 AVD 已回收。

本批参考 [AOSP Android 15 PowerManager 源码](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-15.0.0_r1/core/java/android/os/PowerManager.java)（Apache-2.0，源码头许可证已核对）及 [Android 官方 ANR 诊断文档](https://developer.android.com/topic/performance/anrs/diagnose-and-fix-anrs)。源码显示 `isPowerSaveMode()` 使用属性缓存，缓存未命中时同步查询系统服务；不能宣称每次调用都有 Binder。

独立源码核对发现本 App 默认关闭高刷新率时，`onStart`/`onResume`/焦点回调仍先取省电状态，再检查是否需要请求模式。本批只将系统查询延迟到已启用、已恢复、已获焦点且非画中画/关闭中的窗口，保留省电优先、同分辨率及默认系统刷新率行为。新增两个 JVM 回归方法检查 5 种不合格窗口绝不调用系统查询，以及合格窗口只查询一次并尊重省电值；尚待本批新 CI，未把旧结果当作通过。这是可证明的无用启动工作，尚不能认定为上述 ANR 根因；没有复制上游源码。

验收脚本现已补齐 `lastanr` 的精确 `Reason:` 识别。上一轮原始报告在旧匹配器下为 false，新匹配器为 true；其他进程的 ANR 报告即使含目标 Activity 元数据，也不会被误归属。失败时优先按 [AOSP 官方栈诊断说明](https://source.android.com/docs/core/tests/debug/read-bug-reports#find-stack-traces) 保存 `/data/anr` 中精确目标进程块；最多 4 文件、每个 4 MiB，不导出其他进程线程栈，记录时间/PID/哈希/完整性，缺失明确标记不可用。栈只是某一时刻状态，仍须绑定 ANR 时间和 PID 才能分析原因，不将晚采集的 idle 状态当成根因。新增 11 个识别/采集回归，本次完整宿主 harness 105 个测试于 0.598 秒通过，仅证明脚本逻辑，尚待新 Android 执行。不点击 ANR 的“等待”、不扩大期限、不跳过最后实际 App 检查。

## 第七批：可重复的包和原始 Android 证据核验

采用理由：依据 [AOSP ANR 诊断](https://source.android.com/docs/core/tests/debug/read-bug-reports#find-stack-traces) 的进程归属、时间/PID 绑定及晚采集栈限制，把本轮已有的独立核验过程保存为 [可执行工具](../tests/reviewed-artifacts/README.md)，复用原判定器和挂载/轴选择 helper。除了报告布尔值，还读取真实 Root 阶段的原始日志与 Android XML，发现已记录的目标 ANR或仍存在的弹窗就拒绝通过；初次无 Root 的 App 阶段单独保留。没有复制上游实现，也没有新增 Android 操作、引擎或后台服务。

包核验绑定 GitHub artifact SHA-256、确切源码、模块内外 APK、9 个运行文件、17 冻结文件及旧引擎。Root 核验使用运行时固定 harness，复算实际启动 ID、CFF2 编译、原厂别名挂载、实际导入/UI 和回收；同时拒绝重复/格式错误的内核启动 ID。

[本地重放证明](ARTIFACT_VERIFIER_REPLAY_20261004.json) 标注 `HOST_ARTIFACT_REPLAY`：本轮第六批候选原包验真 PASS；错误的源码身份与 artifact 摘要分别被拒绝。第四批原包被拒绝，识别出 4 个含目标 ANR 的文件与 3 个弹窗 XML；第五批原包被拒绝，目标 ANR 文件为 0，仍有 3 个真实 System UI 弹窗 XML。重放不会变成新的 Android 测试结果，第六批实际 Root 任务继续执行。

## 不可越过的边界

不修改 1.1.1 挂载核心及 17 个冻结文件；不引入 hook、字体配置重写或后台常驻监听。
所有 Android 操作只针对 CI 的一次性模拟器，不操作用户设备、不增加权限、不合并、不发布。
原生 ARM64 真机、ColorOS/HyperOS 和真实字体库的体验仍需独立设备证据。

第六批代码提交 [`32674f9f`](https://github.com/xgl34222220-ops/LuoShu/commit/32674f9fd41fcbdec4347a40f4f0e816516d2979)，新候选构建 [37173590158](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37173590158) 已完整 PASS，含 App lint/JVM 单测/构建、新增两组高刷新率回归、原厂 CFF2 夹具和源码/补充门禁。下载 artifact `11292815996`，[独立包核验](TEST_CANDIDATE_VERIFICATION_37173590158.json) 通过：外层 ZIP `647d4944469555f740a50478080078dc3f9a13d4a92cc2b8a3e1196584085cb5`，模块 `fb40c6e54cd4145346e98322540d6fad28addc6293e1b7291fefe4ad8b9d50cf`，APK `a89a9891c91362ec0249c1f5cdfde99e9202481c30507a59811c8c61cc9529d1`；构建来源、内外 APK、9 个运行源码、17 个冻结文件和旧冻结引擎一致。Root workflow 绑定这个新包，使用本轮 105 个宿主 harness 测试及修正后的 ANR 观察；完整 Android 结果仍待新执行。

## 第六批完整 Android 结果与下一批入口

上述待执行状态已由 [完整 Root 37174455395](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37174455395) 的新结果取代：2026-10-04 04:17 UTC 完成，整体 PASS。artifact `11293323251` 外层 SHA-256 为 `c695160bbcaef14e7f83a371ab46833f951caec084617c924e9b23af5a181e73`，用第七批工具独立复算的[验收证明](ROOT_ANDROID_VERIFICATION_37174455395.json) 无 blocker。固定运行代码仍为 `32674f9f`，固定 harness 为 `26261083`；测试和文档提交没有被冒充为新运行包。

- 5 面原厂 CFF2 实际编译，输出 SHA-256 `b8c9cba7c6c48a27f5d5f7a16234dde55910cf35824ee5247411748d73ba6da9`；14 个实际内核启动 ID 唯一且变化，19 条规范路径挂载证明覆盖 2 个别名。
- 本轮 32 交接、18 来源选择、15 当前错误函数用例在原 ARM64 Python、Android shell、同一启动身份和 Enforcing 下通过；完整组合、App 单字体应用、重启挂载和系统默认恢复另行通过。
- 实际原生导入哈希一致，9 个真实轴 UI 帧通过，[最后轴 XML](evidence/root-axis-37174455395.xml) 和[原始日志](evidence/root-axis-37174455395.txt) 保留可见字宽/自定义轴和隐藏轴约束。此次只有 1 份新 tombstone，任务 `1791085467-7282` 对应未改基线的提交失败注入；候选无意外原生崩溃。
- 恢复重启后实际 App 冷/暖检查通过；原始 Root 阶段日志没有目标 App ANR，XML 没有阻断弹窗。无失败发生，因此 Android 的目标线程栈采集路径未实际触发；旧焦点 ANR 根因仍未证明。
- 临时 Root 政策撤销、任务空间为空、两个 AVD 已回收、KVM 元数据未变。本轮初次无 Root App 阶段由 `runner-lifecycle.json:stock_app_ui.result` 实际记录 PASS；此前轮次的 BLOCKED 仅留在其各自历史证明。

1000 文件库暖进入本轮为 6615/6809/6876 ms，首个真实库存帧为 554/500/525 ms。恢复后的最终冷核验为 **58385 ms**（含真实导航），暖核验为 7628 ms：[冷日志](evidence/root-final-cold-37174455395.txt)、[暖日志](evidence/root-final-warm-37174455395.txt)。冷日志有 `fingerprint duration_ms=12583 code=124`，后续重试为 9571 ms、code 0，刷新为 27256 ms、code 0；不能宣称超时均已消失或性能全部修复。下一批优先拆分这一有限请求的耗时并消除能证明的重复工作，保留现有验证、超时和回收门禁。

本轮通过范围仍为 AOSP API35 x86_64/nativebridge 上的原 ARM64 运行库。原生 ARM64/OEM 真机、App 完整组合创建 UI、像素几何、备份恢复 API、1000 份不同真实字体内容及基线 App 性能未验证。

## 第八批：普通库复核复用已核查模块索引与有限请求耗时

参考 [AndroidX 字体请求缓存源码](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/compose/ui/ui-text/src/commonMain/kotlin/androidx/compose/ui/text/font/FontFamilyResolver.kt) 及其 [Apache-2.0 许可证](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/LICENSE.txt)：复用与真实来源身份匹配的成功结果，避免重复加载。这里只借鉴原则，模块索引的当前目录指纹、双快照证明及 App 就绪判定仍是洛书独立契约，没有复制代码。另核对 [Python DirEntry 文档](https://docs.python.org/3/library/os.html#os.DirEntry.stat)，其 stat 结果有内部缓存；没有把源码中的两个 stat 调用猜成两次真实系统调用，也没有移除任何指纹身份字段。

具体差距：App 旧列表与当前指纹不同时，普通前台复核也传入 `refresh=true`，无条件重读字体头并写回索引，即便模块已通过其他操作取得同一当前索引。改为普通检查调用既有 `scan`；模块照常捕获当前目录、核对协议/版本/当前字体/指纹键，命中后仍用第二次实时快照核实。目录变化、权限丢失、无效缓存及不匹配的证明照常拒绝或重建；手动刷新继续强制 `refresh`，8 秒/60 秒命令预算和请求回收契约不变。

本轮新本地库存回归为 19 个、0.360 秒 PASS，含两项新增：1000 行命中不调用索引重建/缓存写回且确实取两次实时快照，以及两次快照之间变化必须拒绝且保留旧缓存。另有新 JVM 交叉层用例要求旧 App 列表只发 `fingerprint` 和 `scan`，消费同请求的新证明，并保持未核实状态直到成功；尚待本批 CI。

[本轮宿主操作比较](INVENTORY_CACHE_REUSE_HOST_20261004.json) 明确标注 `HOST_ONLY`：同一已有效的 1000 字体模块索引，5 次强制 refresh 调用重建 5 次/缓存写回 10 次，5 次 scan 均为 0/0；两者每请求均保留 2 次实时快照。中位数 52.754→32.576 ms 只证明宿主已有两条路径的工作差异，不能算作 Android 冷启动改善，更不能承诺消除第六轮超时。

依据 [Android 官方 ANR 诊断](https://developer.android.com/topic/performance/anrs/diagnose-and-fix-anrs) 对系统/应用工作区分的要求，隔离诊断版现在从既有 stderr 提取库存函数和有限请求总耗时，与 App 外层计时一起保留；最多两个固定阶段，数值/状态有界，绝不记录路径、字体 ID、token、PID 或任意错误消息。新增 3 个 JVM 回归覆盖带私人字段的实际协议、超时/未清理状态以及畸形/过长/非数值/错阶段输入；正式版仍关闭日志。尚无本批新 Android 数据，不把推测当成底层根因。

代码提交 [`cb321a66`](https://github.com/xgl34222220-ops/LuoShu/commit/cb321a6635733d09d726a35b66b7838813d85ce8)。`scope` 数字沿用现有监督器计时，包含 publish/worker/回收，不含其自身导入、参数解析和旧请求恢复；外层与 scope 的差值不能直接归因于单独某一层。库存函数计时也不包含 worker 的 Python 导入。没有新增解释器、修改回收器或把这些诊断当作目录/界面通过的替代品。

新 harness 增加 6 个数值证据负例方法，本轮 111 个宿主测试于 0.766 秒通过，后续最终状态检查重跑于 0.609 秒通过。新门禁要求 100/1000 库和恢复后的最终冷/暖共 14 个采样有当前、完整、成功回收的有限请求及一致计时；独立包复核再对照原始 App 日志。缺失、错阶段、旧采样、未完成、未清理、失败码和不可能的数值均不能充当通过证据。第六轮原始 artifact 用固定 `26261083` 重放仍为 PASS、初次无 Root 也为 PASS，新阶段采样为 0，明确只是历史重放而不是这批新 Android 结果。

[第八批新候选 CI 37177845100](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37177845100) 完整 PASS：App lint/JVM 单测/构建、源码/补充门禁和真实 Android 15 CFF2 夹具均通过。[CI 原始库存日志](evidence/candidate-inventory-37177845100.txt) 记录本批 19 个用例于 0.489 秒通过；该候选 CI 的旧版 harness 前置仍为 105 个，不能写成新 Root harness 的 111 个。未读取到完整 JVM 结果 XML，不编造总单测数。

artifact `11294395635` 下载后[独立包核验](TEST_CANDIDATE_VERIFICATION_37177845100.json) PASS：外层 ZIP `239cfa8dd4428f557c1ac444234e004587c84f015a73a183f83dc08a34828485`，模块 `50024470b5758bc76282fe970545752ed0564c849e2691ceec3c6acb2a50bb1c`，APK `07d2951dd0d858aa1d43fdcff3e35683e9413395e62f527ee188a9c4ab47a9c8`。确切 Git 源码、内外 APK、9 个运行文件、17 冻结文件及旧冻结引擎一致。新 Root workflow 现在只绑定这个新包；Android 阶段仍待实际执行。

验收提交 [`93b4075d`](https://github.com/xgl34222220-ops/LuoShu/commit/93b4075dcb24919579ca2af64ff6f96ad40fee48) 的[第八批完整 Root 37178617912](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37178617912) 已于 05:36:32 UTC 成功。下载 artifact `11294953144`，独立验证外层 SHA-256 `b393f36810e29cbbef8f290c3dc28c5d2bcc1c0c965c26cac8dae618ed1d3f46`，用本轮固定判定器重新计算 [Android 证明](ROOT_ANDROID_VERIFICATION_37178617912.json) 为 PASS。实际前置是 111 个宿主测试；Android 的 32 个交接、18 个预览来源、15 个当前组合错误用例均通过，5 面真实 CFF2 编译、14 次不同内核启动 ID、19 条规范挂载证明（2 个别名）、9 个实际轴 UI 帧、CLI 组合和 App 单字体应用/重启/默认恢复重新验证通过。

14 个实际冷/暖采样与本轮原始日志逐一匹配，保留 [数值证据](INVENTORY_ANDROID_TIMINGS_37178617912.json) 和 [最终冷](evidence/root-final-cold-37178617912.txt)/[最终暖](evidence/root-final-warm-37178617912.txt)、[1000 库冷](evidence/root-library1000-cold-37178617912.txt)/[1000 库暖](evidence/root-library1000-warm-37178617912.txt) 日志。1000 库暖复核为 5390/5649/5365 ms，首库存帧 449/440/436 ms；最终冷复核为 46785 ms（含实际导航），暖复核 8218 ms。所检查的所有 App 门禁原始请求没有非零退出码，Root 原始日志没有目标 ANR 或阻断弹窗；不将本次成功归因于尚未证明的旧 ANR/超时根因，也不当作真机速度保证。

最终冷扫描仍需 26871 ms：既有监督器计时 23274.124 ms，库存函数执行与 stdout 19096.482 ms。尚未拆分目录快照、头读取、缓存写入、输出等内部阶段，不能推断是其中某一项或据此直接并发扫描。2 份 tombstone 均由任务号绑定到未改的原版失败注入，候选无意外原生崩溃。初次无 Root 仅 App 启动检查 PASS；临时 Root 政策已撤销、工作空间为空、两个 AVD 已回收、KVM 元数据未变。

本批不覆盖原生 ARM64/OEM 真机、App 完整组合创建 UI、像素字形几何、备份恢复 API、1000 份不同真实字体内容或 Android 失败分支的线程栈采集。第九批 helper 改动不在本轮固定候选内，另跑门禁。

## 第九批：原厂扫描错误消息复用现有有界 JSON 解码

参考 [Font Manager JSON 源码及函数文档](https://github.com/FontManager/font-manager/blob/ff593362d69a893ce59897b0e01952d1f57654d5/lib/json/font-manager-json.c)、[项目文档](https://github.com/FontManager/font-manager/blob/ff593362d69a893ce59897b0e01952d1f57654d5/README.md) 和 [GPL-3.0 许可证](https://github.com/FontManager/font-manager/blob/ff593362d69a893ce59897b0e01952d1f57654d5/COPYING)。其结构化读取不会把转义引号当作字符串终点；洛书这个剩余路由仍用贪婪正则提取最后一行。只借鉴结构化读取原则，复用本项目既有解码器，没有复制 GPL 实现或引入字体资源。

[改前独立宿主复现](STOCK_ERROR_BEFORE_HOST_20261004.json) 绑定 `93b4075d`：实际 `stock_scan_json` 遇到带引号、反斜杠及中文的错误消息时只返回开头片段，退出 1。修复提取完整已捕获的扫描输出，用新的 `error-message-stdin` 入口调用同一解码逻辑。每次读 64 KiB，保留最多 256 KiB 尾部，消息仍上限 4096 字符并清理控制字符；不创建临时文件、任务或新的 stdin 租约。原 `error-message PATH` 含字面文件名 `-` 的调用保持有效，进程身份、发布、发现、回收等实现逐字节未变。成功路径、扫描锁、手动强制扫描、纯文本/缺失组件回退及切换核心路由保持既有行为。

本轮新宿主证据：

- [14 个当前错误函数用例](STOCK_ERROR_CONTRACT_HOST_20261004.json) PASS，包括引号/Unicode、嵌套与非字符串、控制字符、日志尾部、组件不可用、空错误，以及成功和缺失库存两种退出边界。明确是函数契约，不能代替完整原厂扫描或挂载验收。
- 新增 4 个管道回归后，完整消息/切换错误测试 14 个于 0.604 秒 PASS；实际 CLI 覆盖字面文件名兼容，2 MiB 噪声读取使用固定块且尾部/消息有界。共享解码器的当前组合错误 15 个重新 PASS；原厂扫描序列化/等待复用测试 PASS，17 个冻结文件匹配。
- 当前宿主真实进程回归仍 FAIL：[原始限制记录](STOCK_ERROR_HOST_PROCESS_LIMIT_20261004.json) 保留 task_scope 20 个中 12 失败/2 错误及有限请求 5 失败。只读比较发现 `os.getpid()` 与 `/proc/self` 指向不同 PID，未改版本和工作版读取到同样错误视图；不能通过降低身份检查或跳过门禁“修复”这一宿主环境。正常新 CI 与隔离 Android 的进程门禁仍必须重新通过。

代码提交 [`634a6d45`](https://github.com/xgl34222220-ops/LuoShu/commit/634a6d45dae07e59fc73ffb36725b98e2dcee080) 的 [第九批新候选 CI 37180012702](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37180012702) 完整 PASS，含 App lint/JVM/构建、源码/补充门禁、原厂 CFF2 夹具和包校验。[本轮原始 CI 日志节选](evidence/candidate-stock-process-37180012702.txt) 保留 14 个扫描错误用例、14 个消息回归，以及在正常 Linux 上重新通过的真实 `task_scope` 20 个（24.667 秒）和有限请求 5 个（9.557 秒）；强制发布前检查再次通过。候选 CI 的前置 harness 为 111 个，不能写成尚未上传的新 harness 113 个；不编造 JVM 总测试数。新的 CI 进程 PASS 不改写上面的本地环境失败。

下载 artifact `11295201887` 后 [独立包核验](TEST_CANDIDATE_VERIFICATION_37180012702.json) PASS：外层 ZIP `5b448894e42c1628c3fe69035fe6088d6bd7e9e69433c59458773de79ce2a0ed`，模块 `99180db7357c0035b6baa60fec2ef6a667106adb89e05aabaf2b3329a4514882`，APK `1eb859a22d3b428c46b0e590972e8a6c7fe21f3a9c35dcab074b77f9fa9cc6a7`。10 个运行文件、来源/内外 APK、17 个冻结文件及旧冻结引擎逐项一致。

新 Root workflow 只绑定这个已验真的包，新增实际安装模块下的 14 个扫描错误函数用例，要求原 ARM64 Python、Android shell、同一内核启动 ID、Enforcing 及正确 helper 哈希。判定器拒绝错环境、缺失/重复/失败用例；独立 verifier 进一步核对真实命令 stdout 与 Git helper 字节。新宿主 harness 113 个于 0.638 秒 PASS，仅证明脚本与判定逻辑；完整 Android 结果仍待本次新运行。第八批固定候选的 PASS 保留为该批证据，不替代第九批验收。

验收提交 [`b108bf8d`](https://github.com/xgl34222220-ops/LuoShu/commit/b108bf8d5f95b5136564dfb7e56b23fbd04daf50) 的 [第九批完整 Root 37181343923](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37181343923) 已于 06:28 UTC 结束 FAIL。实际原 ARM64 错误函数的 `bounded-log-tail`（300 KiB 前缀）触发 `/system/bin/printf: Argument list too long`，无法把捕获日志送进 decoder；输出错误消息为空，命令退出 1。本轮不称为 14 个通过，也没有到达 Root App 轴/库/应用/最终冷暖阶段。下面第十一批按这条新失败修复，不改写第八批的独立 PASS 或取消第十批固定任务。

## 第十批：有限库存请求的内部阶段与实际工作计数

具体差距：第八批恢复后的最终冷扫描函数及 stdout 耗时 19096.482 ms，但日志不能区别目录读取、索引命中、字体核查、二次验证、持久化或输出。参考 [AOSP Android 15 Trace 源码](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-15.0.0_r1/core/java/android/os/Trace.java)（源码头 [Apache-2.0 许可证](https://www.apache.org/licenses/LICENSE-2.0) 已核对）及 [Android 官方自定义阶段文档](https://developer.android.com/topic/performance/tracing/custom-events)，采用命名边界、成对完成的阶段原则。这里独立实现单进程 monotonic/finally 计时，没有复制源码、接入系统 trace、修改 profileable 或引入权限。

原有限 worker 只增加七个固定阶段：storage、首目录 snapshot、cache 读取、build（配置/头/行构造）、verify（二次快照及当前证明）、write（序列化、fsync 和重命名）、output（序列化和 stdout flush）。记录缓存命中与尝试快照/重建/写入次数，异常仍完成本段计时并保留失败码；次数不代表操作成功，也不能取得就绪权。stdout JSON、排序/指纹身份、两次快照、原子写入、所有预算和进程回收未变，计时不含 Python 导入/参数解析，也不含少量阶段间调度/当前配置键生成。

App 隔离诊断版仅导出固定数值字段，单行不超过 2048 字符，每请求最多三组，拒绝私有尾部、错阶段、过界耗时/次数、非数值和坏退出码；正式版本仍不开 App 诊断日志。新增两项 JVM 回归尚待新 CI。

本轮库存回归 23 个于 0.617 秒 PASS，新增四项覆盖新建/复用且证明相同、失败后二次验证计时完整且旧缓存保留、实际 CLI 数值/路径隐私/阶段总和、失败快照不得伪造成工作成功。17 个冻结文件重新匹配。[当前宿主 1000 文件阶段证据](INVENTORY_SUBPHASE_HOST_20261004.json) 标记 HOST_ONLY 和人工头部夹具；refresh 的两次快照/一次重建/两次写入，与 scan 的两次快照/零重建/零写入分开记录，不能称为 Android 提速或真实字体内容覆盖。新候选 CI 与带阶段证据的 Android 复测仍需实际运行。

提交 [`5194e3c4`](https://github.com/xgl34222220-ops/LuoShu/commit/5194e3c4aac878a19098bb2be10a05940b86260a) 的 [第十批新候选 CI 37181760478](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37181760478) 完整 PASS，App lint/JVM/构建、源码/补充门禁、真实 Android 15 CFF2 夹具和包检查全部成功。[CI 原始节选](evidence/candidate-inventory-subphases-37181760478.txt) 的当前库存 23 个于 0.402 秒通过，真实进程 20 个于 23.821 秒、有限请求 5 个于 9.354 秒通过，强制发布前检查再跑通过。候选 CI 前置仍为旧 113 个 harness 测试，不把工作区新 118 个当成该 CI 结果，也不填未知 JVM 总数。

下载 artifact `11295571904`，[独立核验](TEST_CANDIDATE_VERIFICATION_37181760478.json) PASS：外层 ZIP `32c3dbe10bad56ba94d5fa93700ce89e392c7b6083f69c47b686ccb7397abfc6`、模块 `e271b52d6210b937bae6e9bffcda2a4974414eee8c42bfe1ffe5d2d8c8fc2ff4`、APK `d43941f0a519454c0d64837792e0b826f60351fefecc2f2a6b31b632a1580dce`，11 个运行文件（包括新库存 worker）、17 冻结文件、旧引擎、内外 APK 与来源一致。另用已验真第九批包制作临时已知坏夹具，只改 worker 并更新模块摘要使检查确实进入源码身份比较；[源码负例](INVENTORY_SOURCE_GUARD_HOST_20261004.json) 明确被拒且未写 PASS。这是 HOST_ARTIFACT_MUTATION_TEST，不是 Android 验收。原包逐字节保留。

新 harness 要求全部 14 个当前冷/暖采样取得固定阶段；每条成功的 live fingerprint/scan/refresh 都必须有一致的阶段总和及正确工作次数。指纹成功不能掩盖缺少明细的成功 scan；失败请求原样保留且仍必须随后成功，缓存命中仍须两次快照且零重建/写入。五个新增解析/判定负例方法后本轮宿主 118 个于 0.633 秒 PASS。独立 verifier 继续按实际原始 App 日志重算。新的完整 Root workflow 仅绑定本批新包；第九批任务继续使用其固定旧包及判定器，concurrency 不取消运行任务，本批将按同组队列接续。阶段采样尚不是新 Android 结果。

验收提交 [`e1b2748f`](https://github.com/xgl34222220-ops/LuoShu/commit/e1b2748f674a8b6092c65144d82e67d45363c380) 的 [第十批 Root 37182379231](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37182379231) 已接续进入完整 Android 步骤，固定 `5194e3c4` 候选；它尚未包含下面的修正。正在跟进，不能以旧结果填写阶段数据。

## 第十一批：按实际 Android 失败修复大日志的参数传递

第九批 artifact `11296120669` 已下载并校验外层 `dd81556305e20f2a169a146ae53017d2f55b5f6f7db1b00b0f76de46b0962709`。保留 [实际错误 stderr](evidence/root-stock-error-37181343923.txt) 和 [独立失败证明](ROOT_ANDROID_FAILURE_37181343923.json)：12 个实际内核重启 ID、16 条可重算挂载证明/2 别名、5 面真实 CFF2 和 CLI 组合完成；32 交接/18 来源/15 组合错误的命令与 stdout 一致。候选无意外原生 tombstone，两个 AVD 已回收、KVM 元数据未变。初次无 Root App 遇 System UI ANR，明确 BLOCKED；Root App 后续未到达，没有授予 App 的 Root 政策。最终任务空间检查也未到达，不能填空目录 PASS。

采用理由：Linux 对 execve 的单参数长度有限制，而宿主 dash 的 `printf` 为内建，之前宿主用例未进入这个限制。核对 [Linux v6.6 定义源码](https://github.com/torvalds/linux/blob/v6.6/include/uapi/linux/binfmts.h)、[COPYING / GPL-2.0 WITH Linux-syscall-note](https://github.com/torvalds/linux/blob/v6.6/COPYING) 和 [execve 项目手册](https://man7.org/linux/man-pages/man2/execve.2.html)，只借鉴参数与数据分离原则，没有复制内核实现。限制与页大小有关，不宣称所有 Android 设备都有同一字节阈值，也不修改内核或资源限制。

原厂扫描的末行读取、锁等待复用输出和错误解码改为 here-document stdin 重定向，避免把整段日志作为外部 `printf` 参数。变量内容只展开为数据，保留 shell-looking 文本和分隔符行；仍在已完成扫描后使用相同 bounded decoder，不建立项目日志文件、任务或调用方 stdin 租约，shell 可使用其自身临时描述符。helper 文件和进程监督实现与 `e1b2748f` 字节一致；成功/返回码/锁/核心委托、17 冻结文件未变。本批仅覆盖这条有结构化尾部的大日志失败，不能据此宣称所有异常原始日志及解释器缺失情形都已穷尽。

宿主 fixture 现在强制调用真实 `/usr/bin/printf`，不伪造 E2BIG；Android 保留原 shell。[改前宿主复现](STOCK_ERROR_ARGV_BEFORE_HOST_20261004.json) 在同一 `bounded-log-tail` 失败；[改后 14 个函数用例](STOCK_ERROR_EXTERNAL_PRINTF_HOST_20261004.json) PASS，保留 300 KiB 长度，并增强 `$()`/变量/反引号与同名 delimiter 的字面数据检查。原厂扫描锁/等待复用、17 文件边界重新 PASS，宿主 harness 118 个于 0.640 秒 PASS；不把这些当 Android 成功。

独立 Root verifier 对已知早期失败、尚无后续 App 文件的 artifact 现在写出 FAIL/缺失范围及已独立检查的部分证据，仍拒绝不完整验收。实际第九批重放保持 FAIL；第八批固定 `93b4075d` 历史重放仍 PASS，不能替本批新 Android 结果。新的候选 CI 和完整 Root 修复验收尚待执行。

修正提交 [`57aa02ed`](https://github.com/xgl34222220-ops/LuoShu/commit/57aa02ed950a50d054cb1596021a51df0349d0d8) 的 [新候选 CI 37183661227](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37183661227) 已完整 PASS。[当前原始 CI 节选](evidence/candidate-stock-argv-37183661227.txt) 记录真实外部 printf 模式的 14 个函数用例、当前库存 23 个（0.662 秒）、正常 Linux 真实进程 20 个（24.689 秒）、有限请求 5 个（9.552 秒）及新 harness 118 个（0.455 秒）通过。强制构建前进程与有限请求再次通过；App lint/JVM/构建和原厂 CFF2 夹具也通过，不编造未读取的 JVM 总数。

artifact `11295993991` 下载后 [独立包核验](TEST_CANDIDATE_VERIFICATION_37183661227.json) PASS：外层 ZIP `5cd8d606bab34ed41a93d97c781b24b2263a612ad4a6e29e4246f3a0e05b3cac`，模块 `3da0ffbdc27b550d9c4468a5157a2f07257e9e3927288d94c5bce37b0cf62004`，APK `73ba5a1bf845fa8efa99a4e123490a522fa47b75829728b8e8e2c27a2d1015bf`。11 个运行源码、来源、内外 APK、17 个冻结文件和旧冻结引擎一致。新 Root workflow 只绑定这个实际修正包，仍要求全部既定门禁。

先前已运行的 [第十次 Root 37182379231](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37182379231) 于 06:58 UTC 结束 FAIL。固定旧包 `5194e3c4` 的 300 KiB 用例再次报同一外部 printf 错误，保留 [新原始 stderr](evidence/root-stock-error-37182379231.txt) 和 [独立失败证明](ROOT_ANDROID_FAILURE_37182379231.json)。本次实际 12 个内核重启、16 条规范挂载证明/2 别名、5 面 CFF2/CLI 组合及 32/18/15 函数用例完成，后续 Root App 和内部阶段采样没有到达；初次无 Root App 因 System UI ANR 为 BLOCKED。两个 AVD 已回收、KVM 元数据未变，不能把缺失阶段或最终工作空间检查填 PASS。

同时补齐独立 verifier 的 32 交接报告与原 ARM64 命令 stdout 完整对照，沿用第七批保留原始证据的原则。[已知篡改夹具](HANDOFF_STDOUT_GUARD_HOST_20261004.json) 仅把报告 elapsed_seconds 加 1、实际 stdout 不动；旧 verifier 错误接受，新 guard 明确拒绝。未改第八批 artifact 固定判定器重放仍 PASS。这是宿主证据校验器负例，不是新 Android 执行。第十一批完整 Android 修复与七阶段采样仍待新任务实际完成。

验收提交 [`f7917b7c`](https://github.com/xgl34222220-ops/LuoShu/commit/f7917b7c7818b63d7147e215a9979d4e01eca009) 已触发 [第十一轮完整 Root 37184908266](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37184908266)，固定修正源码 `57aa02ed` 和验真包，原任务没有取消。该提交前新宿主 harness 118 个于 0.663 秒 PASS；这不是正在运行的 Android 结果。

## 第十二批：补齐 App 实际组合生成、重启挂载和恢复入口

具体差距：已有完整门禁验证了 CLI 组合生成和 App 单字体应用，App 组合界面只完成了只读轴检查，没有通过真实“生成并应用”入口创建组合。不能据此称 App 全部组合功能已验收。参考 [AndroidX UI Automator 源码](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/test/uiautomator/uiautomator/src/main/java/androidx/test/uiautomator/UiObject2.java)、同提交的 [Apache-2.0 许可证](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/LICENSE.txt) 及 [Android 官方 UI 测试文档](https://developer.android.com/training/testing/other-components/ui-automator)，采用真实 package/槽位/文字身份、条件等待和原始截图/层次证据。没有复制实现、升级库、接入 instrumentation 或增加权限；继续使用已有 ADB/UI Automator 与隔离 AVD。

新门禁从原始合成字体的实际库存选择中文、英文、数字三个槽位，选择不同的中文与英文字体以确保进入组合路径，点击真实“生成并应用”。只读轮询必须取得不同于旧任务、来源匹配且属于当前内核启动的新父任务；App 点击失败没有 CLI 启动兜底。随后共享原来那一份组合门禁，继续检验后台 monitor 完成、5 面真实可变 CFF2 集合、实际 fd 锁与并发幂等提交、工作区/sidecar 回收、未重启前 live 字节不变、实际重启挂载和系统默认恢复。还要求 App 的当前 PID 显示对应成功消息/100% 并保存实际截图，再进入重启。旧 CLI 入口判定不放宽，没有新生成引擎。

本批 App 数字槽选择第三个实际夹具 ID，区别于前面 CLI 的组合方案，避免把合法的旧方案复用误当成本次新生成；原方案复用语义没有修改。所有文件仍只有此前两种原始合成字体内容，不扩大为真实字体库覆盖。

独立 verifier 新增实际选择/操作/完成 XML、截图摘要、ADB PID stdout 和新任务原始 cat stdout 的对照；完整新门禁至少要求 16 个不同内核重启与 7 组实际挂载视图。历史固定 harness 仍用其自身 14 次/6 组契约，不能把历史结果写成新 App 组合结果。Miuix/Material 产品代码、候选 `57aa02ed`、17 冻结文件、hook/权限边界全未改；第十一轮仍用其固定验收提交继续运行，本批另在同一原分支排队。

[当前宿主证明](APP_COMPOSITE_GUARDS_HOST_20261004.json) 与 [原始测试输出](evidence/app-composite-harness-host-20261004.txt) 标记 HOST_SYNTHETIC_HARNESS_TESTS：新增 8 个方法后总 126 个 PASS，覆盖错误 package/重复或禁用控件、槽位外同名字体、直接应用/CLI 替代、旧任务/错来源/换启动或 PID、错误成功文字、伪造原始帧及失败后 CLI 兜底等拒绝条件。原始第八批用固定 `93b4075d` 重放仍 PASS，仅证明历史判定兼容。新 App 完整组合的 Android 结果尚未取得；截图与像素几何、原生 ARM64/OEM 真机、备份恢复 API 和不同真实字体库的未验证项保留。

验收提交 [`e2dd5b16`](https://github.com/xgl34222220-ops/LuoShu/commit/e2dd5b16eb53380536dc926b98994760f115ef2b) 的 [第十二轮 Root 37185796564](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37185796564) 已于第十一轮结束后接续运行，固定同一修正候选。当前没有该轮 Android 完成结果；原任务继续跟进。

## 第十三批：按本轮原始 XML 修复轴验收的异步载入时序

第十一轮于 07:43 UTC 结束 **FAIL**。下载 artifact `11296349946`，独立验证外层摘要 `51b608498ecc5231033136a7e3734c278f8fa037a386f5fa722fb0b6987a0f4d`。[新失败证明](ROOT_ANDROID_FAILURE_37184908266.json) 保留本次 12 个实际内核重启、16 条规范挂载证明/2 别名、5 面真实 CFF2/CLI 组合通过与后续缺失范围。长日志修正在原 ARM64/Android shell 上实际通过全部 [14 个扫描错误函数用例](evidence/root-stock-error-37184908266.json)，包括 300 KiB、shell-looking 字面数据和同名 delimiter。32 交接/18 来源/15 当前组合错误也重新通过；并非沿用宿主或旧 Android 数字。安装 APK 已绑定新包，候选无意外原生 tombstone，App 临时政策已撤销、工作区为空、两个 AVD 回收、KVM 元数据未变，初次无 Root App 独立检查为 PASS。

新的 blocker 为 `original-axis-fixture-row` 没有找到实际字体行。[失效点记录](AXIS_NAVIGATION_FAILURE_37184908266.json) 和 [载入前 XML](evidence/root-axis-loading-37184908266.xml)/[随后 XML](evidence/root-axis-loaded-37184908266.xml) 与真实 input 命令显示：脚本从占位框 `[95,1101][985,1227]` 取到点击点 `(540,1164)`；随后框变为 `[95,1179][985,1359]`，旧点击点落在其上方，选择器未打开。这个相邻帧观察符合异步载入使坐标失效；没有捕获精确点击瞬间的帧，不把推断写成目标 App ANR 的根因。实际失败诊断读取了 4 份有界系统 ANR 文件，没有找到目标 App 栈，结果 NOT_AVAILABLE；库存采样、App 应用及最终验收未到达。

采用理由：上批 [AndroidX UI Automator 源码](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/test/uiautomator/uiautomator/src/main/java/androidx/test/uiautomator/UiObject2.java)/[Apache-2.0](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/LICENSE.txt) 的条件等待，以及 [官方文档](https://developer.android.com/training/testing/other-components/ui-automator) 对“稳定层次并不代表后台任务完成”的区分，适用于这个真实失败。脚本先复用已有实际 App 库门禁，要求当前导入夹具的冷/暖实时核查、正确数量、完整数值阶段和请求回收；保持同一已就绪 App 进程进入组合页面，不再重新冷启到占位状态。没有把固定睡眠、CLI 校验或旧缓存当作 UI 就绪，也不增加预算、改产品界面或授予新权限。

独立 verifier 对新增的 2 个轴准备采样按原始日志重算，并与实际阶段 JSON 和轴 App PID 一致；原来 14 个 100/1000/最终采样继续独立要求，不能合并成新的性能样本数。新 [宿主负例证明](AXIS_PREFLIGHT_GUARDS_HOST_20261004.json) 和 [原始输出](evidence/axis-preflight-harness-host-20261004.txt) 标记 HOST_SYNTHETIC_AND_RAW_XML_REPLAY：2 个新增方法后总 128 个 PASS，覆盖这次真实 XML 的旧坐标失效，以及未核实、失败、过期、换 PID、缺少内部阶段的准备请求不得通过。17 冻结文件匹配。第十二轮仍用其固定旧脚本运行；本批将接续同一原分支和验真候选进行完整门禁，Android 结果尚待实际执行。

修正提交 [`6afbb02a`](https://github.com/xgl34222220-ops/LuoShu/commit/6afbb02a38e4cbbf630d451e7496e301b0801486) 的 [第十三轮 Root 37187408273](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37187408273) 已于第十二轮结束后接续进入完整 Android 步骤，仍固定候选 `57aa02ed`。当前任务继续运行，下一批库存输出修正尚不在此固定包中。

## 第十四批：按实际大库存失败修复兼容列表的 stdout 传递

第十二轮于 08:14 UTC 结束 **FAIL**。下载 artifact `11297922610` 并独立核验外层 `6f29a22dbe939f7278a2990e2aacbad164209eae8f8fa6f11714ffd97dc31cf2`，[新失败证明](ROOT_ANDROID_FAILURE_37185796564.json) 记录本次 14 个实际内核重启、5 面真实 CFF2/CLI 组合、9 个实际轴帧、100/1000 库各 6 个当前采样，以及 App 单字体应用/重启/默认恢复完成。12 个性能采样及原始七阶段日志独立一致；尚无最终冷/暖两项，App 完整组合未进入，整体不能填 PASS。

新的 [真实失败命令](evidence/root-inventory-output-37185796564.json) 为 `app_bridge.sh fonts scan`：原 ARM64 worker 成功生成 1000 行，函数耗时 8485.100 ms，snapshot/verify 合计约 1584.144 ms、build 6784.336 ms、write 40.470 ms、output 25.002 ms，尝试计数为 2/1/2。随后 `font_manager.sh` 的兼容 list 路由把全部 JSON 放进外部 printf 的一个参数，报 `Argument list too long`；stdout 为空而后端原退出码仍为 0。它不是扫描失败或缺少权限。前面的 App 有限库存调用走已有直接 worker 路径，不能替这个兼容路由通过。上述只有本次失败命令的阶段观察，不是全门禁成功或跨轮提速结论。

参考第十一批已核对的 [Linux exec 参数定义](https://github.com/torvalds/linux/blob/v6.6/include/uapi/linux/binfmts.h)、[COPYING / GPL-2.0 WITH Linux-syscall-note](https://github.com/torvalds/linux/blob/v6.6/COPYING) 和 [execve 项目手册](https://man7.org/linux/man-pages/man2/execve.2.html)，同样采用 stdin 数据通道，独立实现并不复制上游代码。仅把既有 nativeAvailable 的固定替换器改为 here-document stdin，保留后端内容、该布尔转换和返回码；没有改库存格式/双快照/扫描次数/预算、监督器、界面或核心委托。

[改前真实外部 printf 宿主复现](INVENTORY_OUTPUT_BEFORE_HOST_20261004.json) 绑定 `57aa02ed`，实际 1000 行用例复现空 stdout/E2BIG。[改后 5 个函数传输用例](INVENTORY_OUTPUT_CONTRACT_HOST_20261004.json) PASS：332948 字节、1000 行含中文/引号/shell-looking 字面数据的列表完整，307262 字节后端错误仍退出 7，组件不可用时仍直接委托，空后端失败保留其既有状态。明确仅测试原 list 路由，不能冒充完整扫描/挂载。新 CI 会用同样真实外部 printf 模式重跑。当前库存 23 个于 0.686 秒 PASS，原扫描错误 14 个、扫描锁/等待复用、17 冻结文件重新通过；实际 Android 的 5 个传输用例和完整 App 组合须用新候选另跑，不取消仍在运行的第十三轮。

## 第十五批：把大库存传输修正纳入真实 Android 必过门禁

参考上批已核对的 [Linux execve 参数定义与许可证](https://github.com/torvalds/linux/blob/v6.6/include/uapi/linux/binfmts.h)，以及 [AndroidX UI Automator 的实际节点与条件判定](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/test/uiautomator/uiautomator/src/main/java/androidx/test/uiautomator/UiObject2.java)/[Apache-2.0](https://github.com/androidx/androidx/blob/11ece46a49d485c7644e53cb0684a611d7a0ec10/LICENSE.txt)，采用理由是这次失败发生在真实 shell 数据通道，宿主结果不能代表 Android；独立编写门禁，不复制上游实现。

原安装模块的 list 路由在原 ARM64 Python 与 `/system/bin/sh` 上重跑 5 个函数传输夹具。报告要求同一 Enforcing 启动、安装路由 SHA、完整唯一用例、固定夹具字节数与后端退出码。独立 verifier 进一步核对原始命令 stdout、精确模块/shell 参数和审阅源码 SHA；报告打印 PASS、空输出、旧来源或重复制品都不能通过。该检查仍只覆盖兼容路由；完整库存、16 个实际模块重启、7 组挂载视图、App 组合 UI 和 14 个当前性能观察继续分别强制要求。缺失 App 组合证据现在准确标记 App 缺失，避免把已经通过的 CLI 组合混为失败。

[本次宿主负例证明](INVENTORY_OUTPUT_GUARDS_HOST_20261004.json) 与 [原始输出](evidence/inventory-output-harness-host-20261004.txt) 为 HOST_SYNTHETIC_HARNESS_TESTS：新增 3 个方法后总 131 个，0.657 秒 PASS，17 冻结文件再次匹配。固定 `93b4075d` 的第八轮历史 artifact 用当前 verifier 重放仍 PASS，新增输出门禁字段为空，仅证明固定历史契约兼容，不取得本批 Android 覆盖。新 Android 与完整 App 组合尚待新候选执行。

修正提交 [`a70b19c8`](https://github.com/xgl34222220-ops/LuoShu/commit/a70b19c89a0c8daf21d724d10201915fda7eafc8) 的 [本轮候选 CI 37189036319](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37189036319) 已完整 PASS。[原始新 CI 节选](evidence/candidate-inventory-output-37189036319.txt) 包含 5 个真实外部 printf 模式的传输用例、当前库存 23 个（0.431 秒）、正常 Linux 真实进程 20 个（24.011 秒）、有限请求 5 个（9.361 秒）及构建时原 harness 128 个（0.334 秒）通过；打包前重复要求也通过。App lint/JVM/构建和原厂 CFF2 夹具门禁通过，不编造未读取的 JVM 总数。

下载 artifact `11298680369` 后 [独立包核验](TEST_CANDIDATE_VERIFICATION_37189036319.json) PASS：外层 ZIP `114797201b8e51c6fd6f9fcbc108b7ddbfb69ebe3df0d0a5c3950e08b58cca25`、模块 `f8e357c0b4ad0f47c2ed1f078e5e89f522d934fed2d858fc5689001ba41f86d3`、APK `72fd36d03d7c548356e20bb0bc358e7c25ab5257d9397b1928062313c6793356`。11 个运行源码、内外 APK、来源、17 冻结文件和旧引擎一致。完整 Root workflow 只绑定这份审阅修正包；不跳过任一新旧必过门禁，第十三轮仍按其旧 pin 跟进。
