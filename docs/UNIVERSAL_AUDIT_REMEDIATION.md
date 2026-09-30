# Universal 引擎审计修复清单

基准：56c77c98470df51d059ac8a5d5377a5d8defd9f6（2026-09-30）。
本清单记录可复现缺陷与验证，不把宿主回归或CI构建等同所有ROM真机认证。
用户原始字体和设备诊断不作为仓库fixture；回归使用自造字体、最小拓扑和受控模拟。

| ID | 失败反例 | 修复/验证状态 |
|---|---|---|
| LC1 | 实际dynamic-mounts.conf及额外partition文件不受冻结manifest约束 | 已修复；执行树/动态conf与密封manifest精确一致，未声明文件拒绝；LifecycleTests.test_sealed_execution_set |
| LC2 | nextboot helper污染调用者backup变量，失败恢复遗失legacy状态 | 已修复；隔离helper局部命名，故障恢复旧负载与legacy标记；test_activation_write_failure_restores_legacy_mode |
| LC3 | 自动回滚复制期间，新请求stage被旧回滚覆盖 | 已修复；内核提交锁+身份核对，真实并发新提交胜出、进程死亡释放；test_rollback_concurrent_new_commit_wins / test_commit_lease_crash_nested_and_background |
| LC4 | verifier子进程失败却沿用旧PASS，删除retired回滚材料 | 已修复；本次rc/boot/deployment/hash一致才采纳PASS；test_failed_verifier_cannot_reuse_pass_or_release_recovery |
| LC5 | default仅排队却提前显示已生效 | 已修复；后端pending优先、App标签不提前称default生效；test_default_pending_and_stale_boot_status / NativeFontFormatsTest |
| LC6 | 已挂载rw同hash被当作有效ro，挂载ownership不完整 | 已修复；RO、同boot归属及hash验证，第三方不收编；test_dynamic_rw_or_foreign_mount_is_rejected |
| D1 | 拓扑去重丢不同weight/lang/axis路由 | 已修复；精确路由图identity；DiscoveryPipelineTest.test_all_exact_weights_and_axis_nodes_survive_to_router |
| D2 | runtime发现的/data/fonts文件未变成可规划槽 | 已修复；权威动态配置/PS/face解析，identity贯通并密封；test_real_dynamic_config_flows_to_target_compiler_and_deployment；旧/歧义/被覆盖原厂证据仍拒绝 |
| D3 | wrapper继承属性使扫描器与路由器定位不一致 | 已修复；扫描与路由共享继承属性；test_inherited_wrapper_attributes_match_without_losing_semantics |
| D4 | 原始450字重被取整导致找不到XML节点 | 已修复；原始450独立路由，原始XML值保留；test_all_exact_weights_and_axis_nodes_survive_to_router |
| D5 | sans-serif-*分支判定不可达 | 已修复；正确识别sans-serif子族；test_condensed_ui_family_with_han_is_not_review_only |
| D6 | 未知主语言+ASCII覆盖被当作Latin | 已修复；未知主语言/脚本保护；test_language_refs_not_deduplicated_and_unknown_scripts_are_protected |
| C1 | 物理VF默认实例通过，但非默认轴轮廓越行框 | 已修复；全glyph有符号gvar/IUP保守区间，重开再验；SemanticCompilerTest.test_extreme_and_interior_vf_ink_rejected 等 |
| C2 | 导入glyf带CALL，却未携带来源fpgm依赖 | 已修复；外来glyf去hint、不替换OEM fpgm环境；test_foreign_hint_program_removed_without_replacing_oem_environment |
| C3 | 未替换的复合/共享glyph因替换依赖而间接变形 | 已修复；追加原始glyph克隆、重定向保护依赖，保留变化映射；test_nonselected_composites_keep_old_gvar_and_metric_dependencies / test_nonselected_shared_cmap_alias_is_isolated |
| C4 | GSUB非cmap字形/GPOS定位未同步几何变换 | 已修复已覆盖语义；GSUB闭包、glyph-local GPOS/点anchor；真实DejaVu/Noto不同探针变换后RAQM渲染；保留MATH与跨脚本shared marks，未支持布局明确拒绝 |
| E1 | App入口拒绝底层支持的WOFF/WOFF2/OTC | 已修复；统一入口/目录白名单与转换时间预算；native_font_formats_test真实WOFF/WOFF2解码、OTC混合轮廓拆面；Android设备操作待测 |

## 汇总验收门

