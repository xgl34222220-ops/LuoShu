# 洛书 v3.3.1

这是针对 v3.3.0 的紧急热修，优先修复 KernelSU / SukiSU / APatch 路径的自挂载入口漏打包问题，并纠正 quick 切换仍执行多字重扫描的问题。

## 挂载修复
- 正式模块 ZIP 现在明确包含根目录 `post-mount.sh`。
- KSU / SukiSU / APatch 在 `post-fs-data.sh` 阶段会等待 post-mount 再执行洛书自挂载；v3.3.0 的显式发布清单遗漏了该脚本，可能导致自挂载根本没有启动。
- `scripts/check.sh` 现在强制要求 payload manifest 包含 `post-mount.sh`。
- `scripts/build.sh` 在最终 ZIP 生成后再次检查 `post-mount.sh`，缺失时直接阻止发布。

## 切换速度
- ColorOS / HyperOS 静态 ROM 适配的 `quick` 模式不再扫描、构建 Bold / Medium / Light 等多字重族。
- 前台切换继续保留事务快照、payload 校验、挂载同步和失败回滚，不重新引入 v3.2.3 / v3.2.4 的高风险挂载改动。

## 升级建议
- v3.3.0 用户建议直接更新到 v3.3.1 后完整重启一次，使 KSU / SukiSU / APatch 的 post-mount 自挂载入口重新参与启动流程。
