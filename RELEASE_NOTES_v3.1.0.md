# 洛书 v3.1.0

洛书 3.1.0 是基于 v3.0.0 的一次定向性能更新，重点减少可变字体在 payload 构建阶段的重复实例化开销。字体覆盖策略、安全边界和静态字体处理路径保持不变。

## 可变字体构建性能
- 同一次 payload 构建中，相同源字体、face 与字重的可变字体静态实例现在会安全复用，不再因为不同字体槽位重复执行完整 `instantiateVariableFont`。
- 缓存仅针对可变字体实例；普通静态字体继续走原有直接读取路径，不改变既有行为。
- 缓存采用小型有界策略，避免实例数据无限增长。

## 缓存失效与安全
- 缓存身份同时包含路径、face、weight、device、inode、文件大小、`mtime_ns` 与 `ctime_ns`。
- 即使同一路径、同大小字体被快速覆盖，只要文件身份发生变化，也会重新实例化，避免复用旧字体数据。
- 不同字重独立缓存，避免 400/700 等实例相互污染。

## 回归测试
- 新增常驻实例缓存回归测试并接入 `scripts/check.sh`。
- 覆盖同源同字重重复读取只实例化一次、不同字重隔离、ctime 变化失效、源文件重写失效以及静态字体绕过缓存。
- 合入前已通过 Build Test Candidate、Font engine smoke tests、Beta feature checks 与 Pre-release Readiness；正式发布工作流仍会重新执行完整源码检查、Android Release Lint、单元测试、签名 APK 构建、证书校验、模块 ZIP 一致性与发布就绪门禁。

## 版本信息
- 模块版本：v3.1.0
- 模块 versionCode：30100
- App versionCode：3010001

## 发布验证
ColorOS 16、HyperOS 3、Magisk、APatch 的完整真机设备矩阵仍保持 pending；本次稳定版由维护者明确授权放行，不伪造未执行的真机 PASS。