1. 每条先保留最小失败反例，再验证修复后正例和负例；不能通过关闭全部功能宣布修复
2. 合并后统一运行检测、编译、生命周期、导入、App状态、原有回归；对同一提交构建和验证产物
3. 清楚记录未运行/环境阻塞项；ARM64包结构检查与宿主FontTools测试不能替代Android执行
4. 真机仍按TEST_MATRIX验证实际挂载、字体命中、字形/布局、图标/Emoji、完整重启、恢复/卸载
5. 保留显式部分覆盖与不支持状态；不使用routingComplete或任务success宣传所有系统全覆盖
6. 不更换正式签名、发布标签或更新feed。测试APK签名兼容问题不得通过要求卸载来规避

## 证据层级和未完成项

- 生命周期同一六条原反例在冻结56c77c9均失败，修复后通过；新增租约/动态generation/部分覆盖回归独立通过
- 检测、编译、原有混合及全部源码门禁由整合阶段统一重跑，以最终提交CI为准；本清单的“已修复”不等同最终成品或真机认证
- 有界内存/时间预算、未知字体角色、被覆盖原厂动态文件、复杂未支持布局仍可拒绝并给原因；没有删掉安全门来换绿勾
- MATH及跨文字共享标记保留会在report和UI明确部分覆盖，不能宣称全字形更换
- 原厂容器的固定选择轮廓不随OEM变量轴变化；普通多轴保留使用真实变化证明，两种语义不能混淆
- 测试App包名io.github.xgl34222220.luoshu.audit，名称“洛书·核心验收测试”；与旧App并排，不自动安装、升级或卸载旧App，私有设置/队列不自动迁移。字体目录及模块仍共用，需用户自行授予该App Root后测试
- 临时CI签名不保证后续同包更新；没有创建或替换正式签名密钥
- 仍须真实Android/Root后端、屏幕布局/时钟、完整重启和恢复/卸载验收。宿主RAQM渲染也不是Android证明

## 构建身份和缓存隔离补充

- 包装必须由 apkanalyzer 读取实际 APK package/versionCode，环境值仅可作为一致性期望；audit开关与实际.audit包名双向约束
- App缓存来源/预览/归档限定官方、debug、audit三个精确包的user0缓存；拒绝dot段、跨包路径及符号链接逃逸；不把解析后的任意目录当作新的信任根
- 测试候选强制宿主Brotli真实WOFF2转换及Pillow/RAQM真实字体渲染，依赖缺失不得静默跳过；补充候选门禁不再continue-on-error
- 新必需的拓扑、字形语义和提交锁代码增加压缩体积，ZIP上限由10.75MiB有界调整至11MiB，没有裁掉运行依赖换体积

## 独立复核记录

最终整合阶段独立复跑：发现14、编译语义17（强制RAQM）、生命周期9、逐路由9及ColorOS式固定组合完整管线通过。App包身份、手动安装策略、缓存隔离5例、预览隔离、原安装器及预览源回归通过。所有代码随后冻结，再跑同一提交的完整源码/App/打包CI；没有把上述宿主结果记作真机通过。

## 强制候选门禁发现的既有退出缺陷

R1：后台provider的TERM处理需要约1秒回收子树，但原task scope在0.6秒就SIGKILL整树，导致EXIT未能释放单例锁。修正为先给直接worker有界协作退出机会，再清理剩余子孙；总清理仍有界。新增重复启动、旧boot/PID复用、新token保护和TERM-ignore子孙测试。没有恢复continue-on-error绕过失败。

R2：31731dc 真机反馈暴露 mksh 的私有 FD 不随外部 exec 继承；真实 mksh R59 + Toybox 0.8.9 复现 `flock: flock: Bad file descriptor`、返回码1，原实现把错误误当竞争而等待。现在显式把同一打开文件描述映射到标准 FD0，native 失败后用 Python fcntl 的 errno 区分竞争与异常，异常立即停止。新增真实 mksh/Toybox、关闭 FD、fallback 失败及既有互斥/崩溃释放回归；仍非 Android ARM/SELinux 真机验收。module-only 构建固定复用已验证的31731dc APK，核对其 SHA256 和 App 源码未变，不重签也不要求用户重装 App。

R3：685411f 真机“通用准备超时后提交失败”对应嵌套 axes 与内层 monitor 双 finalizer，原 mkdir 锁20秒过期误报。嵌套请求改为 axes 唯一提交者，直接 fixed 保留 monitor；提交统一使用内核锁并在获锁后核对代次。真实 mksh/Toybox 完整超时→兼容生成→22秒慢提交反例由红转绿，取消不迟到提交且旧 pending 完整。另修取消监督器时1秒提前KILL与其3秒清理预算冲突，并对cleanup报告绑定PID/starttime/boot/task。独立复跑混合故障流程16项和进程树8项通过；保留660秒外层预算与180秒通用准备预算。

