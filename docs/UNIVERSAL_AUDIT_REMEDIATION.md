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
