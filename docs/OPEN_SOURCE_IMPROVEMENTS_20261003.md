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
