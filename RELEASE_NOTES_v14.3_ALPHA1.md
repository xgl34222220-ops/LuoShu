# 洛书 v14.3 Alpha1.3

## 多字重导入升级

- 字体模块 ZIP 中的静态字体优先读取内部 `OS/2.usWeightClass`，文件名仅作为失败兜底。
- 使用字体内部 Family 将命名混乱的多字重文件正确归为同一字体族。
- 支持完整九档角色：Thin、ExtraLight、Light、Regular、Medium、SemiBold、Bold、ExtraBold、Black。
- 使用字体内部斜体标记过滤 Italic/Oblique，不再只依赖文件名。
- 新增真实回归测试：两个文件名完全不含字重的字体，内部字重分别为 200 与 800，导入后必须生成 ExtraLight 与 ExtraBold。
- 保留 Alpha1.2 的预览真实源绑定、失败显式提示，以及 Alpha1.1 的字体模块 ZIP 安全导入修复。

本版本为开发测试版，不建议作为最终稳定版本长期使用。
