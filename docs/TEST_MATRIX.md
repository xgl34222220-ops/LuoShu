# 洛书发布测试矩阵

每个候选版本至少完成下列检查。未实际验证的组合不得标记为“已支持”。

## 自动化门禁

- Shell、JavaScript、Python 语法检查通过。
- Full/Lite ZIP 均可构建，ZIP 完整性与 SHA-256 校验通过。
- Full 包内 APK 与独立 APK 字节一致，Lite 包不包含 APK。
- 全局字体必须通过中文、英文、数字和标点覆盖率门禁。
- Latin-only 测试字体必须被门禁拒绝。
- 模块不得包含 `skip_mount` 或 `skip_mountify`。
- 元模块镜像只在字体事务成功后同步，不在开机脚本注入全量同步。

## 真机回归

| 系统 | Root/挂载 | 基础界面 | Google Play | 微信/XWeb | 回滚 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| ColorOS 16 / Android 16 | KernelSU 原生 | 待测 | 待测 | 待测 | 待测 | 待测 |
| ColorOS 16 / Android 16 | Hybrid Mount | 待测 | 待测 | 待测 | 待测 | 待测 |
| HyperOS 3 / Android 16 | KernelSU 原生 | 待测 | 待测 | 待测 | 待测 | 待测 |
| HyperOS 3 / Android 16 | Hybrid Mount | 待测 | 待测 | 待测 | 待测 | 待测 |

基础界面至少检查：开机、锁屏、状态栏、设置、桌面、通知中心及三个普通应用。
Google Play 至少检查：首页、搜索、应用详情和订阅付款弹窗。
字体类型至少覆盖：静态 TTF/OTF、可变字体、复合字体及缺少中文字形的字体。

## 发布规则

- Alpha/Beta 只发布为 GitHub prerelease。
- 正式版必须使用固定签名，并保留同一签名的历史 APK。
- 标签只创建一次；发布流程禁止移动或覆盖已有标签。
- 任一系统出现黑屏、SystemUI 重启、批量闪退或方框乱码，立即停止发布并回滚。