## 大组合字体性能与扫描档案（宿主证据）

- 固定组合的几何测量改为只实例化实际探针及组件闭包；成品仍保留完整字体，并独立回读验证。修复先替换轮廓再解码旧gvar导致不同点数IndexError的确定缺陷
- 单次请求内复用相同完整渲染结果，并有界缓存来源测量/边界（16MiB估算预算）与不可变供体glyf字节（32MiB估算预算）；不共享可变TTFont对象，不跨请求认领旧结果
- 相同2万汉字、35槽/23份原厂资产分布：基线339.96秒、峰值752.69MiB；优化69.27秒、峰值330.4MiB。两边35/35成功，全部35份输出SHA256相同
- 另测3.5万真实Han码位、每字48轮廓，合成源19,803,088字节、合成原厂VF27,316,780字节：35/35成功，152.50秒。该样本不是用户字体，也不是手机计时；此规模仍可能触发手机180秒准备预算。没有延长预算，兼容退路必须如实报告legacy
- 可复现命令见 `scripts/universal_fixed_batch_benchmark.py`；大样本非默认CI耗时门禁，小样本数值/产物等价测试进入源码门禁
- 扫描时保存每槽原始字节SHA、face、轴与度量、默认轴真实字形探针；可信升级时补齐旧档案。应用复用匹配的默认轴档案，其他轴或共享稀有汉字按需测量，不将当前替换字体回收为原厂
- 来源证明是当前内核挂载视图、只读ROM文件系统位置与字节身份核验，不是密码学OEM认证。合法同目录ROM符号链接可验证；无法证明的跨分区绝对链接明确受限，不猜测或套用其他ROM的偏移常量
- 初次升级补建档案可能增加一次扫描耗时；后续相同系统/字体代次复用。失败日志保留最后编译槽位与阶段，避免必须重跑才能诊断

### R4: scan-to-compile ROM view continuity

Device feedback for `bdc67d0` showed a fast preparation failure resolving
`/system/fonts/SysFont-Hant-Regular.ttf`, followed by successful legacy staging.
The log does not include mountinfo, so it does not establish the exact device
mount condition. Two independently reproduced implementation gaps are corrected:

- Scanning could recover a temporary non-recursive parent bind, seal the original
  SHA/face/geometry, and unmount that view. Compilation previously could not
  recreate it. One request-owned view now survives preflight and compilation.
- A clean installer namespace without a lower/mirror could be scanned, but its
  current path was excluded by the compiler's old opt-in flag. Current paths now
  require the same kernel ROM lineage proof and sealed SHA/face checks as other
  candidates. Replacement bind mounts still fail.

Eight focused tests cover scan cleanup followed by recovery and real font output,
changed bytes/face rejection, covering-directory rejection, exception/SIGTERM
cleanup, and failed mount/unmount paths that must never recursively delete font
contents. Mount syscalls are modeled on the host; this is not a device mount test.
Recovery only handles per-file overlays with an intact original parent filesystem.
Whole-directory overlays without a proven lower/mirror remain blocked. SIGKILL or
an unmount failure can leave a private recovery mount; it is never accepted merely
because its directory exists. Candidate diagnostics now distinguish missing views
from failed provenance. The original 317 audit APK remains byte-identical.

### R5: independently prove ROM aliases across partition views

HyperOS 3 feedback identified `stock-provenance-alias-target-unproven` for both
lower and current candidates of `MiSansLatinVF.ttf`. The log did not contain its
actual link target. A reproduced defect required every terminal to share the
starting partition device, rejecting valid system-to-product ROM links.

Resolution now proves each alias inode and each target against that target's
read-only ROM partition and exact filesystem location. Absolute links are mapped
to the selected original lower/mirror/recovered view; compilation opens that
proven terminal rather than following the old alias into a live replacement.
The original alias chain is revalidated immediately before SHA/face validation.
Loops, user-data targets, mismatched filesystem locations and changed terminal
paths/bytes remain rejected. Nested `/system/product/fonts` partition aliases
also retain their own partition proof. An unproven view is never accepted solely
because the proposed filename exists.

Scanner identities now have capture revision 2. Old identities are rebuilt once
through the existing stock-safe scan; protected or unprovable entries do not
become trusted merely because the cache is current. Focused tests combine actual
scanner path mapping, sealed geometry, two-partition/two-hop resolution, compiled
font output, cache migration, changed-alias and changed-byte rejection. Kernel
mount rows are modeled on the host; the user's exact symlink and native Android
mount behavior remain unverified until device evidence confirms them.
