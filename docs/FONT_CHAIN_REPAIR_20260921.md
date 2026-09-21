# 字体处理链修复记录 · 2026-09-21

基线：`5373f85eb8bf2a5eb89c1f88119374573a911bce`（重构版 1.1.1）。
本批不改版本号，不创建正式 Release。

## 不变的架构

保留刷写时的唯一原厂扫描器 `font_inventory_scan.py` 和本机 inventory。
不新增品牌扫描器、不扩大保护字体替换、不修改挂载和原厂配置。
扫描结果必须沿筛选、生成、映射、加载逐级核验；文件生成成功不是页面验证成功。

## 本批代码修复

- `--weight` 在未显式提供 `wght` 时实际驱动该轴；显式轴仍优先。
- 没有 `wght` 的静态字体/可变字体保留实际源字重，不将 Regular 仅改标成 Bold。
- TTC 选面同时考虑 Unicode 探针覆盖与可变字重的真实可达范围；`.notdef` 不算命中。
- 实例 JSON 返回请求字重、源字重、实际字重、匹配状态及生成方式。
- 删除生成结果小于 4096 字节就判失败的规则，改为提交前重读 SFNT、基础表、Unicode 映射与实例状态校验。
- 参数中的 NaN/Infinity、重复轴及直接覆盖源文件被明确拒绝；异常不替换上一份输出。
- 旧组合实例化入口委托给共享引擎，保留旧路径的“不先重写度量”行为，避免两个实现继续分叉。

以上是生成层修复，不能据此宣称状态栏、X 或锁屏的所有反馈已在真机消失。

## 验证

新增 `scripts/font_instance_contract_test.py`，使用程序生成的小型测试字体，无商业或 ROM 字体附件。
28 项本机回归通过（Python 3.13.5 / FontTools 4.63.0）：
真实字形变化、多轴、上下限、静态真实字重、TTC 选面、CFF、小于 4 KiB 的合法字体、
非法参数、源文件不变、失败原子性、旧入口及其符号链接路径。
本机测试刻意使用 `preserve_metrics=True`；不等于 Android 度量/页面渲染验证。
新增 CI 对 Python 3.11/3.14 执行同一套测试；既有整包流水线仍需单独通过。

## 仍需验证与后续修复

- 调用者的缓存/已应用结果复用，以及后续命名器、XML 字重声明是否仍改标：旧输出不会被本补丁自动改写。
- 从实际 inventory 出发检查目标是否在分类、生成、映射中丢失，补充每槽结果和原因。
- 系统全局粗细设置的真实渲染验证、多用户设置和恢复。
- 状态栏/锁屏的真实失败日志、度量偏移/裁切、拨号及部分 App 的覆盖。
- Google 兼容冲突状态/灰按钮、中文来源，以及 Chrome 崩溃日志与对照复现。
- 原厂视图、挂载命名空间、重启后加载、各 ROM 真机回归、性能与容量复测。

参考：FontTools varLib.instancer 官方 API 与 OpenType OS/2 字重定义。
https://fonttools.readthedocs.io/en/latest/varLib/instancer.html
https://learn.microsoft.com/en-us/typography/opentype/spec/os2#usweightclass
