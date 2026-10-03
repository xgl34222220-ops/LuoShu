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

同一 64 MiB 原创 SFNT（含大尾部区域）的 `tracemalloc` 测量：旧读取器分配峰值 `67,114,265` 字节，新读取器 `16,938` 字节，两者均正确读出 2 个轴。该数据是此读取路径的宿主 Python 分配峰值，不是 Android 整机 RSS、延迟或真机结果。

仍沿用集合面 0 的轴描述策略；异构集合的按角色选面界面一致性不在本批宣称已解决。

第二批提交 [`17783f22`](https://github.com/xgl34222220-ops/LuoShu/commit/17783f2229e8ecb946bbd280a7c6343292e296da) 的 [完整候选 CI 37157991533](https://github.com/xgl34222220-ops/LuoShu/actions/runs/37157991533) 已成功，包含上述新增 App 单测。
下载本轮 artifact `11286956067` 独立校验：外层 ZIP SHA-256 `c53aa732931955f8c0c81b104935e77756f7c895904542f1ddca5dd95a2397ad`；模块 `a56a54ea9618946f8a96cf9e3d91fea751f72f1aa9d318842e6865ad5b9b957c`；APK `a929619682dca646c1a2486ec42a0813de595e9be93c4f5571faa70c0a69a8e5`。
已对 17 个冻结文件、6 个运行源码、模块内外 APK 字节、构建来源和校验文件逐一核对。

## 本轮隔离 Android 验收的新增门禁

Root workflow 只绑定上述已通过、已下载验真的候选包。新增门禁包括：

- 同一套 32 个交接/UTF-8/进度用例，用原 ARM64 Python 和 Android shell/toybox 在 Magisk/SELinux Enforcing 环境重新运行。
- 真实 Android CFF2 集合的轴名称、范围、默认值及隐藏标志读取。
- 只用项目原创几何字体构造无字重轴的可变字体，实际在 App 中文基底选择器选择它；检查“可变字体”、字体声明的“纹理细节”/`XTRA`、隐藏轴未曝光，保存新 UI XML 与实际截图，并确认系统字体哈希不变。
- 判定器拒绝 HOST_ONLY、缺失/重复用例、缺失名称、错误范围、隐藏轴曝光和不完整的 App 实际证据。

本轮新增后，宿主 Root harness 的 85 个测试通过。这里只是脚本/判定器回归；实际 Android 成败须等本轮运行完成，尚未预填成功。

## 不可越过的边界

不修改 1.1.1 挂载核心及 17 个冻结文件；不引入 hook、字体配置重写或后台常驻监听。
所有 Android 操作只针对 CI 的一次性模拟器，不操作用户设备、不增加权限、不合并、不发布。
原生 ARM64 真机、ColorOS/HyperOS 和真实字体库的体验仍需独立设备证据。
