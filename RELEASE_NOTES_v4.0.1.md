# 洛书 v4.0.1

这是 v4.0.0 的紧急启动安全修复版。

## 启动安全

- 修复更新/回退时 payload schema 已变化，却仍继承上一版本 `system/fonts` 与 OEM 分区字体负载的问题。
- 只有与当前引擎 schema 完全一致的已生成 payload 才允许跨版本保留。
- schema 不一致时，在安装阶段清除旧 `system/fonts`、OEM 分区负载、旧 payload manifest/schema/boot 状态和 device payload cache，避免 Root 管理器在 `post-fs-data` 校验前挂载不兼容字体。
- 针对 v4.0.0 Latin 覆盖实验产生的 v10 payload，升级到 v4.0.1 时会强制隔离旧负载，首次使用 ROM 原厂字体启动。

## 字体状态

- 安全隔离旧 payload 时仍保留 `active_font.conf` 中的用户字体选择，以及复合字体的中英数字配置。
- 首次安全启动后，在洛书中明确应用一次当前字体，即会使用 v4.0.1 当前引擎重新生成完整负载。
- 不再因为跨架构安全回退而把用户已选择字体直接改写成 `default`。

## 回归测试

- 新增 v10 → v9 跨 schema 迁移测试，覆盖 `system`、`system_ext`、`product`、`vendor`、`odm`、`oem`、`my_*`、`oplus_*`、`mi_ext`、`cust`、`hw_product` 等旧 payload 树。
- 同 schema 更新仍验证可安全保留已证明有效的 payload 与 device cache。

## 版本

- 模块：v4.0.1（40001）
- App：v4.0.1（4000101）
