<!-- prerelease -->

# 洛书 v2.1.2 预发行版

本版本基于 v2.1.1，优先修复 HyperOS 真机排版与系统字体覆盖问题。

## HyperOS 修复

- 为 HyperOS 的 MiSans、Roboto、GoogleSans 和数字字重物理槽使用固定紧凑行框，避免字体极端轮廓扩大控件高度，处理 QQ 回复信息栏错位、个人资料年龄标签裁切，以及酷安话题标题和热度叠字。
- 新增 HyperOS 3 `mi_ext` 字体分区映射。
- 覆盖 Mitype、MitypeClock、MiClock、AndroidClock、Clockopia 等直连物理槽，使系统时钟及部分系统管理页面的英文、数字跟随用户字体。
- 保持 Emoji、图标、符号和斜体槽不变。
- 调整旧 XML/动态映射清理顺序，避免删除刚生成的 Roboto、GoogleSans 等新槽位。

## 版本信息

- 模块版本：v2.1.2
- 模块 versionCode：20102
- 正式 App versionCode：2010201
- 发布渠道：GitHub 预发行版

## 测试重点

请在 HyperOS 3 重启后检查：QQ 回复栏、用户年龄标签、酷安话题页标题/热度、系统时钟、Root 管理器及系统管理类页面的英文与数字。
