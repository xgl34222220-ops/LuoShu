# 洛书 v4.0.1 正式版

v4.0.1 不再沿用 v4.0.0 的错误运行路径，集中修复真机“任务显示成功但重启后字体没有变化”、复合字体写错目录、HyperOS 补槽未真正进入下一启动负载、已成功挂载却长期显示待验证，以及原厂字体手动扫描不可用的问题。

## 真正的字体切换链路修复

- 修复 legacy/composite runtime 将 `.luoshu-payload-next` 写入 `.legacy-v14-runtime` 的根因；所有下一启动字体负载统一提交到真实模块目录 `/data/adb/modules/LuoShu/.luoshu-payload-next`。
- 复合字体改为独立 `.luoshu-mix-stage` 生成，成功后才提交为真实 next payload；本次启动正在使用的 `.luoshu-payload` 保持只读，不再因为切换导致 ColorOS App/SystemUI 闪退。
- 后台复合任务完成后自动提交 next payload，不再依赖 App 再次进入页面或轮询状态；App 被系统杀掉也不会留下“生成成功但没有可启动负载”的半完成状态。
- 下一次 `post-fs-data` / `post-mount` 才激活新负载；激活失败会恢复上一套 payload 和选择状态。
- 复合运行时产生的临时字体族不再覆盖用户真实选择，组合字体统一持久化为 `mix`。

## HyperOS 覆盖

- 修复 HyperOS staged 补槽后端定位错误，确保补槽逻辑实际加载并写入下一启动负载。
- 下一启动负载按设备真实存在的 system/system_ext/product/mi_ext/vendor/odm/oem/my_product/cust/hw_product 等普通 UI 字体槽补齐 MiSans、Mitype、MiClock、Roboto、Google Sans、Noto Sans 等安全 TTF/OTF 目标。
- 状态栏、锁屏、控制中心和系统 UI 使用的时钟/英文/数字槽与普通字体切换走同一份真实 next payload，避免 UI 显示已准备而物理槽仍是旧字体。
- 继续排除 Emoji、图标、衬线、语言专用字体和不安全 TTC 动态补槽，避免为了覆盖率引入 native 字体解析风险。

## ColorOS 与任务状态

- 切换时不再删除、重建或重命名当前启动正在挂载的字体源，避免 ColorOS 切换字体时 App 闪退或系统字体树短暂失效。
- 更新/切换保留当前可用 payload，下一启动负载完整准备成功前不会破坏当前字体。
- 后台任务继续校验 PID、task sidecar、boot ID 和 cmdline，跨启动死任务或 PID 复用会自动回收。
- `state=verified + mode=mount-confirmed` 现在会被 App 正确识别为“本次启动字体已确认”，不再错误显示“待本次启动验证”。

## 原厂字体扫描

- 恢复 App 的“重新扫描原厂字体”入口，并显示扫描中、成功槽位数量、主槽或具体失败原因。
- 修复字体库能力长期硬编码 `nativeAvailable=false` 导致原厂扫描被判定不可用的问题。
- 手动扫描认识洛书私有 `.luoshu-payload`。当自定义字体正在生效时，强制从洛书 self-mount lower 或 Magisk mirror 读取原厂字体；不会把当前洛书覆盖层反扫成“原厂”。
- 对不存在的 OEM 可选分区允许跳过；真实存在的字体分区如果找不到可信 lower/mirror，则直接拒绝扫描并给出原因。
- 新增私有 payload 原厂扫描安全回归，覆盖 overlay-risk 识别、lower 读取和无可信原厂视图时拒绝扫描。

## 升级说明

v4.0.0 已被真机验证存在上述运行路径问题。升级到 v4.0.1 后，请重新应用一次需要使用的单字体或复合字体，等待任务完成到 100%，然后执行一次完整重启。不要继续使用旧 v4.0.0 作为验证基线。
