# 更新日志

## v13.3 Beta2

- 恢复 ARM64 原生扫描器 `luoshud`，作为旧目录诊断和故障回退工具，WebUI 默认仍走安全 Shell 扫描
- 字体列表接口新增扫描器状态，诊断报告增加原生扫描器、公开目录和桥接状态
- WebUI 解析可变字体 `fvar` 表，显示轴标签、范围、默认值和命名实例数量
- GMS 动态字体桥接增加 Google 搜索、Gemini、Chrome 和 WebView 相关挂载命名空间
- Google Sans Flex 仅在存在可变字体源时桥接，避免用静态正文字体冒充 Flex/Code 字体
- 更新公开目录、Hybrid Mount、重启保护和字体风险说明
- 重构 GitHub Actions 发布流程，版本号包含 Beta/RC 后缀，自动生成预发布 Release

## v13.3 Beta1

- 新增 `/sdcard/LuoShu/fonts/`、`emoji/` 和 `reports/` 公开目录
- 文字字体与 Emoji 独立管理
- 增加真实文件头检测，拦截伪装格式和损坏字体
- 默认保留系统 fallback、符号、其他语言字体与 `fonts.xml`
- 加入一次开机一次切换的重启保护，减少连续热切换死机
- 增加 Hybrid Mount Magic 标记和存储、inode、挂载诊断

## v13.2 Beta2

- 增加真实 cmap 字符抽样分析与字体风险评分
- 增加后台任务状态轮询、使用次数和排序
- 增加字体检测报告复制功能
