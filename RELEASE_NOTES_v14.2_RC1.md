# 洛书 v14.2 RC1

RC1 是 v14.2 正式版前的真机回归候选版本，基于 Alpha5 已验证的挂载架构，收口发布一致性、字体安全与原生管理 App。

- 支持 Android 16、ColorOS 16 与 HyperOS 3 的全局中文、英文和数字字体管理。
- 提供复合字体、可变字重、事务切换、失败回滚与恢复默认。
- 增加全局字形覆盖门禁，降低缺字方框、界面异常和应用崩溃风险。
- 同时发布 Full（内置固定签名 App）与 Lite（不内置 App）模块包。
- Release 直接提供模块 ZIP、独立 APK 与 SHA-256 校验文件，无需解压 Actions 外层包。
- Hybrid/Mountify 镜像仅在字体事务成功后同步，不在开机阶段执行高风险全量重建。

> RC1 仍为预发行测试版。刷入前请保留可用模块备份，并在一加 15 / ColorOS 16、Redmi K80 至尊版 / HyperOS 3 上完成两次完整重启及 GMS、Google Play、微信 XWeb 回归。
